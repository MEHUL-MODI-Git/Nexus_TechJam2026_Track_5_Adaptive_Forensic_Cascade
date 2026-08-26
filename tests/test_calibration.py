"""Calibration + threshold-selection tests (training workstream).

The objective is FROZEN across both agents, so these tests exist to prove the
implementation matches the words in DECISIONS -- especially the three parts
that are easy to get subtly wrong: clean is excluded from the objective,
severities pool within a family, and the bootstrap unit is the source.
"""

import json
import math

import numpy as np
import pytest

from src.router.calibration import (
    DevSet,
    ThresholdArtifact,
    apply_temperature_bias,
    balanced_accuracy,
    binary_entropy,
    bootstrap_worst_family_recall,
    expected_calibration_error,
    fake_recall,
    fit_temperature_bias,
    logit,
    select_threshold,
    sigmoid,
    worst_exact_condition_fake_recall,
    worst_family_fake_recall,
)

FAMILIES = {
    "clean": ["clean"],
    "jpeg": ["jpeg_q90", "jpeg_q70", "jpeg_q50", "jpeg_q30"],
    "blur": ["blur_s0.5", "blur_s1.0", "blur_s2.0"],
    "resize": ["resize_0.5", "resize_0.25"],
    "noise": ["noise_s0.02", "noise_s0.05", "noise_s0.10"],
    "color": ["bright_-20", "bright_+20", "contrast_-20", "contrast_+20",
              "saturation_-20", "saturation_+20"],
    "crop": ["crop_0.8"],
}


def make_dev(n_sources=40, family_fake_score=None, real_score=0.05, seed=0):
    """Synthetic dev set with per-family fake scores, so the worst family is known."""
    family_fake_score = family_fake_score or {}
    rng = np.random.default_rng(seed)
    sids, conds, fams, labels, scores = [], [], [], [], []
    for i in range(n_sources):
        label = i % 2  # balanced
        sid = f"s{i:03d}"
        for family, condition_ids in FAMILIES.items():
            for condition in condition_ids:
                sids.append(sid)
                conds.append(condition)
                fams.append(family)
                labels.append(label)
                if label == 1:
                    base = family_fake_score.get(family, 0.9)
                else:
                    base = real_score
                scores.append(float(np.clip(base + rng.normal(0, 1e-4), 0, 1)))
    return DevSet(
        source_ids=np.array(sids), condition_ids=np.array(conds),
        families=np.array(fams), labels=np.array(labels), scores=np.array(scores),
    )


# --- scalar helpers -------------------------------------------------------
def test_binary_entropy_endpoints_and_peak():
    assert binary_entropy(0.0) == 0.0
    assert binary_entropy(1.0) == 0.0
    assert binary_entropy(0.5) == pytest.approx(math.log(2))


@pytest.mark.parametrize("bad", [-0.1, 1.1, float("nan")])
def test_binary_entropy_rejects_invalid(bad):
    with pytest.raises(ValueError):
        binary_entropy(bad)


def test_logit_sigmoid_roundtrip():
    p = np.array([0.01, 0.5, 0.99])
    assert np.allclose(sigmoid(logit(p)), p, atol=1e-9)


def test_logit_clips_instead_of_infinity():
    assert np.isfinite(logit(np.array([0.0, 1.0]))).all()


# --- rates ----------------------------------------------------------------
def test_threshold_boundary_predicts_fake():
    # p == threshold must count as AI-generated (matches the eval contract).
    scores = np.array([0.5, 0.5])
    labels = np.array([1, 0])
    assert fake_recall(scores, labels, 0.5) == 1.0


def test_balanced_accuracy_perfect_and_chance():
    s = np.array([0.9, 0.9, 0.1, 0.1])
    y = np.array([1, 1, 0, 0])
    assert balanced_accuracy(s, y, 0.5) == 1.0
    assert balanced_accuracy(np.array([0.9] * 4), y, 0.5) == 0.5


