"""Format-canonicalization test — DIAGNOSTIC ONLY.

Every `real` source in the router corpus (`data/manifests/router_corpus_v2.json`)
is a JPEG file and every `fully_synthetic` source is a PNG file, both hidden
under a misleading `.jpg` extension (established separately, not re-derived
here). `quality_shortcut_audit.py` already showed `blockiness` alone reaches
AUROC 0.89 on cached clean rows because of this. The proposed fix is to
canonicalize every source to ONE container before feature extraction.

THE QUESTION this answers: does that fix actually remove the leak, and how
much genuine class separation survives afterwards?

Method: decode each sampled image to RGB pixels ONCE via the project's
canonical `decode_image`. From those same pixels build four variants that
differ only in container:

    A. native    - the file exactly as it sits on disk today (status quo)
    B. jpeg_q95  - re-encode the decoded pixels to JPEG quality 95
    C. jpeg_q75  - re-encode the decoded pixels to JPEG quality 75
    D. png       - re-encode the decoded pixels losslessly to PNG

B/C/D contain identical pre-encode pixels; only the container differs. Each
variant is round-tripped back through `decode_image` (so quality descriptors
see exactly what the rest of the pipeline would see) and scored with the
project's own `compute_quality` — no reimplementation of the descriptors.

Reuses the grouped source_id split / numpy-only logistic-regression /
rank-sum AUROC conventions from `scripts/diagnostics/quality_shortcut_audit.py`
(reimplemented here standalone; that file is untouched).

    .venv/bin/python scripts/diagnostics/format_canonicalization_test.py [seed]
"""

from __future__ import annotations

import io
import json
import sys
import time
from pathlib import Path

import numpy as np
import PIL.Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.pipeline.decode import DecodedImage, decode_image
from src.pipeline.quality import QualityDescriptors, compute_quality

MANIFEST = ROOT / "data" / "manifests" / "router_corpus_v2.json"
OUT = ROOT / "results" / "corpus" / "format_canonicalization_test.json"

N_PER_CLASS = 400
BLOCKINESS_THRESHOLD = 1.05

QUALITY_KEYS = (
    "blur_varlap", "blockiness", "noise_sigma", "luminance_mean",
    "luminance_std", "saturation_mean", "clipped_low_frac", "clipped_high_frac",
)

VARIANTS = ("native", "jpeg_q95", "jpeg_q75", "png")


# --------------------------------------------------------------------------
# Sampling
# --------------------------------------------------------------------------

def load_sample(seed: int) -> list[dict]:
    """Deterministically sample N_PER_CLASS reals and N_PER_CLASS fakes.

    Sampling is over the manifest rows (index order as written), shuffled by
    a seeded RNG and truncated — no reliance on dict/set iteration order.
    """
    manifest = json.loads(MANIFEST.read_text())
    images = manifest["images"]
    reals = [row for row in images if row["label"] == 0]
    fakes = [row for row in images if row["label"] == 1]

    rng = np.random.default_rng(seed)

    def pick(rows: list[dict]) -> list[dict]:
        idx = rng.permutation(len(rows))[:N_PER_CLASS]
        return [rows[i] for i in idx]

    return pick(reals) + pick(fakes)


# --------------------------------------------------------------------------
# Variant construction — same pixels in, only the container differs out
# --------------------------------------------------------------------------

def reencode(image: PIL.Image.Image, variant: str) -> bytes:
    buf = io.BytesIO()
    if variant == "jpeg_q95":
        image.save(buf, format="JPEG", quality=95)
    elif variant == "jpeg_q75":
        image.save(buf, format="JPEG", quality=75)
    elif variant == "png":
        image.save(buf, format="PNG")
    else:
        raise ValueError(f"unknown variant: {variant}")
    return buf.getvalue()


def quality_vector(q: QualityDescriptors) -> list[float]:
    return [float(getattr(q, key)) for key in QUALITY_KEYS]


