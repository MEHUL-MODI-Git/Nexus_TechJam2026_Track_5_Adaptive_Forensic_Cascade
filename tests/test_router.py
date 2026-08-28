"""Router feature-assembly and model tests (doc 03 steps 5-6).

The assembly tests all circle one rule: absence must be encoded, never
invented. The model tests all circle another: an unavailable expert must
receive exactly zero weight.
"""

import numpy as np
import pytest
import torch

from src.router.features import (
    PROBE_KEYS,
    QUALITY_KEYS,
    FeatureSpec,
    Standardizer,
    binary_entropy_array,
    row_to_vector,
    rows_to_matrix,
)
from src.router.model import (
    FixedWeightFusion,
    LogisticRouter,
    MLPRouter,
    ProbabilityMeanFusion,
    QualityOnlyRouter,
    StaticAverageFusion,
    group_index,
    reliability_targets,
    worst_group_loss,
)

SPEC1 = FeatureSpec(expert_ids=("commfor_384",))
SPEC2 = FeatureSpec(expert_ids=("commfor_384", "rigid"))


def good_row(p_fake=0.12, probe_scores=None):
    """probe_flip is DERIVED from probe_scores at consumption (R9), never stored."""
    if probe_scores is None:
        probe_scores = {"probe_jpeg_q92": p_fake, "probe_crop_0.96": p_fake}
    return {
        "experts": {"commfor_384": {"ok": True, "raw_logit": -2.0, "p_fake": p_fake}},
        "probes": {"commfor_384": {"probe_mean": 0.13, "probe_std": 0.01,
                                   "probe_range": 0.03, "probe_max_delta": 0.02,
                                   "probe_scores": probe_scores, "n_probes_ok": 3}},
        "disagreement": None,
        "quality": {"width": 256, "height": 192, "aspect_ratio": 4 / 3,
                    "megapixels": 0.049, "is_portrait": False,
                    **{k: 0.1 for k in QUALITY_KEYS}},
    }


def _idx(spec, name):
    return spec.names.index(name)


# --- feature spec ---------------------------------------------------------
def test_dim_matches_names():
    assert SPEC1.dim == len(SPEC1.names)
    assert SPEC2.dim == len(SPEC2.names)
    assert SPEC2.dim > SPEC1.dim


def test_vector_length_matches_spec():
    assert row_to_vector(good_row(), SPEC1).shape == (SPEC1.dim,)


def test_every_optional_feature_has_a_presence_flag():
    names = SPEC1.names
    for key in QUALITY_KEYS:
        assert f"quality.{key}__present" in names
    for key in PROBE_KEYS:
        assert f"commfor_384.{key}__present" in names


# --- missing-value discipline --------------------------------------------
def test_failed_expert_yields_zero_value_and_zero_indicator():
    row = {"experts": {"commfor_384": {"ok": False, "reason_code": "x", "message": "y"}},
           "probes": {}, "disagreement": None, "quality": {}}
    v = row_to_vector(row, SPEC1)
    assert v[_idx(SPEC1, "commfor_384.p_fake")] == 0.0
    assert v[_idx(SPEC1, "commfor_384.p_fake__present")] == 0.0
    assert np.isfinite(v).all()


def test_present_expert_sets_indicator():
    v = row_to_vector(good_row(p_fake=0.7), SPEC1)
    assert v[_idx(SPEC1, "commfor_384.p_fake")] == pytest.approx(0.7)
    assert v[_idx(SPEC1, "commfor_384.p_fake__present")] == 1.0


def test_probe_flip_is_tri_state():
    """True / False / unknown must be three distinguishable encodings.

    The flip is derived from stored probe scores against the threshold in force,
    so the cache never has to carry a threshold-dependent value (R9).
    """
    vi, pi = _idx(SPEC1, "commfor_384.probe_flip"), _idx(SPEC1, "commfor_384.probe_flip__present")

    # base 0.12 is below 0.5; a probe at 0.9 crosses the boundary -> flip
    flipped = row_to_vector(
        good_row(probe_scores={"probe_jpeg_q92": 0.9}), SPEC1, threshold=0.5)
    assert (flipped[vi], flipped[pi]) == (1.0, 1.0)

    stable = row_to_vector(
        good_row(probe_scores={"probe_jpeg_q92": 0.11}), SPEC1, threshold=0.5)
    assert (stable[vi], stable[pi]) == (0.0, 1.0)

    unknown = row_to_vector(good_row(probe_scores={}), SPEC1, threshold=0.5)
    assert (unknown[vi], unknown[pi]) == (0.0, 0.0)            # distinct from False


