"""Which stress conditions does the certificate actually need?

Audit mode costs 80 CF-384 forward passes because it runs all 20 official
conditions. If a subset carries most of the retention signal, the audit gets
proportionally cheaper for the same predictive power.

Free: every condition's score for every source is already in the internal-test
cache, so subsets are evaluated by re-counting, not by re-running the detector.

Greedy forward selection on the metric that matters -- AUROC of retention
predicting a WRONG clean verdict. Reported as a diagnostic; the shipped
certificate still uses all 20 unless this is confirmed on the fresh holdout.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.pipeline.transforms import CONDITION_IDS
from src.router.head import RouterHead
from src.router.train import build_batch, load_cache_rows, load_checkpoint


def auroc(scores, y):
    scores, y = np.asarray(scores, float), np.asarray(y, int)
    order = np.argsort(scores, kind="mergesort")
    ranks = np.empty(len(scores), float)
    ranks[order] = np.arange(1, len(scores) + 1)
    p, n = int((y == 1).sum()), int((y == 0).sum())
    return float((ranks[y == 1].sum() - p * (p + 1) / 2) / (p * n)) if p and n else float("nan")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cache", type=Path, default=Path("data/feature_cache/internal-test-v2"))
    ap.add_argument("--checkpoint", type=Path,
                    default=Path("results/router-fitting-v2/router_reliability.pt"))
    ap.add_argument("--out", type=Path,
                    default=Path("results/robustness/certificate-condition-budget.json"))
    args = ap.parse_args()

    head = RouterHead.from_checkpoint(args.checkpoint)
    loaded = load_checkpoint(args.checkpoint)
    thr = head.threshold

    rows = load_cache_rows(args.cache / "rows.jsonl")
    b = build_batch(rows, loaded.spec, loaded.standardizer, thr)
    with torch.no_grad():
        p = loaded.model(b.features, b.expert_logits, b.available).p_fake.numpy()
    pred = p >= thr
    lab = np.array([r["label"] for r in rows])
    src = np.array([r["source_id"] for r in rows])
    cond = np.array([r["condition_id"] for r in rows])

    clean_pred, clean_lab = {}, {}
    per_cond = defaultdict(dict)                # source -> condition -> retained?
    for i in range(len(rows)):
        if cond[i] == "clean":
            clean_pred[src[i]] = bool(pred[i])
            clean_lab[src[i]] = int(lab[i])
    for i in range(len(rows)):
        s = src[i]
        if s in clean_pred:
            per_cond[s][cond[i]] = bool(pred[i]) == clean_pred[s]

    ids = [s for s in per_cond if len(per_cond[s]) == len(CONDITION_IDS)]
    wrong = np.array([clean_pred[s] != (clean_lab[s] == 1) for s in ids]).astype(int)
    mat = {c: np.array([per_cond[s][c] for s in ids], dtype=float) for c in CONDITION_IDS}
    print(f"sources {len(ids)}   wrong clean verdicts {int(wrong.sum())}", file=sys.stderr)

    full = auroc(-sum(mat[c] for c in CONDITION_IDS), wrong)
    singles = sorted(((c, auroc(-mat[c], wrong)) for c in CONDITION_IDS),
                     key=lambda kv: -kv[1])
    print(f"\nall 20 conditions: AUROC {full:.4f}\n", file=sys.stderr)
    print("best single conditions:", file=sys.stderr)
    for c, a in singles[:6]:
        print(f"  {c:<16} {a:.4f}", file=sys.stderr)

    chosen, curve = [], []
    remaining = list(CONDITION_IDS)
    while remaining:
        best_c, best_a = None, -1.0
        for c in remaining:
            a = auroc(-sum(mat[x] for x in [*chosen, c]), wrong)
            if a > best_a:
                best_c, best_a = c, a
        chosen.append(best_c)
        remaining.remove(best_c)
        curve.append({"n_conditions": len(chosen), "added": best_c, "auroc": round(best_a, 4),
                      "forward_passes": len(chosen) * 4,
                      "fraction_of_full_auroc": round(best_a / full, 4)})
        if len(chosen) <= 8:
            print(f"  +{best_c:<16} n={len(chosen):2d}  AUROC {best_a:.4f}  "
                  f"({best_a/full*100:.1f}% of full)  {len(chosen)*4} passes", file=sys.stderr)

    reach = next((c for c in curve if c["auroc"] >= full - 0.005), None)
    doc = {
        "schema_version": "certificate-condition-budget.v1",
        "NOT_A_HEADLINE_RESULT": "internal-test diagnostic; the shipped certificate still "
                                 "uses all 20 conditions unless confirmed on the fresh holdout",
        "n_sources": len(ids), "auroc_all_20": round(full, 4),
        "single_condition_auroc": {c: round(a, 4) for c, a in singles},
        "greedy_forward_selection": curve,
        "cheapest_within_0.005_of_full": reach,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, indent=2) + "\n")
    if reach:
        print(f"\ncheapest subset within 0.005 of full: {reach['n_conditions']} conditions "
              f"({reach['forward_passes']} passes vs 80), AUROC {reach['auroc']:.4f}",
              file=sys.stderr)
    print(f"wrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