def build_variant_rows(sample: list[dict]) -> dict[str, list[dict]]:
    """For each sampled source, decode once and derive all four variants.

    Returns {variant_name: [{"source_id", "label", "quality": [...]}, ...]}.
    """
    rows: dict[str, list[dict]] = {v: [] for v in VARIANTS}

    for row in sample:
        path = ROOT / row["relative_path"]
        native: DecodedImage = decode_image(path)
        native_quality = compute_quality(native)

        rows["native"].append({
            "source_id": row["source_id"],
            "label": int(row["label"]),
            "quality": quality_vector(native_quality),
        })

        for variant in ("jpeg_q95", "jpeg_q75", "png"):
            encoded = reencode(native.image, variant)
            redecoded = decode_image(encoded)
            q = compute_quality(redecoded)
            rows[variant].append({
                "source_id": row["source_id"],
                "label": int(row["label"]),
                "quality": quality_vector(q),
            })

    return rows


# --------------------------------------------------------------------------
# Stats: AUROC (rank-sum), grouped logistic regression — numpy only
# --------------------------------------------------------------------------

def auroc(scores: np.ndarray, labels: np.ndarray) -> float:
    """AUROC by rank-sum (Mann-Whitney U), ties averaged."""
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


def signed_auroc(values: np.ndarray, labels: np.ndarray) -> tuple[float, str]:
    """AUROC of a single descriptor treated as a fake-positive score.

    Reports max(a, 1-a) and the direction that achieves it (fake = positive
    class per the task spec): "higher=fake" if raw values rank fakes higher,
    "higher=real" if the reverse orientation is needed to reach the max.
    """
    a = auroc(values, labels)
    if np.isnan(a):
        return float("nan"), "undefined"
    if a >= 1.0 - a:
        return float(a), "higher=fake"
    return float(1.0 - a), "higher=real"


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

    Standardization statistics come from the TRAIN matrix only.
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


def apply_model(model, x: np.ndarray) -> np.ndarray:
    mu, sd, w = model
    return np.hstack([(x - mu) / sd, np.ones((len(x), 1))]) @ w


def logistic_auroc(rows: list[dict], seed: int) -> dict:
    train, dev = grouped_split(rows, seed)
    x_train = np.asarray([r["quality"] for r in train], dtype=np.float64)
    y_train = np.array([r["label"] for r in train], dtype=np.float64)
    x_dev = np.asarray([r["quality"] for r in dev], dtype=np.float64)
    y_dev = np.array([r["label"] for r in dev], dtype=np.float64)

    model = fit_logistic(x_train, y_train)
    dev_scores = apply_model(model, x_dev)
    return {
        "n_train": len(train),
        "n_dev": len(dev),
        "n_features": x_train.shape[1],
        "dev_auroc": auroc(dev_scores, y_dev),
    }


def per_feature_auroc(rows: list[dict]) -> dict:
    x = np.asarray([r["quality"] for r in rows], dtype=np.float64)
    y = np.array([r["label"] for r in rows], dtype=np.float64)
    out = {}
    for i, key in enumerate(QUALITY_KEYS):
        a, direction = signed_auroc(x[:, i], y)
        out[key] = {"auroc": a, "direction": direction}
    return out


def blockiness_class_stats(rows: list[dict]) -> dict:
    idx = QUALITY_KEYS.index("blockiness")
    x = np.asarray([r["quality"][idx] for r in rows], dtype=np.float64)
    y = np.array([r["label"] for r in rows], dtype=np.float64)
    real = x[y == 0]
    fake = x[y == 1]
    return {
        "real_mean": float(real.mean()), "real_std": float(real.std()),
        "fake_mean": float(fake.mean()), "fake_std": float(fake.std()),
        "real_frac_above_1.05": float(np.mean(real > BLOCKINESS_THRESHOLD)),
        "fake_frac_above_1.05": float(np.mean(fake > BLOCKINESS_THRESHOLD)),
    }


