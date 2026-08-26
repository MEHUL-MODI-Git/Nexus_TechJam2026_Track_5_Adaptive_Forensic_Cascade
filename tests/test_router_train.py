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
    save_checkpoint,
    train_rung,
    validate_cache_rows,
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
                    "cache_key": "K",
                    "experts": {"e1": {"ok": True,
                                       "raw_logit": float(np.log(p / (1 - p))),
                                       "p_fake": p}},
                    "probes": {"e1": {"probe_mean": p, "probe_std": 0.01,
                                      "probe_range": 0.02, "probe_max_delta": 0.01,
                                      "probe_scores": {"probe_jpeg_q92": p},
                                      "n_probes_ok": 3}},
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
    recall, family = worst_family_recall(p, labels, families, 0.5, require_all=False)
    assert family == "jpeg" and recall == 1.0     # clean's 0.0 is not selected


def test_worst_family_recall_picks_the_minimum():
    p = np.array([0.9, 0.9, 0.1]); labels = np.array([1, 1, 1])
    families = np.array(["jpeg", "blur", "noise"])
    recall, family = worst_family_recall(p, labels, families, 0.5, require_all=False)
    assert family == "noise" and recall == 0.0


def test_objective_refuses_a_reduced_family_set():
    """R10: silently skipping a family turns six into fewer while keeping the name."""
    p = np.array([0.9]); labels = np.array([1]); families = np.array(["jpeg"])
    with pytest.raises(ValueError, match="all six transform families"):
        worst_family_recall(p, labels, families, 0.5)


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
    """With TWO experts the comparison is real, so a null result must be stated
    as a reportable negative ablation rather than quietly dropped."""
    rows = make_rows()
    for row in rows:                       # a second expert that adds no signal
        row["experts"]["e2"] = dict(row["experts"]["e1"])
        row["probes"]["e2"] = dict(row["probes"]["e1"])
    result = run_ladder(rows, threshold=0.5, expert_ids=("e1", "e2"))
    assert result["fusion_comparison_degenerate"] is False
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
    assert batch.expert_logits.shape == (n, 1) and batch.available.shape == (n, 1)
    assert batch.labels.shape == (n,) and len(batch.families) == n


def test_failed_expert_is_marked_unavailable_in_the_batch():
    rows = make_rows(n_sources=4, split_at=2)
    rows[0]["experts"]["e1"] = {"ok": False, "reason_code": "x", "message": "y"}
    spec = FeatureSpec(expert_ids=EXPERTS)
    std = Standardizer.fit(rows_to_matrix(rows, spec), spec)
    batch = build_batch(rows, spec, std)
    assert batch.available[0, 0].item() is False
    assert batch.expert_logits[0, 0].item() == 0.0   # zero WITH an unavailable flag


# --- degeneracy guard -----------------------------------------------------
def test_single_expert_fusion_is_flagged_as_vacuous():
    """One expert ⇒ softmax weight 1.0 ⇒ every rung emits the primary score.

    Reporting that as "the router did not beat the baseline" would present a
    configuration artefact as a scientific finding.
    """
    result = run_ladder(make_rows(), threshold=0.5, expert_ids=("e1",))
    assert result["fusion_comparison_degenerate"] is True
    assert result["router_earns_its_complexity"] is False
    assert "VACUOUS" in result["verdict_note"]
    scores = {r["dev_worst_family_fake_recall"] for r in result["results"]}
    assert len(scores) == 1          # identical by construction, as claimed


def test_two_experts_are_not_flagged_degenerate():
    rows = make_rows()
    for row in rows:
        p = row["experts"]["e1"]["p_fake"]
        row["experts"]["e2"] = {"ok": True, "raw_logit": 0.0, "p_fake": 1.0 - p}
        row["probes"]["e2"] = dict(row["probes"]["e1"])
    result = run_ladder(rows, threshold=0.5, expert_ids=("e1", "e2"))
    assert result["fusion_comparison_degenerate"] is False


def test_degenerate_flag_overrides_a_spurious_improvement():
    result = run_ladder(make_rows(), threshold=0.5, expert_ids=("e1",))
    # even if delta were positive, N=1 must never claim the router earned its keep
    assert result["router_earns_its_complexity"] is False