# --- the frozen objective -------------------------------------------------
def test_objective_excludes_clean():
    """Clean must never enter the minimum -- it enters only via constraints."""
    # clean is the WORST family by far; if it were included it would be selected.
    dev = make_dev(family_fake_score={"clean": 0.0, "crop": 0.30})
    value, family = worst_family_fake_recall(dev, threshold=0.5)
    assert family == "crop"          # not "clean"
    assert value == pytest.approx(0.0, abs=1e-9)
    assert "clean" not in dev.transform_families


def test_exactly_six_transform_families():
    dev = make_dev()
    assert dev.transform_families == ["blur", "color", "crop", "jpeg", "noise", "resize"]


def test_severities_pool_within_family():
    """A family's recall is computed over ALL its severities pooled together."""
    dev = make_dev()
    # Rewrite jpeg: half its conditions detected, half missed -> pooled recall 0.5
    jpeg_mask = dev.families == "jpeg"
    scores = dev.scores.copy()
    hard = jpeg_mask & (dev.labels == 1) & np.isin(dev.condition_ids, ["jpeg_q50", "jpeg_q30"])
    easy = jpeg_mask & (dev.labels == 1) & np.isin(dev.condition_ids, ["jpeg_q90", "jpeg_q70"])
    scores[hard] = 0.10
    scores[easy] = 0.95
    pooled = DevSet(dev.source_ids, dev.condition_ids, dev.families, dev.labels, scores)
    value, family = worst_family_fake_recall(pooled, threshold=0.5)
    assert family == "jpeg"
    assert value == pytest.approx(0.5)   # pooled, NOT the 0.0 of the worst severity


def test_worst_exact_condition_is_reported_separately():
    dev = make_dev()
    scores = dev.scores.copy()
    scores[(dev.condition_ids == "jpeg_q30") & (dev.labels == 1)] = 0.01
    d = DevSet(dev.source_ids, dev.condition_ids, dev.families, dev.labels, scores)
    recall, condition = worst_exact_condition_fake_recall(d, threshold=0.5)
    assert condition == "jpeg_q30"
    assert recall == pytest.approx(0.0)
    # the family value stays higher because severities pool
    assert worst_family_fake_recall(d, 0.5)[0] > recall


def test_family_with_no_fake_rows_is_skipped_not_zero():
    dev = make_dev()
    keep = ~((dev.families == "crop") & (dev.labels == 1))
    d = DevSet(dev.source_ids[keep], dev.condition_ids[keep], dev.families[keep],
               dev.labels[keep], dev.scores[keep])
    value, family = worst_family_fake_recall(d, 0.5)
    assert family != "crop"          # absent measurement != failure to detect
    assert value > 0.0


# --- bootstrap ------------------------------------------------------------
def test_bootstrap_is_deterministic_given_seed():
    dev = make_dev()
    a = bootstrap_worst_family_recall(dev, 0.5, n_replicates=50, seed=7)
    b = bootstrap_worst_family_recall(dev, 0.5, n_replicates=50, seed=7)
    assert a == b


def test_bootstrap_ci_brackets_the_mean():
    dev = make_dev(family_fake_score={"crop": 0.55})
    mean, (lo, hi) = bootstrap_worst_family_recall(dev, 0.5, n_replicates=100, seed=1)
    assert lo <= mean <= hi


def test_bootstrap_rejects_inconsistent_source_labels():
    dev = make_dev()
    labels = dev.labels.copy()
    labels[0] = 1 - labels[0]  # one view of a source disagrees with the rest
    d = DevSet(dev.source_ids, dev.condition_ids, dev.families, labels, dev.scores)
    with pytest.raises(ValueError, match="inconsistent labels"):
        bootstrap_worst_family_recall(d, 0.5, n_replicates=5)


