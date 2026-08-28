"""The prediction service (core spec v2 §6) -- the single decision path.

Gradio, scripts/predict.py, scripts/infer_dir.py and the eval harness all
IMPORT this. Nothing spawns a CLI as a subprocess and nothing re-implements
thresholding, because two copies of a decision rule drift and then the demo and
the results table disagree about what the system predicted.

Failure discipline (review notes N1/N9): decode failure and total expert failure
raise typed errors. The service never returns a fabricated score.
"""

from __future__ import annotations

import math
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

from ..experts.base import Expert, ExpertInferenceError, ExpertInitError, ExpertOutput
from .decode import DecodedImage, DecodeError, decode_image
from .transforms import apply_transform
from .version import PIPELINE_VERSION

_CONFIG_PATH = Path(__file__).resolve().parents[2] / "configs" / "predict.yaml"

SCHEMA_VERSION = "prediction.v1"

# `naive_mean` is the Phase-0 baseline path; `router` runs the frozen router
# head over quality/probe features. Anything else must fail loudly rather than
# quietly behaving like the mean.
_SUPPORTED_FUSION = frozenset({"naive_mean", "router"})


def _default_registry() -> dict:
    """expert_id -> factory. Imported lazily so the module loads without torch."""
    from ..experts.commfor import CommForExpert

    return {"commfor_384": CommForExpert}


class PredictionError(Exception):
    """No expert could score this image; there is no verdict to report."""


@dataclass
class PredictionRecord:
    """`prediction.v1` -- matches specs/phase0-product.md §2 field-for-field."""

    schema_version: str
    image: dict[str, Any]
    transform_id: str
    p_fake: float
    forced_prediction: int          # 0 real / 1 AI-generated, at threshold_used
    decision: str                   # Phase 0: "REAL" | "AI-GENERATED"
    reliability: float | None       # null until a validated estimator exists
    experts: list[dict[str, Any]]
    expert_failures: list[dict[str, Any]]
    rescue_invoked: bool
    inference_ms: dict[str, Any]
    warnings: list[str]
    pipeline_version: str
    threshold_used: float
    threshold_provenance: str
    fusion: str = "naive_mean"      # which decision path produced `p_fake`
    router: dict[str, Any] | None = None
    # `decision` stays strictly binary so the required deliverable format is
    # unaffected; abstention is an ADDITIONAL surface, not a third label.
    abstain: bool = False
    abstain_reason: str | None = None

    def to_json_dict(self) -> dict:
        return asdict(self)


def load_predict_config(path: Path | None = None) -> dict:
    return yaml.safe_load((path or _CONFIG_PATH).read_text())


def _load_router_from_config(cfg: dict):
    """Load the frozen router head and the frozen threshold it must be served at.

    The threshold comes from the VALIDATED artifact, not from `cfg["threshold"]`.
    A YAML file is easy to edit and carries no provenance; the artifact is
    schema-checked and hashed, so it is the only thing allowed to move a
    production decision boundary.
    """
    from ..eval.protocol import load_frozen_threshold
    from ..router.head import RouterHead

    rcfg = cfg.get("router") or {}
    checkpoint = rcfg.get("checkpoint")
    artifact = rcfg.get("threshold_artifact")
    if not checkpoint or not artifact:
        raise ValueError(
            "fusion='router' requires router.checkpoint and router.threshold_artifact "
            f"in the config; got checkpoint={checkpoint!r} artifact={artifact!r}"
        )
    root = Path(__file__).resolve().parents[2]
    checkpoint = Path(checkpoint)
    artifact = Path(artifact)
    if not checkpoint.is_absolute():
        checkpoint = root / checkpoint
    if not artifact.is_absolute():
        artifact = root / artifact

    frozen = load_frozen_threshold(artifact)      # validates schema or raises
    head = RouterHead.from_checkpoint(checkpoint, threshold=float(frozen.value))
    provenance = f"frozen:{artifact.name}:{frozen.artifact_sha256[:12]}"
    return head, float(frozen.value), provenance


