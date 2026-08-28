"""Does the PGC rescue earn its slot? Fit on dev, report once on the test.

The rescue only ever sees rows the cascade DEFERRED (reliability below the
frozen abstention threshold). On those rows we ask the one question that matters
for a second opinion:

    P(candidate correct | common path wrong)

A rescue that is merely accurate is worthless -- if it is right exactly where the
common path is already right, it corrects nothing and only adds latency. So the
gate is correction MINUS harm, where harm is the rows the common path had right
and the rescue breaks.

PGC's own decision threshold is fitted on the DEV deferred rows and then frozen;
the internal-test rows are scored once with it and nothing is tuned on them.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

FAMS = ("blur", "color", "crop", "jpeg", "noise", "resize")


def load(path: Path) -> list[dict]:
    rows = [json.loads(line) for line in path.open()]
    return [r for r in rows if r.get("ok", True) and "pgc_p_fake" in r]


def arrays(rows):
    return (np.array([r["pgc_p_fake"] for r in rows]),
            np.array([r["router_p_fake"] for r in rows]),
            np.array([r["label"] for r in rows]),
            np.array([r["family"] for r in rows]),
            np.array([r["condition_id"] for r in rows]))


def fit_pgc_threshold(pgc, router_correct, labels, decision_thr):
    """Choose PGC's cut to MAXIMISE correction-minus-harm on dev deferred rows.

    Optimising the rescue's own objective directly is the honest target: a
    threshold picked for standalone accuracy would ignore that the rescue is
    only allowed to act where the common path is already struggling.
    """
    best, best_net = 0.5, -1e9
    for t in np.unique(np.round(pgc, 4)):
        rescued = (pgc >= t).astype(int)
        rescue_correct = rescued == labels
        corr = int((rescue_correct & ~router_correct).sum())
        harm = int((~rescue_correct & router_correct).sum())
        if corr - harm > best_net:
            best, best_net = float(t), corr - harm
    return best, best_net


def report(tag, pgc, router_p, labels, fams, decision_thr, pgc_thr):
    router_pred = (router_p >= decision_thr).astype(int)
    router_correct = router_pred == labels
    rescue_pred = (pgc >= pgc_thr).astype(int)
    rescue_correct = rescue_pred == labels

    n = labels.size
    corr = int((rescue_correct & ~router_correct).sum())
    harm = int((~rescue_correct & router_correct).sum())
    p_cand_given_wrong = (float(rescue_correct[~router_correct].mean())
                          if (~router_correct).any() else float("nan"))
    out = {
        "rows_deferred_scored": int(n),
        "router_accuracy_on_deferred": float(router_correct.mean()),
        "pgc_accuracy_on_deferred": float(rescue_correct.mean()),
        "P(pgc correct | router wrong)": p_cand_given_wrong,
        "corrections": corr, "harms": harm, "net": corr - harm,
        "net_per_1000_rescued": round(1000.0 * (corr - harm) / n, 2),
        "accuracy_if_rescue_applied": float(rescue_correct.mean()),
    }
    print(f"\n=== {tag} ===")
    print(f"  rows scored (deferred only)      {n}")
    print(f"  router accuracy on these rows    {out['router_accuracy_on_deferred']:.4f}")
    print(f"  PGC accuracy on these rows       {out['pgc_accuracy_on_deferred']:.4f}")
    print(f"  P(PGC correct | router wrong)    {p_cand_given_wrong:.4f}")
    print(f"  corrections {corr}   harms {harm}   NET {corr - harm:+d}"
          f"  ({out['net_per_1000_rescued']:+.1f} per 1000 rescued)")
    per_fam = {}
    for f in FAMS:
        m = fams == f
        if not m.any():
            continue
        rc, cc = router_correct[m], rescue_correct[m]
        per_fam[f] = {
            "n": int(m.sum()),
            "router_acc": round(float(rc.mean()), 4),
            "pgc_acc": round(float(cc.mean()), 4),
            "net": int((cc & ~rc).sum() - (~cc & rc).sum()),
        }
    print(f"  {'family':<9}{'n':>7}{'router':>9}{'PGC':>9}{'net':>7}")
    for f, v in per_fam.items():
        print(f"  {f:<9}{v['n']:>7}{v['router_acc']:>9.4f}{v['pgc_acc']:>9.4f}{v['net']:>+7d}")
    out["per_family"] = per_fam
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dev", type=Path, default=Path("results/pgc/dev_deferred.jsonl"))
    ap.add_argument("--test", type=Path, default=Path("results/pgc/test_deferred.jsonl"))
    ap.add_argument("--decision-threshold", type=float, default=0.4667367651127279)
    ap.add_argument("--out", type=Path, default=Path("results/pgc/rescue.json"))
    args = ap.parse_args()

    dev = load(args.dev)
    if not dev:
        print("no usable dev rows", file=sys.stderr)
        return 2
    p, rp, y, fam, _ = arrays(dev)
    router_correct = ((rp >= args.decision_threshold).astype(int) == y)
    pgc_thr, dev_net = fit_pgc_threshold(p, router_correct, y, args.decision_threshold)
    print(f"PGC threshold fitted on DEV deferred rows: {pgc_thr:.4f} (dev net {dev_net:+d})")
    dev_report = report("DEV (fitting surface)", p, rp, y, fam, args.decision_threshold, pgc_thr)

    doc = {"schema_version": "rescue-analysis.v1",
           "pgc_threshold": pgc_thr, "pgc_threshold_fitted_on": "dev deferred rows",
           "decision_threshold": args.decision_threshold, "dev": dev_report}

    if args.test.exists():
        test = load(args.test)
        if test:
            p2, rp2, y2, fam2, _ = arrays(test)
            doc["test"] = report("INTERNAL TEST (one-shot, nothing fitted here)",
                                 p2, rp2, y2, fam2, args.decision_threshold, pgc_thr)
            net = doc["test"]["net"]
            print(f"\nGATE: rescue is adopted only if net > 0 on the TEST. net = {net:+d}")
            doc["gate_passed"] = bool(net > 0)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, indent=2) + "\n")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
