"""Fit the degradation reporter: quality descriptors -> which transform family.

The system can already say "AI-generated, low reliability". It cannot say WHY.
This closes that: every image carries eight cheap quality measurements, and the
feature cache labels every row with the transformation actually applied, so
"what was done to this image" is a supervised problem we can score rather than
assert.

DELIBERATELY EXCLUDES GEOMETRY. Width, height and megapixels would make crop and
resize almost trivially separable -- but only because we know the original
dimensions, which we do not for a real upload. Training on them would buy
accuracy that evaporates in deployment. Eight descriptors only.

Fitted on the fitting-cache TRAIN split, reported on DEV. Nothing here touches
the classifier, the threshold, or any evaluation surface.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch
from torch import nn

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.pipeline.quality import QualityDescriptors  # noqa: F401  (schema anchor)
from src.router.features import QUALITY_KEYS
from src.router.train import load_cache_rows

FAMILIES = ("clean", "jpeg", "noise", "blur", "color", "crop", "resize")


def featurize(rows: list[dict]) -> np.ndarray:
    """(value, is_present) per descriptor — the same missing-value discipline
    the router uses. Never impute."""
    out = np.zeros((len(rows), len(QUALITY_KEYS) * 2), dtype=np.float64)
    for i, r in enumerate(rows):
        q = r.get("quality") or {}
        for j, key in enumerate(QUALITY_KEYS):
            v = q.get(key)
            if v is None or not np.isfinite(float(v)):
                continue
            out[i, 2 * j] = float(v)
            out[i, 2 * j + 1] = 1.0
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cache", type=Path, default=Path("data/feature_cache/fitting-v2"))
    ap.add_argument("--out", type=Path,
                    default=Path("results/degradation/classifier.pt"))
    ap.add_argument("--report", type=Path,
                    default=Path("results/degradation/dev-report.json"))
    ap.add_argument("--epochs", type=int, default=600)
    ap.add_argument("--lr", type=float, default=0.05)
    ap.add_argument("--seed", type=int, default=20260828)
    args = ap.parse_args()

    torch.manual_seed(args.seed)
    rows = load_cache_rows(args.cache / "rows.jsonl")
    train = [r for r in rows if r["dataset_split"] == "train"]
    dev = [r for r in rows if r["dataset_split"] == "dev"]
    idx = {f: i for i, f in enumerate(FAMILIES)}

    def xy(rs):
        x = featurize(rs)
        y = np.array([idx[r.get("family") or "clean"] for r in rs])
        return x, y

    xtr, ytr = xy(train)
    xdv, ydv = xy(dev)
    mean, scale = xtr.mean(axis=0), xtr.std(axis=0)
    scale[scale < 1e-8] = 1.0
    # indicator columns keep their 0/1 meaning
    for j in range(len(QUALITY_KEYS)):
        mean[2 * j + 1], scale[2 * j + 1] = 0.0, 1.0
    xtr_n = torch.tensor((xtr - mean) / scale, dtype=torch.float32)
    xdv_n = torch.tensor((xdv - mean) / scale, dtype=torch.float32)
    ttr = torch.tensor(ytr, dtype=torch.long)

    model = nn.Sequential(nn.Linear(xtr.shape[1], 32), nn.ReLU(), nn.Linear(32, len(FAMILIES)))
    opt = torch.optim.Adam(model.parameters(), lr=args.lr)
    # The grid is imbalanced by construction (18,000 colour rows against 3,000
    # clean), so an unweighted fit simply predicts the frequent families and
    # reports 0.00 recall on `clean`. Weighting by inverse frequency separates
    # "these classes are inseparable from these descriptors" -- a real finding --
    # from "one class was outnumbered six to one", which is an artefact.
    counts = np.bincount(ytr, minlength=len(FAMILIES)).astype(np.float64)
    weights = torch.tensor(counts.sum() / (len(FAMILIES) * np.maximum(counts, 1)),
                           dtype=torch.float32)
    print("class weights: " + "  ".join(f"{f}={w:.2f}" for f, w in zip(FAMILIES, weights)),
          file=sys.stderr)
    lossf = nn.CrossEntropyLoss(weight=weights)
    print(f"train={len(train)} dev={len(dev)} features={xtr.shape[1]}", file=sys.stderr)
    for ep in range(args.epochs):
        model.train(); opt.zero_grad()
        loss = lossf(model(xtr_n), ttr)
        loss.backward(); opt.step()
        if (ep + 1) % (args.epochs // 6) == 0:
            print(f"  epoch {ep+1:4d}  loss {float(loss.detach()):.4f}", file=sys.stderr)

    model.eval()
    with torch.no_grad():
        pred = model(xdv_n).argmax(dim=1).numpy()
    acc = float((pred == ydv).mean())
    balanced = float(np.mean([(pred[ydv == i] == i).mean()
                              for i in range(len(FAMILIES)) if (ydv == i).any()]))
    per_class, confusion = {}, {}
    for f, i in idx.items():
        m = ydv == i
        if not m.any():
            continue
        per_class[f] = {"n": int(m.sum()), "recall": round(float((pred[m] == i).mean()), 4)}
        confusion[f] = {g: int((pred[m] == idx[g]).sum()) for g in FAMILIES}

    n_params = sum(p.numel() for p in model.parameters())
    print(f"\ndev accuracy {acc:.4f}   balanced accuracy {balanced:.4f}   "
          f"(chance {1/len(FAMILIES):.3f})   params {n_params}", file=sys.stderr)
    print(f"{'family':<8}{'n':>7}{'recall':>9}   most-confused-with", file=sys.stderr)
    for f, v in per_class.items():
        row = {g: c for g, c in confusion[f].items() if g != f}
        top = max(row, key=row.get) if row else "-"
        print(f"{f:<8}{v['n']:>7}{v['recall']:>9.4f}   {top} ({row.get(top,0)})", file=sys.stderr)

    torch.save({"schema_version": "degradation-classifier.v1", "families": list(FAMILIES),
                "quality_keys": list(QUALITY_KEYS), "geometry_excluded": True,
                "mean": mean, "scale": scale, "state_dict": model.state_dict(),
                "n_parameters": n_params, "dev_accuracy": acc,
                "dev_balanced_accuracy": balanced, "seed": args.seed},
               args.out.parent.mkdir(parents=True, exist_ok=True) or args.out)
    args.report.write_text(json.dumps({
        "schema_version": "degradation-report.v1",
        "NOT_A_HEADLINE_RESULT": "dev split only; explains the verdict, never sets it",
        "geometry_excluded": True,
        "geometry_note": "width/height/megapixels would make crop and resize easy, but a "
                         "real upload has no known original dimensions, so that accuracy "
                         "would not survive deployment",
        "dev_accuracy": acc, "dev_balanced_accuracy": balanced,
        "chance": 1 / len(FAMILIES), "n_parameters": n_params,
        "class_weighted": True,
        "per_class": per_class, "confusion": confusion,
    }, indent=2) + "\n")
    print(f"\nwrote {args.out} and {args.report}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
