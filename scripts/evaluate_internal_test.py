"""ONE-SHOT evaluation on the untouched internal test set.

Nothing has been fitted on these 3,000 sources: not weights, not the threshold, not the feature
set, not the rung choice. That is the whole point of holding them back, so this script LOADS a
frozen checkpoint and a validated threshold artifact and never fits anything.

It reports the comparison that actually matters for the write-up: the frozen router against the
raw primary detector — what you would ship if you did nothing — on identical rows, with paired
source bootstrap.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.eval.protocol import load_frozen_threshold
from src.pipeline.transforms import CONDITION_IDS, FAMILY_OF
from src.router.train import build_batch, load_cache_rows, load_checkpoint


def metrics(scores, labels, fams, conds, threshold):
    pred = scores >= threshold
    out = {}
    clean = fams == "clean"
    cf, ck = clean & (labels == 0), clean & (labels == 1)
    fam_recall = {}
    for f in sorted(set(FAMILY_OF.values()) - {"clean"}):
        m = (fams == f) & (labels == 1)
        if m.any():
            fam_recall[f] = float(pred[m].mean())
    worst_fam = min(fam_recall, key=fam_recall.get) if fam_recall else None
    per_cond = {}
    for c in CONDITION_IDS:
        m = conds == c
        if not m.any():
            continue
        fk, rl = m & (labels == 1), m & (labels == 0)
        per_cond[c] = {
            "fake_recall": float(pred[fk].mean()) if fk.any() else float("nan"),
            "fpr": float(pred[rl].mean()) if rl.any() else float("nan"),
            "n": int(m.sum()),
        }
    out.update({
        "worst_family": worst_fam,
        "worst_family_fake_recall": fam_recall.get(worst_fam) if worst_fam else None,
        "family_fake_recall": fam_recall,
        "clean_fake_recall": float(pred[ck].mean()) if ck.any() else float("nan"),
        "clean_fpr": float(pred[cf].mean()) if cf.any() else float("nan"),
        "overall_fake_recall": float(pred[labels == 1].mean()),
        "overall_fpr": float(pred[labels == 0].mean()),
        "overall_accuracy": float((pred == (labels == 1)).mean()),
        "per_condition": per_cond,
    })
    return out


def flip_rates(scores, labels, fams, conds, srcs, threshold):
    """Among sources decided CORRECTLY when clean, how often does a transform flip them?"""
    pred = scores >= threshold
    clean_ok = {}
    for i in range(len(scores)):
        if conds[i] == "clean":
            clean_ok[srcs[i]] = bool(pred[i] == (labels[i] == 1))
    f2r = t = r2f = u = 0
    for i in range(len(scores)):
        if conds[i] == "clean" or not clean_ok.get(srcs[i], False):
            continue
        if labels[i] == 1:
            t += 1; f2r += int(not pred[i])
        else:
            u += 1; r2f += int(pred[i])
    return {"fake_to_real_flip_rate": f2r / t if t else float("nan"), "n_fake_views": t,
            "real_to_fake_flip_rate": r2f / u if u else float("nan"), "n_real_views": u}


def paired_bootstrap(a, b, labels, fams, srcs, ta, tb, n=2000, seed=11):
    uniq = np.unique(srcs)
    idx = {s: np.flatnonzero(srcs == s) for s in uniq}
    rng = np.random.default_rng(seed)
    def worst(sc, sel, thr):
        best = 1.1
        for f in sorted(set(FAMILY_OF.values()) - {"clean"}):
            m = (fams[sel] == f) & (labels[sel] == 1)
            if m.any():
                best = min(best, float((sc[sel][m] >= thr).mean()))
        return best if best <= 1.0 else float("nan")
    d = []
    for _ in range(n):
        pick = rng.choice(uniq, size=len(uniq), replace=True)
        sel = np.concatenate([idx[s] for s in pick])
        d.append(worst(a, sel, ta) - worst(b, sel, tb))
    d = np.asarray(d)
    return {"mean_delta": float(d.mean()), "ci95_low": float(np.quantile(d, 0.025)),
            "ci95_high": float(np.quantile(d, 0.975)), "n_resamples": n}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cache", type=Path, required=True)
    ap.add_argument("--checkpoint", type=Path, required=True)
    ap.add_argument("--threshold-artifact", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=Path("results/internal-test/results.json"))
    ap.add_argument("--bootstrap", type=int, default=2000)
    args = ap.parse_args()

    manifest = json.loads((args.cache / "manifest.json").read_text())
    if manifest.get("role") != "evaluation":
        print(f"REFUSING: cache role is {manifest.get('role')!r}, expected 'evaluation'",
              file=sys.stderr)
        return 2

    frozen = load_frozen_threshold(args.threshold_artifact)   # validates or raises
    loaded = load_checkpoint(args.checkpoint)
    thr = float(frozen.value)
    print(f"frozen threshold {thr:.6f} (artifact {frozen.artifact_sha256[:12]}), "
          f"rung {loaded.payload['rung']}", file=sys.stderr)

    rows = load_cache_rows(args.cache / "rows.jsonl")
    labels = np.array([r["label"] for r in rows])
    fams = np.array([r.get("family") or FAMILY_OF.get(r["condition_id"], "clean") for r in rows])
    conds = np.array([r["condition_id"] for r in rows])
    srcs = np.array([r["source_id"] for r in rows])
    print(f"internal test: {len(rows)} rows, {len(set(srcs))} sources", file=sys.stderr)

    batch = build_batch(rows, loaded.spec, loaded.standardizer, thr)
    with torch.no_grad():
        router = loaded.model(batch.features, batch.expert_logits, batch.available).p_fake.numpy()
    eid = loaded.spec.expert_ids[0]
    primary = np.array([float((r["experts"][eid]).get("p_fake", 0.5)) for r in rows])

    router_m = metrics(router, labels, fams, conds, thr)
    # The primary is judged at ITS OWN best-case operating point, not ours: giving the baseline
    # our threshold would be a straw man. 0.5 is its published default.
    primary_m = metrics(primary, labels, fams, conds, 0.5)
    doc = {
        "schema_version": "internal-test-results.v1",
        "one_shot": "the untouched internal test; nothing was fitted on these sources",
        "cache": str(args.cache), "cache_role": manifest.get("role"),
        "cache_manifest_sha256": hashlib.sha256(
            (args.cache / "manifest.json").read_bytes()).hexdigest(),
        "checkpoint": str(args.checkpoint), "rung": loaded.payload["rung"],
        "n_parameters": loaded.payload.get("n_parameters"),
        "threshold": thr, "threshold_artifact_sha256": frozen.artifact_sha256,
        "n_rows": len(rows), "n_sources": len(set(srcs)),
        "router": router_m, "router_flips": flip_rates(router, labels, fams, conds, srcs, thr),
        "primary_at_0.5": primary_m,
        "primary_flips": flip_rates(primary, labels, fams, conds, srcs, 0.5),
        "paired_bootstrap_router_vs_primary": paired_bootstrap(
            router, primary, labels, fams, srcs, thr, 0.5, n=args.bootstrap),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, indent=2) + "\n")

    print(f"\n{'':<22}{'worst-fam':>10}{'clean-rec':>11}{'clean-FPR':>11}{'overall-acc':>13}",
          file=sys.stderr)
    for tag, m in (("router (frozen)", router_m), ("primary @0.5", primary_m)):
        print(f"{tag:<22}{m['worst_family_fake_recall']:>10.4f}{m['clean_fake_recall']:>11.4f}"
              f"{m['clean_fpr']:>11.4f}{m['overall_accuracy']:>13.4f}", file=sys.stderr)
    b = doc["paired_bootstrap_router_vs_primary"]
    print(f"\npaired source bootstrap, worst-family recall: {b['mean_delta']:+.4f} "
          f"CI95 [{b['ci95_low']:+.4f}, {b['ci95_high']:+.4f}]", file=sys.stderr)
    print(f"wrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
