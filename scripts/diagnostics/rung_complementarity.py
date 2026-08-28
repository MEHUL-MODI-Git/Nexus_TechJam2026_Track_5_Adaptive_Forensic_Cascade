"""Is there anything to gain by gating between our own two rungs? Dev only.

The shipped rung is `mlp+wg` (worst-group loss). Plain `mlp` has HIGHER overall
accuracy and LOWER clean FPR on the untouched test, so the obvious question is
whether a small gate could take the better of the two per image.

Before building any gate, this asks the cheap question that killed the PGC
rescue: what is the ORACLE ceiling? If a perfect oracle -- one that always picks
the correct rung, which no learnable gate can beat -- adds little over the better
single rung, the gate is dead and no implementation effort is warranted.

Dev split only. Nothing here is fitted on the internal test.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.pipeline.version import PIPELINE_VERSION
from src.router.calibration import DevSet, select_threshold
from src.router.features import FeatureSpec, Standardizer, rows_to_matrix
from src.router.train import (
    build_batch,
    load_cache_rows,
    train_rung,
    validate_cache_rows,
    worst_family_recall,
)

FAMS = ("blur", "color", "crop", "jpeg", "noise", "resize")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cache", type=Path, default=Path("data/feature_cache/fitting-v2"))
    ap.add_argument("--out", type=Path,
                    default=Path("results/probe-ablation/rung-complementarity.json"))
    ap.add_argument("--seed", type=int, default=20260827)
    args = ap.parse_args()

    rows = load_cache_rows(args.cache / "rows.jsonl")
    eids = tuple(sorted({e for r in rows for e in (r.get("experts") or {})}))
    usable = validate_cache_rows(rows, eids)["usable_rows"]
    tr = [r for r in usable if r["dataset_split"] == "train"]
    dv = [r for r in usable if r["dataset_split"] == "dev"]
    spec = FeatureSpec(expert_ids=eids)
    std = Standardizer.fit(rows_to_matrix(tr, spec, 0.5), spec)
    tb, db = build_batch(tr, spec, std, 0.5), build_batch(dv, spec, std, 0.5)
    labels = np.array([r["label"] for r in dv])
    fams = np.array([r.get("family") or "clean" for r in dv])
    print(f"train={len(tr)} dev={len(dv)}", file=sys.stderr)

    arms = {}
    for name, wg in (("mlp", False), ("mlp+wg", True)):
        rec = train_rung("mlp", tb, db, spec.dim, len(eids), 0.5, use_worst_group=wg,
                         seed=args.seed, bootstrap_replicates=8, fit_reliability=False,
                         quality_only_indices=spec.non_expert_indices())
        with torch.no_grad():
            trp = rec["_model"](tb.features, tb.expert_logits, tb.available).p_fake.numpy()
        grid = np.unique(np.quantile(np.clip(trp, 0, 1), np.linspace(0, 1, 257)))
        art = select_threshold(
            DevSet(source_ids=np.array([r["source_id"] for r in tr]),
                   condition_ids=np.array([r["condition_id"] for r in tr]),
                   families=np.array([r.get("family") or "clean" for r in tr]),
                   labels=np.array([r["label"] for r in tr], dtype=int),
                   scores=np.clip(trp, 0, 1)),
            candidates=grid, n_replicates=200, seed=args.seed,
            dev_manifest_sha256="rung-complementarity", config_sha256="rung-complementarity",
            pipeline_version=PIPELINE_VERSION, fitting_code_version="rung-complementarity")
        p = np.asarray(rec["_dev_p_fake"], float)
        thr = float(art.threshold)
        arms[name] = {"p": p, "thr": thr, "pred": (p >= thr).astype(int)}
        w, fam = worst_family_recall(p, labels, fams, thr, require_all=False)
        print(f"  {name:<8} thr={thr:.5f} worst={w:.4f} ({fam}) "
              f"acc={( (p>=thr)==(labels==1) ).mean():.4f}", file=sys.stderr)

    a, b = arms["mlp"], arms["mlp+wg"]
    ok_a, ok_b = a["pred"] == labels, b["pred"] == labels
    both_wrong = (~ok_a) & (~ok_b)

    # The oracle: always take whichever rung is right. No gate can beat this.
    oracle_pred = np.where(ok_b, b["pred"], a["pred"])
    def worst_of(pred):
        """Worst-family fake recall for a hard 0/1 prediction vector."""
        return min(float((pred[(fams == f) & (labels == 1)] == 1).mean())
                   for f in FAMS if ((fams == f) & (labels == 1)).any())

    doc = {
        "schema_version": "rung-complementarity.v1",
        "NOT_A_HEADLINE_RESULT": "dev split only; a pre-check, not a result",
        "n_dev_rows": len(labels),
        "accuracy": {"mlp": float(ok_a.mean()), "mlp+wg": float(ok_b.mean()),
                     "oracle": float((oracle_pred == labels).mean())},
        "worst_family_fake_recall": {"mlp": worst_of(a["pred"]),
                                     "mlp+wg": worst_of(b["pred"]),
                                     "oracle": worst_of(oracle_pred)},
        "P(mlp correct | wg wrong)": float(ok_a[~ok_b].mean()) if (~ok_b).any() else float("nan"),
        "P(wg correct | mlp wrong)": float(ok_b[~ok_a].mean()) if (~ok_a).any() else float("nan"),
        "joint_failure_rate": float(both_wrong.mean()),
        "disagreement_rate": float((a["pred"] != b["pred"]).mean()),
    }
    best_single = max(doc["worst_family_fake_recall"]["mlp"],
                      doc["worst_family_fake_recall"]["mlp+wg"])
    upside = doc["worst_family_fake_recall"]["oracle"] - best_single
    doc["oracle_upside_worst_family"] = upside
    doc["verdict"] = ("BUILD THE GATE" if upside >= 0.02 else
                      "KILL — a perfect oracle adds less than 2 points, so no learnable "
                      "gate can be worth its complexity")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, indent=2) + "\n")
    print(f"\nP(mlp correct | wg wrong) = {doc['P(mlp correct | wg wrong)']:.4f}")
    print(f"P(wg correct | mlp wrong) = {doc['P(wg correct | mlp wrong)']:.4f}")
    print(f"joint failure rate        = {doc['joint_failure_rate']:.4f}")
    print(f"disagreement rate         = {doc['disagreement_rate']:.4f}")
    print(f"\nworst-family: mlp {doc['worst_family_fake_recall']['mlp']:.4f}  "
          f"mlp+wg {doc['worst_family_fake_recall']['mlp+wg']:.4f}  "
          f"ORACLE {doc['worst_family_fake_recall']['oracle']:.4f}")
    print(f"oracle upside over best single rung: {upside:+.4f}")
    print(f"\nVERDICT: {doc['verdict']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