def test_bootstrap_needs_both_classes():
    dev = make_dev()
    keep = dev.labels == 1
    d = DevSet(dev.source_ids[keep], dev.condition_ids[keep], dev.families[keep],
               dev.labels[keep], dev.scores[keep])
    with pytest.raises(ValueError, match="both classes"):
        bootstrap_worst_family_recall(d, 0.5, n_replicates=5)


# --- selection ------------------------------------------------------------
def test_select_threshold_produces_valid_artifact():
    dev = make_dev(family_fake_score={"crop": 0.60, "jpeg": 0.75})
    art = select_threshold(dev, n_replicates=40, pipeline_version="0.1.0")
    assert isinstance(art, ThresholdArtifact)
    assert art.schema_version == "threshold-artifact.v1"
    assert art.feasible is True
    assert art.selection_granularity == "family"
    assert 0.0 <= art.threshold <= 1.0
    assert art.worst_family in dev.transform_families
    assert art.bootstrap["unit"] == "source_id"
    assert art.bootstrap["stratified_by"] == "label"
    assert json.loads(json.dumps(art.to_json_dict()))["threshold"] == art.threshold


def test_selected_threshold_respects_clean_constraints():
    dev = make_dev(family_fake_score={"crop": 0.60})
    art = select_threshold(dev, n_replicates=40)
    assert art.clean_fpr <= art.constraint_max_clean_fpr + 1e-12
    assert art.clean_bacc >= art.constraint_min_clean_bacc - 1e-12


def test_infeasible_run_is_recorded_not_silently_relaxed():
    dev = make_dev(family_fake_score={"crop": 0.60})
    art = select_threshold(
        dev, n_replicates=20,
        max_clean_fpr_increase=-1.0,   # impossible constraint
        max_clean_bacc_drop=-1.0,
    )
    assert art.feasible is False
    assert any("infeasible" in w for w in art.warnings)
    assert art.threshold == 0.5        # fell back to baseline, did not relax


def test_selection_prefers_higher_worst_family_recall():
    """A threshold that rescues the worst family must win."""
    dev = make_dev(family_fake_score={"crop": 0.30})
    art = select_threshold(dev, n_replicates=40, candidates=np.array([0.2, 0.5, 0.9]))
    # only a threshold at/below 0.30 detects the crop fakes
    assert art.threshold == pytest.approx(0.2)
    assert art.objective_value == pytest.approx(1.0, abs=0.05)


def test_artifact_records_provenance_for_audit():
    dev = make_dev()
    art = select_threshold(dev, n_replicates=20, dev_manifest_sha256="abc",
                           config_sha256="def", pipeline_version="0.1.0",
                           fitting_code_version="v1")
    for value in (art.dev_manifest_sha256, art.config_sha256,
                  art.pipeline_version, art.fitting_code_version, art.created_at):
        assert value
    assert art.n_dev_sources == 40


def test_requires_clean_rows():
    dev = make_dev()
    keep = dev.families != "clean"
    d = DevSet(dev.source_ids[keep], dev.condition_ids[keep], dev.families[keep],
               dev.labels[keep], dev.scores[keep])
    with pytest.raises(ValueError, match="clean rows"):
        select_threshold(d, n_replicates=5)


def test_exact_condition_upgrade_is_flagged_not_taken():
    dev = make_dev(n_sources=1200)   # >=500 fake sources per condition
    art = select_threshold(dev, n_replicates=5, candidates=np.array([0.5]))
    assert art.n_fake_sources_per_exact_condition_min >= 500
    assert art.selection_granularity == "family"     # still family
    assert any("PERMITS upgrading" in w for w in art.warnings)


# --- temperature/bias calibration ----------------------------------------
def test_recovers_known_temperature():
    rng = np.random.default_rng(0)
    true_logits = rng.normal(0, 2.0, 20000)
    labels = (rng.random(20000) < sigmoid(true_logits)).astype(float)
    miscalibrated = true_logits * 3.0          # T should come back near 3
    T, b = fit_temperature_bias(miscalibrated, labels, max_iter=4000, lr=0.5)
    assert 2.0 < T < 4.5
    assert abs(b) < 0.5


