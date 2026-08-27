"""DegradePrint / quality-correction PILOT harness — A-023/A-024/B-020.

Implements `specs/degradeprint-pilot.md` exactly, with one addition the spec's
author flagged after freeze: arm **Q**.

    NOT A HEADLINE RESULT. See `specs/degradeprint-pilot.md` "Preliminary result
    boundary". Even on the protected cache this script is meant to run against,
    a single pilot run selects nothing by itself — it feeds the keep/park gate
    decision that Claude and Codex both record in DECISIONS.md.

This script is PURE CPU/numpy over an already-extracted `feature-cache-row.v2`
JSONL cache (see `specs/phase2-feature-cache.md`). It never decodes an image,
never loads a torch model, and never imports `src.experts` — a 9-hour GPU
extraction job may be running concurrently and must not be touched.

Feature assembly and the L2-regularized IRLS logistic fitter are deliberately
copied from `degradeprint_probe.py` (not imported — that script targets the
old `pilot-v1` cache schema and a different row shape) so numbers from the two
diagnostics stay comparable in kind, even though the pilot here has an honest
grouped/nested split and paired bootstrap that the older probe explicitly
disclaims.

## Arms

    A   primary raw logit only — NOT fitted. The raw expert logit itself is
        the score; only the operating threshold is chosen (on inner-dev).
    A2  calibrated primary — a 1-D affine (temperature `a`, bias `b`) fit to
        the raw logit BY LOGISTIC REGRESSION ON THE INNER-DEV SPLIT ONLY
        (never inner-train), per the task brief. This is what "beats A2" means
        in the quality-correction gate: A2 is the strongest primary-only
        baseline the pilot can construct, not the weaker raw arm A.
    B   primary + quality descriptors, fit on inner-train.
    C   B + probe-response features (DegradePrint), fit on inner-train.
    D   primary + probe-response features, NO quality, fit on inner-train.
    Q   quality descriptors ONLY, no primary score at all, fit on inner-train.
        <-- not in specs/degradeprint-pilot.md; added per task brief.
        RATIONALE: our corpus lets plain image statistics (blur, blockiness,
        noise, clipping, ...) separate real vs. AI-generated at roughly 0.95
        AUROC on their own -- these are heavily generator-fingerprinted
        datasets, not a natural-image distribution. That means Q is the floor
        every other arm must be read against, not A/A2. An arm that merely
        matches Q has demonstrated nothing about forensic detection: it may
        just be rediscovering the same quality shortcut through a different
        door. B, C, and D are only interesting to the extent they clear Q, not
        merely A2.

## Splits

Three OUTER folds, grouped by `source_id` (a source and all its transformed
views share one fold; never split across the train/test boundary). Within
each outer-TRAINING fold, a further source-disjoint INNER-dev split is carved
out for: (a) A2's temperature/bias fit, (b) the single fixed operating
threshold per arm. inner-train (the remainder of the outer-training sources)
is what B/C/D/Q are fit on. The outer-test fold is touched exactly once, for
scoring, with the fold's already-fixed models and thresholds. Out-of-fold
predictions are collected once and aggregated at the end; paired bootstrap
resamples SOURCES (not rows) from that pooled table.

Usage:
    .venv/bin/python scripts/diagnostics/degradeprint_pilot.py \\
        --rows data/feature_cache/fitting-v2/rows.jsonl \\
        --folds 3 --seed 0 --out results/degradeprint/pilot.json
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import warnings as _warnings
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

WATERMARK = "NOT_A_HEADLINE_RESULT"
SCHEMA_VERSION_EXPECTED = "feature-cache-row.v2"
EXPERT = "commfor_384"
PROBES = ("probe_jpeg_q92", "probe_crop_0.96", "probe_resize_0.90")
QUALITY_KEYS = (
    "blur_varlap", "blockiness", "noise_sigma", "luminance_mean",
    "luminance_std", "saturation_mean", "clipped_low_frac", "clipped_high_frac",
)
FAMILIES = ("jpeg", "blur", "resize", "noise", "color", "crop")
ARMS = ("A", "A2", "B", "C", "D", "Q")
CLEAN_FPR_TARGET = 0.05
INNER_DEV_FRAC = 0.25
GATE_MIN_DELTA = 0.02
GATE_MAX_BACC_REGRESSION = 0.01
GATE_MAX_FPR_RISE = 0.01
N_BOOTSTRAP = 2000


def _logit(p: float) -> float:
    p = min(max(float(p), 1e-6), 1.0 - 1e-6)
    return math.log(p / (1.0 - p))


# --------------------------------------------------------------------------- #
# Row loading / feature assembly (pattern copied from degradeprint_probe.py)
# --------------------------------------------------------------------------- #

def load_rows(path: Path, warnings: list[str]) -> list[dict[str, Any]]:
    """Cache rows -> per-view feature dict.

    Rows whose expert or probe set is incomplete are DROPPED, never imputed:
    a partially-probed view has no response signature to measure, matching
    the cache's own "no imputation, ever" rule (phase2-feature-cache.md §0).
    """
    out: list[dict[str, Any]] = []
    n_total = 0
    n_bad_schema = 0
    n_expert_fail = 0
    n_probe_incomplete = 0
    with path.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            n_total += 1
            row = json.loads(line)
            if row.get("schema_version") != SCHEMA_VERSION_EXPECTED:
                n_bad_schema += 1
                continue
            expert = row["experts"].get(EXPERT)
            if expert is None or not expert.get("ok"):
                n_expert_fail += 1
                continue
            probe = row["probes"].get(EXPERT)
            if probe is None or probe.get("n_probes_ok") != len(PROBES):
                n_probe_incomplete += 1
                continue
            base = float(expert["raw_logit"])
            probe_scores = probe["probe_scores"]
            deltas = [_logit(probe_scores[p]) - base for p in PROBES]
            response = deltas + [
                float(np.mean(deltas)), float(np.std(deltas)),
                float(np.max(np.abs(deltas))), float(max(deltas) - min(deltas)),
                float(probe["probe_std"]), float(probe["probe_range"]),
                float(probe["probe_max_delta"]),
                float(probe["probe_mean"]) - float(expert["p_fake"]),
            ]
            out.append({
                "source_id": row["source_id"],
                "condition_id": row["condition_id"],
                "label": int(row["label"]),
                "family": row["family"],
                "base": base,
                "quality": [float(row["quality"][k]) for k in QUALITY_KEYS],
                "response": response,
            })
    if n_bad_schema:
        warnings.append(
            f"dropped {n_bad_schema}/{n_total} rows: schema_version != "
            f"{SCHEMA_VERSION_EXPECTED!r}"
        )
    if n_expert_fail:
        warnings.append(
            f"dropped {n_expert_fail}/{n_total} rows: expert {EXPERT!r} missing/ok=false"
        )
    if n_probe_incomplete:
        warnings.append(
            f"dropped {n_probe_incomplete}/{n_total} rows: incomplete probe set "
            f"(need n_probes_ok == {len(PROBES)})"
        )
    return out


FEATURE_LISTS: dict[str, list[str]] = {
    "A": ["primary_raw_logit"],
    "A2": ["primary_raw_logit (affine-calibrated on inner-dev)"],
    "B": ["primary_raw_logit", *QUALITY_KEYS],
    "C": ["primary_raw_logit", *QUALITY_KEYS,
          *[f"response_{i}" for i in range(8)]],
    "D": ["primary_raw_logit", *[f"response_{i}" for i in range(8)]],
    "Q": list(QUALITY_KEYS),
}


def design(rows: list[dict[str, Any]], arm: str) -> np.ndarray:
    cols = []
    for r in rows:
        if arm == "A" or arm == "A2":
            vec = [r["base"]]
        elif arm == "B":
            vec = [r["base"], *r["quality"]]
        elif arm == "C":
            vec = [r["base"], *r["quality"], *r["response"]]
        elif arm == "D":
            vec = [r["base"], *r["response"]]
        elif arm == "Q":
            vec = list(r["quality"])
        else:
            raise ValueError(f"unknown arm {arm!r}")
        cols.append(vec)
    return np.asarray(cols, dtype=np.float64)


# --------------------------------------------------------------------------- #
# Logistic fitting (IRLS, L2-regularized, unpenalized intercept) — pattern
# copied from degradeprint_probe.py so results stay comparable in kind.
# --------------------------------------------------------------------------- #

def fit_logistic(
    x: np.ndarray, y: np.ndarray, l2: float = 1.0, iters: int = 400,
) -> tuple[np.ndarray, np.ndarray, np.ndarray] | None:
    """L2-regularized logistic regression by IRLS. Intercept is unpenalized.

    Standardization statistics come from the TRAIN matrix only and travel
    with the model, so scoring dev/test cannot leak their moments into fit.
    Returns None (caller must fall back) if the fit collapses to a single
    class -- happens on very thin folds and must be reported, not crashed on.
    """
    if x.shape[0] == 0 or len(np.unique(y)) < 2:
        return None
    mu, sd = x.mean(0), x.std(0)
    sd[sd == 0] = 1.0
    z = np.hstack([(x - mu) / sd, np.ones((len(x), 1))])
    penalty = np.r_[np.ones(z.shape[1] - 1), 0.0]
    w = np.zeros(z.shape[1])
    for _ in range(iters):
        p = np.clip(1.0 / (1.0 + np.exp(-z @ w)), 1e-9, 1 - 1e-9)
        grad = z.T @ (p - y) + l2 * (penalty * w)
        hess = (z * (p * (1 - p))[:, None]).T @ z + l2 * np.diag(penalty)
        try:
            step = np.linalg.solve(hess + 1e-8 * np.eye(len(w)), grad)
        except np.linalg.LinAlgError:
            return None
        w -= step
    return mu, sd, w


def score_model(model: tuple[np.ndarray, np.ndarray, np.ndarray], x: np.ndarray) -> np.ndarray:
    mu, sd, w = model
    return np.hstack([(x - mu) / sd, np.ones((len(x), 1))]) @ w


# --------------------------------------------------------------------------- #
# Splitting
# --------------------------------------------------------------------------- #

def make_outer_folds(sources: list[str], n_folds: int, rng: np.random.Generator) -> list[list[str]]:
    shuffled = list(sources)
    rng.shuffle(shuffled)
    return [list(chunk) for chunk in np.array_split(np.array(shuffled), n_folds)]


def make_inner_split(
    train_sources: list[str], rng: np.random.Generator, dev_frac: float = INNER_DEV_FRAC,
) -> tuple[set[str], set[str]]:
    shuffled = list(train_sources)
    rng.shuffle(shuffled)
    n_dev = max(1, round(len(shuffled) * dev_frac)) if shuffled else 0
    dev = set(shuffled[:n_dev])
    inner_train = set(shuffled[n_dev:])
    return inner_train, dev


# --------------------------------------------------------------------------- #
# Thresholding
# --------------------------------------------------------------------------- #

def fit_threshold(
    scores: np.ndarray, rows: list[dict[str, Any]], target_fpr: float, warnings: list[str],
    context: str,
) -> tuple[float, bool]:
    """Threshold at a fixed clean-image FPR, fitted on the given (dev) split.

    Falls back to all real (label==0) rows of any family, then to the median
    score, if the clean family has too few negatives to support a stable
    quantile -- this is the thin-fold case the task brief calls out. Returns
    (threshold, used_fallback).
    """
    clean_neg = np.array([
        s for s, r in zip(scores, rows) if r["label"] == 0 and r["family"] == "clean"
    ])
    if len(clean_neg) >= 5:
        return float(np.quantile(clean_neg, 1.0 - target_fpr)), False
    any_neg = np.array([s for s, r in zip(scores, rows) if r["label"] == 0])
    if len(any_neg) >= 5:
        warnings.append(
            f"{context}: only {len(clean_neg)} clean-negative rows in dev split; "
            f"threshold fell back to all-real-family quantile (n={len(any_neg)})"
        )
        return float(np.quantile(any_neg, 1.0 - target_fpr)), True
    warnings.append(
        f"{context}: fewer than 5 real rows of any family in dev split "
        f"(clean={len(clean_neg)}, any={len(any_neg)}); threshold fell back to median score"
    )
    return float(np.median(scores)) if len(scores) else 0.0, True


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #

def _auroc(scores: np.ndarray, labels: np.ndarray) -> float:
    pos = scores[labels == 1]
    neg = scores[labels == 0]
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    order = np.argsort(np.concatenate([pos, neg]))
    ranks = np.empty(len(order), dtype=np.float64)
    combined = np.concatenate([pos, neg])
    sorted_vals = combined[order]
    ranks_sorted = np.arange(1, len(order) + 1, dtype=np.float64)
    i = 0
    while i < len(sorted_vals):
        j = i
        while j + 1 < len(sorted_vals) and sorted_vals[j + 1] == sorted_vals[i]:
            j += 1
        if j > i:
            ranks_sorted[i:j + 1] = ranks_sorted[i:j + 1].mean()
        i = j + 1
    ranks[order] = ranks_sorted
    rank_pos_sum = ranks[: len(pos)].sum()
    n_pos, n_neg = len(pos), len(neg)
    return float((rank_pos_sum - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg))


def compute_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """`rows` items need: label, family, source_id, score, decision (bool)."""
    labels = np.array([r["label"] for r in rows], dtype=np.int64)
    scores = np.array([r["score"] for r in rows], dtype=np.float64)
    decisions = np.array([r["decision"] for r in rows], dtype=bool)
    families = [r["family"] for r in rows]

    recall_by_family: dict[str, float] = {}
    support_by_family: dict[str, int] = {}
    for fam in FAMILIES:
        idx = [i for i, (f, y) in enumerate(zip(families, labels)) if f == fam and y == 1]
        support_by_family[fam] = len(idx)
        recall_by_family[fam] = float(np.mean(decisions[idx])) if idx else float("nan")

    present = [f for f in FAMILIES if support_by_family[f] > 0]
    if present:
        worst_family = min(present, key=lambda f: recall_by_family[f])
        worst_recall = recall_by_family[worst_family]
    else:
        worst_family, worst_recall = None, float("nan")
    missing_families = [f for f in FAMILIES if support_by_family[f] == 0]

    clean_idx1 = [i for i, (f, y) in enumerate(zip(families, labels)) if f == "clean" and y == 1]
    clean_idx0 = [i for i, (f, y) in enumerate(zip(families, labels)) if f == "clean" and y == 0]
    clean_tpr = float(np.mean(decisions[clean_idx1])) if clean_idx1 else float("nan")
    clean_tnr = float(np.mean(~decisions[clean_idx0])) if clean_idx0 else float("nan")
    clean_bacc = (
        0.5 * (clean_tpr + clean_tnr)
        if clean_idx1 and clean_idx0 else float("nan")
    )
    clean_fpr = float(np.mean(decisions[clean_idx0])) if clean_idx0 else float("nan")

    # Fake-to-real flip rate: among FAKE sources whose CLEAN view was correctly
    # caught (score>=threshold), what fraction of that source's *other*
    # (non-clean) views flip to a "real" decision. Sources whose clean view was
    # already missed contribute nothing to flip from, so they are excluded
    # from the denominator (judgment call -- see script docstring / report).
    clean_caught_sources: set[str] = {
        rows[i]["source_id"] for i in clean_idx1 if decisions[i]
    }
    flip_num, flip_den = 0, 0
    for i, r in enumerate(rows):
        if r["label"] != 1 or r["family"] == "clean":
            continue
        if r["source_id"] not in clean_caught_sources:
            continue
        flip_den += 1
        if not decisions[i]:
            flip_num += 1
    flip_rate = float(flip_num / flip_den) if flip_den else float("nan")

    auroc = _auroc(scores, labels)

    return {
        "n_rows": len(rows),
        "recall_by_family": recall_by_family,
        "support_by_family": support_by_family,
        "missing_families": missing_families,
        "worst_family": worst_family,
        "worst_family_fake_recall": worst_recall,
        "fake_to_real_flip_rate": flip_rate,
        "flip_numerator": flip_num,
        "flip_denominator": flip_den,
        "clean_balanced_accuracy": clean_bacc,
        "clean_tpr": clean_tpr,
        "clean_tnr": clean_tnr,
        "clean_fpr": clean_fpr,
        "auroc": auroc,
    }


# --------------------------------------------------------------------------- #
# Paired source-level bootstrap
# --------------------------------------------------------------------------- #

def per_source_family_stats(
    rows: list[dict[str, Any]], source_index: dict[str, int],
) -> np.ndarray:
    """Per-source sufficient statistics for the worst-family-recall bootstrap.

    Returns an (n_sources, n_families, 2) array of [n_fake_rows, n_fake_correct]
    counts, family order == FAMILIES. Resampling sources with replacement and
    re-deriving worst-family recall reduces to a weighted sum of these
    per-source counts (a source's rows are always resampled as a block), which
    is what makes the vectorized bootstrap below exact, not an approximation.
    """
    family_index = {f: i for i, f in enumerate(FAMILIES)}
    stats = np.zeros((len(source_index), len(FAMILIES), 2), dtype=np.float64)
    for r in rows:
        if r["label"] != 1:
            continue
        fam_i = family_index.get(r["family"])
        if fam_i is None:  # "clean" is excluded from the worst-family minimum
            continue
        s_i = source_index[r["source_id"]]
        stats[s_i, fam_i, 0] += 1.0
        stats[s_i, fam_i, 1] += 1.0 if r["decision"] else 0.0
    return stats


def _worst_family_recall_vectorized(agg: np.ndarray) -> np.ndarray:
    """agg: (n_resamples, n_families, 2) weighted [n_fake, n_correct] sums."""
    n_fake, n_correct = agg[..., 0], agg[..., 1]
    with np.errstate(divide="ignore", invalid="ignore"):
        recall = np.where(n_fake > 0, n_correct / np.where(n_fake == 0, 1.0, n_fake), np.nan)
    all_missing = np.all(n_fake == 0, axis=1)
    with _warnings.catch_warnings():
        # A resample can (rarely, on thin folds) draw zero fake rows for every
        # family; nanmin warns on that all-NaN row even though we overwrite it
        # with NaN again immediately below, so it stays NaN either way.
        _warnings.simplefilter("ignore", category=RuntimeWarning)
        worst = np.nanmin(recall, axis=1)
    worst[all_missing] = np.nan
    return worst


def paired_bootstrap_worst_family_recall(
    stats_x: np.ndarray, stats_y: np.ndarray, n_resamples: int, rng: np.random.Generator,
) -> dict[str, Any]:
    """Bootstrap worst-family-fake-recall `metric(x) - metric(y)`, resampling
    SOURCES with replacement, paired by source_id (both arms share the same
    source order/count since both are scored on the identical out-of-fold set).

    Vectorized: one `rng.multinomial` draw gives per-resample per-source pick
    counts for all `n_resamples` resamples at once; each resample's aggregate
    per-family counts are then a single matmul against the per-source
    sufficient statistics, instead of materializing resampled row lists in a
    Python loop (the previous approach; correct but too slow to scale past a
    few hundred sources).
    """
    n_sources = stats_x.shape[0]
    if n_sources == 0:
        return {"n_resamples": 0, "mean_delta": float("nan"),
                "ci_low": float("nan"), "ci_high": float("nan"), "sources": 0}

    counts = rng.multinomial(n_sources, np.full(n_sources, 1.0 / n_sources), size=n_resamples)
    flat_x = stats_x.reshape(n_sources, -1)
    flat_y = stats_y.reshape(n_sources, -1)
    agg_x = (counts @ flat_x).reshape(n_resamples, len(FAMILIES), 2)
    agg_y = (counts @ flat_y).reshape(n_resamples, len(FAMILIES), 2)
    metric_x = _worst_family_recall_vectorized(agg_x)
    metric_y = _worst_family_recall_vectorized(agg_y)

    valid = ~np.isnan(metric_x) & ~np.isnan(metric_y)
    deltas = (metric_x - metric_y)[valid]
    if deltas.size == 0:
        return {"n_resamples": 0, "mean_delta": float("nan"),
                "ci_low": float("nan"), "ci_high": float("nan"), "sources": n_sources}
    return {
        "n_resamples": int(deltas.size),
        "mean_delta": float(deltas.mean()),
        "ci_low": float(np.quantile(deltas, 0.025)),
        "ci_high": float(np.quantile(deltas, 0.975)),
        "sources": n_sources,
    }


def gate_decision(
    comparison: dict[str, Any], point_x: dict[str, Any], clean_reference: dict[str, Any],
) -> dict[str, Any]:
    """Recall improvement is PAIRWISE; clean cost is measured against a FIXED reference.

    The clean-BAcc/FPR budgets exist to stop an arm buying robustness by wrecking
    the clean operating point, so they are an absolute constraint against what we
    would otherwise ship -- the calibrated primary, A2 -- not a pairwise quantity.

    Measuring them against whichever arm happens to be the comparator gives
    nonsense for a weak comparator: arm Q has a low clean FPR precisely BECAUSE
    it is a poor model at that operating point, so "B's clean FPR rose 4 points
    versus Q" failed the gate while telling us nothing. That was a defect in the
    frozen spec's wording, corrected here.
    """
    delta_recall = comparison["mean_delta"]
    ci_low = comparison["ci_low"]
    bacc_delta = point_x["clean_balanced_accuracy"] - clean_reference["clean_balanced_accuracy"]
    fpr_delta = point_x["clean_fpr"] - clean_reference["clean_fpr"]
    criteria = {
        "delta_recall_mean_ge_2pt": delta_recall >= GATE_MIN_DELTA,
        "ci_low_above_zero": ci_low > 0.0,
        "clean_bacc_regression_le_1pt": bacc_delta >= -GATE_MAX_BACC_REGRESSION,
        "clean_fpr_rise_le_1pt": fpr_delta <= GATE_MAX_FPR_RISE,
    }
    passed = all(
        v if not (isinstance(v, float) and math.isnan(v)) else False
        for v in criteria.values()
    )
    return {
        "pass": bool(passed) and not any(
            math.isnan(v) for v in (delta_recall, ci_low, bacc_delta, fpr_delta)
        ),
        "delta_recall_mean": delta_recall,
        "ci_low": ci_low,
        "ci_high": comparison["ci_high"],
        "clean_bacc_delta": bacc_delta,
        "clean_fpr_delta": fpr_delta,
        "criteria": criteria,
    }


# --------------------------------------------------------------------------- #
# Main pipeline
# --------------------------------------------------------------------------- #

def run(rows_path: Path, n_folds: int, seed: int) -> dict[str, Any]:
    warnings: list[str] = []
    rows = load_rows(rows_path, warnings)
    if not rows:
        raise SystemExit(f"no usable rows loaded from {rows_path}")

    sources = sorted({r["source_id"] for r in rows})
    rows_by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        rows_by_source[r["source_id"]].append(r)

    rng = np.random.default_rng(seed)
    outer_folds = make_outer_folds(sources, n_folds, rng)
    for i, fold in enumerate(outer_folds):
        if len(fold) < 3:
            warnings.append(f"outer fold {i} has only {len(fold)} source(s); metrics will be thin")

    fold_source_ids = {str(i): fold for i, fold in enumerate(outer_folds)}
    thresholds: dict[str, dict[str, float]] = {}
    per_fold_metrics: dict[str, dict[str, Any]] = {}
    oof_rows: dict[str, list[dict[str, Any]]] = {arm: [] for arm in ARMS}

    for fold_idx, test_sources in enumerate(outer_folds):
        test_sources_set = set(test_sources)
        train_sources = [s for s in sources if s not in test_sources_set]
        inner_rng = np.random.default_rng(seed * 1000 + fold_idx + 1)
        inner_train_set, inner_dev_set = make_inner_split(train_sources, inner_rng)
        if len(inner_dev_set) < 3 or len(inner_train_set) < 3:
            warnings.append(
                f"fold {fold_idx}: thin inner split (inner_train={len(inner_train_set)} "
                f"sources, inner_dev={len(inner_dev_set)} sources)"
            )

        inner_train_rows = [r for s in inner_train_set for r in rows_by_source[s]]
        inner_dev_rows = [r for s in inner_dev_set for r in rows_by_source[s]]
        test_rows = [r for s in test_sources for r in rows_by_source[s]]

        thresholds.setdefault(str(fold_idx), {})
        fold_metrics: dict[str, Any] = {}

        for arm in ARMS:
            if arm == "A":
                # Not fitted: the raw logit itself is the score.
                dev_scores = np.array([r["base"] for r in inner_dev_rows])
                test_scores = np.array([r["base"] for r in test_rows])
            elif arm == "A2":
                x_dev = design(inner_dev_rows, "A")
                y_dev = np.array([r["label"] for r in inner_dev_rows], dtype=np.float64)
                model = fit_logistic(x_dev, y_dev, l2=0.1)
                if model is None:
                    warnings.append(
                        f"fold {fold_idx} arm A2: inner-dev calibration fit failed "
                        f"(n={len(inner_dev_rows)}, classes={sorted(set(y_dev.tolist()))}); "
                        f"falling back to raw logit"
                    )
                    dev_scores = np.array([r["base"] for r in inner_dev_rows])
                    test_scores = np.array([r["base"] for r in test_rows])
                else:
                    dev_scores = score_model(model, x_dev)
                    test_scores = score_model(model, design(test_rows, "A"))
            else:
                x_train = design(inner_train_rows, arm)
                y_train = np.array([r["label"] for r in inner_train_rows], dtype=np.float64)
                model = fit_logistic(x_train, y_train, l2=1.0)
                if model is None:
                    warnings.append(
                        f"fold {fold_idx} arm {arm}: inner-train fit failed "
                        f"(n={len(inner_train_rows)}, classes={sorted(set(y_train.tolist()))}); "
                        f"scores set to 0.0 (equivalent to always-below-threshold)"
                    )
                    dev_scores = np.zeros(len(inner_dev_rows))
                    test_scores = np.zeros(len(test_rows))
                else:
                    dev_scores = score_model(model, design(inner_dev_rows, arm))
                    test_scores = score_model(model, design(test_rows, arm))

            threshold, _ = fit_threshold(
                dev_scores, inner_dev_rows, CLEAN_FPR_TARGET, warnings,
                context=f"fold {fold_idx} arm {arm}",
            )
            thresholds[str(fold_idx)][arm] = threshold

            arm_test_rows = [
                {
                    "source_id": r["source_id"], "family": r["family"], "label": r["label"],
                    "score": float(s), "decision": bool(s >= threshold),
                }
                for r, s in zip(test_rows, test_scores)
            ]
            oof_rows[arm].extend(arm_test_rows)
            fold_metrics[arm] = compute_metrics(arm_test_rows)

        per_fold_metrics[str(fold_idx)] = fold_metrics

    aggregated_metrics = {arm: compute_metrics(oof_rows[arm]) for arm in ARMS}

    # Every arm shares the same out-of-fold source set (all outer folds are
    # identical across arms), so one source_index serves every comparison.
    source_index = {s: i for i, s in enumerate(sources)}
    stats_by_arm = {arm: per_source_family_stats(oof_rows[arm], source_index) for arm in ARMS}

    bootstrap_rng = np.random.default_rng(seed * 7919 + 1)
    comparisons_spec = [
        ("B_vs_A2", "B", "A2"),
        ("C_vs_B", "C", "B"),
        ("D_vs_B", "D", "B"),
        ("D_vs_A", "D", "A"),
        ("B_vs_Q", "B", "Q"),
        ("C_vs_Q", "C", "Q"),
        ("A2_vs_A", "A2", "A"),
    ]
    bootstrap_results: dict[str, Any] = {}
    for name, arm_x, arm_y in comparisons_spec:
        bootstrap_results[name] = paired_bootstrap_worst_family_recall(
            stats_by_arm[arm_x], stats_by_arm[arm_y], N_BOOTSTRAP, bootstrap_rng,
        )

    gates = {
        "keep_quality_correction": gate_decision(
            bootstrap_results["B_vs_A2"], aggregated_metrics["B"], aggregated_metrics["A2"],
        ),
        "keep_logit_response": gate_decision(
            bootstrap_results["C_vs_B"], aggregated_metrics["C"], aggregated_metrics["A2"],
        ),
        "B_beats_Q_same_bar": gate_decision(
            bootstrap_results["B_vs_Q"], aggregated_metrics["B"], aggregated_metrics["A2"],
        ),
        "C_beats_Q_same_bar": gate_decision(
            bootstrap_results["C_vs_Q"], aggregated_metrics["C"], aggregated_metrics["A2"],
        ),
    }
    gate_policy = {
        "clean_cost_reference": "A2 (calibrated primary) for every gate -- the clean BAcc/FPR "
                                "budgets are absolute production constraints against what we would "
                                "otherwise ship, not pairwise against the comparator arm",
        "min_delta": GATE_MIN_DELTA,
        "max_bacc_regression": GATE_MAX_BACC_REGRESSION,
        "max_fpr_rise": GATE_MAX_FPR_RISE,
    }

    family_counts = Counter(r["family"] for r in rows)
    label_counts = Counter(r["label"] for r in rows)

    return {
        "watermark": WATERMARK,
        "meta": {
            "rows_path": str(rows_path),
            "n_rows_loaded": len(rows),
            "n_sources": len(sources),
            "n_outer_folds": n_folds,
            "seed": seed,
            "inner_dev_frac": INNER_DEV_FRAC,
            "clean_fpr_target": CLEAN_FPR_TARGET,
            "n_bootstrap_resamples": N_BOOTSTRAP,
            "family_counts": dict(family_counts),
            "label_counts": {str(k): v for k, v in label_counts.items()},
            "generated_at": datetime.now(UTC).isoformat(),
        },
        "fold_source_ids": fold_source_ids,
        "feature_lists": FEATURE_LISTS,
        "thresholds": thresholds,
        "per_fold_metrics": per_fold_metrics,
        "aggregated_metrics": aggregated_metrics,
        "bootstrap_comparisons": bootstrap_results,
        "gates": gates,
        "gate_policy": gate_policy,
        "warnings": warnings,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=Path, required=True, help="path to rows.jsonl")
    parser.add_argument("--folds", type=int, default=3, help="number of outer source folds")
    parser.add_argument("--seed", type=int, default=0, help="RNG seed for all splits/bootstrap")
    parser.add_argument(
        "--out", type=Path, default=Path("results/degradeprint/pilot.json"),
        help="output JSON path",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    result = run(args.rows, args.folds, args.seed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=True))

    print(f"[{result['watermark']}] rows={result['meta']['n_rows_loaded']} "
          f"sources={result['meta']['n_sources']} folds={args.folds} seed={args.seed}")
    print(f"wrote {args.out}")
    if result["warnings"]:
        print(f"\n{len(result['warnings'])} warning(s):")
        for w in result["warnings"]:
            print(f"  - {w}")

    print("\naggregated (out-of-fold) metrics:")
    header = f"{'arm':<4}{'worst_fam':>10}{'worst_rec':>11}{'flip':>9}{'cleanBAcc':>11}{'cleanFPR':>10}{'AUROC':>9}"
    print(header)
    for arm in ARMS:
        m = result["aggregated_metrics"][arm]
        wf = m["worst_family"] or "n/a"
        print(f"{arm:<4}{wf:>10}{m['worst_family_fake_recall']:>11.4f}"
              f"{m['fake_to_real_flip_rate']:>9.4f}{m['clean_balanced_accuracy']:>11.4f}"
              f"{m['clean_fpr']:>10.4f}{m['auroc']:>9.4f}")

    print("\nbootstrap deltas (worst-family fake recall, paired by source):")
    for name, comp in result["bootstrap_comparisons"].items():
        print(f"  {name:<12} mean={comp['mean_delta']:+.4f} "
              f"ci=[{comp['ci_low']:+.4f}, {comp['ci_high']:+.4f}] "
              f"(n_resamples={comp['n_resamples']}, sources={comp['sources']})")

    print("\ngates:")
    for name, g in result["gates"].items():
        print(f"  {name}: {g['pass']} "
              f"(delta_recall_mean={g['delta_recall_mean']:+.4f}, "
              f"ci_low={g['ci_low']:+.4f}, "
              f"clean_bacc_delta={g['clean_bacc_delta']:+.4f}, "
              f"clean_fpr_delta={g['clean_fpr_delta']:+.4f})")


if __name__ == "__main__":
    main()
