"""Train the router ladder on a feature cache (Phase 2).

    python scripts/train_router.py --cache data/feature_cache/v1 \
        --out results/router-v1/training.json

Trains every rung of the doc-04 ladder on the train split and compares them on
the SAME dev split, then states plainly whether the trained router beat
parameter-free averaging. If it did not, that is printed as the headline and
written into the artifact — a negative ablation is a result, not a failure to
hide (doc 08 kill criteria).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.pipeline.service import load_predict_config
from src.router.train import load_cache_rows, run_ladder, save_checkpoint


def main() -> int:
    parser = argparse.ArgumentParser(description="Train the router fusion ladder.")
    parser.add_argument("--cache", type=Path, required=True, help="feature cache directory")
    parser.add_argument("--manifest", type=Path, default=None,
                        help="corpus manifest supplying dataset_split per source")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--threshold", type=float, default=None)
    parser.add_argument("--seed", type=int, default=20260827)
    args = parser.parse_args()

    rows = load_cache_rows(args.cache / "rows.jsonl")
    cache_manifest = json.loads((args.cache / "manifest.json").read_text())

    # The feature cache stores dataset_split per row, but a cache built before
    # the split was assigned needs it joined from the corpus manifest.
    if args.manifest and not all(r.get("dataset_split") for r in rows):
        corpus = json.loads(args.manifest.read_text())["images"]
        split_by_source = {r["source_id"]: r["dataset_split"] for r in corpus}
        for row in rows:
            row["dataset_split"] = split_by_source.get(row["source_id"])
        rows = [r for r in rows if r.get("dataset_split")]

    threshold = args.threshold
    if threshold is None:
        threshold = float(load_predict_config()["threshold"])

    expert_ids = tuple(sorted({
        eid for row in rows for eid in (row.get("experts") or {})
    }))
    if not expert_ids:
        print("no expert blocks in the cache", file=sys.stderr)
        return 2

    print(f"rows={len(rows)} experts={expert_ids} threshold={threshold}", file=sys.stderr)
    provenance = load_predict_config().get("threshold_provenance", "unspecified")
    result = run_ladder(rows, threshold=threshold, expert_ids=expert_ids, seed=args.seed,
                        threshold_provenance=provenance)
    result["cache_unprotected"] = cache_manifest.get("UNPROTECTED_SMOKE_ONLY", False)

    out = args.out or (args.cache / "router_training.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    checkpoint = save_checkpoint(result, out.with_suffix(".pt"), threshold)
    serialisable = {k: v for k, v in result.items() if not k.startswith("_")}
    serialisable["checkpoint"] = str(checkpoint)
    out.write_text(json.dumps(serialisable, indent=2) + "\n")
    if result.get("rows_dropped_all_experts_unavailable"):
        print(f"excluded {result['rows_dropped_all_experts_unavailable']} row(s) where every "
              "expert failed: they would train as fabricated REAL scores", file=sys.stderr)

    print(f"\n{'rung':<18}{'params':>8}{'worst-family':>14}{'clean recall':>14}"
          f"{'clean FPR':>11}{'accuracy':>10}")
    for entry in result["results"]:
        name = entry["rung"] + ("+wg" if entry["use_worst_group_loss"] else "")
        flag = "" if entry.get("satisfies_clean_constraints", True) else "  (violates clean constraints)"
        print(f"{name:<18}{entry['n_parameters']:>8}"
              f"{entry['dev_worst_family_bootstrap_mean']:>14.4f}"
              f"{entry['dev_clean_fake_recall']:>14.4f}"
              f"{entry['dev_clean_fpr']:>11.4f}{entry['dev_overall_accuracy']:>10.4f}{flag}")
    delta = result["improvement_over_baseline"]
    if result.get("fusion_comparison_degenerate"):
        print("\n*** FUSION COMPARISON IS VACUOUS ***")
        print("Only one expert is available, so the fusion weight is 1.0 by")
        print("construction and every rung emits the primary score unchanged.")
        print("The identical rows above say nothing about the router.")
        print("With N=1, judge the router by SELECTIVE metrics (coverage vs")
        print("accuracy on the accepted set), or add a second expert.")
        print(f"\nwrote {out}", file=sys.stderr)
        return 0
    verdict = ("ROUTER BEATS the parameter-free baseline"
               if result["router_earns_its_complexity"]
               else "ROUTER DOES NOT BEAT the parameter-free baseline")
    print(f"\n{verdict}: best={result['best_rung']} "
          f"{result['best_worst_family_recall']:.4f} vs baseline "
          f"{result['baseline_worst_family_recall']:.4f} (delta {delta:+.4f})")
    if not result["router_earns_its_complexity"]:
        print("Report this as a negative ablation; do not bury it.")
    print(f"\nwrote {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
