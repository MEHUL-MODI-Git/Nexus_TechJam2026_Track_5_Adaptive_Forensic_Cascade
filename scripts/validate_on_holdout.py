"""Confirm three findings on a SECOND untouched set. One run, nothing refitted on it.

The internal test is spent for these questions: its per-family and per-condition
results are what generated all three hypotheses. So a fresh 3,000-source holdout
was acquired (shards 30-35, never previously consumed), canonicalized through the
same pipeline, and verified disjoint from everything we have fitted on.

Every subset and threshold below was FIXED BEFORE this cache existed. Nothing is
selected here; this only asks whether what we measured once reproduces.

  1. Do the certificate's grade bands hold, and does retention still beat the
     reliability head?
  2. Does the PRE-SPECIFIED 2-condition subset match the full 20-condition grid?
  3. Does a probe-free router match the shipped one? (The ablation says probes
     buy nothing; probes are 3 of 4 forward passes.)
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.app.certificate import GRADE_BANDS
from src.eval.metrics import auroc as canonical_auroc
from src.pipeline.transforms import FAMILY_OF
from src.pipeline.version import PIPELINE_VERSION
from src.router.calibration import DevSet, select_threshold
from src.router.features import FeatureSpec, Standardizer, rows_to_matrix
from src.router.head import RouterHead
from src.router.train import (
    build_batch,
    load_cache_rows,
    load_checkpoint,
    train_rung,
    validate_cache_rows,
    worst_family_recall,
)

# Fixed on the internal test, before this holdout was extracted.
PRESPECIFIED_SUBSET = ("resize_0.25", "crop_0.8")
FAMS = sorted(set(FAMILY_OF.values()) - {"clean"})


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


def recompute_probe_block(block, base, subset):
    scores = {p: v for p, v in (block.get("probe_scores") or {}).items() if p in subset}
    vals = list(scores.values())
    pop = [base, *vals]
    n = len(vals)
    return {"probe_scores": scores, "n_probes_ok": n,
            "probe_mean": statistics.fmean(pop) if n else None,
            "probe_std": statistics.pstdev(pop) if n else None,
            "probe_range": (max(pop) - min(pop)) if n else None,
            "probe_max_delta": max(abs(base - v) for v in vals) if n else None,
            "probe_failures": block.get("probe_failures", [])}


def strip_probes(rows, eid):
    out = []
    for r in rows:
        base = float(r["experts"][eid]["p_fake"])
        blk = (r.get("probes") or {}).get(eid) or {}
        out.append({**r, "probes": {eid: recompute_probe_block(blk, base, ())}})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--holdout", type=Path, default=Path("data/feature_cache/holdout-v1"))
    ap.add_argument("--fitting", type=Path, default=Path("data/feature_cache/fitting-v2"))
    ap.add_argument("--checkpoint", type=Path,
                    default=Path("results/router-fitting-v2/router_reliability.pt"))
    ap.add_argument("--out", type=Path, default=Path("results/holdout/validation.json"))
    ap.add_argument("--seed", type=int, default=20260827)
    args = ap.parse_args()

    man = json.loads((args.holdout / "manifest.json").read_text())
    if man.get("role") != "evaluation" or man.get("status") != "complete":
        print(f"REFUSING: holdout role={man.get('role')} status={man.get('status')}",
              file=sys.stderr)
        return 2

    head = RouterHead.from_checkpoint(args.checkpoint)
    loaded = load_checkpoint(args.checkpoint)
    thr, rel_thr = head.threshold, head.abstain_threshold

    rows = load_cache_rows(args.holdout / "rows.jsonl")
    lab = np.array([r["label"] for r in rows])
    src = np.array([r["source_id"] for r in rows])
    cond = np.array([r["condition_id"] for r in rows])
    fam = np.array([r.get("family") or FAMILY_OF[r["condition_id"]] for r in rows])
    b = build_batch(rows, loaded.spec, loaded.standardizer, thr)
    with torch.no_grad():
        o = loaded.model(b.features, b.expert_logits, b.available)
    p, rel = o.p_fake.numpy(), o.reliability.numpy()
    pred = p >= thr
    print(f"holdout: {len(rows)} rows, {len(set(src))} sources", file=sys.stderr)

    doc = {"schema_version": "holdout-validation.v1",
           "holdout_manifest_sha256": man.get("cache_key"),
           "n_rows": len(rows), "n_sources": len(set(src)),
           "note": "second untouched set; every subset/threshold fixed before it existed"}

    # --- headline sanity: does the shipped model hold up at all? -------------
    fam_rec = {f: float(pred[(fam == f) & (lab == 1)].mean()) for f in FAMS}
    worst_f = min(fam_rec, key=fam_rec.get)
    clean = fam == "clean"
    doc["shipped_model"] = {
        "worst_family": worst_f, "worst_family_fake_recall": round(fam_rec[worst_f], 4),
        "family_fake_recall": {k: round(v, 4) for k, v in fam_rec.items()},
        "clean_fpr": round(float(pred[clean & (lab == 0)].mean()), 4),
        "clean_fake_recall": round(float(pred[clean & (lab == 1)].mean()), 4),
        "overall_accuracy": round(float((pred == (lab == 1)).mean()), 4),
        "internal_test_reference": {"worst_family_fake_recall": 0.8258, "clean_fpr": 0.0833},
    }
    print(f"\n[headline] worst-family {fam_rec[worst_f]:.4f} ({worst_f})  "
          f"clean FPR {doc['shipped_model']['clean_fpr']:.4f}   "
          f"(internal test: 0.8258 / 0.0833)", file=sys.stderr)

    # --- 1. certificate: retention vs reliability ---------------------------
    cp, cl, keep = {}, {}, defaultdict(dict)
    for i in range(len(rows)):
        if cond[i] == "clean":
            cp[src[i]], cl[src[i]] = bool(pred[i]), int(lab[i])
    for i in range(len(rows)):
        keep[src[i]][cond[i]] = bool(pred[i]) == cp.get(src[i], bool(pred[i]))
    ids = [s for s in keep if len(keep[s]) == 20]
    ret = np.array([sum(keep[s].values()) for s in ids])
    relc = np.array([rel[(src == s) & (cond == "clean")][0] for s in ids])
    ok = np.array([cp[s] == (cl[s] == 1) for s in ids])
    wrong = (~ok).astype(int)
    hi = relc >= rel_thr

    bands = {}
    mins = [x[0] for x in GRADE_BANDS]
    for j, (minimum, grade, quoted) in enumerate(GRADE_BANDS):
        upper = mins[j - 1] if j > 0 else 21
        m = (ret >= minimum) & (ret < upper)
        if m.any():
            bands[grade] = {"n": int(m.sum()), "share": round(float(m.mean()), 4),
                            "holdout_accuracy": round(float(ok[m].mean()), 4),
                            "internal_test_accuracy": quoted,
                            "delta": round(float(ok[m].mean()) - quoted, 4)}
    doc["v1_certificate"] = {
        "auroc_reliability_head": round(auroc(-relc, wrong), 4),
        "auroc_verdict_retention": round(auroc(-ret.astype(float), wrong), 4),
        "internal_test_auroc": {"reliability_head": 0.7206, "verdict_retention": 0.8696},
        "grade_bands": bands,
        "blind_spot_n": int((hi & ~ok).sum()),
        "blind_spot_mean_retention": round(float(ret[hi & ~ok].mean()), 4) if (hi & ~ok).any() else None,
        "confident_correct_mean_retention": round(float(ret[hi & ok].mean()), 4),
    }
    v1 = doc["v1_certificate"]
    print(f"\n[1 certificate] retention AUROC {v1['auroc_verdict_retention']:.4f} "
          f"(internal 0.8696)   reliability {v1['auroc_reliability_head']:.4f} (internal 0.7206)",
          file=sys.stderr)
    for g, v in bands.items():
        print(f"    {g:<9} n={v['n']:5d}  holdout {v['holdout_accuracy']:.4f}  "
              f"internal {v['internal_test_accuracy']:.4f}  delta {v['delta']:+.4f}",
              file=sys.stderr)

    # --- 2. pre-specified 2-condition subset --------------------------------
    sub = np.array([sum(keep[s][c] for c in PRESPECIFIED_SUBSET) for s in ids], float)
    doc["v2_condition_subset"] = {
        "subset": list(PRESPECIFIED_SUBSET),
        "auroc_subset": round(auroc(-sub, wrong), 4),
        "auroc_all_20": round(auroc(-ret.astype(float), wrong), 4),
        "internal_test": {"subset": 0.8690, "all_20": 0.8696},
        "forward_passes": {"subset": len(PRESPECIFIED_SUBSET) * 4, "all_20": 80},
    }
    v2 = doc["v2_condition_subset"]
    print(f"\n[2 subset] {'+'.join(PRESPECIFIED_SUBSET)}: AUROC {v2['auroc_subset']:.4f} "
          f"vs all-20 {v2['auroc_all_20']:.4f}   (internal: 0.8690 vs 0.8696)   "
          f"{v2['forward_passes']['subset']} passes vs 80", file=sys.stderr)

    # --- 3. probe-free variant ---------------------------------------------
    frows = load_cache_rows(args.fitting / "rows.jsonl")
    eids = tuple(sorted({e for r in frows for e in (r.get("experts") or {})}))
    eid = eids[0]
    usable = validate_cache_rows(frows, eids)["usable_rows"]
    tr = [r for r in usable if r["dataset_split"] == "train"]
    spec = FeatureSpec(expert_ids=eids)
    tr_np = strip_probes(tr, eid)
    ho_np = strip_probes(rows, eid)
    std = Standardizer.fit(rows_to_matrix(tr_np, spec, 0.5), spec)
    tb = build_batch(tr_np, spec, std, 0.5)
    hb = build_batch(ho_np, spec, std, 0.5)
    rec = train_rung("mlp", tb, hb, spec.dim, len(eids), 0.5, use_worst_group=True,
                     seed=args.seed, bootstrap_replicates=8, fit_reliability=False,
                     quality_only_indices=spec.non_expert_indices())
    with torch.no_grad():
        trp = rec["_model"](tb.features, tb.expert_logits, tb.available).p_fake.numpy()
    grid = np.unique(np.quantile(np.clip(trp, 0, 1), np.linspace(0, 1, 257)))
    art = select_threshold(
        DevSet(source_ids=np.array([r["source_id"] for r in tr_np]),
               condition_ids=np.array([r["condition_id"] for r in tr_np]),
               families=np.array([r.get("family") or "clean" for r in tr_np]),
               labels=np.array([r["label"] for r in tr_np], dtype=int),
               scores=np.clip(trp, 0, 1)),
        candidates=grid, n_replicates=200, seed=args.seed,
        dev_manifest_sha256="holdout-validation", config_sha256="holdout-validation",
        pipeline_version=PIPELINE_VERSION, fitting_code_version="holdout-validation")
    nthr = float(art.threshold)
    npf = np.asarray(rec["_dev_p_fake"], float)
    nw, nfam = worst_family_recall(npf, lab, fam, nthr, require_all=False)
    npred = npf >= nthr
    doc["v3_probe_free"] = {
        "threshold": nthr,
        "worst_family_fake_recall": round(float(nw), 4), "worst_family": nfam,
        "clean_fpr": round(float(npred[clean & (lab == 0)].mean()), 4),
        "overall_accuracy": round(float((npred == (lab == 1)).mean()), 4),
        "shipped_worst_family": doc["shipped_model"]["worst_family_fake_recall"],
        "delta_vs_shipped": round(float(nw) - doc["shipped_model"]["worst_family_fake_recall"], 4),
        "forward_passes": {"probe_free": 1, "shipped": 4},
    }
    v3 = doc["v3_probe_free"]
    print(f"\n[3 probe-free] worst-family {v3['worst_family_fake_recall']:.4f} vs shipped "
          f"{v3['shipped_worst_family']:.4f}  (delta {v3['delta_vs_shipped']:+.4f})   "
          f"1 forward pass vs 4", file=sys.stderr)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, indent=2) + "\n")
    print(f"\nwrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
