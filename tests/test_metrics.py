import math

import numpy as np
import pytest

from src.eval.metrics import (
    ConfusionCounts,
    auroc,
    average_precision,
    binary_decisions,
    brier_score,
    condition_metrics,
    confusion_counts,
    expected_calibration_error,
    negative_log_likelihood,
    paired_flip_metrics,
    signed_drop,
    worst_condition,
)

LABELS = np.array([0, 0, 1, 1])
SCORES = np.array([0.1, 0.5, 0.5, 0.9])


def test_confusion_counts_and_rates_use_fake_as_positive():
    counts = confusion_counts(LABELS, SCORES, threshold=0.5)
    assert counts == ConfusionCounts(tp=2, fn=0, fp=1, tn=1)
    assert counts.fake_recall == 1.0
    assert counts.false_positive_rate == 0.5
    assert counts.balanced_accuracy == 0.75


def test_threshold_equality_predicts_fake():
    assert binary_decisions([0.49, 0.5, 0.51], 0.5).tolist() == [0, 1, 1]


def test_auroc_and_average_precision_match_known_reference_values():
    labels = [0, 0, 1, 1]
    scores = [0.1, 0.4, 0.35, 0.8]
    assert auroc(labels, scores) == pytest.approx(0.75)
    assert average_precision(labels, scores) == pytest.approx(5 / 6)


def test_rank_metrics_handle_score_ties_without_order_dependence():
    assert auroc([0, 1], [0.5, 0.5]) == pytest.approx(0.5)
    assert average_precision([0, 1], [0.5, 0.5]) == pytest.approx(0.5)
    assert average_precision([1, 0], [0.5, 0.5]) == pytest.approx(0.5)


def test_probability_metrics_include_boundary_scores():
    labels = [0, 1]
    perfect = [0.0, 1.0]
    assert brier_score(labels, perfect) == 0.0
    assert expected_calibration_error(labels, perfect, n_bins=15) == 0.0
    assert math.isfinite(negative_log_likelihood(labels, perfect))
    assert negative_log_likelihood(labels, perfect) < 1e-9


def test_ece_uses_fixed_bins_and_weighted_absolute_gaps():
    # Each example lands in a separate 0.5-width bin. Gaps are 0.1 and 0.2.
    assert expected_calibration_error([0, 1], [0.1, 0.8], n_bins=2) == pytest.approx(0.15)


def test_condition_metrics_keeps_counts_auditable():
    result = condition_metrics(LABELS, SCORES, 0.5, ece_bins=5)
    assert result["counts"] == {"tp": 2, "fn": 0, "fp": 1, "tn": 1}
    assert result["balanced_accuracy"] == pytest.approx(0.75)
    assert result["fake_recall"] == pytest.approx(1.0)
    assert result["false_positive_rate"] == pytest.approx(0.5)


def test_directional_flips_use_all_sources_of_the_requested_class_as_denominator():
    labels = [0, 0, 1, 1]
    clean = [0.1, 0.9, 0.9, 0.1]
    transformed = [0.9, 0.1, 0.1, 0.9]
    assert paired_flip_metrics(labels, clean, transformed, 0.5) == {
        "flip_rate": 1.0,
        "fake_to_real_flip": 0.5,
        "real_to_fake_flip": 0.5,
    }


def test_signed_drop_and_worst_condition_are_deterministic():
    assert signed_drop(0.8, 0.6) == pytest.approx(0.2)
    assert signed_drop(0.6, 0.8) == pytest.approx(-0.2)
    assert worst_condition({"jpeg_q30": 0.5, "blur_s2.0": 0.5, "clean": 0.9}) == (
        "blur_s2.0",
        0.5,
    )


@pytest.mark.parametrize(
    ("labels", "scores", "message"),
    [
        ([], [], "empty"),
        ([0], [0.2], "both"),
        ([0, 2], [0.2, 0.8], "0 or 1"),
        ([0, 1], [0.2], "equal length"),
        ([0, 1], [0.2, float("nan")], "finite"),
        ([0, 1], [-0.1, 0.8], r"\[0,1\]"),
    ],
)
def test_headline_metrics_reject_undefined_or_invalid_inputs(labels, scores, message):
    with pytest.raises(ValueError, match=message):
        auroc(labels, scores)


@pytest.mark.parametrize("threshold", [-0.1, 1.1, float("nan"), float("inf")])
def test_invalid_thresholds_fail_closed(threshold):
    with pytest.raises(ValueError, match="threshold"):
        confusion_counts(LABELS, SCORES, threshold)


def test_probability_helpers_reject_bad_configuration():
    with pytest.raises(ValueError, match="n_bins"):
        expected_calibration_error([0, 1], [0.1, 0.9], n_bins=0)
    with pytest.raises(ValueError, match="eps"):
        negative_log_likelihood([0, 1], [0.1, 0.9], eps=0.5)
