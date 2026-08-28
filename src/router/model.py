"""The reliability/fusion router (doc 03 step 6) — our original contribution.

The fusion ladder from doc 04 is implemented as seven rungs that share one
interface, so an ablation compares like with like and a negative result is
reportable rather than embarrassing:

    0. QualityOnlyRouter     — no expert score, ever. A linear layer over the
       router feature vector alone (image-statistics descriptors). The
       corpus has a shortcut (real=JPEG, fake=PNG) that these descriptors can
       exploit with no idea what AI generation is; this rung makes that
       shortcut an explicit floor the rest of the ladder must clear.
    1. StaticAverageFusion   — no learned parameters, fuses in LOGIT space.
       The honest baseline the router must beat to justify its existence.
    2. ProbabilityMeanFusion — no learned parameters, fuses in PROBABILITY
       space. Tests the "fuse in logit space" choice (Codex R23) against the
       naive alternative instead of just asserting it.
    3. FixedWeightFusion     — a non-learned weight vector chosen by a coarse
       grid search on TRAIN ONLY. Does a single fixed-but-tuned weighting
       already capture most of what learning buys?
    4. LogisticRouter        — a single linear layer. If this matches the MLP,
       the MLP is unjustified complexity and we say so.
    5. MLPRouter             — doc 03's two-head architecture (also run with
       the worst-group loss, so the ladder has seven entries in total).

Two heads, because they answer different questions:
  - **fusion**: how much to trust each expert ON THIS IMAGE (weights over the
    experts that actually produced a score);
  - **reliability**: how likely the fused decision is correct — which is what
    drives abstention, and is deliberately NOT the same thing as p_fake. A
    confident score can be reliably wrong; that is the whole point.

Availability masking matters more than it looks: with the second expert parked,
every row has one available expert, and a softmax over a padded expert slot
would silently hand weight to a score that does not exist.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import torch
from torch import nn

SCHEMA_VERSION = "router-model.v1"

NEG_INF = -1e9  # masking constant for softmax over unavailable experts


@dataclass
class FusionOutput:
    """What every rung of the ladder returns, so ablations stay comparable."""

    p_fake: torch.Tensor            # (B,) fused probability
    fused_logit: torch.Tensor       # (B,) pre-sigmoid, the calibration target
    weights: torch.Tensor           # (B, n_experts) zero for unavailable experts
    reliability: torch.Tensor | None  # (B,) or None for rungs without the head
    reliability_logit: torch.Tensor | None  # (B,) pre-sigmoid form of `reliability`,
                                             # so the trainer can use BCE-with-logits
                                             # on this head too (doc 04, B-018 T5).


def _fuse_logits(weights: torch.Tensor, expert_logits: torch.Tensor,
                 bias: torch.Tensor | None = None) -> tuple[torch.Tensor, torch.Tensor]:
    """Weighted fusion in LOGIT space, per doc 03 step 6 (Codex R23).

    The previous version averaged probabilities. Averaging probabilities pulls
    confident disagreement toward 0.5 and interacts badly with the temperature
    calibration that follows, which operates on logits. Fusing logits keeps the
    two stages compatible.
    """
    fused = (weights * expert_logits).sum(dim=-1)
    if bias is not None:
        fused = fused + bias
    return fused, torch.sigmoid(fused)


def _masked_weights(logits: torch.Tensor, available: torch.Tensor) -> torch.Tensor:
    """Softmax over available experts only; unavailable slots get exactly 0.

    Rows with NO available expert return all-zero weights rather than a uniform
    distribution over nothing — the caller must treat that as "no verdict",
    which is what PredictionService already does.
    """
    masked = logits.masked_fill(~available, NEG_INF)
    weights = torch.softmax(masked, dim=-1)
    weights = weights * available.to(weights.dtype)
    total = weights.sum(dim=-1, keepdim=True)
    return torch.where(total > 0, weights / total.clamp(min=1e-12), torch.zeros_like(weights))


class QualityOnlyRouter(nn.Module):
    """Rung 0: predicts from IMAGE PROPERTIES ONLY -- no detector evidence at all.

    This rung exists so that any claim about the cascade is measured against a
    model that has never seen the detector's opinion. If the cascade cannot beat
    it, we do not have a detection result, only image statistics that happen to
    correlate with how this corpus was built.

    **It takes an explicit column subset, and that is the whole point.** The
    router feature vector opens with `<expert>.raw_logit`, `.p_fake`, `.entropy`
    and the probe statistics (probes are the expert re-scored on perturbed
    views, so they are detector output too), then `disagreement.*`, which is
    derived from expert scores. An earlier version of this rung took the FULL
    vector and merely declined to read the separate `expert_logits` argument --
    so it still received the detector's logit at index 0 and its probability at
    index 2. That "no detector" baseline was the full model under another name,
    and it scored 0.90 worst-family recall for exactly that reason. A baseline
    that secretly reads the thing it is meant to exclude is worse than no
    baseline at all, because it silently raises the bar every other rung is
    measured against.

    `FeatureSpec.non_expert_indices()` is the single source of truth for which
    columns qualify; this module never picks them itself.
    """

    def __init__(self, feature_indices) -> None:
        super().__init__()
        idx = torch.as_tensor(list(feature_indices), dtype=torch.long)
        # A buffer, not a parameter: it must survive save/load so a reloaded
        # checkpoint reads the same columns, but it is not learned.
        self.register_buffer("feature_indices", idx)
        self.linear = nn.Linear(idx.numel(), 1)

    def forward(self, features, expert_logits, available) -> FusionOutput:
        fused = self.linear(features[:, self.feature_indices]).squeeze(-1)
        # No expert is used: weights are all zero, not a uniform/degenerate
        # vector that would suggest some expert contributed.
        weights = torch.zeros_like(expert_logits)
        return FusionOutput(p_fake=torch.sigmoid(fused), fused_logit=fused,
                            weights=weights, reliability=None, reliability_logit=None)


class StaticAverageFusion(nn.Module):
    """Rung 1: unweighted mean over available experts. No learned parameters.

    This is the baseline the trained router has to beat. If it doesn't, doc 08's
    kill criteria say we report that honestly rather than shipping complexity.
    """

    def __init__(self, n_experts: int) -> None:
        super().__init__()
        self.n_experts = n_experts

    def forward(self, features, expert_logits, available) -> FusionOutput:
        weights = _masked_weights(torch.zeros_like(expert_logits), available)
        fused, p = _fuse_logits(weights, expert_logits)
        return FusionOutput(p_fake=p, fused_logit=fused, weights=weights,
                            reliability=None, reliability_logit=None)


class ProbabilityMeanFusion(nn.Module):
    """Baseline rung: mean of PROBABILITIES over available experts.

    Zero parameters, like StaticAverageFusion, but fuses in probability space
    instead of logit space -- the doc-04 ladder's other parameter-free
    baseline, included so R23's "fuse in logit space" choice is tested against
    the naive alternative rather than merely asserted.
    """

    def __init__(self, n_experts: int) -> None:
        super().__init__()
        self.n_experts = n_experts

    def forward(self, features, expert_logits, available) -> FusionOutput:
        weights = _masked_weights(torch.zeros_like(expert_logits), available)
        probs = torch.sigmoid(expert_logits)
        p = (weights * probs).sum(dim=-1)
        has_signal = available.any(dim=-1)
        # No available expert: weights are all zero, so the weighted sum above
        # is 0.0 -- a confident REAL score no expert produced. Read it as "no
        # verdict" (p=0.5, logit=0) instead, matching StaticAverageFusion's
        # all-zero-weight convention for the same row.
        p = torch.where(has_signal, p, torch.full_like(p, 0.5))
        fused = torch.logit(p.clamp(1e-6, 1 - 1e-6))
        return FusionOutput(p_fake=p, fused_logit=fused, weights=weights,
                            reliability=None, reliability_logit=None)


class FixedWeightFusion(nn.Module):
    """Baseline rung: a fixed, non-learned weight vector over experts.

    The vector is chosen by a coarse grid search on the TRAIN split only (see
    `train.train_rung`) and frozen here as a BUFFER, not a parameter, so the
    optimizer never touches it. Sits between the uniform-average baselines and
    the learned rungs: does a single fixed-but-tuned weighting already capture
    most of what a learned router buys?
    """

    def __init__(self, weights: torch.Tensor) -> None:
        super().__init__()
        self.n_experts = weights.numel()
        self.register_buffer("fixed_weights", weights.to(torch.float32))

    def forward(self, features, expert_logits, available) -> FusionOutput:
        available_f = available.to(self.fixed_weights.dtype)
        raw = self.fixed_weights.unsqueeze(0) * available_f
        total = raw.sum(dim=-1, keepdim=True)
        # Renormalise over the AVAILABLE mask directly: unavailable experts
        # get exactly 0, available ones sum to 1. (No available expert leaves
        # an all-zero row, same "no verdict" convention as _masked_weights.)
        weights = torch.where(total > 0, raw / total.clamp(min=1e-12), torch.zeros_like(raw))
        fused, p = _fuse_logits(weights, expert_logits)
        return FusionOutput(p_fake=p, fused_logit=fused, weights=weights,
                            reliability=None, reliability_logit=None)


class LogisticRouter(nn.Module):
    """Rung: one linear layer to both heads. The complexity control."""

    def __init__(self, n_features: int, n_experts: int) -> None:
        super().__init__()
        self.n_experts = n_experts
        self.fusion_head = nn.Linear(n_features, n_experts)
        self.bias_head = nn.Linear(n_features, 1)
        self.reliability_head = nn.Linear(n_features, 1)

    def forward(self, features, expert_logits, available) -> FusionOutput:
        weights = _masked_weights(self.fusion_head(features), available)
        fused, p = _fuse_logits(weights, expert_logits,
                                self.bias_head(features).squeeze(-1))
        reliability_logit = self.reliability_head(features).squeeze(-1)
        return FusionOutput(
            p_fake=p, fused_logit=fused, weights=weights,
            reliability=torch.sigmoid(reliability_logit),
            reliability_logit=reliability_logit,
        )


class MLPRouter(nn.Module):
    """doc 03 step 6 — Linear(32) -> GELU -> Dropout -> Linear(16) -> GELU -> 2 heads.

    The ladder's last two rungs (with and without the worst-group loss).

    Deliberately tiny (order 10^3 parameters). The <2B budget is dominated by
    the frozen experts; the trainable part of this system is negligible, which
    is exactly the "small trainable component" shape the brief's limited-compute
    framing points at.
    """

    def __init__(self, n_features: int, n_experts: int, hidden: int = 32,
                 hidden2: int = 16, dropout: float = 0.1) -> None:
        super().__init__()
        self.n_experts = n_experts
        self.trunk = nn.Sequential(
            nn.Linear(n_features, hidden), nn.GELU(), nn.Dropout(dropout),
            nn.Linear(hidden, hidden2), nn.GELU(),
        )
        self.fusion_head = nn.Linear(hidden2, n_experts)
        self.bias_head = nn.Linear(hidden2, 1)
        self.reliability_head = nn.Linear(hidden2, 1)

    def forward(self, features, expert_logits, available) -> FusionOutput:
        h = self.trunk(features)
        weights = _masked_weights(self.fusion_head(h), available)
        fused, p = _fuse_logits(weights, expert_logits, self.bias_head(h).squeeze(-1))
        reliability_logit = self.reliability_head(h).squeeze(-1)
        return FusionOutput(
            p_fake=p, fused_logit=fused, weights=weights,
            reliability=torch.sigmoid(reliability_logit),
            reliability_logit=reliability_logit,
        )

    @property
    def param_count(self) -> int:
        return sum(p.numel() for p in self.parameters())


def group_index(families: np.ndarray, labels: torch.Tensor) -> tuple[torch.Tensor, int]:
    """CLASS x FAMILY groups (Codex R11).

    Grouping by family alone hides exactly the directional failures this project
    emphasises: `blur_s2.0` pushes REAL images toward "fake" while `noise_s0.10`
    erases FAKE detections, and a family-only group averages those two opposite
    problems into one number.
    """
    keys = [f"{int(y)}|{f}" for y, f in zip(labels.tolist(), families.tolist())]
    order = {k: i for i, k in enumerate(sorted(set(keys)))}
    return torch.tensor([order[k] for k in keys], dtype=torch.long), len(order)


def worst_group_loss(
    per_sample_loss: torch.Tensor, groups: torch.Tensor, n_groups: int,
    *, lambda_worst: float = 1.0, temperature: float = 0.1,
) -> torch.Tensor:
    """The worst-group-loss rung's objective: `BCE + lambda * smooth_logsumexp(group
    means)` (Codex R11).

    The previous version REPLACED the BCE with a hard max over family means. A
    hard max has zero gradient for every group but the current worst, so
    training oscillates between groups and the overall fit is unconstrained. The
    planned form keeps the BCE term and adds a smooth upper bound on the group
    means, so every group contributes gradient and the worst one dominates.
    """
    means = []
    for g in range(n_groups):
        mask = groups == g
        if mask.any():
            means.append(per_sample_loss[mask].mean())
    if not means:
        raise ValueError("no non-empty groups in batch")
    stacked = torch.stack(means)
    smooth_max = temperature * torch.logsumexp(stacked / temperature, dim=0)
    return per_sample_loss.mean() + lambda_worst * smooth_max


def reliability_targets(
    fused_p_fake: torch.Tensor, labels: torch.Tensor, threshold: float
) -> torch.Tensor:
    """Target for the reliability head: was the forced decision CORRECT?

    Note this is supervision on outcome, not on confidence — the head learns
    when the system is right, which is what abstention needs to know.
    """
    predicted = (fused_p_fake >= threshold).to(labels.dtype)
    return (predicted == labels).to(fused_p_fake.dtype)