def test_calibration_improves_ece():
    rng = np.random.default_rng(1)
    true_logits = rng.normal(0, 2.0, 8000)
    labels = (rng.random(8000) < sigmoid(true_logits)).astype(float)
    over = true_logits * 3.0
    before = expected_calibration_error(sigmoid(over), labels)
    T, b = fit_temperature_bias(over, labels, max_iter=3000, lr=0.5)
    after = expected_calibration_error(apply_temperature_bias(over, T, b), labels)
    assert after < before


def test_apply_rejects_non_positive_temperature():
    with pytest.raises(ValueError):
        apply_temperature_bias(np.array([0.1]), 0.0, 0.0)


def test_ece_perfect_calibration_is_zero():
    probs = np.concatenate([np.zeros(50), np.ones(50)])
    labels = np.concatenate([np.zeros(50), np.ones(50)])
    assert expected_calibration_error(probs, labels) == pytest.approx(0.0)


def test_ece_includes_edge_bins():
    # p == 0.0 must land in the first bin, not be dropped.
    probs = np.array([0.0, 0.0, 1.0, 1.0])
    labels = np.array([1.0, 1.0, 0.0, 0.0])   # maximally wrong
    assert expected_calibration_error(probs, labels) == pytest.approx(1.0)


def test_fit_rejects_shape_mismatch():
    with pytest.raises(ValueError):
        fit_temperature_bias(np.zeros(5), np.zeros(4))


# --- B-013: strict protocol validation before any artifact is produced ---
def test_selection_rejects_p_fake_out_of_range():
    dev = make_dev()
    scores = dev.scores.copy()
    scores[5] = 1.7
    d = DevSet(dev.source_ids, dev.condition_ids, dev.families, dev.labels, scores)
    with pytest.raises(ValueError, match=r"outside \[0,1\]"):
        select_threshold(d, n_replicates=5)


def test_selection_rejects_unknown_condition_id():
    dev = make_dev()
    conds = dev.condition_ids.copy()
    conds[0] = "jpeg_q42"
    d = DevSet(dev.source_ids, conds, dev.families, dev.labels, dev.scores)
    with pytest.raises(ValueError, match="unknown condition ids"):
        select_threshold(d, n_replicates=5)


def test_selection_rejects_family_condition_mismatch():
    dev = make_dev()
    fams = dev.families.copy()
    fams[dev.condition_ids == "jpeg_q90"] = "blur"     # mislabelled family
    d = DevSet(dev.source_ids, dev.condition_ids, fams, dev.labels, dev.scores)
    with pytest.raises(ValueError, match="belongs to"):
        select_threshold(d, n_replicates=5)


def test_selection_rejects_inconsistent_source_labels():
    dev = make_dev()
    labels = dev.labels.copy()
    labels[0] = 1 - labels[0]
    d = DevSet(dev.source_ids, dev.condition_ids, dev.families, labels, dev.scores)
    with pytest.raises(ValueError, match="inconsistent labels"):
        select_threshold(d, n_replicates=5)


def test_selection_refuses_a_five_family_objective():
    """The frozen objective must not silently become an easier five-family one."""
    dev = make_dev()
    keep = dev.families != "crop"
    d = DevSet(dev.source_ids[keep], dev.condition_ids[keep], dev.families[keep],
               dev.labels[keep], dev.scores[keep])
    with pytest.raises(ValueError, match="all six transform families"):
        select_threshold(d, n_replicates=5)


def test_selection_refuses_family_without_fake_rows():
    dev = make_dev()
    keep = ~((dev.families == "crop") & (dev.labels == 1))
    d = DevSet(dev.source_ids[keep], dev.condition_ids[keep], dev.families[keep],
               dev.labels[keep], dev.scores[keep])
    with pytest.raises(ValueError, match="no fake rows"):
        select_threshold(d, n_replicates=5)


