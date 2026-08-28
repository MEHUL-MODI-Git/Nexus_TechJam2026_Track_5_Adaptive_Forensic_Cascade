"""Score the sealed reference run. Reports only — nothing here is fitted.

Two conventions are reported side by side, per A-029:

* **deduplicated** (primary): one vote per unique image. 5,000 COCO val2017 reals
  and 3,719 unique DALL-E images.
* **per-file** (secondary): each unique image weighted by how many times the
  organizers' archive contains it, so our numbers can be reconciled with any
  computed the naive way over 13,843 files.

This is a REFERENCE BENCHMARK, not our headline. The threshold was frozen on a
different corpus (SID-Set), and COCO val2017 reals plus DALL-E 3 fakes are a
different distribution; a shift in operating point here is a finding to report,
never a reason to re-tune.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.pipeline.transforms import FAMILY_OF

FAMS = sorted(set(FAMILY_OF.values()) - {"clean"})


def auroc(scores, y, w=None):
    scores, y = np.asarray(scores, float), np.asarray(y, int)
    w = np.ones_like(scores) if w is None else np.asarray(w, float)
    order = np.argsort(scores, kind="mergesort")
    y, w = y[order], w[order]
    pos_w, neg_w = w * (y == 1), w * (y == 0)
    # weighted AUROC via rank sums with ties averaged
    cum_neg = np.cumsum(neg_w) - neg_w / 2.0
    tot_pos, tot_neg = pos_w.sum(), neg_w.sum()
    if tot_pos == 0 or tot_neg == 0:
        return float("nan")
    return float((pos_w * cum_neg).sum() / (tot_pos * tot_neg))


def block(scores, labels, weights, thr):
    pred = scores >= thr
    f, r = labels == 1, labels == 0
    return {
        "n_images": len(labels),
        "n_effective": float(weights.sum()),
        "fake_recall": float(np.average(pred[f], weights=weights[f])) if f.any() else float("nan"),
        "fpr": float(np.average(pred[r], weights=weights[r])) if r.any() else float("nan"),
        "accuracy": float(np.average(pred == f, weights=weights)),
        "auroc": auroc(scores, labels, weights),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pred", type=Path, default=Path("results/sealed/predictions.jsonl"))
    ap.add_argument("--out", type=Path, default=Path("results/sealed/reference-results.json"))
    ap.add_argument("--threshold", type=float, default=0.4667367651127279)
    ap.add_argument("--bootstrap", type=int, default=2000)
    args = ap.parse_args()

    rows = []
    with args.pred.open() as fh:
        for line in fh:
            r = json.loads(line)
            if r.get("ok") is False:
                continue
            rows.append(r)
    if not rows:
        print("no usable rows", file=sys.stderr)
        return 2

    thr = args.threshold
    sha = np.array([r["sha256"] for r in rows])
    cond = np.array([r["condition_id"] for r in rows])
    fam = np.array([FAMILY_OF[c] for c in cond])
    lab = np.array([r["label"] for r in rows])
    p = np.array([r["p_fake"] for r in rows], float)
    mult = np.array([r["file_multiplicity"] for r in rows], float)
    ones = np.ones_like(mult)
    rel = np.array([np.nan if r.get("reliability") is None else r["reliability"] for r in rows])
    absta = np.array([bool(r.get("abstain")) for r in rows])
    prim = np.array([np.nan if r.get("primary_p_fake") is None else r["primary_p_fake"] for r in rows])

    doc = {
        "schema_version": "sealed-reference-results.v1",
        "status": "REFERENCE BENCHMARK — one run, after freeze; never fitted on, never re-tuned",
        "threshold": thr,
        "n_rows": len(rows),
        "n_unique_images": len(set(sha)),
        "duplication_note": "the DALL-E half ships 8,843 files containing 3,719 unique images; "
                            "deduplicated numbers are primary, per-file reported for reconciliation",
        "conventions": {},
    }

    for name, w in (("deduplicated", ones), ("per_file", mult)):
        clean = cond == "clean"
        conv = {
            "clean": block(p[clean], lab[clean], w[clean], thr),
            "all_conditions": block(p, lab, w, thr),
            "per_family": {},
            "per_condition": {},
        }
        for f in FAMS:
            m = fam == f
            if m.any():
                conv["per_family"][f] = block(p[m], lab[m], w[m], thr)
        for c in sorted(set(cond)):
            m = cond == c
            conv["per_condition"][c] = block(p[m], lab[m], w[m], thr)
        fam_rec = {k: v["fake_recall"] for k, v in conv["per_family"].items()}
        worst = min(fam_rec, key=fam_rec.get)
        conv["worst_family"] = worst
        conv["worst_family_fake_recall"] = fam_rec[worst]
        # primary baseline at its published default, same rows
        if np.isfinite(prim).any():
            conv["primary_at_0.5"] = {
                "clean": block(prim[clean], lab[clean], w[clean], 0.5),
                "all_conditions": block(prim, lab, w, 0.5),
                "worst_family_fake_recall": min(
                    block(prim[fam == f], lab[fam == f], w[fam == f], 0.5)["fake_recall"]
                    for f in FAMS if (fam == f).any()),
            }
        # THE SAME ADVERSARIAL CONTROL WE APPLY TO OURSELVES ELSEWHERE.
        # The cascade runs at a much higher FPR than the primary at 0.5, so the
        # naive gap flatters us. Hand the primary our clean FPR with its
        # threshold fitted ON THIS SET, in its favour, and re-ask.
        if np.isfinite(prim).any():
            clean_real = clean & (lab == 0)
            target = conv["clean"]["fpr"]
            s_sorted = np.sort(prim[clean_real])
            k = int(np.floor(target * s_sorted.size))
            t_match = float(s_sorted[s_sorted.size - k]) if k > 0 else float(
                np.nextafter(s_sorted[-1], np.inf))
            fam_rec = [block(prim[fam == f], lab[fam == f], w[fam == f], t_match)["fake_recall"]
                       for f in FAMS if (fam == f).any()]
            conv["primary_at_matched_clean_fpr"] = {
                "threshold": t_match,
                "threshold_fitted_on": "THIS SEALED SET, in the baseline's favour",
                "target_clean_fpr": target,
                "clean": block(prim[clean], lab[clean], w[clean], t_match),
                "worst_family_fake_recall": min(fam_rec) if fam_rec else float("nan"),
                "cascade_advantage": (conv["worst_family_fake_recall"] - min(fam_rec))
                                     if fam_rec else float("nan"),
            }

        # abstention, using the frozen policy
        if np.isfinite(rel).any():
            keep = ~absta
            conv["abstention"] = {
                "coverage": float(np.average(keep, weights=w)),
                "accuracy_all": block(p, lab, w, thr)["accuracy"],
                "accuracy_kept": float(np.average((p[keep] >= thr) == (lab[keep] == 1),
                                                  weights=w[keep])) if keep.any() else float("nan"),
                "accuracy_deferred": float(np.average((p[~keep] >= thr) == (lab[~keep] == 1),
                                                      weights=w[~keep])) if (~keep).any() else float("nan"),
            }
        doc["conventions"][name] = conv

    # image-level bootstrap on the DEDUPLICATED convention
    uniq = np.unique(sha)
    idx = {s: np.flatnonzero(sha == s) for s in uniq}
    rng = np.random.default_rng(20260828)
    stats = []
    for _ in range(args.bootstrap):
        pick = rng.choice(uniq, size=len(uniq), replace=True)
        sel = np.concatenate([idx[s] for s in pick])
        fr = [float((p[sel][(fam[sel] == f) & (lab[sel] == 1)] >= thr).mean())
              for f in FAMS if ((fam[sel] == f) & (lab[sel] == 1)).any()]
        stats.append(min(fr) if fr else np.nan)
    stats = np.asarray(stats, float)
    doc["worst_family_bootstrap_dedup"] = {
        "mean": float(np.nanmean(stats)),
        "ci95_low": float(np.nanquantile(stats, 0.025)),
        "ci95_high": float(np.nanquantile(stats, 0.975)),
        "n_resamples": args.bootstrap,
        "unit": "unique image (never file), per A-029",
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, indent=2) + "\n")

    d = doc["conventions"]["deduplicated"]
    pf = doc["conventions"]["per_file"]
    print(f"rows {len(rows)}  unique images {doc['n_unique_images']}\n")
    print(f"{'':<22}{'dedup':>12}{'per-file':>12}")
    for k, lbl in (("clean", "clean"), ("all_conditions", "all conditions")):
        print(f"{lbl+' AUROC':<22}{d[k]['auroc']:>12.4f}{pf[k]['auroc']:>12.4f}")
        print(f"{lbl+' recall':<22}{d[k]['fake_recall']:>12.4f}{pf[k]['fake_recall']:>12.4f}")
        print(f"{lbl+' FPR':<22}{d[k]['fpr']:>12.4f}{pf[k]['fpr']:>12.4f}")
    print(f"{'worst family':<22}{d['worst_family_fake_recall']:>12.4f}"
          f"{pf['worst_family_fake_recall']:>12.4f}   ({d['worst_family']})")
    b = doc["worst_family_bootstrap_dedup"]
    print(f"\nworst-family bootstrap (unique-image unit): {b['mean']:.4f} "
          f"CI95 [{b['ci95_low']:.4f}, {b['ci95_high']:.4f}]")
    if "abstention" in d:
        a = d["abstention"]
        print(f"\nabstention: coverage {a['coverage']:.3f}  "
              f"accuracy {a['accuracy_all']:.4f} -> {a['accuracy_kept']:.4f} "
              f"(deferred {a['accuracy_deferred']:.4f})")
    if "primary_at_0.5" in d:
        pr = d["primary_at_0.5"]
        print(f"\nprimary @0.5 baseline: clean AUROC {pr['clean']['auroc']:.4f}  "
              f"worst-family {pr['worst_family_fake_recall']:.4f}")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
