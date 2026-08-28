"""Report the FROZEN abstention policy on the untouched internal test.

Nothing is selected here. The reliability head was fitted on the fitting-cache
TRAIN split, and the abstention threshold was chosen on the fitting-cache DEV
split by a pre-registered rule (`scripts/fit_reliability.py`), both before this
script was ever pointed at the internal test. This only measures what that
already-frozen policy does on unseen sources.

The question abstention has to answer: when the system declines to decide, is it
declining on the images it would have got WRONG? If accuracy on the kept images
does not rise, the abstention is theatre and we report it as a negative result.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.eval.protocol import load_frozen_threshold
from src.pipeline.transforms import FAMILY_OF
from src.router.head import RouterHead
from src.router.train import build_batch, load_cache_rows, load_checkpoint

FAMS = sorted(set(FAMILY_OF.values()) - {"clean"})


def worst_family(pred, labels, fams, mask):
    vals = []
    for f in FAMS:
        m = mask & (fams == f) & (labels == 1)
        if m.any():
            vals.append(float(pred[m].mean()))
    return min(vals) if vals else float("nan")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cache", type=Path, default=Path("data/feature_cache/internal-test-v2"))
    ap.add_argument("--checkpoint", type=Path,
                    default=Path("results/router-fitting-v2/router_reliability.pt"))
    ap.add_argument("--threshold-artifact", type=Path,
                    default=Path("results/router-fitting-v2/threshold-artifact.v1.json"))
    ap.add_argument("--out", type=Path, default=Path("results/internal-test/abstention.json"))
    args = ap.parse_args()

    manifest = json.loads((args.cache / "manifest.json").read_text())
    if manifest.get("role") != "evaluation":
        print(f"REFUSING: cache role {manifest.get('role')!r} != 'evaluation'", file=sys.stderr)
        return 2

    frozen = load_frozen_threshold(args.threshold_artifact)
    thr = float(frozen.value)
    head = RouterHead.from_checkpoint(args.checkpoint, threshold=thr)
    if not head.abstention_adopted:
        print("REFUSING: this checkpoint carries no adopted abstention policy", file=sys.stderr)
        return 2
    rel_thr = head.abstain_threshold
    loaded = load_checkpoint(args.checkpoint)

    rows = load_cache_rows(args.cache / "rows.jsonl")
    labels = np.array([r["label"] for r in rows])
    fams = np.array([r.get("family") or FAMILY_OF.get(r["condition_id"], "clean") for r in rows])
    batch = build_batch(rows, loaded.spec, loaded.standardizer, thr)
    with torch.no_grad():
        out = loaded.model(batch.features, batch.expert_logits, batch.available)
    p = out.p_fake.numpy()
    rel = out.reliability.numpy()

    pred = p >= thr
    correct = pred == (labels == 1)
    keep = rel >= rel_thr
    cov = float(keep.mean())

    full = {
        "coverage": 1.0,
        "accuracy": float(correct.mean()),
        "worst_family_fake_recall": worst_family(pred, labels, fams, np.ones_like(keep)),
        "n": int(keep.size),
    }
    kept = {
        "coverage": round(cov, 4),
        "accuracy": float(correct[keep].mean()),
        "worst_family_fake_recall": worst_family(pred, labels, fams, keep),
        "n": int(keep.sum()),
    }
    deferred_acc = float(correct[~keep].mean()) if (~keep).any() else float("nan")

    print(f"frozen decision threshold  {thr:.10f}")
    print(f"frozen abstention threshold {rel_thr:.6f}  "
          f"(dev coverage {head.payload['abstention']['dev_coverage']:.2f})\n")
    print(f"{'':<26}{'coverage':>10}{'accuracy':>10}{'worst-fam':>11}")
    print(f"{'all images':<26}{full['coverage']:>10.3f}{full['accuracy']:>10.4f}"
          f"{full['worst_family_fake_recall']:>11.4f}")
    print(f"{'kept (system decides)':<26}{kept['coverage']:>10.3f}{kept['accuracy']:>10.4f}"
          f"{kept['worst_family_fake_recall']:>11.4f}")
    print(f"\naccuracy on the DEFERRED images: {deferred_acc:.4f}")
    print("  (the policy works only if this is markedly WORSE than the kept set --")
    print("   it means the system is declining on the images it would have failed)")

    doc = {
        "schema_version": "abstention-results.v1",
        "one_shot": "frozen policy measured on the untouched internal test; nothing selected here",
        "policy_selected_on": "dev split of the fitting cache, before this cache was consulted",
        "decision_threshold": thr,
        "abstention_threshold": rel_thr,
        "dev_policy": head.payload["abstention"],
        "all_images": full,
        "kept": kept,
        "deferred": {"n": int((~keep).sum()), "accuracy": deferred_acc},
        "accuracy_gain_points": round(kept["accuracy"] - full["accuracy"], 4),
        "worst_family_gain_points": round(
            kept["worst_family_fake_recall"] - full["worst_family_fake_recall"], 4),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, indent=2) + "\n")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