def test_selection_requires_both_classes_in_clean():
    dev = make_dev()
    drop = (dev.families == "clean") & (dev.labels == 0)
    keep = ~drop
    d = DevSet(dev.source_ids[keep], dev.condition_ids[keep], dev.families[keep],
               dev.labels[keep], dev.scores[keep])
    with pytest.raises(ValueError, match="both classes"):
        select_threshold(d, n_replicates=5)


@pytest.mark.parametrize("bad", [np.array([]), np.array([0.5, np.nan]), np.array([1.5])])
def test_invalid_candidates_rejected(bad):
    dev = make_dev()
    with pytest.raises(ValueError):
        select_threshold(dev, n_replicates=5, candidates=bad)


def test_tie_break_is_deterministic_and_recorded():
    """Equal objective values must resolve by a recorded rule, not by grid order."""
    dev = make_dev(family_fake_score={f: 0.9 for f in
                                      ("jpeg", "blur", "resize", "noise", "color", "crop")})
    cands = np.array([0.1, 0.2, 0.3])   # all detect everything -> objective ties
    a = select_threshold(dev, n_replicates=10, candidates=cands)
    b = select_threshold(dev, n_replicates=10, candidates=cands[::-1])
    assert a.threshold == b.threshold           # order-independent
    assert a.tie_break.startswith("objective")


# --- artifact save/load ---------------------------------------------------
def test_artifact_roundtrip_validates(tmp_path):
    art = select_threshold(make_dev(), n_replicates=10)
    path = tmp_path / "t.json"
    art.save(path)
    loaded = ThresholdArtifact.load(path)
    assert loaded.threshold == art.threshold
    assert loaded.tie_break == art.tie_break


def test_artifact_save_is_atomic(tmp_path):
    art = select_threshold(make_dev(), n_replicates=10)
    out = tmp_path / "nested" / "t.json"
    art.save(out)
    assert out.exists()
    assert not list(out.parent.glob("*.tmp"))


def test_corrupt_artifact_is_rejected_on_load(tmp_path):
    art = select_threshold(make_dev(), n_replicates=10)
    path = tmp_path / "t.json"
    art.save(path)
    payload = json.loads(path.read_text())
    payload["threshold"] = 42.0
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="threshold"):
        ThresholdArtifact.load(path)


def test_saving_an_invalid_artifact_raises(tmp_path):
    art = select_threshold(make_dev(), n_replicates=10)
    art.threshold = float("nan")
    with pytest.raises(ValueError):
        art.save(tmp_path / "bad.json")


# --- helper guards --------------------------------------------------------
def test_sigmoid_is_stable_at_extremes():
    out = sigmoid(np.array([-800.0, 0.0, 800.0]))
    assert np.isfinite(out).all()
    assert out[0] == pytest.approx(0.0) and out[2] == pytest.approx(1.0)


@pytest.mark.parametrize("kwargs", [
    dict(logits=np.array([]), labels=np.array([])),
    dict(logits=np.array([0.1, 0.2]), labels=np.array([0.0, 0.0])),   # one class
    dict(logits=np.array([0.1, 0.2]), labels=np.array([0.0, 2.0])),   # bad label
])
def test_fit_temperature_bias_guards(kwargs):
    with pytest.raises(ValueError):
        fit_temperature_bias(**kwargs)


@pytest.mark.parametrize("probs,labels", [
    (np.array([]), np.array([])),
    (np.array([0.5, 1.5]), np.array([0.0, 1.0])),
    (np.array([0.5, np.nan]), np.array([0.0, 1.0])),
    (np.array([0.5, 0.5]), np.array([0.0, 3.0])),
])
def test_ece_guards(probs, labels):
    with pytest.raises(ValueError):
        expected_calibration_error(probs, labels)