# --- R12 / R20 / R21: checkpointing, exclusions, validation ---------------
def test_checkpoint_is_deployable(tmp_path):
    """R12: the trainer previously returned metrics only, so no rung could be
    loaded into the prediction service or reproduced."""
    import torch

    result = run_ladder(make_rows(), threshold=0.5, expert_ids=EXPERTS)
    path = save_checkpoint(result, tmp_path / "router.pt", threshold=0.5)
    payload = torch.load(path, weights_only=False)
    assert payload["schema_version"] == "router-checkpoint.v1"
    assert payload["rung"] == result["best_rung"]
    assert payload["expert_order"] == list(EXPERTS)
    assert payload["standardizer"]["mean"] and payload["feature_spec"]["dim"] > 0
    assert payload["fusion_space"] == "logit"
    assert payload["cache_key"] == "K"


def test_rows_with_every_expert_failed_are_excluded_not_trained():
    """R20: they fuse to p_fake=0, a confident REAL score no model produced."""
    rows = make_rows()
    for row in rows[:7]:
        row["experts"]["e1"] = {"ok": False, "reason_code": "x", "message": "y"}
    report = validate_cache_rows(rows, EXPERTS)
    assert report["dropped_all_experts_unavailable"] == 7
    assert all(r["experts"]["e1"]["ok"] for r in report["usable_rows"])


def test_dropped_rows_are_reported_in_the_artifact():
    rows = make_rows()
    for row in rows[:5]:
        row["experts"]["e1"] = {"ok": False, "reason_code": "x", "message": "y"}
    result = run_ladder(rows, threshold=0.5, expert_ids=EXPERTS)
    assert result["rows_dropped_all_experts_unavailable"] == 5


def test_non_finite_score_is_dropped():
    rows = make_rows()
    rows[0]["experts"]["e1"]["p_fake"] = float("nan")
    report = validate_cache_rows(rows, EXPERTS)
    assert report["dropped_invalid_scores"] == 1


def test_mixed_cache_keys_are_refused():
    rows = make_rows()
    rows[0]["cache_key"] = "OTHER"
    with pytest.raises(ValueError, match="never mix generations"):
        validate_cache_rows(rows, EXPERTS)


def test_source_in_both_splits_is_refused():
    """A leaked source makes dev measure memorisation."""
    rows = make_rows()
    for row in rows:
        if row["source_id"] == "s0":
            row["dataset_split"] = "dev"
    rows.append(dict(rows[0], dataset_split="train"))
    with pytest.raises(ValueError, match="BOTH train and dev"):
        validate_cache_rows(rows, EXPERTS)


def test_unknown_condition_is_refused():
    rows = make_rows()
    rows[0]["condition_id"] = "not_a_condition"
    with pytest.raises(ValueError, match="unknown condition_id"):
        validate_cache_rows(rows, EXPERTS)


def test_selection_uses_bootstrap_mean_and_clean_constraints():
    """R10: selection must be the frozen objective it claims to be."""
    result = run_ladder(make_rows(), threshold=0.5, expert_ids=EXPERTS,
                        bootstrap_replicates=25)
    assert "bootstrap-mean" in result["selection_metric"]
    assert "clean FPR" in result["selection_metric"]
    assert result["clean_constraints"]["max_clean_fpr"] >= 0
    for entry in result["results"]:
        assert "dev_worst_family_bootstrap_mean" in entry
        assert "satisfies_clean_constraints" in entry
        lo, hi = entry["dev_worst_family_ci95"]
        assert lo <= entry["dev_worst_family_bootstrap_mean"] <= hi


def test_placeholder_threshold_provenance_is_warned_about():
    """R22: reliability targets mean something different under a real threshold."""
    result = run_ladder(make_rows(), threshold=0.5, expert_ids=EXPERTS,
                        threshold_provenance="PLACEHOLDER-uncalibrated-phase0")
    assert result["threshold_provenance_warning"]
    assert "changes meaning" in result["threshold_provenance_warning"]


def test_fusion_happens_in_logit_space():
    result = run_ladder(make_rows(), threshold=0.5, expert_ids=EXPERTS)
    assert result["fusion_space"] == "logit"