# --------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------

def interpret(native_quality_auroc: float, canon_quality_aurocs: dict[str, float]) -> str:
    canon_values = list(canon_quality_aurocs.values())
    canon_max = max(canon_values)
    canon_min = min(canon_values)
    parts = [
        f"native quality-only dev AUROC = {native_quality_auroc:.4f}.",
        ("canonicalized (jpeg_q95/jpeg_q75/png) quality-only dev AUROC in "
         f"[{canon_min:.4f}, {canon_max:.4f}]."),
    ]
    if canon_max >= 0.85:
        parts.append(
            "Canonicalization does NOT remove the leak: quality-only AUROC stays "
            "high under a shared container, so the separation is not purely a "
            "format artifact and the proposed fix is INSUFFICIENT on its own."
        )
    elif canon_max <= 0.65:
        parts.append(
            "Canonicalization removes the bulk of the leak: quality-only AUROC "
            "drops to near-chance under a shared container, consistent with the "
            "original signal being mostly format, not AI-generation evidence."
        )
    else:
        parts.append(
            "Canonicalization removes PART of the leak but a moderate residual "
            f"AUROC (~{canon_max:.4f}) remains: some genuine, non-format class "
            "separation survives, but it should be reported as that residual "
            "number, not conflated with the original near-perfect result."
        )
    return " ".join(parts)


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main(seed: int = 0) -> None:
    t0 = time.time()
    sample = load_sample(seed)
    n_real = sum(1 for r in sample if r["label"] == 0)
    n_fake = sum(1 for r in sample if r["label"] == 1)
    print(f"sampled {len(sample)} sources (real={n_real}, fake={n_fake}), seed={seed}")

    variant_rows = build_variant_rows(sample)
    print(f"decoded + re-encoded all variants in {time.time() - t0:.1f}s")

    per_variant: dict[str, dict] = {}
    for variant in VARIANTS:
        rows = variant_rows[variant]
        feature_aurocs = per_feature_auroc(rows)
        logistic = logistic_auroc(rows, seed)
        blockiness_stats = blockiness_class_stats(rows)

        per_variant[variant] = {
            "n_rows": len(rows),
            "blockiness_auroc": feature_aurocs["blockiness"]["auroc"],
            "blockiness_auroc_direction": feature_aurocs["blockiness"]["direction"],
            "per_descriptor_auroc": feature_aurocs,
            "logistic_all_descriptors": logistic,
            "blockiness_class_stats": blockiness_stats,
        }

        print(f"[{variant:9s}] blockiness AUROC={feature_aurocs['blockiness']['auroc']:.4f} "
              f"({feature_aurocs['blockiness']['direction']})  "
              f"logistic-all dev AUROC={logistic['dev_auroc']:.4f}  "
              f"real_frac>1.05={blockiness_stats['real_frac_above_1.05']:.3f}  "
              f"fake_frac>1.05={blockiness_stats['fake_frac_above_1.05']:.3f}")

    native_quality_auroc = per_variant["native"]["logistic_all_descriptors"]["dev_auroc"]
    canon_quality_aurocs = {
        v: per_variant[v]["logistic_all_descriptors"]["dev_auroc"]
        for v in ("jpeg_q95", "jpeg_q75", "png")
    }
    reading = interpret(native_quality_auroc, canon_quality_aurocs)

    result = {
        "manifest": str(MANIFEST.relative_to(ROOT)),
        "seed": seed,
        "n_per_class_requested": N_PER_CLASS,
        "n_real_sampled": n_real,
        "n_fake_sampled": n_fake,
        "quality_keys": list(QUALITY_KEYS),
        "blockiness_threshold": BLOCKINESS_THRESHOLD,
        "variants": per_variant,
        "reading": reading,
        "elapsed_seconds": time.time() - t0,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2))

    print(f"\nreading: {reading}")
    print(f"\nwrote {OUT}")
    print(f"total elapsed {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 0)