def test_missing_disagreement_cannot_read_as_agreement():
    """The single-expert case: zeros must come with a zero indicator."""
    v = row_to_vector(good_row(), SPEC1)
    assert v[_idx(SPEC1, "disagreement.max_abs_p_diff")] == 0.0
    assert v[_idx(SPEC1, "disagreement.max_abs_p_diff__present")] == 0.0


def test_present_disagreement_sets_indicator():
    row = good_row()
    row["disagreement"] = {"max_abs_p_diff": 0.4, "mean_abs_p_diff": 0.4, "n_experts_ok": 2}
    v = row_to_vector(row, SPEC1)
    assert v[_idx(SPEC1, "disagreement.max_abs_p_diff")] == pytest.approx(0.4)
    assert v[_idx(SPEC1, "disagreement.max_abs_p_diff__present")] == 1.0
    assert v[_idx(SPEC1, "disagreement.n_experts_ok")] == 2.0


def test_non_finite_values_are_treated_as_missing():
    row = good_row()
    row["experts"]["commfor_384"]["raw_logit"] = float("inf")
    v = row_to_vector(row, SPEC1)
    assert v[_idx(SPEC1, "commfor_384.raw_logit")] == 0.0
    assert v[_idx(SPEC1, "commfor_384.raw_logit__present")] == 0.0


def test_entropy_is_computed_not_read_from_cache():
    """A stored entropy must never override the value implied by p_fake."""
    row = good_row(p_fake=0.5)
    row["experts"]["commfor_384"]["entropy"] = 999.0      # poisoned cache value
    v = row_to_vector(row, SPEC1)
    assert v[_idx(SPEC1, "commfor_384.entropy")] == pytest.approx(np.log(2))


def test_binary_entropy_endpoints():
    out = binary_entropy_array(np.array([0.0, 0.5, 1.0]))
    assert out[0] == 0.0 and out[2] == 0.0
    assert out[1] == pytest.approx(np.log(2))


def test_empty_row_still_produces_finite_vector():
    v = row_to_vector({}, SPEC1)
    assert v.shape == (SPEC1.dim,) and np.isfinite(v).all()


# --- standardizer ---------------------------------------------------------
def test_standardizer_leaves_indicator_columns_untouched():
    rows = [good_row(p_fake=p) for p in (0.1, 0.5, 0.9)]
    M = rows_to_matrix(rows, SPEC1)
    std = Standardizer.fit(M, SPEC1)
    pi = _idx(SPEC1, "commfor_384.p_fake__present")
    assert std.mean[pi] == 0.0 and std.scale[pi] == 1.0
    assert std.transform(M)[:, pi].tolist() == [1.0, 1.0, 1.0]


def test_standardizer_zscores_real_columns():
    rows = [good_row(p_fake=p) for p in (0.1, 0.5, 0.9)]
    M = rows_to_matrix(rows, SPEC1)
    Z = Standardizer.fit(M, SPEC1).transform(M)
    vi = _idx(SPEC1, "commfor_384.p_fake")
    assert Z[:, vi].mean() == pytest.approx(0.0, abs=1e-9)
    assert Z[:, vi].std() == pytest.approx(1.0, abs=1e-6)


def test_standardizer_survives_zero_variance_column():
    M = rows_to_matrix([good_row(), good_row()], SPEC1)   # identical rows
    Z = Standardizer.fit(M, SPEC1).transform(M)
    assert np.isfinite(Z).all()


def test_standardizer_rejects_wrong_width():
    M = rows_to_matrix([good_row()], SPEC1)
    std = Standardizer.fit(M, SPEC1)
    with pytest.raises(ValueError):
        std.transform(np.zeros((1, SPEC1.dim + 3)))


