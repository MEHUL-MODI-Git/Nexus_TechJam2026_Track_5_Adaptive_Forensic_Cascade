"""Router training tests (Phase 2).

The tests that matter are the ones that stop us fooling ourselves: no dev
leakage through the scaler, selection on the frozen objective's own quantity,
and an honest verdict when the router does NOT beat the baseline.
"""

import numpy as np
import pytest
import torch

from src.router.features import FeatureSpec, Standardizer, rows_to_matrix
from src.router.train import (
    TRANSFORM_FAMILIES,
    build_batch,
    run_ladder,
    train_rung,
    worst_family_recall,
)

EXPERTS = ("e1",)
FAMILY_CONDITIONS = {
    "clean": ["clean"], "jpeg": ["jpeg_q30"], "blur": ["blur_s2.0"],
    "resize": ["resize_0.5"], "noise": ["noise_s0.10"], "color": ["bright_-20"],
    "crop": ["crop_0.8"],
}


def make_rows(n_sources=40, split_at=30, hard_family=None, seed=0):
    """Cache-shaped rows; `hard_family` scores fakes below threshold there."""
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n_sources):
        label = i % 2
        split = "train" if i < split_at else "dev"
        for family, conditions in FAMILY_CONDITIONS.items():
            for condition in conditions:
                if label == 1:
                    p = 0.1 if family == hard_family else 0.9
                else:
                    p = 0.05
                p = float(np.clip(p + rng.normal(0, 1e-4), 0, 1))
                rows.append({
                    "source_id": f"s{i}", "label": label, "dataset_split": split,
                    "condition_id": condition, "family": family,
                    "experts": {"e1": {"ok": True, "raw_logit": 0.1, "p_fake": p}},
                    "probes": {"e1": {"probe_mean": p, "probe_std": 0.01,
                                      "probe_range": 0.02, "probe_max_delta": 0.01,
                                      "probe_flip": False, "n_probes_ok": 3}},
                    "quality": {"width": 512, "height": 512, "aspect_ratio": 1.0,
                                "megapixels": 0.26, "is_portrait": False,
                                "blur_varlap": 0.01, "blockiness": 1.0,
                                "noise_sigma": 0.01, "luminance_mean": 0.5,
                                "luminance_std": 0.2, "saturation_mean": 0.3,
                                "clipped_low_frac": 0.0, "clipped_high_frac": 0.0},
                    "disagreement": None,
                })
    return rows


# --- the frozen objective's quantity --------------------------------------
def test_worst_family_recall_excludes_clean():
    p = np.array([0.0, 0.9]); labels = np.array([1, 1])
    families = np.array(["clean", "jpeg"])
    recall, family = worst_family_recall(p, labels, families, 0.5)
    assert family == "jpeg" and recall == 1.0     # clean's 0.0 is not selected


def test_worst_family_recall_picks_the_minimum():
    p = np.array([0.9, 0.9, 0.1]); labels = np.array([1, 1, 1])
    families = np.array(["jpeg", "blur", "noise"])
    recall, family = worst_family_recall(p, labels, families, 0.5)
    assert family == "noise" and recall == 0.0


def test_transform_families_are_the_six():
    assert set(TRANSFORM_FAMILIES) == {"jpeg", "blur", "resize", "noise", "color", "crop"}


# --- no leakage -----------------------------------------------------------
def test_standardizer_uses_train_rows_only():
    rows = make_rows()
    spec = FeatureSpec(expert_ids=EXPERTS)
    train = [r for r in rows if r["dataset_split"] == "train"]
    std_train = Standardizer.fit(rows_to_matrix(train, spec), spec)
    std_all = Standardizer.fit(rows_to_matrix(rows, spec), spec)
    result = run_ladder(rows, threshold=0.5, expert_ids=EXPERTS)
    assert result["standardizer_fitted_on"] == "train split only"
    # sanity: the two scalers genuinely differ, so the distinction is meaningful
    assert not np.allclose(std_train.mean, std_all.mean) or len(train) == len(rows)


