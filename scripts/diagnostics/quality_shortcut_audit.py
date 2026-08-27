"""Quality-descriptor format-shortcut audit — DIAGNOSTIC ONLY.

Every "real" source in the router corpus is a JPEG and every "fully_synthetic"
source is a PNG, all written under a misleading `.jpg` extension (established
separately; not re-derived here). JPEG compression leaves 8x8 block artifacts
that our quality descriptors (`blockiness`, `noise_sigma`, `blur_varlap`, ...)
directly measure. This script asks how much of the headline "quality
descriptors improved worst-family fake recall +39.3 points" result is really
just those descriptors reading file format off of `clean` (untransformed)
rows, rather than anything about AI generation.

Restricted to `condition_id == "clean"` rows only: that is where an
undisturbed format shortcut would show up most cleanly (every other condition
re-encodes/re-processes the image and can blur the format signal).

Reuses the cache-loading conventions and grouped source_id split from
`scripts/diagnostics/degradeprint_probe.py`: group split by `source_id`,
train-fitted standardization, numpy-only logistic regression (no sklearn).

    .venv/bin/python scripts/diagnostics/quality_shortcut_audit.py [seed]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROWS = Path("data/feature_cache/pilot-v1/rows.jsonl")
OUT = Path("results/corpus/quality_shortcut_audit.json")
EXPERT = "commfor_384"
QUALITY_KEYS = (
    "blur_varlap", "blockiness", "noise_sigma", "luminance_mean",
    "luminance_std", "saturation_mean", "clipped_low_frac", "clipped_high_frac",
)


def load_clean_rows(path: Path) -> list[dict]:
    """Load only condition_id == 'clean' rows, keeping quality + expert p_fake.

    Mirrors degradeprint_probe.load_rows: rows with an incomplete/failed
    expert block are dropped, never imputed.
    """
    out: list[dict] = []
    with path.open() as fh:
        for line in fh:
            row = json.loads(line)
            if row["condition_id"] != "clean":
                continue
            expert = row["experts"][EXPERT]
            if not expert["ok"]:
                continue
            out.append({
                "source_id": row["source_id"],
                "label": int(row["label"]),
                "quality": [float(row["quality"][k]) for k in QUALITY_KEYS],
                "p_fake": float(expert["p_fake"]),
            })
    return out


def grouped_split(rows: list[dict], seed: int) -> tuple[list[dict], list[dict]]:
    sources = sorted({r["source_id"] for r in rows})
    rng = np.random.default_rng(seed)
    rng.shuffle(sources)
    dev_sources = set(sources[: len(sources) // 4])
    train = [r for r in rows if r["source_id"] not in dev_sources]
    dev = [r for r in rows if r["source_id"] in dev_sources]
    return train, dev


def fit_logistic(x: np.ndarray, y: np.ndarray, l2: float = 1.0, iters: int = 400):
    """L2-regularized logistic regression by Newton/IRLS (intercept unpenalized).

    Standardization statistics come from the TRAIN matrix only, matching
    degradeprint_probe.fit_logistic exactly so dev cannot leak into the fit.
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


def auroc(scores: np.ndarray, labels: np.ndarray) -> float:
    """AUROC by rank-sum (Mann-Whitney U), ties averaged via scipy-free ranking."""
    order = np.argsort(scores, kind="mergesort")
    ranks = np.empty(len(scores), dtype=np.float64)
    sorted_scores = scores[order]
    i = 0
    n = len(scores)
    while i < n:
        j = i
        while j + 1 < n and sorted_scores[j + 1] == sorted_scores[i]:
            j += 1
        avg_rank = (i + j) / 2.0 + 1.0
        ranks[order[i:j + 1]] = avg_rank
        i = j + 1
    n_pos = float(np.sum(labels == 1))
    n_neg = float(np.sum(labels == 0))
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    sum_ranks_pos = float(np.sum(ranks[labels == 1]))
    u = sum_ranks_pos - n_pos * (n_pos + 1) / 2.0
    return u / (n_pos * n_neg)


def accuracy_at_train_threshold(train_scores: np.ndarray, train_y: np.ndarray,
                                 dev_scores: np.ndarray, dev_y: np.ndarray) -> float:
    """Threshold fitted on TRAIN (best-accuracy cut over train scores), scored on dev."""
    order = np.argsort(train_scores)
    candidates = train_scores[order]
    best_t, best_acc = candidates[0] - 1.0, -1.0
    for t in candidates:
        acc = float(np.mean((train_scores >= t) == train_y.astype(bool)))
        if acc > best_acc:
            best_acc, best_t = acc, t
    return float(np.mean((dev_scores >= best_t) == dev_y.astype(bool)))


def fit_and_eval(train: list[dict], dev: list[dict], feature_key: str,
                  indices: list[int] | None = None) -> dict:
    def build(rows: list[dict]) -> np.ndarray:
        if feature_key == "quality":
            vecs = [r["quality"] for r in rows]
            if indices is not None:
                vecs = [[v[i] for i in indices] for v in vecs]
            return np.asarray(vecs, dtype=np.float64)
        return np.asarray([[r["p_fake"]] for r in rows], dtype=np.float64)

    x_train = build(train)
    x_dev = build(dev)
    y_train = np.array([r["label"] for r in train], dtype=np.float64)
    y_dev = np.array([r["label"] for r in dev], dtype=np.float64)

    model = fit_logistic(x_train, y_train)
    train_scores = score(model, x_train)
    dev_scores = score(model, x_dev)

    return {
        "n_train": len(train),
        "n_dev": len(dev),
        "n_features": x_train.shape[1],
        "dev_auroc": auroc(dev_scores, y_dev),
        "dev_accuracy_train_threshold": accuracy_at_train_threshold(
            train_scores, y_train, dev_scores, y_dev),
    }


