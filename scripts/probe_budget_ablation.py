"""How much of the robustness gain does each self-probe actually buy?

The shipped system runs three probes (JPEG q92, crop 0.96, resize 0.90) on EVERY
image, which is why p50 latency is 127.9 ms against 18.8 ms for the bare
detector. Before building any adaptive controller we answer the cheap question:
can one or two probes recover most of the three-probe result?

This costs no forward passes. The cache stores each probe's score individually,
and every probe feature is a pure function of `[base_p_fake, *probe_values]`
(`pipeline/probes.py:compute_probe_features`), so a subset is simulated by
recomputing the aggregates offline.

DEV SPLIT ONLY. The internal test's per-family results are what generated this
idea; using that test to validate a component built from it would destroy the
"untouched" claim. Output is stamped accordingly.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

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

ALL_PROBES = ("probe_jpeg_q92", "probe_crop_0.96", "probe_resize_0.90")
SHORT = {"probe_jpeg_q92": "jpeg", "probe_crop_0.96": "crop", "probe_resize_0.90": "resize"}
# all-3 FIRST, deliberately: it is the reproduction check against the freeze's
# dev 0.8144. If the harness diverges from the freeze, we find out in ~2 minutes
# instead of after the whole sweep.
SUBSETS = [
    ALL_PROBES,
    (),
    ("probe_jpeg_q92",),
    ("probe_crop_0.96",),
    ("probe_resize_0.90",),
    ("probe_jpeg_q92", "probe_crop_0.96"),
    ("probe_jpeg_q92", "probe_resize_0.90"),
    ("probe_crop_0.96", "probe_resize_0.90"),
]


def recompute_probe_block(block: dict, base_p_fake: float, subset: tuple[str, ...]) -> dict:
    """Reproduce `compute_probe_features` for a subset of probes.

    Mirrors the upstream definitions exactly: statistics are taken over
    `[base, *values]`, the stdev is POPULATION (these are all the probes there
    are), and `max_delta` is over the probe values alone. An empty subset yields
    None everywhere so `features._pair` encodes it as absent-with-indicator-0
    rather than a fabricated number.

    `probe_flip` is deliberately absent: the cache is threshold-free and
    `features.derive_probe_flip` computes it at consumption from `probe_scores`.
    """
    scores = {p: v for p, v in (block.get("probe_scores") or {}).items() if p in subset}
    values = list(scores.values())
    n_ok = len(values)
    population = [base_p_fake, *values]
    return {
        "probe_scores": scores,
        "n_probes_ok": n_ok,
        "probe_mean": statistics.fmean(population) if n_ok else None,
        "probe_std": statistics.pstdev(population) if n_ok else None,
        "probe_range": (max(population) - min(population)) if n_ok else None,
        "probe_max_delta": max(abs(base_p_fake - v) for v in values) if n_ok else None,
        "probe_failures": block.get("probe_failures", []),
    }


def project(rows: list[dict], eid: str, subset: tuple[str, ...]) -> list[dict]:
    out = []
    for r in rows:
        base = float((r["experts"][eid])["p_fake"])
        blk = (r.get("probes") or {}).get(eid) or {}
        out.append({**r, "probes": {eid: recompute_probe_block(blk, base, subset)}})
    return out


def fidelity_check(rows: list[dict], eid: str, n: int = 2000) -> None:
    """The all-3 recomputation must reproduce what the cache stores.

    If this fails every other arm is meaningless, so it is a hard abort.
    """
    worst = 0.0
    for r in rows[:n]:
        blk = (r.get("probes") or {}).get(eid) or {}
        if not blk.get("probe_scores"):
            continue
        base = float((r["experts"][eid])["p_fake"])
        got = recompute_probe_block(blk, base, ALL_PROBES)
        for k in ("probe_mean", "probe_std", "probe_range", "probe_max_delta"):
            if blk.get(k) is None or got[k] is None:
                continue
            worst = max(worst, abs(float(blk[k]) - float(got[k])))
    if worst > 1e-9:
        raise SystemExit(f"FIDELITY CHECK FAILED: recomputed aggregates differ by {worst:.3e}")
    print(f"fidelity check OK: max |recomputed - cached| = {worst:.2e} over {n} rows",
          file=sys.stderr)


def flip_rate(scores, labels, conds, srcs, thr) -> float:
    """Of sources decided CORRECTLY when clean, how often does a transform flip them?"""
    pred = scores >= thr
    clean_ok = {srcs[i]: bool(pred[i] == (labels[i] == 1))
                for i in range(len(scores)) if conds[i] == "clean"}
    t = f2r = 0
    for i in range(len(scores)):
        if conds[i] == "clean" or not clean_ok.get(srcs[i], False) or labels[i] != 1:
            continue
        t += 1
        f2r += int(not pred[i])
    return f2r / t if t else float("nan")


def paired_bootstrap(a, b, labels, fams, srcs, ta, tb, n=1000, seed=11):
    """Paired source bootstrap of worst-family recall, a minus b."""
    uniq = np.unique(srcs)
    idx = {s: np.flatnonzero(srcs == s) for s in uniq}
    rng = np.random.default_rng(seed)
    families = sorted(set(fams) - {"clean"})

    def worst(sc, sel, thr):
        vals = [float((sc[sel][(fams[sel] == f) & (labels[sel] == 1)] >= thr).mean())
                for f in families if ((fams[sel] == f) & (labels[sel] == 1)).any()]
        return min(vals) if vals else np.nan

    d = []
    for _ in range(n):
        sel = np.concatenate([idx[s] for s in rng.choice(uniq, size=len(uniq), replace=True)])
        d.append(worst(a, sel, ta) - worst(b, sel, tb))
    d = np.asarray(d, float)
    return {"mean_delta": float(np.nanmean(d)),
            "ci95_low": float(np.nanquantile(d, 0.025)),
            "ci95_high": float(np.nanquantile(d, 0.975)), "n_resamples": n}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cache", type=Path, default=Path("data/feature_cache/fitting-v2"))
    ap.add_argument("--out", type=Path, default=Path("results/probe-ablation/dev-results.json"))
    ap.add_argument("--seeds", default="20260827,20260828,20260829")
    ap.add_argument("--bootstrap", type=int, default=1000)
    args = ap.parse_args()
    seeds = [int(s) for s in args.seeds.split(",")]

    rows = load_cache_rows(args.cache / "rows.jsonl")
    expert_ids = tuple(sorted({e for r in rows for e in (r.get("experts") or {})}))
    eid = expert_ids[0]
    usable = validate_cache_rows(rows, expert_ids)["usable_rows"]
    fidelity_check(usable, eid)

    train_src = [r for r in usable if r["dataset_split"] == "train"]
    dev_src = [r for r in usable if r["dataset_split"] == "dev"]
    spec = FeatureSpec(expert_ids=expert_ids)
    dev_labels = np.array([r["label"] for r in dev_src])
    dev_fams = np.array([r.get("family") or "clean" for r in dev_src])
    dev_conds = np.array([r["condition_id"] for r in dev_src])
    dev_srcs = np.array([r["source_id"] for r in dev_src])
    print(f"train={len(train_src)} dev={len(dev_src)} dim={spec.dim}", file=sys.stderr)

    results, dev_scores_by_arm = {}, {}
    for subset in SUBSETS:
        label = "+".join(SHORT[p] for p in subset) if subset else "none"
        tr_rows = project(train_src, eid, subset)
        dv_rows = project(dev_src, eid, subset)
        per_seed = []
        for seed in seeds:
            std = Standardizer.fit(rows_to_matrix(tr_rows, spec, 0.5), spec)
            tb = build_batch(tr_rows, spec, std, 0.5)
            db = build_batch(dv_rows, spec, std, 0.5)
            rec = train_rung("mlp", tb, db, spec.dim, len(expert_ids), 0.5, use_worst_group=True,
                             seed=seed, bootstrap_replicates=8, fit_reliability=False,
                             quality_only_indices=spec.non_expert_indices())
            with torch.no_grad():
                tr_p = rec["_model"](tb.features, tb.expert_logits, tb.available).p_fake.numpy()
            grid = np.unique(np.quantile(np.clip(tr_p, 0, 1), np.linspace(0, 1, 257)))
            art = select_threshold(
                DevSet(source_ids=np.array([r["source_id"] for r in tr_rows]),
                       condition_ids=np.array([r["condition_id"] for r in tr_rows]),
                       families=np.array([r.get("family") or "clean" for r in tr_rows]),
                       labels=np.array([r["label"] for r in tr_rows], dtype=int),
                       scores=np.clip(tr_p, 0, 1)),
                candidates=grid, n_replicates=200, seed=seed,
                dev_manifest_sha256="probe-ablation", config_sha256="probe-ablation",
                pipeline_version=PIPELINE_VERSION, fitting_code_version="probe-ablation")
            thr = float(art.threshold)
            dv = np.asarray(rec["_dev_p_fake"], dtype=float)
            w, fam = worst_family_recall(dv, dev_labels, dev_fams, thr, require_all=False)
            pred = dv >= thr
            clean = dev_fams == "clean"
            tpr = float(pred[dev_labels == 1].mean())
            tnr = float((~pred)[dev_labels == 0].mean())
            per_seed.append({
                "seed": seed, "threshold": thr,
                "worst_family_fake_recall": float(w), "worst_family": fam,
                "clean_fpr": float(pred[clean & (dev_labels == 0)].mean()),
                "overall_accuracy": float((pred == (dev_labels == 1)).mean()),
                "balanced_accuracy": (tpr + tnr) / 2.0,
                "fake_to_real_flip_rate": flip_rate(dv, dev_labels, dev_conds, dev_srcs, thr),
                "_dev": dv,
            })
        ws = [p["worst_family_fake_recall"] for p in per_seed]
        best = per_seed[0]                       # seed[0] is the freeze seed: used for pairing
        dev_scores_by_arm[label] = (best["_dev"], best["threshold"])
        results[label] = {
            "probes": list(subset), "n_forward_passes": 1 + len(subset),
            "worst_family_mean": float(np.mean(ws)),
            "worst_family_sd": float(np.std(ws)),
            "worst_family_by_seed": ws,
            "clean_fpr_mean": float(np.mean([p["clean_fpr"] for p in per_seed])),
            "overall_accuracy_mean": float(np.mean([p["overall_accuracy"] for p in per_seed])),
            "balanced_accuracy_mean": float(np.mean([p["balanced_accuracy"] for p in per_seed])),
            "flip_rate_mean": float(np.mean([p["fake_to_real_flip_rate"] for p in per_seed])),
            "threshold_seed0": best["threshold"],
            "per_seed": [{k: v for k, v in p.items() if k != "_dev"} for p in per_seed],
        }
        print(f"  {label:<14} passes={1+len(subset)}  worst={np.mean(ws):.4f} "
              f"(sd {np.std(ws):.4f})  cleanFPR={results[label]['clean_fpr_mean']:.4f}  "
              f"bacc={results[label]['balanced_accuracy_mean']:.4f}", file=sys.stderr)

    # paired bootstrap: all-3 minus each subset, on the freeze seed
    full_label = "+".join(SHORT[p] for p in ALL_PROBES)
    fa, fthr = dev_scores_by_arm[full_label]
    for label, (sa, sthr) in dev_scores_by_arm.items():
        if label == full_label:
            continue
        results[label]["paired_loss_vs_all3"] = paired_bootstrap(
            fa, sa, dev_labels, dev_fams, dev_srcs, fthr, sthr, n=args.bootstrap)

    doc = {
        "schema_version": "probe-budget-ablation.v1",
        "NOT_A_HEADLINE_RESULT": "DEV SPLIT ONLY. The untouched internal test was not consulted; "
                                 "it already informed the hypothesis under study.",
        "decision_rule": "pre-registered: adopt the SMALLEST budget whose paired-bootstrap loss "
                         "vs all-3 has CI95 upper bound below 0.02 worst-family recall",
        "seeds": seeds, "rung": "mlp+worst_group", "arms": results,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, indent=2) + "\n")
    print(f"\nwrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
