"""The reliability/fusion router (doc 03 step 6) — our original contribution.

The fusion ladder from doc 04 is implemented as three rungs that share one
interface, so an ablation compares like with like and a negative result is
reportable rather than embarrassing:

    1. StaticAverageFusion — no learned parameters. The honest baseline the
       router must beat to justify its existence.
    2. LogisticRouter      — a single linear layer. If this matches the MLP,
       the MLP is unjustified complexity and we say so.
    3. MLPRouter           — doc 03's two-head architecture.

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
import torch.nn as nn

SCHEMA_VERSION = "router-model.v1"

NEG_INF = -1e9  # masking constant for softmax over unavailable experts


@dataclass
class FusionOutput:
    """What every rung of the ladder returns, so ablations stay comparable."""

    p_fake: torch.Tensor            # (B,) fused probability
    fused_logit: torch.Tensor       # (B,) pre-sigmoid, the calibration target
    weights: torch.Tensor           # (B, n_experts) zero for unavailable experts
    reliability: torch.Tensor | None  # (B,) or None for rungs without the head


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
        return FusionOutput(p_fake=p, fused_logit=fused, weights=weights, reliability=None)


class LogisticRouter(nn.Module):
    """Rung 2: one linear layer to both heads. The complexity control."""

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
        return FusionOutput(
            p_fake=p, fused_logit=fused, weights=weights,
            reliability=torch.sigmoid(self.reliability_head(features)).squeeze(-1),
        )


class MLPRouter(nn.Module):
    """Rung 3: doc 03 step 6 — Linear(32) -> GELU -> Dropout -> Linear(16) -> GELU -> 2 heads.

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
        return FusionOutput(
            p_fake=p, fused_logit=fused, weights=weights,
            reliability=torch.sigmoid(self.reliability_head(h)).squeeze(-1),
        )

    @property
    def param_count(self) -> int:
        return sum(p.numel() for p in self.parameters())


def group_index(families: "np.ndarray", labels: torch.Tensor) -> tuple[torch.Tensor, int]:
    """CLASS x FAMILY groups (Codex R11).

    Grouping by family alone hides exactly the directional failures this project
    emphasises: `blur_s2.0` pushes REAL images toward "fake" while `noise_s0.10`
    erases FAKE detections, and a family-only group averages those two opposite
    problems into one number.
    """
    import numpy as np

    keys = [f"{int(y)}|{f}" for y, f in zip(labels.tolist(), families.tolist())]
    order = {k: i for i, k in enumerate(sorted(set(keys)))}
    return torch.tensor([order[k] for k in keys], dtype=torch.long), len(order)


def worst_group_loss(
    per_sample_loss: torch.Tensor, groups: torch.Tensor, n_groups: int,
    *, lambda_worst: float = 1.0, temperature: float = 0.1,
) -> torch.Tensor:
    """Rung 4: `BCE + lambda * smooth_logsumexp(group means)` (Codex R11).

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
