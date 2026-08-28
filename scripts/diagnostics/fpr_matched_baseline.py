"""POST-HOC diagnostic, added AFTER the one-shot test was unblinded.

Purpose: the headline compares the frozen router against `primary @0.5`, but those two run at
very different operating points (overall FPR 0.1023 vs 0.0057). A recall gain measured across an
18x FPR gap is not, on its own, evidence that the cascade helps -- some of it is just a looser cut.

This script does NOT refit our model or our threshold. It only makes the BASELINE stronger, which
biases every number here AGAINST us:

  A. primary @ the dev-fitted `static_average` threshold (0.1272509451955557). With a single
     expert the static-average rung is exactly the primary probability, so this is "primary with a
     threshold fitted honestly on dev". No test-set information at all.
  B. primary @ an ORACLE threshold fitted ON THIS TEST SET to match the router's overall FPR.
     This is leakage we deliberately grant the baseline and deny ourselves; it is an upper bound
     on what the primary could do at our operating point.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import torch

from src.pipeline.transforms import FAMILY_OF
from src.router.train import build_batch, load_cache_rows, load_checkpoint

CACHE = Path("data/feature_cache/internal-test-v2")
DEV_FITTED_STATIC_AVG_THR = 0.1272509451955557

rows = load_cache_rows(CACHE / "rows.jsonl")
labels = np.array([r["label"] for r in rows])
fams = np.array([r.get("family") or FAMILY_OF.get(r["condition_id"], "clean") for r in rows])
srcs = np.array([r["source_id"] for r in rows])

loaded = load_checkpoint(Path("results/router-fitting-v2/router.pt"))
thr = 0.4667367651127279
batch = build_batch(rows, loaded.spec, loaded.standardizer, thr)
with torch.no_grad():
    router = loaded.model(batch.features, batch.expert_logits, batch.available).p_fake.numpy()
eid = loaded.spec.expert_ids[0]
primary = np.array([float(r["experts"][eid].get("p_fake", 0.5)) for r in rows])

FAMS = sorted(set(FAMILY_OF.values()) - {"clean"})
def worst_fam(sc, t, sel=None):
    sel = slice(None) if sel is None else sel
    return min(float((sc[sel][(fams[sel] == f) & (labels[sel] == 1)] >= t).mean()) for f in FAMS)
def overall_fpr(sc, t): return float((sc[labels == 0] >= t).mean())
def clean_fpr(sc, t): return float((sc[(fams == "clean") & (labels == 0)] >= t).mean())

router_fpr = overall_fpr(router, thr)
# B: oracle threshold on the test set matching the router's overall FPR
neg = np.sort(primary[labels == 0])
oracle = float(np.quantile(neg, 1.0 - router_fpr))

print(f"router overall FPR to match: {router_fpr:.4f}\n")
print(f"{'arm':<46}{'thr':>10}{'worst-fam':>11}{'ovr-FPR':>10}{'clean-FPR':>11}")
arms = [
    ("router (frozen, dev-fitted thr)", router, thr),
    ("A. primary @ dev-fitted static_average thr", primary, DEV_FITTED_STATIC_AVG_THR),
    ("B. primary @ ORACLE test-fitted FPR-matched", primary, oracle),
    ("   primary @0.5 (published default)", primary, 0.5),
]
for tag, sc, t in arms:
    print(f"{tag:<46}{t:>10.4f}{worst_fam(sc, t):>11.4f}{overall_fpr(sc, t):>10.4f}{clean_fpr(sc, t):>11.4f}")

# paired source bootstrap of router vs each baseline
uniq = np.unique(srcs); idx = {s: np.flatnonzero(srcs == s) for s in uniq}
rng = np.random.default_rng(11)
print()
out = {"router_overall_fpr": router_fpr, "oracle_threshold": oracle, "arms": {}}
for tag, sc, t in arms[1:]:
    d = []
    for _ in range(2000):
        sel = np.concatenate([idx[s] for s in rng.choice(uniq, size=len(uniq), replace=True)])
        d.append(worst_fam(router, thr, sel) - worst_fam(sc, t, sel))
    d = np.asarray(d)
    lo, hi = float(np.quantile(d, .025)), float(np.quantile(d, .975))
    print(f"router - [{tag.strip()}]: {d.mean():+.4f} CI95 [{lo:+.4f}, {hi:+.4f}]")
    out["arms"][tag.strip()] = {"threshold": t, "worst_family_fake_recall": worst_fam(sc, t),
                                "overall_fpr": overall_fpr(sc, t), "clean_fpr": clean_fpr(sc, t),
                                "paired_delta_mean": float(d.mean()), "ci95_low": lo, "ci95_high": hi}
out["router"] = {"threshold": thr, "worst_family_fake_recall": worst_fam(router, thr),
                 "overall_fpr": router_fpr, "clean_fpr": clean_fpr(router, thr)}
Path("results/internal-test/fpr-matched-baseline.json").write_text(json.dumps(out, indent=2) + "\n")
print("\nwrote results/internal-test/fpr-matched-baseline.json")