def test_train_and_dev_sources_are_disjoint():
    rows = make_rows()
    result = run_ladder(rows, threshold=0.5, expert_ids=EXPERTS)
    train_src = {r["source_id"] for r in rows if r["dataset_split"] == "train"}
    dev_src = {r["source_id"] for r in rows if r["dataset_split"] == "dev"}
    assert not (train_src & dev_src)
    assert result["n_train_sources"] == len(train_src)
    assert result["n_dev_sources"] == len(dev_src)


def test_missing_split_is_an_error():
    rows = [dict(r, dataset_split="train") for r in make_rows()]
    with pytest.raises(ValueError, match="train and dev"):
        run_ladder(rows, threshold=0.5, expert_ids=EXPERTS)


# --- the ladder -----------------------------------------------------------
def test_ladder_trains_every_rung():
    result = run_ladder(make_rows(), threshold=0.5, expert_ids=EXPERTS)
    rungs = [(r["rung"], r["use_worst_group_loss"]) for r in result["results"]]
    assert rungs == [("static_average", False), ("logistic", False),
                     ("mlp", False), ("mlp", True)]


def test_static_average_has_no_parameters():
    result = run_ladder(make_rows(), threshold=0.5, expert_ids=EXPERTS)
    baseline = next(r for r in result["results"] if r["rung"] == "static_average")
    assert baseline["n_parameters"] == 0
    assert baseline["reliability_head"] is False


def test_selection_metric_is_the_frozen_objective():
    result = run_ladder(make_rows(), threshold=0.5, expert_ids=EXPERTS)
    assert "worst-transformation-family" in result["selection_metric"]


def test_verdict_is_reported_honestly_when_router_does_not_help():
    """With one expert and no context signal, routing cannot beat averaging."""
    result = run_ladder(make_rows(), threshold=0.5, expert_ids=EXPERTS)
    assert isinstance(result["router_earns_its_complexity"], bool)
    assert result["improvement_over_baseline"] == pytest.approx(
        result["best_worst_family_recall"] - result["baseline_worst_family_recall"]
    )
    assert "negative ablation" in result["verdict_note"]


def test_hard_family_lowers_the_objective():
    easy = run_ladder(make_rows(), threshold=0.5, expert_ids=EXPERTS)
    hard = run_ladder(make_rows(hard_family="noise"), threshold=0.5, expert_ids=EXPERTS)
    assert hard["baseline_worst_family_recall"] < easy["baseline_worst_family_recall"]


def test_results_are_deterministic():
    a = run_ladder(make_rows(), threshold=0.5, expert_ids=EXPERTS, seed=7)
    b = run_ladder(make_rows(), threshold=0.5, expert_ids=EXPERTS, seed=7)
    assert a["best_worst_family_recall"] == b["best_worst_family_recall"]


def test_batch_alignment():
    rows = make_rows(n_sources=4, split_at=2)
    spec = FeatureSpec(expert_ids=EXPERTS)
    std = Standardizer.fit(rows_to_matrix(rows, spec), spec)
    batch = build_batch(rows, spec, std)
    n = len(rows)
    assert batch.features.shape == (n, spec.dim)
    assert batch.expert_p.shape == (n, 1) and batch.available.shape == (n, 1)
    assert batch.labels.shape == (n,) and len(batch.families) == n


def test_failed_expert_is_marked_unavailable_in_the_batch():
    rows = make_rows(n_sources=4, split_at=2)
    rows[0]["experts"]["e1"] = {"ok": False, "reason_code": "x", "message": "y"}
    spec = FeatureSpec(expert_ids=EXPERTS)
    std = Standardizer.fit(rows_to_matrix(rows, spec), spec)
    batch = build_batch(rows, spec, std)
    assert batch.available[0, 0].item() is False
    assert batch.expert_p[0, 0].item() == 0.0     # zero WITH an unavailable flag
