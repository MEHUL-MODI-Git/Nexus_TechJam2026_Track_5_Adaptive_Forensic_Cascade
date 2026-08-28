"""Fit ONE operating threshold per rung, then compare the ladder at real operating points.

Why this exists: `run_ladder` computes every metric at whatever threshold it is handed, and the
first protected run was handed the unfitted placeholder 0.5. At that point every learned rung
breached the clean-FPR budget and was excluded from selection, so a parameter-free baseline "won"
with delta 0.0000 — an artifact of the operating point, not a finding about the router.

Protocol, chosen to avoid double-dipping:
  * rung WEIGHTS are fitted on the TRAIN split (unchanged, `train_rung`);
  * each rung's SINGLE threshold is fitted on the TRAIN split under the frozen objective
    (`calibration.select_threshold`: maximise bootstrap worst-FAMILY fake recall, clean excluded
    from the minimum, severities pooled, `source_id` as the resampling unit, subject to the clean
    FPR/BAcc constraints);
  * every reported number is then measured on DEV, which no threshold was fitted on.
One threshold per method, fixed across all 20 conditions. Never per-condition — at inference we do
not know which transform was applied, so a per-condition threshold is leakage.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.router.calibration import DevSet, select_threshold
from src.router.features import FeatureSpec, Standardizer, rows_to_matrix
from src.router.train import (
    LADDER_RUNGS,
    build_batch,
    load_cache_rows,
    train_rung,
    validate_cache_rows,
    worst_family_recall,
)


def _metrics(scores, rows, threshold):
    labels = np.array([r["label"] for r in rows])
    fams = np.array([r.get("family") or "clean" for r in rows])
    worst, worst_fam = worst_family_recall(scores, labels, fams, threshold, require_all=False)
    clean = fams == "clean"
    cf = clean & (labels == 0)
    ck = clean & (labels == 1)
    return {
        "worst_family_fake_recall": float(worst),
        "worst_family": worst_fam,
        "clean_fake_recall": float((scores[ck] >= threshold).mean()) if ck.any() else float("nan"),
        "clean_fpr": float((scores[cf] >= threshold).mean()) if cf.any() else float("nan"),
        "overall_accuracy": float(((scores >= threshold) == (labels == 1)).mean()),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cache", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=Path("results/router-fitting-v2/threshold-fitted.json"))
    ap.add_argument("--seed", type=int, default=20260827)
    ap.add_argument("--bootstrap", type=int, default=200)
    ap.add_argument("--candidates", type=int, default=257,
                    help="quantile-spaced threshold candidates; the default grid of every "
                         "unique score is computationally intractable at this scale")
    args = ap.parse_args()

    rows = load_cache_rows(args.cache / "rows.jsonl")
    expert_ids = tuple(sorted({e for r in rows for e in (r.get("experts") or {})}))
    report = validate_cache_rows(rows, expert_ids)
    usable = report["usable_rows"]
    train_rows = [r for r in usable if r["dataset_split"] == "train"]
    dev_rows = [r for r in usable if r["dataset_split"] == "dev"]
    print(f"rows={len(usable)} train={len(train_rows)} dev={len(dev_rows)} experts={expert_ids}",
          file=sys.stderr)

    spec = FeatureSpec(expert_ids=expert_ids)
    std = Standardizer.fit(rows_to_matrix(train_rows, spec, 0.5), spec)
    train_batch = build_batch(train_rows, spec, std, 0.5)
    dev_batch = build_batch(dev_rows, spec, std, 0.5)

    results = []
    for name, wg in LADDER_RUNGS:
        rec = train_rung(name, train_batch, dev_batch, spec.dim, len(expert_ids), 0.5,
                         use_worst_group=wg, seed=args.seed, bootstrap_replicates=8,
                         fit_reliability=False,
                         quality_only_indices=spec.non_expert_indices())
        model = rec["_model"]
        import torch
        with torch.no_grad():
            tr = model(train_batch.features, train_batch.expert_logits,
                       train_batch.available).p_fake.numpy()
            dv = np.asarray(rec["_dev_p_fake"], dtype=float)

        # ONE threshold, fitted on TRAIN only, under the frozen objective.
        train_dev = DevSet(
            source_ids=np.array([r["source_id"] for r in train_rows]),
            condition_ids=np.array([r["condition_id"] for r in train_rows]),
            families=np.array([r.get("family") or "clean" for r in train_rows]),
            labels=np.array([r["label"] for r in train_rows], dtype=int),
            scores=np.clip(tr, 0.0, 1.0),
        )
        # Candidate grid: select_threshold defaults to EVERY unique observed score, which
        # on 180k train rows is ~180k candidates x 400 bootstrap replicates -- hours per rung.
        # Quantile spacing over the observed scores keeps the grid dense exactly where the
        # decision boundary can actually move and is sufficient for a single scalar.
        grid = np.unique(np.quantile(np.clip(tr, 0.0, 1.0),
                                     np.linspace(0.0, 1.0, args.candidates)))
        art = select_threshold(train_dev, candidates=grid,
                               n_replicates=args.bootstrap, seed=args.seed)
        label = f"{name}+wg" if wg else name
        entry = {
            "rung": label,
            "n_parameters": rec["n_parameters"],
            "threshold": float(art.threshold),
            "threshold_feasible": bool(art.feasible),
            "at_0.5": _metrics(dv, dev_rows, 0.5),
            "at_fitted": _metrics(dv, dev_rows, float(art.threshold)),
        }
        results.append(entry)
        m = entry["at_fitted"]
        print(f"{label:<18}{rec['n_parameters']:>6}  thr={art.threshold:<8.5f} "
              f"feasible={art.feasible!s:<5} worst={m['worst_family_fake_recall']:.4f} "
              f"({m['worst_family']})  cleanFPR={m['clean_fpr']:.4f} "
              f"cleanRec={m['clean_fake_recall']:.4f}  acc={m['overall_accuracy']:.4f}",
              file=sys.stderr)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({
        "schema_version": "router-threshold-fitted.v1",
        "NOT_A_HEADLINE_RESULT": "dev-split numbers, single expert; the untouched internal test "
                                 "is the reportable surface",
        "cache": str(args.cache),
        "protocol": "weights fitted on train; ONE threshold per rung fitted on train under the "
                    "frozen objective; all reported metrics measured on dev",
        "n_train_rows": len(train_rows), "n_dev_rows": len(dev_rows),
        "expert_ids": list(expert_ids), "feature_dim": spec.dim,
        "results": results,
    }, indent=2) + "\n")
    print(f"\nwrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
