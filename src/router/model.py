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
    weights: torch.Tensor           # (B, n_experts) zero for unavailable experts
    reliability: torch.Tensor | None  # (B,) or None for rungs without the head


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

    def forward(self, features, expert_p_fake, available) -> FusionOutput:
        weights = _masked_weights(torch.zeros_like(expert_p_fake), available)
        return FusionOutput(
            p_fake=(weights * expert_p_fake).sum(dim=-1),
            weights=weights,
            reliability=None,
        )


class LogisticRouter(nn.Module):
    """Rung 2: one linear layer to both heads. The complexity control."""

    def __init__(self, n_features: int, n_experts: int) -> None:
        super().__init__()
        self.n_experts = n_experts
        self.fusion_head = nn.Linear(n_features, n_experts)
        self.reliability_head = nn.Linear(n_features, 1)

    def forward(self, features, expert_p_fake, available) -> FusionOutput:
        weights = _masked_weights(self.fusion_head(features), available)
        return FusionOutput(
            p_fake=(weights * expert_p_fake).sum(dim=-1),
            weights=weights,
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
        self.reliability_head = nn.Linear(hidden2, 1)

    def forward(self, features, expert_p_fake, available) -> FusionOutput:
        h = self.trunk(features)
        weights = _masked_weights(self.fusion_head(h), available)
        return FusionOutput(
            p_fake=(weights * expert_p_fake).sum(dim=-1),
            weights=weights,
            reliability=torch.sigmoid(self.reliability_head(h)).squeeze(-1),
        )

    @property
    def param_count(self) -> int:
        return sum(p.numel() for p in self.parameters())


def worst_group_loss(
    per_sample_loss: torch.Tensor, groups: torch.Tensor, n_groups: int
) -> torch.Tensor:
    """Rung 4: optimize the WORST group's mean loss, not the overall mean.

    Our headline metric is worst-transformation-family fake recall, so training
    on the overall mean optimizes something we do not report. This aligns the
    objective with the claim. Empty groups are skipped rather than contributing
    a zero that would look like a perfectly-solved group.
    """
    means = []
    for g in range(n_groups):
        mask = groups == g
        if mask.any():
            means.append(per_sample_loss[mask].mean())
    if not means:
        raise ValueError("no non-empty groups in batch")
    return torch.stack(means).max()


def reliability_targets(
    fused_p_fake: torch.Tensor, labels: torch.Tensor, threshold: float
) -> torch.Tensor:
    """Target for the reliability head: was the forced decision CORRECT?

    Note this is supervision on outcome, not on confidence — the head learns
    when the system is right, which is what abstention needs to know.
    """
    predicted = (fused_p_fake >= threshold).to(labels.dtype)
    return (predicted == labels).to(fused_p_fake.dtype)