def test_standardizer_rejects_empty_fit():
    with pytest.raises(ValueError):
        Standardizer.fit(np.empty((0, SPEC1.dim)), SPEC1)


# --- model: availability masking -----------------------------------------
@pytest.mark.parametrize("cls", [StaticAverageFusion, LogisticRouter, MLPRouter])
def test_unavailable_expert_gets_exactly_zero_weight(cls):
    model = cls(2) if cls is StaticAverageFusion else cls(SPEC2.dim, 2)
    features = torch.randn(4, SPEC2.dim)
    p = torch.rand(4, 2)
    available = torch.ones(4, 2, dtype=torch.bool)
    available[0, 1] = False
    out = model(features, p, available)
    assert out.weights[0, 1].item() == 0.0
    assert out.weights[0].sum().item() == pytest.approx(1.0)


@pytest.mark.parametrize("cls", [StaticAverageFusion, LogisticRouter, MLPRouter])
def test_no_available_expert_yields_zero_weights(cls):
    model = cls(2) if cls is StaticAverageFusion else cls(SPEC2.dim, 2)
    available = torch.zeros(1, 2, dtype=torch.bool)
    out = model(torch.randn(1, SPEC2.dim), torch.rand(1, 2), available)
    assert out.weights.sum().item() == 0.0     # no verdict, not a uniform guess


def test_static_average_is_the_plain_mean_of_logits():
    """Fusion happens in LOGIT space (doc 03 step 6, Codex R23)."""
    logits = torch.tensor([[-2.0, 2.0]])
    out = StaticAverageFusion(2)(torch.randn(1, SPEC2.dim), logits,
                                 torch.ones(1, 2, dtype=torch.bool))
    assert out.fused_logit.item() == pytest.approx(0.0)
    assert out.p_fake.item() == pytest.approx(0.5)


def test_static_average_ignores_unavailable_expert():
    logits = torch.tensor([[-2.0, 2.0]])
    out = StaticAverageFusion(2)(torch.randn(1, SPEC2.dim), logits,
                                 torch.tensor([[True, False]]))
    assert out.fused_logit.item() == pytest.approx(-2.0)


def test_static_average_fused_logit_is_a_convex_combination():
    logits = torch.randn(16, 2)
    out = StaticAverageFusion(2)(torch.randn(16, SPEC2.dim), logits,
                                 torch.ones(16, 2, dtype=torch.bool))
    assert (out.fused_logit >= logits.min(dim=1).values - 1e-5).all()
    assert (out.fused_logit <= logits.max(dim=1).values + 1e-5).all()


def test_probability_mean_is_the_mean_of_probabilities():
    """Baseline rung: fuses in PROBABILITY space, unlike StaticAverageFusion."""
    logits = torch.logit(torch.tensor([[0.2, 0.8]]))
    out = ProbabilityMeanFusion(2)(torch.randn(1, SPEC2.dim), logits,
                                   torch.ones(1, 2, dtype=torch.bool))
    assert out.p_fake.item() == pytest.approx(0.5, abs=1e-5)   # mean of 0.2 and 0.8


def test_probability_mean_no_available_expert_is_half():
    """No expert available: 0.5/logit-0 ("no verdict"), never a fabricated 0.0."""
    out = ProbabilityMeanFusion(2)(torch.randn(1, SPEC2.dim), torch.randn(1, 2),
                                   torch.zeros(1, 2, dtype=torch.bool))
    assert torch.isfinite(out.p_fake).all()
    assert out.p_fake.item() == pytest.approx(0.5)
    assert out.fused_logit.item() == pytest.approx(0.0)


def test_fixed_weight_fusion_masks_and_renormalises():
    """Unavailable experts get exactly 0 weight; available ones sum to 1."""
    model = FixedWeightFusion(torch.tensor([0.7, 0.3]))
    available = torch.tensor([[True, False]])
    out = model(torch.randn(1, SPEC2.dim), torch.tensor([[-1.0, 2.0]]), available)
    assert out.weights[0, 1].item() == 0.0
    assert out.weights[0].sum().item() == pytest.approx(1.0)
    assert out.fused_logit.item() == pytest.approx(-1.0)   # only expert 0 available


