"""DegradePrint cheap validation (update-pack doc 10 §11) — DIAGNOSTIC ONLY.

Answers the one question the post-LOTA update pack rests on: does a
transformation-RESPONSE signature (per-probe delta logits, probe spread) carry
forensic signal BEYOND the primary logit and the direct image-quality
descriptors we already compute?

Four arms, one grouped split by `source_id`, one identical threshold rule
(train-fitted clean FPR = 5%), so the arms differ only in feature set:

    A  primary logit only
    B  primary + quality descriptors
    C  primary + quality + response signature   (DegradePrint)
    D  primary + response signature             (no quality)

B vs C is the honest test: doc 10 §18 names "response features may mostly
encode severity rather than authenticity" as the idea's main risk, and quality
descriptors measure severity directly. D isolates how much severity the probes
recover on their own.

NOT A HEADLINE RESULT: runs on the UNPROTECTED 1,200-source pilot cache with a
regularized logistic regression. It steers design; it never reports a score.

    .venv/bin/python scripts/diagnostics/degradeprint_probe.py [seed]
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

ROWS = Path("data/feature_cache/pilot-v1/rows.jsonl")
EXPERT = "commfor_384"
PROBES = ("probe_jpeg_q92", "probe_crop_0.96", "probe_resize_0.90")
QUALITY_KEYS = ("blur_varlap", "blockiness", "noise_sigma", "luminance_mean",
                "luminance_std", "saturation_mean", "clipped_low_frac",
                "clipped_high_frac")
FAMILIES = ("jpeg", "blur", "resize", "noise", "color", "crop")
CLEAN_FPR_TARGET = 0.05


def _logit(p: float) -> float:
    p = min(max(float(p), 1e-6), 1.0 - 1e-6)
    return math.log(p / (1.0 - p))


def load_rows(path: Path) -> list[dict]:
    """Cache rows -> (base logit, quality vector, response vector) per view.

    Rows whose expert or probe set is incomplete are DROPPED, never imputed:
    a partially-probed view has no response signature to measure.
    """
    out: list[dict] = []
    with path.open() as fh:
        for line in fh:
            row = json.loads(line)
            expert = row["experts"][EXPERT]
            probe = row["probes"][EXPERT]
            if not expert["ok"] or probe["n_probes_ok"] != len(PROBES):
                continue
            base = float(expert["raw_logit"])
            deltas = [_logit(probe["probe_scores"][p]) - base for p in PROBES]
            response = deltas + [
                float(np.mean(deltas)), float(np.std(deltas)),
                float(np.max(np.abs(deltas))), float(max(deltas) - min(deltas)),
                float(probe["probe_std"]), float(probe["probe_range"]),
                float(probe["probe_max_delta"]),
                float(probe["probe_mean"]) - float(expert["p_fake"]),
            ]
            out.append({
                "source_id": row["source_id"], "label": int(row["label"]),
                "family": row["family"], "base": base,
                "quality": [float(row["quality"][k]) for k in QUALITY_KEYS],
                "response": response,
            })
    return out


def design(rows: list[dict], arm: str) -> np.ndarray:
    cols = []
    for r in rows:
        vec = [r["base"]]
        if arm in ("B", "C"):
            vec += r["quality"]
        if arm in ("C", "D"):
            vec += r["response"]
        cols.append(vec)
    return np.asarray(cols, dtype=np.float64)


def fit_logistic(x: np.ndarray, y: np.ndarray, l2: float = 1.0, iters: int = 400):
    """L2-regularized logistic regression by IRLS. Intercept is unpenalized.

    Standardization statistics come from the TRAIN matrix only and travel with
    the model, so scoring dev cannot leak dev moments back into the fit.
    """
    mu, sd = x.mean(0), x.std(0)
    sd[sd == 0] = 1.0
    z = np.hstack([(x - mu) / sd, np.ones((len(x), 1))])
    penalty = np.r_[np.ones(z.shape[1] - 1), 0.0]
    w = np.zeros(z.shape[1])
    for _ in range(iters):
        p = np.clip(1.0 / (1.0 + np.exp(-z @ w)), 1e-9, 1 - 1e-9)
        grad = z.T @ (p - y) + l2 * (penalty * w)
        hess = (z * (p * (1 - p))[:, None]).T @ z + l2 * np.diag(penalty)
        w -= np.linalg.solve(hess + 1e-8 * np.eye(len(w)), grad)
    return mu, sd, w


def score(model, x: np.ndarray) -> np.ndarray:
    mu, sd, w = model
    return np.hstack([(x - mu) / sd, np.ones((len(x), 1))]) @ w


def clean_fpr_threshold(scores: np.ndarray, rows: list[dict], target: float) -> float:
    """Threshold at a fixed clean-image FPR, fitted on TRAIN.

    Every arm is held to the same real-image cost, so worst-family recall is
    comparable across arms rather than reflecting a friendlier operating point.
    """
    negatives = np.array([s for s, r in zip(scores, rows)
                          if r["label"] == 0 and r["family"] == "clean"])
    return float(np.quantile(negatives, 1.0 - target)) if len(negatives) else 0.0


def main(seed: int = 0) -> None:
    rows = load_rows(ROWS)
    sources = sorted({r["source_id"] for r in rows})
    rng = np.random.default_rng(seed)
    rng.shuffle(sources)
    dev_sources = set(sources[: len(sources) // 4])

    train = [r for r in rows if r["source_id"] not in dev_sources]
    dev = [r for r in rows if r["source_id"] in dev_sources]
    y_train = np.array([r["label"] for r in train], dtype=np.float64)

    print(f"rows {len(rows)} · sources {len(sources)} "
          f"(train {len(sources) - len(dev_sources)} / dev {len(dev_sources)}) · seed {seed}")
    print(f"{'arm':<4}{'feats':>6}{'worst':>8}{'recall':>9}{'cleanRec':>10}{'cleanFPR':>10}   per-family fake recall")

    worst: dict[str, float] = {}
    for arm in ("A", "B", "C", "D"):
        x_train = design(train, arm)
        model = fit_logistic(x_train, y_train)
        threshold = clean_fpr_threshold(score(model, x_train), train, CLEAN_FPR_TARGET)
        dev_scores = score(model, design(dev, arm))

        recall = {}
        for family in FAMILIES + ("clean",):
            idx = [i for i, r in enumerate(dev) if r["family"] == family and r["label"] == 1]
            recall[family] = float(np.mean(dev_scores[idx] >= threshold)) if idx else float("nan")
        clean_neg = [i for i, r in enumerate(dev) if r["family"] == "clean" and r["label"] == 0]
        fpr = float(np.mean(dev_scores[clean_neg] >= threshold))

        worst_family = min(FAMILIES, key=lambda f: recall[f])
        worst[arm] = recall[worst_family]
        print(f"{arm:<4}{x_train.shape[1]:>6}{worst_family:>8}{recall[worst_family]:>9.4f}"
              f"{recall['clean']:>10.4f}{fpr:>10.4f}   "
              + " ".join(f"{f}={recall[f]:.3f}" for f in FAMILIES))

    print(f"\nworst-family fake recall: A={worst['A']:.4f} B={worst['B']:.4f} "
          f"C={worst['C']:.4f} D={worst['D']:.4f}")
    print(f"  quality over primary        (B-A) = {worst['B'] - worst['A']:+.4f}")
    print(f"  response over primary       (D-A) = {worst['D'] - worst['A']:+.4f}")
    print(f"  response over quality       (C-B) = {worst['C'] - worst['B']:+.4f}   <-- doc 10 §12 kill test (needs ~+0.02)")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 0)
