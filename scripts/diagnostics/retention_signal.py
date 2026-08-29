"""Is verdict retention a better confidence signal than the reliability head?

Produces the artifact behind README section 7's audit-mode claims. Every number
this project publishes must have a committed artifact; these were computed
ad-hoc first, which is exactly the drift the rule exists to prevent.

Retention = of the 20 official conditions, how many preserve the CLEAN verdict.
Nothing is fitted here: the router, its threshold and the abstention threshold
are all loaded frozen.
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

from src.app.certificate import GRADE_BANDS
from src.eval.metrics import auroc as canonical_auroc
from src.router.head import RouterHead
from src.router.train import build_batch, load_cache_rows, load_checkpoint


def auroc(scores, y):
    """Tie-aware AUROC via the canonical implementation (R4, Codex review).

    This file previously assigned unique sequential ranks. Retention is an
    integer 0-20, so ties are pervasive and the result became input-order
    dependent -- 0.8615 to 0.8775 across 20 shuffles.

    `scores` are "higher = more likely WRONG" and the canonical helper validates
    scores in [0,1], so we pass the equivalent orientation instead: score
    CORRECTNESS with the min-max normalised signal. AUROC(-s predicting wrong)
    rank statistic; call sites already orient higher = more likely wrong.
    """
    s = np.asarray(scores, float)
    y = np.asarray(y, int)
    lo, hi = float(np.min(s)), float(np.max(s))
    s01 = np.full_like(s, 0.5) if hi <= lo else (s - lo) / (hi - lo)
    return float(canonical_auroc(y, s01))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cache", type=Path, default=Path("data/feature_cache/internal-test-v2"))
    ap.add_argument("--checkpoint", type=Path,
                    default=Path("results/router-fitting-v2/router_reliability.pt"))
    ap.add_argument("--out", type=Path,
                    default=Path("results/robustness/retention-signal.json"))
    args = ap.parse_args()

    head = RouterHead.from_checkpoint(args.checkpoint)
    loaded = load_checkpoint(args.checkpoint)
    thr, rel_thr = head.threshold, head.abstain_threshold

    rows = load_cache_rows(args.cache / "rows.jsonl")
    b = build_batch(rows, loaded.spec, loaded.standardizer, thr)
    with torch.no_grad():
        o = loaded.model(b.features, b.expert_logits, b.available)
    p, rel = o.p_fake.numpy(), o.reliability.numpy()
    pred = p >= thr
    lab = np.array([r["label"] for r in rows])
    src = np.array([r["source_id"] for r in rows])
    cond = np.array([r["condition_id"] for r in rows])

    clean_pred, clean_rel, clean_lab = {}, {}, {}
    kept = defaultdict(list)
    for i in range(len(rows)):
        if cond[i] == "clean":
            clean_pred[src[i]] = bool(pred[i])
            clean_rel[src[i]] = float(rel[i])
            clean_lab[src[i]] = int(lab[i])
    for i in range(len(rows)):
        kept[src[i]].append(bool(pred[i]) == clean_pred.get(src[i], bool(pred[i])))

    ids = np.array(list(kept))
    ret = np.array([sum(kept[k]) for k in ids])
    r = np.array([clean_rel[k] for k in ids])
    ok = np.array([clean_pred[k] == (clean_lab[k] == 1) for k in ids])
    wrong = (~ok).astype(int)
    high = r >= rel_thr                       # would NOT abstain

    bands = {}
    for minimum, grade, _ in GRADE_BANDS:
        m = (ret >= minimum) if minimum == 20 else (ret >= minimum) & (ret < _next_min(minimum))
        if m.any():
            bands[grade] = {"n": int(m.sum()), "share": round(float(m.mean()), 4),
                            "clean_verdict_accuracy": round(float(ok[m].mean()), 4)}

    flags = {}
    for t in (20, 19, 18, 17, 16):
        f = high & (ret < t)
        if not f.any():
            continue
        flags[f"retention_lt_{t}"] = {
            "catches_share_of_blindspot_errors": round(float((f & ~ok).sum() /
                                                             max(1, (high & ~ok).sum())), 4),
            "precision": round(float((~ok[f]).mean()), 4),
            "defers_share_of_high_reliability": round(float(f.sum() / high.sum()), 4),
        }

    doc = {
        "schema_version": "retention-signal.v1",
        "NOT_A_HEADLINE_RESULT": "measured on the internal test, whose per-family results "
                                 "already informed this analysis; needs the fresh holdout "
                                 "to become a headline claim",
        "n_sources": len(ids),
        "decision_threshold": thr, "abstention_threshold": rel_thr,
        "auroc_predicting_wrong_clean_verdict": {
            "reliability_head": round(auroc(-r, wrong), 4),
            "verdict_retention": round(auroc(-ret.astype(float), wrong), 4),
            "combined": round(auroc(-(r + ret / 20.0), wrong), 4),
        },
        "blind_spot": {
            "definition": "high reliability (would not abstain) but the clean verdict is wrong",
            "n": int((high & ~ok).sum()),
            "mean_retention": round(float(ret[high & ~ok].mean()), 4),
            "mean_retention_high_reliability_and_correct": round(float(ret[high & ok].mean()), 4),
        },
        "grade_bands_measured": bands,
        "flagging_rules_among_high_reliability": flags,
        "retention_quantiles": {f"p{q}": int(np.percentile(ret, q)) for q in (1, 5, 10, 25, 50)},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, indent=2) + "\n")

    a = doc["auroc_predicting_wrong_clean_verdict"]
    print(f"sources {len(ids)}   AUROC predicting a WRONG verdict:")
    print(f"  reliability head   {a['reliability_head']:.4f}")
    print(f"  verdict retention  {a['verdict_retention']:.4f}")
    print(f"  combined           {a['combined']:.4f}")
    bs = doc["blind_spot"]
    print(f"\nblind spot: {bs['n']} confident-but-wrong sources, "
          f"mean retention {bs['mean_retention']:.2f} vs "
          f"{bs['mean_retention_high_reliability_and_correct']:.2f} for confident-and-correct")
    print(f"\ngrade bands: { {k: v['clean_verdict_accuracy'] for k, v in bands.items()} }")
    print(f"wrote {args.out}")
    return 0


def _next_min(minimum: int) -> int:
    mins = [b[0] for b in GRADE_BANDS]
    i = mins.index(minimum)
    return mins[i - 1] if i > 0 else 21


if __name__ == "__main__":
    raise SystemExit(main())