def test_fixed_weight_fusion_has_zero_trainable_parameters():
    model = FixedWeightFusion(torch.tensor([0.6, 0.4]))
    assert sum(p.numel() for p in model.parameters()) == 0


@pytest.mark.parametrize("cls", [LogisticRouter, MLPRouter])
def test_trained_rungs_emit_a_probability_and_its_logit(cls):
    model = cls(SPEC2.dim, 2)
    out = model(torch.randn(16, SPEC2.dim), torch.randn(16, 2),
                torch.ones(16, 2, dtype=torch.bool))
    assert ((out.p_fake >= 0) & (out.p_fake <= 1)).all()
    assert torch.allclose(out.p_fake, torch.sigmoid(out.fused_logit), atol=1e-6)


@pytest.mark.parametrize("cls", [LogisticRouter, MLPRouter])
def test_reliability_is_a_probability(cls):
    out = cls(SPEC2.dim, 2)(torch.randn(8, SPEC2.dim), torch.rand(8, 2),
                            torch.ones(8, 2, dtype=torch.bool))
    assert ((out.reliability >= 0) & (out.reliability <= 1)).all()


def test_static_average_has_no_parameters():
    assert sum(p.numel() for p in StaticAverageFusion(2).parameters()) == 0


# --- quality_only: the shortcut floor (router-repair-b018) -----------------
def test_quality_only_ignores_expert_scores():
    """The important one: QualityOnlyRouter must not read `expert_logits` at
    all, so wildly different expert scores on the same features must not
    change `p_fake` by even a bit."""
    torch.manual_seed(0)
    model = QualityOnlyRouter(SPEC2.non_expert_indices())
    model.eval()
    features = torch.randn(8, SPEC2.dim)
    available = torch.ones(8, 2, dtype=torch.bool)
    with torch.no_grad():
        out_a = model(features, torch.full((8, 2), -50.0), available)
        out_b = model(features, torch.full((8, 2), 50.0), available)
    assert torch.equal(out_a.p_fake, out_b.p_fake)
    assert torch.equal(out_a.fused_logit, out_b.fused_logit)


def test_quality_only_weights_are_zero():
    model = QualityOnlyRouter(SPEC2.non_expert_indices())
    out = model(torch.randn(4, SPEC2.dim), torch.randn(4, 2),
                torch.ones(4, 2, dtype=torch.bool))
    assert out.weights.shape == (4, 2)
    assert torch.equal(out.weights, torch.zeros(4, 2))
    assert out.reliability is None and out.reliability_logit is None


def test_quality_only_reads_no_detector_column():
    """The floor is only a floor if its columns carry no detector output. Passing
    the full width -- the pre-repair behaviour -- must not even be expressible as
    a silently-accepted default."""
    idx = SPEC2.non_expert_indices()
    names = [SPEC2.names[i] for i in idx]
    assert names, "quality_only would have no features at all"
    assert all(n.startswith(("geom.", "quality.")) for n in names)
    for leaky in ("raw_logit", "p_fake", "entropy", "probe", "disagreement"):
        assert not any(leaky in n for n in names), f"{leaky} reached the floor"
    assert QualityOnlyRouter(idx).linear.in_features == len(idx) < SPEC2.dim


def test_router_is_tiny():
    # "tens of thousands of parameters or fewer" (doc 03) -- negligible vs <2B.
    assert MLPRouter(SPEC2.dim, 2).param_count < 20_000


# --- worst-group loss + reliability targets -------------------------------
def test_worst_group_loss_is_bce_plus_smooth_upper_bound():
    """R11: the planned form is BCE + lambda * smooth_logsumexp(group means),
    not a hard max that REPLACES the BCE (a hard max has zero gradient for every
    group but the current worst)."""
    losses = torch.tensor([0.1, 0.1, 5.0, 5.0])
    groups = torch.tensor([0, 0, 1, 1])
    value = worst_group_loss(losses, groups, 2).item()
    assert value > losses.mean().item()        # the BCE term is still present
    assert value == pytest.approx(losses.mean().item() + 5.0, abs=0.05)


