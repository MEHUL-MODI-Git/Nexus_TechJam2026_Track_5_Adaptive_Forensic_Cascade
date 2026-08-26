"""Expert contract (core spec v2 §4, FROZEN 2026-08-26).

The single rule that shapes this file: a failure never becomes a number.
ExpertOutput exists only for a successful inference and every field in it is
non-null; per-image failure raises ExpertInferenceError and init failure raises
ExpertInitError. A detector that silently emits 0.5 for an image it could not
read produces an eval table that looks complete and is quietly wrong -- so the
types make that impossible rather than merely discouraged.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

import numpy as np

from ..pipeline.decode import DecodedImage

# Above this length, patch_scores go to the feature cache as an array and the
# JSON carries a key + summary instead of the full vector (review note N2).
MAX_INLINE_PATCH_SCORES = 64


class ExpertError(Exception):
    """Base for expert failures. Never carries a score."""


class ExpertInitError(ExpertError):
    """Expert unavailable for the whole run (missing checkpoint, bad device).

    The registry records the reason in the run manifest and continues with the
    remaining experts; zero available experts is a fatal run error, not a
    fabricated verdict.
    """

    def __init__(self, expert_id: str, reason_code: str, message: str) -> None:
        super().__init__(f"[{expert_id}] {reason_code}: {message}")
        self.expert_id = expert_id
        self.reason_code = reason_code
        self.message = message


class ExpertInferenceError(ExpertError):
    """Recoverable per-image failure.

    The cascade catches this, records {expert_id, reason_code, message} in the
    prediction record's expert_failures, marks the expert unavailable FOR THAT
    IMAGE, and degrades per doc 03.
    """

    def __init__(
        self, expert_id: str, reason_code: str, message: str, image_sha256: str | None = None
    ) -> None:
        super().__init__(f"[{expert_id}] {reason_code}: {message}")
        self.expert_id = expert_id
        self.reason_code = reason_code
        self.message = message
        self.image_sha256 = image_sha256

    def to_dict(self) -> dict:
        return {
            "expert_id": self.expert_id,
            "reason_code": self.reason_code,
            "message": self.message,
            "image_sha256": self.image_sha256,
        }


@dataclass(frozen=True)
class ExpertOutput:
    """One expert's verdict on one image. SUCCESS ONLY -- all fields non-null.

    Field mapping to doc 03's logical contract (review note N2):
      raw_logit -> raw_score
      p_fake    -> probability_after_expert_calibration
    In Phase 0 p_fake is a plain sigmoid of raw_logit (no per-expert calibration
    is fitted yet); the name is stable so Phase-2 calibration lands without a
    schema change.
    """

    expert_id: str          # "commfor_384" | "lota" | "warpad" | "rigid"
    raw_logit: float        # finite; HIGHER = more likely AI-generated
    p_fake: float           # finite, [0,1]
    inference_ms: float
    embedding: np.ndarray | None = None
    patch_scores: list[float] | None = None
    warnings: list[str] = field(default_factory=list)
    # Optional v1 extension, jointly ACKed (A-006 §2 / B-006): populated on the
    # live predict path, omitted in cache rows where the run manifest covers it.
    model_version: str | None = None

    def __post_init__(self) -> None:
        # Cheap invariants, enforced at construction so a bad adapter fails at
        # its own boundary rather than poisoning a downstream metric.
        if not math.isfinite(self.raw_logit):
            raise ValueError(f"{self.expert_id}: raw_logit must be finite, got {self.raw_logit}")
        if not math.isfinite(self.p_fake) or not (0.0 <= self.p_fake <= 1.0):
            raise ValueError(f"{self.expert_id}: p_fake must be finite in [0,1], got {self.p_fake}")

    def to_json_dict(self) -> dict:
        """JSON-safe view. Embeddings are never serialized (review note N2)."""
        patch = self.patch_scores
        patch_inline = patch if patch is not None and len(patch) <= MAX_INLINE_PATCH_SCORES else None
        out = {
            "expert_id": self.expert_id,
            "raw_logit": self.raw_logit,
            "p_fake": self.p_fake,
            "inference_ms": self.inference_ms,
            "embedding_present": self.embedding is not None,
            "embedding_dim": int(self.embedding.shape[-1]) if self.embedding is not None else None,
            "patch_scores": patch_inline,
            "patch_scores_count": len(patch) if patch is not None else None,
            "warnings": list(self.warnings),
        }
        if self.model_version is not None:
            out["model_version"] = self.model_version
        return out


@runtime_checkable
class Expert(Protocol):
    """What the cascade requires of every expert adapter.

    The ADAPTER owns preprocessing, device placement, class-order mapping to
    P(fake), applying sigmoid exactly once, and determinism (inference_mode +
    eval mode). Callers never touch those.
    """

    expert_id: str
    param_count: int
    license: str
    model_version: str | None

    def predict(self, img: DecodedImage) -> ExpertOutput:
        """Score one decoded image. Raises ExpertInferenceError on failure."""
        ...