class PredictionService:
    """Decode -> optional transform -> experts -> fuse -> threshold."""

    def __init__(
        self,
        experts: list[Expert],
        threshold: float,
        threshold_provenance: str = "unspecified",
        fusion: str = "naive_mean",
        router: Any = None,
    ) -> None:
        if not experts:
            raise ValueError("PredictionService requires at least one expert")
        # Fail CLOSED on a corrupt threshold artifact: a NaN or out-of-range
        # threshold would silently make every verdict meaningless (B-012 #3).
        threshold = float(threshold)
        if not math.isfinite(threshold) or not (0.0 <= threshold <= 1.0):
            raise ValueError(f"threshold must be finite in [0,1], got {threshold}")
        if fusion not in _SUPPORTED_FUSION:
            raise ValueError(
                f"unknown fusion {fusion!r}; implemented: {sorted(_SUPPORTED_FUSION)}. "
                "Refusing to run rather than silently averaging."
            )
        if fusion == "router":
            if router is None:
                raise ValueError(
                    "fusion='router' requires a loaded RouterHead. Refusing to "
                    "fall back to the mean: a caller that asked for the routed "
                    "decision must not silently receive the baseline one."
                )
            # Config drift is the realistic failure here -- someone flips fusion
            # to 'router' and leaves the Phase-0 placeholder threshold in place,
            # and every verdict is then made at a boundary the router was never
            # fitted against. The frozen threshold travels WITH the checkpoint,
            # so disagreement means the config is wrong, not the artifact.
            if abs(float(router.threshold) - threshold) > 1e-12:
                raise ValueError(
                    f"threshold {threshold!r} does not match the router's frozen "
                    f"threshold {router.threshold!r}; refusing to serve a routed "
                    "decision at an unfrozen boundary"
                )
        self.experts = experts
        self.threshold = threshold
        self.threshold_provenance = threshold_provenance
        self.fusion = fusion
        self.router = router
        self.init_failures: list[dict] = []

    @classmethod
    def from_config(cls, config: dict | None = None, experts: list[Expert] | None = None,
                    registry: dict | None = None):
        """Build from configs/predict.yaml, instantiating enabled experts.

        An expert that fails to initialize is dropped with its reason recorded
        (ExpertInitError semantics); the run continues on the survivors.
        """
        cfg = config or load_predict_config()
        init_failures: list[dict] = []
        if experts is None:
            registry = registry or _default_registry()
            experts = []
            for spec in cfg.get("experts", []):
                if not spec.get("enabled", True):
                    continue
                factory = registry.get(spec["id"])
                if factory is None:
                    raise ValueError(f"unknown expert id in config: {spec['id']!r}")
                try:
                    experts.append(factory(device=spec.get("device")))
                except ExpertInitError as exc:
                    # An unavailable expert degrades the cascade; it does not
                    # abort the run (doc 03). Zero survivors IS fatal (B-012 #1).
                    init_failures.append({
                        "expert_id": exc.expert_id, "reason_code": exc.reason_code,
                        "message": exc.message,
                    })
            if not experts:
                raise ExpertInitError(
                    "registry", "no_experts_available",
                    f"every configured expert failed to initialize: {init_failures}",
                )
        fusion = cfg.get("fusion", "naive_mean")
        threshold = cfg["threshold"]
        threshold_provenance = cfg.get("threshold_provenance", "unspecified")
        router = None
        if fusion == "router":
            router, threshold, threshold_provenance = _load_router_from_config(cfg)
        service = cls(
            experts=experts,
            threshold=threshold,
            threshold_provenance=threshold_provenance,
            fusion=fusion,
            router=router,
        )
        # Recorded so the run manifest can report which experts were absent and
        # why; empty when the caller supplied experts directly.
        service.init_failures = init_failures
        return service

    def predict_image(self, path_or_bytes, transform_id: str = "clean") -> PredictionRecord:
        """Decode then score. Raises DecodeError for an unreadable input."""
        return self.predict_decoded(decode_image(path_or_bytes), transform_id)

    def predict_decoded(self, img: DecodedImage, transform_id: str = "clean") -> PredictionRecord:
        started = time.perf_counter()
        warnings = list(img.warnings)

        image = img.image
        transform_ms = 0.0
        if transform_id != "clean":
            t0 = time.perf_counter()
            image = apply_transform(image, transform_id, img.sha256)
            transform_ms = (time.perf_counter() - t0) * 1000.0
            # The experts must see the transformed pixels, so hand them a view
            # of the same provenance with the transformed image swapped in.
            img = _with_image(img, image)

        outputs: list[ExpertOutput] = []
        failures: list[dict[str, Any]] = []
        components: dict[str, float] = {"transform": round(transform_ms, 3)}
        for expert in self.experts:
            try:
                out = expert.predict(img)
            except ExpertInferenceError as exc:
                # Recoverable: record it, mark the expert unavailable for THIS
                # image, and degrade. No invented logit (review note N1).
                failures.append(exc.to_dict())
                warnings.append(f"expert_failed:{exc.expert_id}:{exc.reason_code}")
                continue
            outputs.append(out)
            components[out.expert_id] = round(out.inference_ms, 3)
            # Surface preprocessing warnings at the top level, prefixed so they
            # stay machine-readable. Without this the UI showed "none" while CF
            # was reporting upsampled_before_crop (B-012 #2).
            warnings.extend(f"{out.expert_id}:{w}" for w in out.warnings)

        if not outputs:
            raise PredictionError(
                f"no expert produced a score for {img.sha256[:12]} "
                f"({len(failures)} failure(s)): {failures}"
            )

        reliability: float | None = None
        router_info: dict[str, Any] | None = None
        if self.fusion == "router":
            # The router reads quality descriptors and probe responses, so this
            # is where the extra work happens: probes re-score the expert on
            # perturbed views. Cost is measured, not hidden -- it lands in
            # `inference_ms.components.router`.
            t0 = time.perf_counter()
            from ..router.feature_cache import extract_feature_blocks

            blocks = extract_feature_blocks(
                img, self.experts, precomputed={o.expert_id: o for o in outputs},
            )
            score = self.router.score_blocks(blocks)
            components["router"] = round((time.perf_counter() - t0) * 1000.0, 3)
            p_fake = score.p_fake
            reliability = score.reliability
            abstain = bool(score.abstain)
            abstain_reason = (
                f"reliability {score.reliability:.4f} below the frozen policy threshold {score.abstain_threshold:.4f}"
                if abstain and score.reliability is not None
                and score.abstain_threshold is not None else None
            )
            router_info = {
                "rung": score.rung,
                "n_parameters": score.n_parameters,
                "expert_available": score.expert_available,
                "primary_p_fake": (
                    sum(o.p_fake for o in outputs) / len(outputs)
                ),
                "quality": blocks.get("quality"),
                "abstain_threshold": score.abstain_threshold,
            }
        else:
            abstain, abstain_reason = False, None
            p_fake = sum(o.p_fake for o in outputs) / len(outputs)  # Phase 0 naive mean
        forced = int(p_fake >= self.threshold)  # >= so p == threshold predicts fake

        total_ms = (time.perf_counter() - started) * 1000.0
        return PredictionRecord(
            schema_version=SCHEMA_VERSION,
            image={
                "sha256": img.sha256,
                "width": image.width,
                "height": image.height,
                "format": img.orig_format,
                "warnings": list(img.warnings),
            },
            transform_id=transform_id,
            p_fake=p_fake,
            forced_prediction=forced,
            decision="AI-GENERATED" if forced else "REAL",
            reliability=reliability,   # None unless the head was actually fitted
            experts=[o.to_json_dict() for o in outputs],
            expert_failures=failures,
            rescue_invoked=False,      # rescue path lands in Phase 3
            inference_ms={"total": round(total_ms, 3), "components": components},
            warnings=warnings,
            pipeline_version=PIPELINE_VERSION,
            threshold_used=self.threshold,
            threshold_provenance=self.threshold_provenance,
            fusion=self.fusion,
            router=router_info,
            abstain=abstain,
            abstain_reason=abstain_reason,
        )


def _with_image(img: DecodedImage, image) -> DecodedImage:
    """Same provenance, transformed pixels (DecodedImage is frozen)."""
    from dataclasses import replace

    return replace(img, image=image, width=image.width, height=image.height)


__all__ = [
    "SCHEMA_VERSION",
    "DecodeError",
    "PredictionError",
    "PredictionRecord",
    "PredictionService",
    "load_predict_config",
]