def class_stats(rows: list[dict]) -> dict:
    x = np.asarray([r["quality"] for r in rows], dtype=np.float64)
    y = np.array([r["label"] for r in rows], dtype=np.float64)
    pooled_std = x.std(0)
    pooled_std[pooled_std == 0] = 1.0

    per_feature = []
    for i, key in enumerate(QUALITY_KEYS):
        real = x[y == 0, i]
        fake = x[y == 1, i]
        mean_diff = float(fake.mean() - real.mean())
        std_mean_diff = mean_diff / float(pooled_std[i])
        per_feature.append({
            "feature": key,
            "real_mean": float(real.mean()),
            "real_std": float(real.std()),
            "fake_mean": float(fake.mean()),
            "fake_std": float(fake.std()),
            "abs_standardized_mean_diff": abs(std_mean_diff),
            "standardized_mean_diff": std_mean_diff,
        })
    per_feature.sort(key=lambda d: d["abs_standardized_mean_diff"], reverse=True)
    return {"n_real": int(np.sum(y == 0)), "n_fake": int(np.sum(y == 1)),
            "per_feature": per_feature}


def p_fake_stats(rows: list[dict]) -> dict:
    y = np.array([r["label"] for r in rows], dtype=np.float64)
    p = np.array([r["p_fake"] for r in rows], dtype=np.float64)
    real = p[y == 0]
    fake = p[y == 1]
    pooled_std = p.std()
    pooled_std = pooled_std if pooled_std != 0 else 1.0
    return {
        "real_mean": float(real.mean()), "real_std": float(real.std()),
        "fake_mean": float(fake.mean()), "fake_std": float(fake.std()),
        "abs_standardized_mean_diff": abs(float(fake.mean() - real.mean()) / pooled_std),
    }


def interpret(quality_auroc: float) -> str:
    if quality_auroc >= 0.97:
        return (
            f"quality-only dev AUROC = {quality_auroc:.4f} is near 1.0 on clean rows: "
            "the +39.3 point quality-descriptor result is confounded by file format "
            "(JPEG-real vs PNG-fake) and cannot be reported as evidence about "
            "AI-image detection without controlling for format."
        )
    if quality_auroc <= 0.55:
        return (
            f"quality-only dev AUROC = {quality_auroc:.4f} is near 0.5 on clean rows: "
            "quality descriptors are not carrying the format signal here, and the "
            "original +39.3 point result survives this particular challenge."
        )
    return (
        f"quality-only dev AUROC = {quality_auroc:.4f} on clean rows is between chance "
        "and near-perfect: this is partial confounding. Some, but not all, of the "
        "quality-descriptor benefit is plausibly explained by file format rather than "
        "AI-generation signal; the headline result should be reported with this caveat, "
        "not as clean evidence either way."
    )


def main(seed: int = 0) -> None:
    rows = load_clean_rows(ROWS)
    train, dev = grouped_split(rows, seed)

    quality_result = fit_and_eval(train, dev, "quality")
    blockiness_idx = QUALITY_KEYS.index("blockiness")
    blockiness_result = fit_and_eval(train, dev, "quality", indices=[blockiness_idx])
    p_fake_result = fit_and_eval(train, dev, "p_fake")

    quality_class_stats = class_stats(rows)
    p_fake_class_stats = p_fake_stats(rows)

    result = {
        "cache_file": str(ROWS),
        "cache_row_count_total": sum(1 for _ in ROWS.open()),
        "clean_row_count": len(rows),
        "seed": seed,
        "split": {"n_train": len(train), "n_dev": len(dev),
                   "n_sources": len({r["source_id"] for r in rows})},
        "quality_only_logistic": quality_result,
        "blockiness_only_logistic": blockiness_result,
        "p_fake_only_logistic_reference": p_fake_result,
        "quality_descriptor_class_stats": quality_class_stats,
        "p_fake_class_stats_reference": p_fake_class_stats,
        "reading": interpret(quality_result["dev_auroc"]),
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2))

    print(f"clean rows {len(rows)} (train {len(train)} / dev {len(dev)}) · seed {seed}")
    print(f"quality-only    dev AUROC={quality_result['dev_auroc']:.4f}  "
          f"acc={quality_result['dev_accuracy_train_threshold']:.4f}  "
          f"n_feat={quality_result['n_features']}")
    print(f"blockiness-only dev AUROC={blockiness_result['dev_auroc']:.4f}  "
          f"acc={blockiness_result['dev_accuracy_train_threshold']:.4f}")
    print(f"p_fake-only     dev AUROC={p_fake_result['dev_auroc']:.4f}  "
          f"acc={p_fake_result['dev_accuracy_train_threshold']:.4f}  (reference)")
    print("\ntop quality descriptors by |standardized mean diff| (real vs fake):")
    for feat in quality_class_stats["per_feature"]:
        print(f"  {feat['feature']:<18} |smd|={feat['abs_standardized_mean_diff']:.3f}  "
              f"real={feat['real_mean']:.5g}±{feat['real_std']:.5g}  "
              f"fake={feat['fake_mean']:.5g}±{feat['fake_std']:.5g}")
    print(f"\np_fake reference |smd|={p_fake_class_stats['abs_standardized_mean_diff']:.3f}  "
          f"real={p_fake_class_stats['real_mean']:.5g}±{p_fake_class_stats['real_std']:.5g}  "
          f"fake={p_fake_class_stats['fake_mean']:.5g}±{p_fake_class_stats['fake_std']:.5g}")
    print(f"\nreading: {result['reading']}")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 0)
