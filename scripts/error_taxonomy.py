"""Build the Error Analysis Note's evidence from the PROTECTED internal test.

The existing note was drafted on the 8,000-row smoke grid at an unfitted 0.5
threshold, on a set whose real half was COCO and fake half SID-Set -- a
comparison we have since disowned in README section 8. This regenerates every
claim from the untouched 3,000-source internal test at the frozen threshold, and
names actual files so each representative case can be inspected.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.pipeline.transforms import FAMILY_OF
from src.router.head import RouterHead
from src.router.train import build_batch, load_cache_rows, load_checkpoint


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cache", type=Path, default=Path("data/feature_cache/internal-test-v2"))
    ap.add_argument("--checkpoint", type=Path,
                    default=Path("results/router-fitting-v2/router_reliability.pt"))
    ap.add_argument("--out", type=Path, default=Path("results/robustness/error-taxonomy.json"))
    ap.add_argument("--top", type=int, default=12)
    args = ap.parse_args()

    head = RouterHead.from_checkpoint(args.checkpoint)
    loaded = load_checkpoint(args.checkpoint)
    thr, rel_thr = head.threshold, head.abstain_threshold

    rows = load_cache_rows(args.cache / "rows.jsonl")
    labels = np.array([r["label"] for r in rows])
    conds = np.array([r["condition_id"] for r in rows])
    fams = np.array([r.get("family") or FAMILY_OF[r["condition_id"]] for r in rows])
    batch = build_batch(rows, loaded.spec, loaded.standardizer, thr)
    with torch.no_grad():
        out = loaded.model(batch.features, batch.expert_logits, batch.available)
    p = out.p_fake.numpy()
    rel = out.reliability.numpy()
    primary = np.array([float(r["experts"][loaded.spec.expert_ids[0]].get("p_fake", 0.5))
                        for r in rows])
    pred = p >= thr

    fn = np.flatnonzero((labels == 1) & ~pred)      # missed AI images
    fp = np.flatnonzero((labels == 0) & pred)       # real called AI

    def cases(idx, worst_by, n):
        order = idx[np.argsort(worst_by[idx])][:n]
        return [{
            "relative_path": rows[i]["relative_path"],
            "condition_id": rows[i]["condition_id"],
            "family": str(fams[i]),
            "label": int(labels[i]),
            "router_p_fake": round(float(p[i]), 6),
            "primary_p_fake": round(float(primary[i]), 6),
            "reliability": round(float(rel[i]), 4),
            "would_abstain": bool(rel[i] < rel_thr) if rel_thr else None,
        } for i in order]

    # Worst FNs = lowest routed score among true fakes; worst FPs = highest among reals.
    worst_fn = cases(fn, p, args.top)
    worst_fp = cases(fp, -p, args.top)

    per_cond = {}
    for c in sorted(set(conds)):
        m = conds == c
        f_m, r_m = m & (labels == 1), m & (labels == 0)
        per_cond[c] = {
            "fake_recall": round(float(pred[f_m].mean()), 4),
            "fpr": round(float(pred[r_m].mean()), 4),
            "abstain_rate": round(float((rel[m] < rel_thr).mean()), 4) if rel_thr else None,
        }

    doc = {
        "schema_version": "error-taxonomy.v1",
        "source": "untouched internal test, frozen threshold — supersedes the smoke-grid draft",
        "decision_threshold": thr,
        "abstention_threshold": rel_thr,
        "n_rows": len(rows),
        "counts": {
            "false_negatives": int(fn.size), "false_positives": int(fp.size),
            "fn_rate_among_fakes": round(float(fn.size / (labels == 1).sum()), 4),
            "fp_rate_among_reals": round(float(fp.size / (labels == 0).sum()), 4),
        },
        "false_negatives_by_condition": dict(Counter(conds[fn]).most_common()),
        "false_positives_by_condition": dict(Counter(conds[fp]).most_common()),
        "abstention_catches": {
            "share_of_FN_that_would_abstain":
                round(float((rel[fn] < rel_thr).mean()), 4) if rel_thr else None,
            "share_of_FP_that_would_abstain":
                round(float((rel[fp] < rel_thr).mean()), 4) if rel_thr else None,
            "share_of_CORRECT_that_would_abstain":
                round(float((rel[pred == (labels == 1)] < rel_thr).mean()), 4) if rel_thr else None,
        },
        "worst_false_negatives": worst_fn,
        "worst_false_positives": worst_fp,
        "per_condition": per_cond,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, indent=2) + "\n")

    print(f"FN {fn.size} ({doc['counts']['fn_rate_among_fakes']:.1%} of fakes) | "
          f"FP {fp.size} ({doc['counts']['fp_rate_among_reals']:.1%} of reals)")
    print("\nFalse negatives concentrate in:",
          list(doc["false_negatives_by_condition"].items())[:5])
    print("False positives concentrate in:",
          list(doc["false_positives_by_condition"].items())[:5])
    a = doc["abstention_catches"]
    print(f"\nabstention would catch {a['share_of_FN_that_would_abstain']:.1%} of FNs, "
          f"{a['share_of_FP_that_would_abstain']:.1%} of FPs, "
          f"but also defers {a['share_of_CORRECT_that_would_abstain']:.1%} of CORRECT calls")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
