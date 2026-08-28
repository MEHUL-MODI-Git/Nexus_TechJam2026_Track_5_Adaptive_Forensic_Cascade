"""What does each self-probe actually measure? Descriptive, dev-only, zero compute.

Run while the model-based probe-budget ablation trains, to predict its answer and
to inform the adaptive controller's design. Reads only cached probe scores — no
decoding, no forward passes, no fitting.

Two questions:
  1. Are the three probes REDUNDANT with each other? (If yes, drop some.)
  2. Does each probe's deviation predict that the PRIMARY detector is wrong?
     That is the signal the router is actually consuming them for.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

PROBES = ("probe_jpeg_q92", "probe_crop_0.96", "probe_resize_0.90")
SHORT = {"probe_jpeg_q92": "jpeg", "probe_crop_0.96": "crop", "probe_resize_0.90": "resize"}
EID = "commfor_384"


def auroc(scores, y):
    scores, y = np.asarray(scores, float), np.asarray(y, int)
    order = np.argsort(scores, kind="mergesort")
    ranks = np.empty(len(scores), float)
    ranks[order] = np.arange(1, len(scores) + 1)
    p, n = int((y == 1).sum()), int((y == 0).sum())
    return float((ranks[y == 1].sum() - p * (p + 1) / 2) / (p * n)) if p and n else float("nan")


def main() -> int:
    base, fam, lab = [], [], []
    deltas = {p: [] for p in PROBES}
    with open("data/feature_cache/fitting-v2/rows.jsonl") as fh:
        for line in fh:
            r = json.loads(line)
            if r["dataset_split"] != "dev":
                continue
            e = (r.get("experts") or {}).get(EID) or {}
            if not e.get("ok"):
                continue
            ps = ((r.get("probes") or {}).get(EID) or {}).get("probe_scores") or {}
            if len(ps) != len(PROBES):
                continue
            b = float(e["p_fake"])
            base.append(b); fam.append(r.get("family") or "clean"); lab.append(r["label"])
            for p in PROBES:
                deltas[p].append(float(ps[p]) - b)

    base, fam, lab = np.array(base), np.array(fam), np.array(lab)
    D = {p: np.array(v) for p, v in deltas.items()}
    wrong = ((base >= 0.5).astype(int) != lab).astype(int)

    fams = ["clean", "jpeg", "noise", "blur", "color", "crop", "resize"]
    movement = {fm: {SHORT[p]: float(np.abs(D[p][fam == fm]).mean())
                     for p in PROBES} for fm in fams if (fam == fm).any()}
    corr = {SHORT[a]: {SHORT[b]: float(np.corrcoef(D[a], D[b])[0, 1]) for b in PROBES}
            for a in PROBES}
    single = {SHORT[p]: auroc(np.abs(D[p]), wrong) for p in PROBES}
    max3 = auroc(np.max([np.abs(D[p]) for p in PROBES], axis=0), wrong)
    drop = {}
    for p in PROBES:
        rest = [q for q in PROBES if q != p]
        drop[f"without_{SHORT[p]}"] = auroc(np.max([np.abs(D[q]) for q in rest], axis=0), wrong)

    doc = {
        "schema_version": "probe-signal-analysis.v1",
        "NOT_A_HEADLINE_RESULT": "dev split only, descriptive; the model-based ablation decides",
        "n_dev_rows": len(base),
        "mean_abs_delta_by_family": movement,
        "probe_delta_correlation": corr,
        "auroc_delta_predicts_primary_wrong": single,
        "auroc_max_of_all_three": max3,
        "auroc_leave_one_out": drop,
    }
    out = Path("results/probe-ablation/signal-analysis.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2) + "\n")

    print(f"dev rows with all 3 probes: {len(base)}\n")
    print("mean |delta| by family:")
    print(f"  {'family':<8}" + "".join(f"{SHORT[p]:>10}" for p in PROBES))
    for fm, row in movement.items():
        print(f"  {fm:<8}" + "".join(f"{row[SHORT[p]]:>10.4f}" for p in PROBES))
    print("\nprobe-delta correlation (redundancy check):")
    print(f"  {'':<10}" + "".join(f"{SHORT[p]:>10}" for p in PROBES))
    for a in PROBES:
        print(f"  {SHORT[a]:<10}" + "".join(f"{corr[SHORT[a]][SHORT[b]]:>10.3f}" for b in PROBES))
    print("\nAUROC(|delta| -> primary is wrong):")
    for p in PROBES:
        print(f"  {SHORT[p]:<8} {single[SHORT[p]]:.4f}")
    print(f"  {'max3':<8} {max3:.4f}")
    for k, v in drop.items():
        print(f"  {k:<14} {v:.4f}")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