def test_worst_group_loss_dominated_by_the_worst_group():
    balanced = worst_group_loss(torch.tensor([1.0, 1.0]), torch.tensor([0, 1]), 2)
    skewed = worst_group_loss(torch.tensor([0.0, 2.0]), torch.tensor([0, 1]), 2)
    assert skewed.item() > balanced.item()     # same mean, worse worst group


def test_worst_group_loss_skips_empty_groups():
    losses = torch.tensor([1.0, 3.0])
    groups = torch.tensor([0, 2])              # group 1 absent from this batch
    assert torch.isfinite(worst_group_loss(losses, groups, 3))


def test_groups_are_class_by_family():
    """R11: family-only grouping averages opposite directional failures together."""
    import numpy as np

    families = np.array(["blur", "blur", "noise", "noise"])
    labels = torch.tensor([0.0, 1.0, 0.0, 1.0])
    groups, n_groups = group_index(families, labels)
    assert n_groups == 4                       # 2 families x 2 classes
    assert len(set(groups.tolist())) == 4       # every (class, family) is distinct
    # the same family with different labels must NOT share a group
    assert groups[0].item() != groups[1].item()


def test_worst_group_loss_raises_when_no_groups_present():
    with pytest.raises(ValueError):
        worst_group_loss(torch.tensor([]), torch.tensor([], dtype=torch.long), 2)


def test_reliability_target_is_correctness_not_confidence():
    fused = torch.tensor([0.9, 0.9, 0.1, 0.1])
    labels = torch.tensor([1.0, 0.0, 0.0, 1.0])
    t = reliability_targets(fused, labels, threshold=0.5)
    assert t.tolist() == [1.0, 0.0, 1.0, 0.0]   # confident-and-wrong scores 0


def test_reliability_target_threshold_boundary():
    t = reliability_targets(torch.tensor([0.5]), torch.tensor([1.0]), threshold=0.5)
    assert t.item() == 1.0      # p == threshold predicts fake


# --- learnability: the claim the whole project rests on -------------------
def test_router_can_learn_to_beat_static_average():
    """Synthetic world where one expert is right on group A, the other on group B.

    A static average is stuck near chance; a router that reads the context
    feature should approach perfect. If this ever fails, the architecture's
    core premise is not implementable and we would need to know immediately.
    """
    torch.manual_seed(0)
    n = 2000
    context = torch.randint(0, 2, (n,))                  # which expert is reliable
    labels = torch.randint(0, 2, (n,)).float()
    expert_a = torch.where(context == 0, labels, 1 - labels).float()
    expert_b = torch.where(context == 1, labels, 1 - labels).float()
    p = torch.stack([expert_a, expert_b], dim=1).clamp(0.02, 0.98)
    # B-018 T9: fusion happens in LOGIT space (Codex R23) -- feed the model
    # actual logits, not probabilities passed off as logits.
    expert_logits = torch.logit(p.clamp(1e-6, 1 - 1e-6))
    features = torch.stack([context.float(), torch.randn(n)], dim=1)
    available = torch.ones(n, 2, dtype=torch.bool)

    model = MLPRouter(n_features=2, n_experts=2)
    opt = torch.optim.Adam(model.parameters(), lr=0.02)
    for _ in range(300):
        opt.zero_grad()
        out = model(features, expert_logits, available)
        loss = torch.nn.functional.binary_cross_entropy(out.p_fake.clamp(1e-6, 1 - 1e-6), labels)
        loss.backward()
        opt.step()

    model.eval()
    with torch.no_grad():
        routed = model(features, expert_logits, available).p_fake
        baseline = StaticAverageFusion(2)(features, expert_logits, available).p_fake
    routed_acc = ((routed >= 0.5).float() == labels).float().mean().item()
    baseline_acc = ((baseline >= 0.5).float() == labels).float().mean().item()

    assert baseline_acc < 0.65          # averaging cancels the two experts out
    assert routed_acc > 0.90            # routing recovers the signal
    assert routed_acc > baseline_acc + 0.25
