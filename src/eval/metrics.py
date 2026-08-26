"""Auditable binary-classification metrics for the frozen eval protocol.

AI-generated images are always label ``1`` and the decision boundary is
``p_fake >= threshold``.  Functions in this module validate their inputs and
raise instead of manufacturing a metric when either class is absent.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Iterable

import numpy as np


@dataclass(frozen=True)
class ConfusionCounts:
    """Raw counts with AI-generated as the positive class."""

    tp: int
    fn: int
    fp: int
    tn: int

    @property
    def fake_recall(self) -> float:
        return self.tp / (self.tp + self.fn)

    @property
    def true_negative_rate(self) -> float:
        return self.tn / (self.tn + self.fp)

    @property
    def false_positive_rate(self) -> float:
        return self.fp / (self.fp + self.tn)

    @property
    def balanced_accuracy(self) -> float:
        return (self.fake_recall + self.true_negative_rate) / 2.0

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


def _validated_arrays(
    labels: Iterable[int] | np.ndarray,
    scores: Iterable[float] | np.ndarray,
    *,
    require_both_classes: bool = True,
) -> tuple[np.ndarray, np.ndarray]:
    label_array = np.asarray(list(labels) if not isinstance(labels, np.ndarray) else labels)
    score_array = np.asarray(list(scores) if not isinstance(scores, np.ndarray) else scores)
    if label_array.ndim != 1 or score_array.ndim != 1:
        raise ValueError("labels and scores must be one-dimensional")
    if label_array.size == 0:
        raise ValueError("labels and scores must not be empty")
    if label_array.size != score_array.size:
        raise ValueError("labels and scores must have equal length")
    if label_array.dtype.kind not in "biu" or not set(label_array.tolist()).issubset({0, 1}):
        raise ValueError("labels must contain integers 0 or 1")
    score_array = score_array.astype(np.float64, copy=False)
    if not np.isfinite(score_array).all():
        raise ValueError("scores must be finite")
    if np.any((score_array < 0.0) | (score_array > 1.0)):
        raise ValueError("scores must lie in [0,1]")
    classes = set(label_array.tolist())
    if require_both_classes and classes != {0, 1}:
        raise ValueError("metric requires both label classes")
    return label_array.astype(np.int8, copy=False), score_array


def validate_threshold(threshold: float) -> float:
    """Return a finite class threshold in ``[0,1]`` or raise."""
    value = float(threshold)
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError("threshold must be finite and lie in [0,1]")
    return value


def binary_decisions(scores: Iterable[float] | np.ndarray, threshold: float) -> np.ndarray:
    """Apply the frozen inclusive boundary: equality predicts fake."""
    threshold = validate_threshold(threshold)
    score_array = np.asarray(list(scores) if not isinstance(scores, np.ndarray) else scores)
    if score_array.ndim != 1 or score_array.size == 0:
        raise ValueError("scores must be a non-empty one-dimensional array")
    score_array = score_array.astype(np.float64, copy=False)
    if not np.isfinite(score_array).all() or np.any((score_array < 0.0) | (score_array > 1.0)):
        raise ValueError("scores must be finite and lie in [0,1]")
    return (score_array >= threshold).astype(np.int8)


def confusion_counts(
    labels: Iterable[int] | np.ndarray,
    scores: Iterable[float] | np.ndarray,
    threshold: float,
) -> ConfusionCounts:
    labels_array, scores_array = _validated_arrays(labels, scores)
    predictions = binary_decisions(scores_array, threshold)
    return ConfusionCounts(
        tp=int(np.sum((labels_array == 1) & (predictions == 1))),
        fn=int(np.sum((labels_array == 1) & (predictions == 0))),
        fp=int(np.sum((labels_array == 0) & (predictions == 1))),
        tn=int(np.sum((labels_array == 0) & (predictions == 0))),
    )


def auroc(labels: Iterable[int] | np.ndarray, scores: Iterable[float] | np.ndarray) -> float:
    """Area under ROC using the Mann–Whitney statistic with average tie ranks."""
    labels_array, scores_array = _validated_arrays(labels, scores)
    order = np.argsort(scores_array, kind="mergesort")
    sorted_scores = scores_array[order]
    ranks = np.empty(scores_array.size, dtype=np.float64)
    start = 0
    while start < scores_array.size:
        stop = start + 1
        while stop < scores_array.size and sorted_scores[stop] == sorted_scores[start]:
            stop += 1
        ranks[order[start:stop]] = (start + 1 + stop) / 2.0
        start = stop
    positives = labels_array == 1
    n_positive = int(positives.sum())
    n_negative = labels_array.size - n_positive
    rank_sum = float(ranks[positives].sum())
    return (rank_sum - n_positive * (n_positive + 1) / 2.0) / (n_positive * n_negative)


def average_precision(
    labels: Iterable[int] | np.ndarray, scores: Iterable[float] | np.ndarray
) -> float:
    """Non-interpolated AP, processing equal-score examples as one threshold."""
    labels_array, scores_array = _validated_arrays(labels, scores)
    order = np.argsort(-scores_array, kind="mergesort")
    sorted_labels = labels_array[order]
    sorted_scores = scores_array[order]
    total_positive = int(sorted_labels.sum())
    true_positive = 0
    seen = 0
    ap = 0.0
    start = 0
    while start < sorted_labels.size:
        stop = start + 1
        while stop < sorted_labels.size and sorted_scores[stop] == sorted_scores[start]:
            stop += 1
        group_positive = int(sorted_labels[start:stop].sum())
        true_positive += group_positive
        seen += stop - start
        ap += (group_positive / total_positive) * (true_positive / seen)
        start = stop
    return ap


def brier_score(labels: Iterable[int] | np.ndarray, scores: Iterable[float] | np.ndarray) -> float:
    labels_array, scores_array = _validated_arrays(labels, scores, require_both_classes=False)
    return float(np.mean(np.square(scores_array - labels_array)))


def negative_log_likelihood(
    labels: Iterable[int] | np.ndarray,
    scores: Iterable[float] | np.ndarray,
    *,
    eps: float = 1e-12,
) -> float:
    labels_array, scores_array = _validated_arrays(labels, scores, require_both_classes=False)
    if not math.isfinite(eps) or not 0.0 < eps < 0.5:
        raise ValueError("eps must be finite and lie in (0,0.5)")
    clipped = np.clip(scores_array, eps, 1.0 - eps)
    return float(-np.mean(labels_array * np.log(clipped) + (1 - labels_array) * np.log1p(-clipped)))


def expected_calibration_error(
    labels: Iterable[int] | np.ndarray,
    scores: Iterable[float] | np.ndarray,
    *,
    n_bins: int = 15,
) -> float:
    """ECE over fixed equal-width bins, including exact 0 and 1 scores."""
    labels_array, scores_array = _validated_arrays(labels, scores, require_both_classes=False)
    if isinstance(n_bins, bool) or not isinstance(n_bins, int) or n_bins <= 0:
        raise ValueError("n_bins must be a positive integer")
    bin_index = np.minimum((scores_array * n_bins).astype(np.int64), n_bins - 1)
    ece = 0.0
    for index in range(n_bins):
        mask = bin_index == index
        if mask.any():
            ece += float(mask.mean()) * abs(
                float(scores_array[mask].mean()) - float(labels_array[mask].mean())
            )
    return ece


def condition_metrics(
    labels: Iterable[int] | np.ndarray,
    scores: Iterable[float] | np.ndarray,
    threshold: float,
    *,
    ece_bins: int = 15,
) -> dict[str, object]:
    """Return all Phase-1 scalar metrics and the auditable raw counts."""
    labels_array, scores_array = _validated_arrays(labels, scores)
    counts = confusion_counts(labels_array, scores_array, threshold)
    return {
        "counts": counts.to_dict(),
        "fake_recall": counts.fake_recall,
        "true_negative_rate": counts.true_negative_rate,
        "false_positive_rate": counts.false_positive_rate,
        "balanced_accuracy": counts.balanced_accuracy,
        "auroc": auroc(labels_array, scores_array),
        "average_precision": average_precision(labels_array, scores_array),
        "brier_score": brier_score(labels_array, scores_array),
        "negative_log_likelihood": negative_log_likelihood(labels_array, scores_array),
        "expected_calibration_error": expected_calibration_error(
            labels_array, scores_array, n_bins=ece_bins
        ),
    }


def paired_flip_metrics(
    labels: Iterable[int] | np.ndarray,
    clean_scores: Iterable[float] | np.ndarray,
    transformed_scores: Iterable[float] | np.ndarray,
    threshold: float,
) -> dict[str, float]:
    """Compute ordinary and directional paired source flip rates."""
    labels_array, clean_array = _validated_arrays(labels, clean_scores)
    labels_again, transformed_array = _validated_arrays(labels, transformed_scores)
    if not np.array_equal(labels_array, labels_again):
        raise ValueError("paired score arrays must use the same ordered labels")
    clean_pred = binary_decisions(clean_array, threshold)
    transformed_pred = binary_decisions(transformed_array, threshold)
    fake = labels_array == 1
    real = labels_array == 0
    return {
        "flip_rate": float(np.mean(clean_pred != transformed_pred)),
        "fake_to_real_flip": float(np.mean((clean_pred[fake] == 1) & (transformed_pred[fake] == 0))),
        "real_to_fake_flip": float(np.mean((clean_pred[real] == 0) & (transformed_pred[real] == 1))),
    }


def signed_drop(clean_value: float, transformed_value: float) -> float:
    """The protocol's signed clean-to-transformed drop."""
    if not math.isfinite(clean_value) or not math.isfinite(transformed_value):
        raise ValueError("drop inputs must be finite")
    return float(clean_value - transformed_value)


def worst_condition(values: dict[str, float]) -> tuple[str, float]:
    """Return the minimum exact condition; lexical ID breaks exact ties."""
    if not values:
        raise ValueError("at least one condition value is required")
    if any(not isinstance(key, str) or not key for key in values):
        raise ValueError("condition IDs must be non-empty strings")
    if any(not math.isfinite(float(value)) for value in values.values()):
        raise ValueError("condition values must be finite")
    condition_id = min(sorted(values), key=lambda key: values[key])
    return condition_id, float(values[condition_id])
