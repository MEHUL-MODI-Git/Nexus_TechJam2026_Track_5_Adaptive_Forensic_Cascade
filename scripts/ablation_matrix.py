"""Phase 4.2 — the full ablation ladder, reported on the UNTOUCHED internal test.

The freeze compared rungs on dev, which is what selection is allowed to use. That
leaves an obvious question a reviewer should ask: was `mlp+wg` a lucky dev pick?
This refits the whole ladder with the freeze's seed and split (so its dev numbers
must reproduce), then scores EVERY rung on the internal test at its own
dev-fitted threshold.

No selection happens here. The architecture was frozen before the test existed as
a scored object; reporting the losing rungs alongside the winner is disclosure,
not a second bite at the selection.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.pipeline.transforms import FAMILY_OF
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

RUNGS = (("quality_only", False), ("static_average", False),
         ("logistic", False), ("mlp", False), ("mlp", True))
FAMS = sorted(set(FAMILY_OF.values()) - {"clean"})


def metrics(scores, labels, fams, thr):
    pred = scores >= thr
    fam_rec = {f: float(pred[(fams == f) & (labels == 1)].mean()) for f in FAMS
               if ((fams == f) & (labels == 1)).any()}
    worst = min(fam_rec, key=fam_rec.get)
    clean = fams == "clean"
    return {
        "worst_family": worst,
        "worst_family_fake_recall": round(fam_rec[worst], 4),
        "clean_fpr": round(float(pred[clean & (labels == 0)].mean()), 4),
        "clean_fake_recall": round(float(pred[clean & (labels == 1)].mean()), 4),
        "overall_accuracy": round(float((pred == (labels == 1)).mean()), 4),
        "family_fake_recall": {k: round(v, 4) for k, v in fam_rec.items()},
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fitting", type=Path, default=Path("data/feature_cache/fitting-v2"))
    ap.add_argument("--test", type=Path, default=Path("data/feature_cache/internal-test-v2"))
    ap.add_argument("--out", type=Path, default=Path("results/internal-test/ablation.json"))
    ap.add_argument("--seed", type=int, default=20260827)
    ap.add_argument("--bootstrap", type=int, default=200)
    args = ap.parse_args()

    code_rev = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                              text=True, check=False).stdout.strip() or "unknown"
    cfg_digest = hashlib.sha256(
        b"".join(Path(f"configs/{n}").read_bytes()
                 for n in ("transforms.yaml", "probes.yaml", "predict.yaml"))).hexdigest()
    man_sha = hashlib.sha256(Path("data/manifests/launch_fitting.json").read_bytes()).hexdigest()

    rows = load_cache_rows(args.fitting / "rows.jsonl")
    expert_ids = tuple(sorted({e for r in rows for e in (r.get("experts") or {})}))
    usable = validate_cache_rows(rows, expert_ids)["usable_rows"]
    train_rows = [r for r in usable if r["dataset_split"] == "train"]
    dev_rows = [r for r in usable if r["dataset_split"] == "dev"]
    spec = FeatureSpec(expert_ids=expert_ids)
    std = Standardizer.fit(rows_to_matrix(train_rows, spec, 0.5), spec)
    tb = build_batch(train_rows, spec, std, 0.5)
    db = build_batch(dev_rows, spec, std, 0.5)

    test_rows = load_cache_rows(args.test / "rows.jsonl")
    t_labels = np.array([r["label"] for r in test_rows])
    t_fams = np.array([r.get("family") or FAMILY_OF[r["condition_id"]] for r in test_rows])
    dev_labels = np.array([r["label"] for r in dev_rows])
    dev_fams = np.array([r.get("family") or "clean" for r in dev_rows])
    print(f"train={len(train_rows)} dev={len(dev_rows)} test={len(test_rows)}", file=sys.stderr)

    table = {}
    for name, wg in RUNGS:
        label = f"{name}+wg" if wg else name
        rec = train_rung(name, tb, db, spec.dim, len(expert_ids), 0.5, use_worst_group=wg,
                         seed=args.seed, bootstrap_replicates=8, fit_reliability=False,
                         quality_only_indices=spec.non_expert_indices())
        with torch.no_grad():
            tr = rec["_model"](tb.features, tb.expert_logits, tb.available).p_fake.numpy()
        grid = np.unique(np.quantile(np.clip(tr, 0, 1), np.linspace(0, 1, 257)))
        art = select_threshold(
            DevSet(source_ids=np.array([r["source_id"] for r in train_rows]),
                   condition_ids=np.array([r["condition_id"] for r in train_rows]),
                   families=np.array([r.get("family") or "clean" for r in train_rows]),
                   labels=np.array([r["label"] for r in train_rows], dtype=int),
                   scores=np.clip(tr, 0, 1)),
            candidates=grid, n_replicates=args.bootstrap, seed=args.seed,
            dev_manifest_sha256=man_sha, config_sha256=cfg_digest,
            pipeline_version=PIPELINE_VERSION,
            fitting_code_version=f"router-ablation@{code_rev[:12]}")
        thr = float(art.threshold)
        dv = np.asarray(rec["_dev_p_fake"], dtype=float)
        dev_worst, dev_fam = worst_family_recall(dv, dev_labels, dev_fams, thr,
                                                 require_all=False)

        # Score this rung on the untouched test at ITS OWN dev-fitted threshold.
        tbatch = build_batch(test_rows, spec, std, thr)
        with torch.no_grad():
            ts = rec["_model"](tbatch.features, tbatch.expert_logits,
                               tbatch.available).p_fake.numpy()
        m = metrics(ts, t_labels, t_fams, thr)
        table[label] = {"threshold": thr, "n_parameters": rec.get("n_parameters"),
                        "dev_worst_family_fake_recall": round(float(dev_worst), 4),
                        "dev_worst_family": dev_fam, "test": m}
        print(f"  {label:<16} thr={thr:.5f}  dev_worst={dev_worst:.4f}  "
              f"TEST worst={m['worst_family_fake_recall']:.4f} "
              f"cleanFPR={m['clean_fpr']:.4f} acc={m['overall_accuracy']:.4f}",
              file=sys.stderr)

    doc = {"schema_version": "ablation-matrix.v1",
           "note": "every rung refit with the freeze seed/split, then scored ONCE on the "
                   "untouched internal test at its own dev-fitted threshold; no selection here",
           "code_revision": code_rev, "rungs": table}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, indent=2) + "\n")
    print(f"\nwrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
