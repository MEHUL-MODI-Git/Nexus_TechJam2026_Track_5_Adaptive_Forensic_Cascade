"""Serving-side wrapper around a frozen router checkpoint.

The router was fitted offline on cache rows. This is what lets the LIVE path use
it, and the whole point is that it does not re-implement anything: it assembles a
row of exactly the shape `feature_cache.extract_feature_blocks` produces and
hands it to the same `row_to_vector` the trainer used. The single feature
implementation is why a production score can be trusted to mean what the
evaluated score meant.

Nothing here fits, tunes or calibrates. The threshold arrives frozen from its
artifact and is never touched; this module cannot change a decision boundary.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch

from .features import FeatureSpec, Standardizer, row_to_vector


@dataclass(frozen=True)
class RouterScore:
    """One routed decision, with the provenance a caller needs to report it."""

    p_fake: float
    reliability: float | None      # None unless the head was actually fitted
    rung: str
    n_parameters: int
    expert_available: dict[str, bool]
    abstain: bool = False          # reliability below the frozen policy threshold
    abstain_threshold: float | None = None


class RouterHead:
    """A loaded, frozen router. Scores one image's feature blocks."""

    def __init__(self, model, spec: FeatureSpec, standardizer: Standardizer,
                 threshold: float, payload: dict[str, Any]) -> None:
        self.model = model
        self.spec = spec
        self.standardizer = standardizer
        self.threshold = float(threshold)
        self.payload = payload
        self.model.eval()
        # The reliability head exists structurally on the learned rungs but is
        # only meaningful once fitted against out-of-fold correctness targets.
        # Reporting sigmoid(untrained linear layer) as a confidence would be a
        # fabricated number wearing a trustworthy name, so we gate on the flag.
        self.reliability_fitted = bool(payload.get("reliability_head_fitted", False))
        # The abstention threshold is a frozen VALUE chosen on dev, never a
        # percentile recomputed on whatever data arrives -- a percentile would
        # silently re-tune the policy to each new batch.
        policy = payload.get("abstention") or {}
        self.abstention_adopted = bool(policy.get("adopted", False))
        self.abstain_threshold = (
            float(policy["reliability_threshold"])
            if self.abstention_adopted and policy.get("reliability_threshold") is not None
            else None
        )

    @classmethod
    def from_checkpoint(cls, checkpoint_path: Path | str,
                        threshold: float | None = None) -> RouterHead:
        """Load a checkpoint through the trainer's fail-closed loader.

        `threshold` overrides only when a validated frozen artifact supplied it;
        otherwise the checkpoint's own frozen threshold is used. There is no path
        here that invents one.
        """
        from .train import load_checkpoint

        loaded = load_checkpoint(Path(checkpoint_path))
        thr = loaded.threshold if threshold is None else float(threshold)
        if not np.isfinite(thr) or not (0.0 <= thr <= 1.0):
            raise ValueError(f"router threshold must be finite in [0,1], got {thr}")
        # R5 (Codex review 2026-08-29): this override used to REPLACE the
        # checkpoint's own threshold without comparing them, so a separately
        # valid threshold artifact could silently retarget any checkpoint --
        # and `_load_router_from_config` then compared the artifact only to the
        # value it had just supplied, which made that check vacuous. A caller
        # may name the threshold, but it must be the one this checkpoint was
        # frozen at.
        if threshold is not None and not math.isclose(
            thr, float(loaded.threshold), rel_tol=0.0, abs_tol=1e-12
        ):
            raise ValueError(
                f"threshold {thr!r} does not match the threshold this checkpoint was "
                f"frozen at ({loaded.threshold!r}); refusing to retarget a frozen "
                "checkpoint with a threshold it was never fitted against"
            )
        return cls(loaded.model, loaded.spec, loaded.standardizer, thr, loaded.payload)

    @property
    def expert_ids(self) -> tuple[str, ...]:
        return tuple(self.spec.expert_ids)

    def score_blocks(self, blocks: dict) -> RouterScore:
        """Score one image from `extract_feature_blocks` output.

        `blocks` carries only feature-bearing fields; identity fields are absent
        on the live path and `row_to_vector` never reads them.
        """
        experts = blocks.get("experts") or {}
        available = {eid: bool((experts.get(eid) or {}).get("ok", False))
                     for eid in self.spec.expert_ids}
        if not any(available.values()):
            raise ValueError(
                "router cannot score an image where every expert failed; the "
                "caller must surface the expert failure instead of a verdict"
            )

        # Derives probe_flip against the FROZEN threshold -- the same value the
        # trainer and the one-shot evaluator computed.
        vector = row_to_vector(blocks, self.spec, self.threshold)
        matrix = self.standardizer.transform(vector.reshape(1, -1))

        logits, mask = [], []
        for eid in self.spec.expert_ids:
            block = experts.get(eid) or {}
            ok = available[eid]
            logits.append(float(block["raw_logit"]) if ok else 0.0)
            mask.append(ok)

        with torch.no_grad():
            out = self.model(
                torch.tensor(matrix, dtype=torch.float32),
                torch.tensor([logits], dtype=torch.float32),
                torch.tensor([mask], dtype=torch.bool),
            )
        p_fake = float(out.p_fake[0])
        reliability = None
        if self.reliability_fitted and getattr(out, "reliability", None) is not None:
            reliability = float(out.reliability[0])

        abstain = bool(
            self.abstain_threshold is not None
            and reliability is not None
            and reliability < self.abstain_threshold
        )
        return RouterScore(
            p_fake=p_fake,
            reliability=reliability,
            rung=str(self.payload.get("rung", "unknown")),
            n_parameters=int(self.payload.get("n_parameters", 0) or 0),
            expert_available=available,
            abstain=abstain,
            abstain_threshold=self.abstain_threshold,
        )
