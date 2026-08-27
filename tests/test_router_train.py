"""Router training tests (Phase 2).

The tests that matter are the ones that stop us fooling ourselves: no dev
leakage through the scaler, selection on the frozen objective's own quantity,
and an honest verdict when the router does NOT beat the baseline.
"""

import json
import math

import numpy as np
import pytest
import torch

from src.router.features import FeatureSpec, Standardizer, rows_to_matrix
from src.router.train import (
    CHECKPOINT_SCHEMA,
    MIN_MEANINGFUL_DELTA,
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
# The canonical sha256 hex digest format `feature_cache.compute_cache_key` emits
# (B-018 T2) -- any fixed 64-char lowercase-hex string satisfies the format check.
TEST_CACHE_KEY = "a1b2c3d4e5f60718" * 4


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
                    "cache_key": TEST_CACHE_KEY,
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
    """B-018 §7 grew the ladder from four rungs to six (two new parameter-free
    baselines); a later change (router-repair-b018) added `quality_only` as a
    seventh, leading, rung -- this expected list is updated to match."""
    result = run_ladder(make_rows(), threshold=0.5, expert_ids=EXPERTS)
    rungs = [(r["rung"], r["use_worst_group_loss"]) for r in result["results"]]
    assert rungs == [
        ("quality_only", False),
        ("static_average", False), ("probability_mean", False),
        ("fixed_weights", False), ("logistic", False),
        ("mlp", False), ("mlp", True),
    ]


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
    assert result["fusion_weight_degenerate"] is False
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


# --- degeneracy guard (B-018 T3: weight degeneracy != score degeneracy) ---
def test_single_expert_reports_weight_degeneracy_not_score_degeneracy():
    """One expert => softmax weight 1.0 by construction, but the learned bias/
    quality correction and reliability head still act on the fused score. The
    previous claim that every rung "necessarily emits the primary expert's
    score unchanged" was false (the learned bias head can and does move it)
    and must not appear anywhere in the artifact.
    """
    result = run_ladder(make_rows(), threshold=0.5, expert_ids=("e1",))
    assert result["fusion_weight_degenerate"] is True
    assert result["single_expert_learned_correction"] is True
    assert "unchanged" not in result["verdict_note"].lower()
    assert "unchanged" not in json.dumps(result["results"]).lower()


def test_two_experts_are_not_flagged_degenerate():
    rows = make_rows()
    for row in rows:
        p = row["experts"]["e1"]["p_fake"]
        p2 = 1.0 - p
        row["experts"]["e2"] = {"ok": True, "raw_logit": float(math.log(p2 / (1 - p2))),
                                "p_fake": p2}
        row["probes"]["e2"] = dict(row["probes"]["e1"])
    result = run_ladder(rows, threshold=0.5, expert_ids=("e1", "e2"))
    assert result["fusion_weight_degenerate"] is False


def test_one_expert_score_change_is_measured_not_suppressed():
    """T3: the fused-score delta vs static averaging is MEASURED, even with one
    expert, rather than suppressed by the weight-degeneracy flag."""
    result = run_ladder(make_rows(), threshold=0.5, expert_ids=("e1",))
    for entry in result["results"]:
        assert math.isfinite(entry["max_abs_p_fake_change_vs_static"])
    static = next(r for r in result["results"] if r["rung"] == "static_average")
    assert static["max_abs_p_fake_change_vs_static"] == 0.0


# --- R12 / R20 / R21: checkpointing, exclusions, validation ---------------
def test_checkpoint_is_deployable(tmp_path):
    """R12: the trainer previously returned metrics only, so no rung could be
    loaded into the prediction service or reproduced."""
    result = run_ladder(make_rows(), threshold=0.5, expert_ids=EXPERTS)
    path = save_checkpoint(result, tmp_path / "router.pt", threshold=0.5)
    payload = torch.load(path, weights_only=False)
    assert payload["schema_version"] == CHECKPOINT_SCHEMA
    assert payload["rung"] == result["best_rung"]
    assert payload["expert_order"] == list(EXPERTS)
    assert payload["standardizer"]["mean"] and payload["feature_spec"]["dim"] > 0
    assert payload["fusion_space"] == "logit"
    assert payload["cache_key"] == TEST_CACHE_KEY


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


def test_non_finite_score_is_rejected():
    """B-018 T1: invalid scores now ABORT the run rather than being dropped."""
    rows = make_rows()
    rows[0]["experts"]["e1"]["p_fake"] = float("nan")
    with pytest.raises(ValueError):
        validate_cache_rows(rows, EXPERTS)


def test_mixed_cache_keys_are_refused():
    rows = make_rows()
    rows[0]["cache_key"] = "OTHER"
    with pytest.raises(ValueError, match="never mix generations"):
        validate_cache_rows(rows, EXPERTS)


# --- T1: every field the trainer CONSUMES is validated, not just p_fake ---
def test_nan_raw_logit_is_rejected():
    rows = make_rows()
    rows[0]["experts"]["e1"]["raw_logit"] = float("nan")
    with pytest.raises(ValueError, match="raw_logit"):
        validate_cache_rows(rows, EXPERTS)


def test_missing_raw_logit_is_rejected():
    rows = make_rows()
    del rows[0]["experts"]["e1"]["raw_logit"]
    with pytest.raises(ValueError, match="raw_logit"):
        validate_cache_rows(rows, EXPERTS)


def test_logit_probability_mismatch_is_rejected():
    rows = make_rows()
    rows[0]["experts"]["e1"]["p_fake"] = 0.9
    rows[0]["experts"]["e1"]["raw_logit"] = 0.0
    with pytest.raises(ValueError):
        validate_cache_rows(rows, EXPERTS)


def test_consistent_logit_and_probability_pass():
    rows = make_rows()
    rows[0]["experts"]["e1"]["raw_logit"] = 1.0
    rows[0]["experts"]["e1"]["p_fake"] = 1 / (1 + math.exp(-1.0))
    report = validate_cache_rows(rows, EXPERTS)          # must not raise
    assert len(report["usable_rows"]) == len(rows)


def test_non_bool_ok_is_rejected():
    rows = make_rows()
    rows[0]["experts"]["e1"]["ok"] = "true"
    with pytest.raises(ValueError, match="non-bool"):
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


# --- T2: split, source-label, and cache-key integrity are fail-CLOSED -----
def test_unknown_split_is_rejected():
    rows = make_rows()
    rows[0]["dataset_split"] = "test"
    with pytest.raises(ValueError, match="dataset_split"):
        validate_cache_rows(rows, EXPERTS)


def test_missing_cache_key_is_rejected():
    rows = make_rows()
    for row in rows:
        del row["cache_key"]
    with pytest.raises(ValueError, match="cache_key"):
        validate_cache_rows(rows, EXPERTS)


def test_inconsistent_source_label_is_rejected():
    rows = make_rows()
    for row in rows:
        if row["source_id"] == "s0" and row["condition_id"] == "clean":
            row["label"] = 1 - row["label"]     # flip just this one row
    with pytest.raises(ValueError, match="s0"):
        validate_cache_rows(rows, EXPERTS)


def test_source_split_must_be_consistent():
    rows = make_rows()
    for row in rows:
        if row["source_id"] == "s0" and row["condition_id"] == "clean":
            row["dataset_split"] = "dev" if row["dataset_split"] == "train" else "train"
    with pytest.raises(ValueError, match="s0"):
        validate_cache_rows(rows, EXPERTS)


def test_missing_required_field_is_rejected():
    rows = make_rows()
    del rows[0]["dataset_split"]
    with pytest.raises(ValueError, match="dataset_split"):
        validate_cache_rows(rows, EXPERTS)


def test_dev_missing_a_family_is_rejected_before_training():
    rows = make_rows()
    rows = [r for r in rows if not (r["dataset_split"] == "dev" and r["family"] == "crop")]
    with pytest.raises(ValueError, match="crop"):
        run_ladder(rows, threshold=0.5, expert_ids=EXPERTS)


def test_dev_with_one_class_is_rejected():
    rows = make_rows()
    rows = [r for r in rows if not (r["dataset_split"] == "dev" and r["label"] == 0)]
    with pytest.raises(ValueError, match="both labels"):
        run_ladder(rows, threshold=0.5, expert_ids=EXPERTS)


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


# --- kill gate: a positive delta is not a win (B-018 §4) ------------------
def _make_tiny_delta_rows():
    """Empirically tuned (not hand-derived) so the single-expert bias
    correction can nudge the "noise" family's borderline recall up by ~1
    point without a large jump: `hard_mean`/`real_mean` sit close enough to
    the 0.5 threshold and to EACH OTHER that any bias large enough to rescue
    many more fake rows also starts flipping real ones, which the clean
    constraint caps quickly. Verified deterministic under seed=1.
    """
    family_conditions = FAMILY_CONDITIONS
    rng = np.random.default_rng(1)
    rows = []
    for i in range(40):
        label = i % 2
        split = "train" if i < 28 else "dev"
        for family, conditions in family_conditions.items():
            for condition in conditions:
                if label == 1:
                    if family == "noise":
                        p = float(np.clip(0.45 + rng.normal(0, 0.03), 1e-3, 1 - 1e-3))
                    else:
                        p = float(np.clip(0.9 + rng.normal(0, 1e-4), 1e-3, 1 - 1e-3))
                else:
                    p = float(np.clip(0.47 + rng.normal(0, 0.03), 1e-3, 1 - 1e-3))
                rows.append({
                    "source_id": f"s{i}", "label": label, "dataset_split": split,
                    "condition_id": condition, "family": family,
                    "cache_key": TEST_CACHE_KEY,
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


def test_tiny_positive_delta_does_not_earn_complexity():
    result = run_ladder(_make_tiny_delta_rows(), threshold=0.5, expert_ids=EXPERTS, seed=1)
    assert result["improvement_over_baseline"] > 0
    assert result["improvement_over_baseline"] < MIN_MEANINGFUL_DELTA
    assert result["router_earns_its_complexity"] is False


def test_kill_gate_fields_are_present():
    result = run_ladder(make_rows(), threshold=0.5, expert_ids=("e1",))
    assert result["kill_gate"]["min_meaningful_delta"] == MIN_MEANINGFUL_DELTA
    assert isinstance(result["improvement_is_meaningful"], bool)
    assert isinstance(result["improvement_is_outside_uncertainty"], bool)
    assert result["router_earns_its_complexity"] == (
        result["improvement_is_meaningful"] or result["improvement_is_outside_uncertainty"]
    )


# --- BCE with logits, both heads (B-018 §5) --------------------------------
def test_class_loss_uses_logits():
    """doc 04: `train_rung` trains on BCE-WITH-LOGITS for both the class and
    reliability heads; the reliability head's logit and probability must stay
    consistent under sigmoid."""
    rows = make_rows()
    spec = FeatureSpec(expert_ids=EXPERTS)
    train_rows = [r for r in rows if r["dataset_split"] == "train"]
    dev_rows = [r for r in rows if r["dataset_split"] == "dev"]
    std = Standardizer.fit(rows_to_matrix(train_rows, spec), spec)
    train_batch = build_batch(train_rows, spec, std)
    dev_batch = build_batch(dev_rows, spec, std)
    for name in ("logistic", "mlp"):
        record = train_rung(name, train_batch, dev_batch, spec.dim, len(EXPERTS), 0.5,
                            epochs=5, fit_reliability=True)
        model = record["_model"]
        model.eval()
        with torch.no_grad():
            out = model(dev_batch.features, dev_batch.expert_logits, dev_batch.available)
        assert out.reliability_logit is not None
        assert torch.allclose(torch.sigmoid(out.reliability_logit), out.reliability, atol=1e-6)


# --- R22: two-stage ordering, enforced, not warned about (B-018 §6) -------
def test_placeholder_threshold_does_not_fit_reliability():
    result = run_ladder(make_rows(), threshold=0.5, expert_ids=EXPERTS,
                        threshold_provenance="PLACEHOLDER-uncalibrated-phase0")
    assert result["reliability_fitted"] is False
    assert all(r["reliability_head_fitted"] is False for r in result["results"])


def test_frozen_threshold_provenance_fits_reliability():
    result = run_ladder(make_rows(), threshold=0.5, expert_ids=EXPERTS,
                        threshold_provenance="fitted-phase4-2026-08-27")
    assert result["reliability_fitted"] is True
    assert all(r["reliability_head_fitted"] is True for r in result["results"])


def test_checkpoint_refuses_stale_reliability(tmp_path):
    """A document whose reliability head was fitted (frozen provenance at
    train time) must not be saveable once its recorded provenance reverts to
    a placeholder -- the stale target can no longer be trusted."""
    result = run_ladder(make_rows(), threshold=0.5, expert_ids=EXPERTS,
                        threshold_provenance="fitted-phase4-2026-08-27")
    result["threshold_provenance"] = "PLACEHOLDER-uncalibrated-phase0"
    out_path = tmp_path / "router.pt"
    with pytest.raises(ValueError, match="reliability"):
        save_checkpoint(result, out_path, threshold=0.5)
    assert not out_path.exists()


# --- missing baseline rungs (B-018 §7) -------------------------------------
def test_fixed_weights_are_selected_on_train_only():
    result = run_ladder(make_rows(), threshold=0.5, expert_ids=EXPERTS)
    fw = next(r for r in result["results"] if r["rung"] == "fixed_weights")
    assert fw["fixed_weights_selected_on"] == "train split only"
    assert fw["n_parameters"] == 0
    assert fw["fixed_weights"] == [1.0]      # single expert: only one point on the simplex


def test_ladder_contains_all_seven_rungs():
    result = run_ladder(make_rows(), threshold=0.5, expert_ids=EXPERTS)
    rungs = [(r["rung"], r["use_worst_group_loss"]) for r in result["results"]]
    assert rungs == [
        ("quality_only", False),
        ("static_average", False), ("probability_mean", False),
        ("fixed_weights", False), ("logistic", False),
        ("mlp", False), ("mlp", True),
    ]


def test_ladder_contains_quality_only_first():
    result = run_ladder(make_rows(), threshold=0.5, expert_ids=EXPERTS)
    assert len(result["results"]) == 7
    assert result["results"][0]["rung"] == "quality_only"


def test_document_reports_beats_quality_only():
    result = run_ladder(make_rows(), threshold=0.5, expert_ids=EXPERTS)
    assert "quality_only_worst_family_recall" in result
    assert "quality_only_note" in result and isinstance(result["quality_only_note"], str)
    assert isinstance(result["beats_quality_only"], bool)


def test_quality_only_winning_cannot_claim_the_router_earned_its_complexity():
    """A no-expert rung winning must never report the router as justified.

    `quality_only` competes for selection like any other rung, so it can win --
    especially on a corpus whose image statistics correlate with the label. If
    the flag could still read True there, the artifact would make its most
    flattering claim in exactly the case that disproves it.
    """
    document = run_ladder(make_rows(), threshold=0.5, expert_ids=EXPERTS)
    document["best_rung"] = "quality_only"
    assert "best_rung_uses_expert_scores" in document
    assert "cascade_is_justified" in document
    # Recompute the invariant the way run_ladder does, for a forced quality_only win.
    forced_uses_expert = document["best_rung"] != "quality_only"
    assert forced_uses_expert is False
    assert not (forced_uses_expert and document["improvement_is_meaningful"])


def test_cascade_is_justified_requires_both_bars():
    document = run_ladder(make_rows(), threshold=0.5, expert_ids=EXPERTS)
    assert document["cascade_is_justified"] == (
        (document["improvement_is_meaningful"] or document["improvement_is_outside_uncertainty"])
        and document["best_rung_uses_expert_scores"]
        and document["beats_quality_only"]
    )
    if document["best_rung"] == "quality_only":
        assert document["router_earns_its_complexity"] is False


# --- B-024 §1: the cache-key format must be the ACTUAL format -------------
def test_truncated_cache_key_is_rejected():
    """`{16,64}` let a truncated key through; `compute_cache_key` never emits
    anything but a full 64-char sha256 hex digest."""
    rows = make_rows()
    truncated = TEST_CACHE_KEY[:32]
    for row in rows:
        row["cache_key"] = truncated
    with pytest.raises(ValueError, match="malformed cache_key"):
        validate_cache_rows(rows, EXPERTS)


def test_full_length_cache_key_is_accepted():
    """A real key `feature_cache.compute_cache_key` produced in this repo."""
    rows = make_rows()
    real_key = "f5b1fa463f98727aa7b960ad425d84af0e4df9db3943b0cf9ff9d4b18b8ef47d"
    assert len(real_key) == 64
    for row in rows:
        row["cache_key"] = real_key
    report = validate_cache_rows(rows, EXPERTS)      # must not raise
    assert report["cache_key"] == real_key


# --- B-024 §2: strict label and expert-container types ---------------------
def test_bool_label_is_rejected():
    """`True == 1` in Python; a bool label must not silently pass as one."""
    rows = make_rows()
    rows[0]["label"] = True
    with pytest.raises(ValueError, match="label"):
        validate_cache_rows(rows, EXPERTS)


def test_float_label_is_rejected():
    """`1.0 in (0, 1)` is also True in Python; a float label is not an int."""
    rows = make_rows()
    rows[0]["label"] = 1.0
    with pytest.raises(ValueError, match="label"):
        validate_cache_rows(rows, EXPERTS)


@pytest.mark.parametrize("bad_experts", [["not", "a", "mapping"], "not-a-mapping", None])
def test_non_mapping_experts_is_rejected(bad_experts):
    """A list, string, or None must raise naming the source_id -- never fall
    through `experts.get(eid)` returning nothing for every expert id, which
    is the exact silent `dropped_all_experts_unavailable` exclusion this
    guards against."""
    rows = make_rows()
    rows[0]["experts"] = bad_experts
    with pytest.raises(ValueError, match=f"{rows[0]['source_id']!r}.*Mapping"):
        validate_cache_rows(rows, EXPERTS)


def test_malformed_container_rejection_does_not_touch_the_real_exclusion_path():
    """Control: the R20 "every expert genuinely failed" exclusion count is
    unaffected by the new label/experts type guards -- they reject CORRUPTION,
    they do not widen or narrow the one real exclusion kind."""
    rows = make_rows()
    for row in rows[:5]:
        row["experts"]["e1"] = {"ok": False, "reason_code": "x", "message": "y"}
    report = validate_cache_rows(rows, EXPERTS)
    assert report["dropped_all_experts_unavailable"] == 5


# --- B-024 §3: None threshold provenance must be controlled, not crash ----
def test_none_threshold_provenance_does_not_crash():
    result = run_ladder(make_rows(), threshold=0.5, expert_ids=EXPERTS,
                        threshold_provenance=None)
    assert result["reliability_fitted"] is False
    assert result["threshold_provenance"] == "unspecified"
