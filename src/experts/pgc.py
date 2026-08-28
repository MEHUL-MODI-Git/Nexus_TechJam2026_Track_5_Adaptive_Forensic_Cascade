"""PGC (Peak-Guided Calibration) adapter — candidate SECOND expert.

Licence: Apache-2.0 (repo `xiaoyu6868/PGC`, HF `xiaoyuzhou68/PGC_ckpt`). The
official code is vendored under `third_party/PGC` and imported rather than
reimplemented, because the LOTA failure taught us that a detector's behaviour
lives in its preprocessing: PGC scores the QUANTIZATION RESIDUAL alongside RGB,
and a residual computed even slightly differently is a different model.

Deterministic by construction: evaluation uses `PadCenterCrop`, not the random
crop used in training, so the same image always scores the same. (LOTA's random
patch made its score vary by up to 0.31 between runs on one image.)

Parameters ~306.7M. With CF-384's 21.8M the cascade totals ~328.5M, inside the
<2B rule with three orders of magnitude to spare.
"""

from __future__ import annotations

import contextlib
import math
import sys
import time
from pathlib import Path

import torch
from PIL import Image

from ..pipeline.decode import DecodedImage
from .base import ExpertInferenceError, ExpertInitError, ExpertOutput

_ROOT = Path(__file__).resolve().parents[2]
_PGC_ROOT = _ROOT / "third_party" / "PGC"
_DINO_VARIANT = "dinov2-large"
_IMAGE_SIZE = 224


def _select_device(requested: str | None) -> torch.device:
    if requested:
        return torch.device(requested)
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


@contextlib.contextmanager
def _pgc_importable():
    """Put the vendored official package on the path for the duration."""
    added = str(_PGC_ROOT)
    if added not in sys.path:
        sys.path.insert(0, added)
        inserted = True
    else:
        inserted = False
    try:
        yield
    finally:
        if inserted:
            with contextlib.suppress(ValueError):
                sys.path.remove(added)


class PGCExpert:
    """Second-opinion expert. Same contract as every other adapter."""

    expert_id = "pgc"
    license = "Apache-2.0"

    def __init__(self, device: str | None = None,
                 checkpoint: str | Path | None = None) -> None:
        self.device = _select_device(device)
        if not _PGC_ROOT.exists():
            raise ExpertInitError(self.expert_id, "missing_code",
                                  f"vendored PGC source not found at {_PGC_ROOT}")
        ckpt_path = Path(checkpoint) if checkpoint else self._default_checkpoint()
        if ckpt_path is None or not Path(ckpt_path).exists():
            raise ExpertInitError(self.expert_id, "missing_checkpoint",
                                  f"PGC checkpoint not found ({ckpt_path})")
        self.checkpoint_path = Path(ckpt_path)

        try:
            with _pgc_importable():
                from data.transforms import create_eval_transforms
                from models.pgc import PGCNetwork

                model = self._build_network(PGCNetwork)
                self.preprocess = create_eval_transforms(image_size=_IMAGE_SIZE)
        except ExpertInitError:
            raise
        except Exception as exc:
            raise ExpertInitError(self.expert_id, "load_failed",
                                  f"{type(exc).__name__}: {exc}") from exc

        payload = torch.load(self.checkpoint_path, map_location="cpu", weights_only=False)
        state = payload.get("model", payload.get("state_dict", payload))
        missing, unexpected = model.load_state_dict(state, strict=False)
        # STRICT: a partially loaded forensic model silently becomes a different
        # model that still returns confident numbers. Refuse it.
        if missing or unexpected:
            raise ExpertInitError(
                self.expert_id, "unexpected_state_dict",
                f"{len(missing)} missing, {len(unexpected)} unexpected keys; "
                f"missing[:3]={list(missing)[:3]} unexpected[:3]={list(unexpected)[:3]}",
            )
        model.eval().to(self.device)
        self.model = model
        self.param_count = sum(p.numel() for p in model.parameters())
        self.model_version = f"pgc@{self.checkpoint_path.name}"

    @staticmethod
    def _default_checkpoint() -> Path | None:
        hits = sorted((_ROOT / "data" / "hf_cache").rglob("PGC_train_*_ckpt.pth"))
        return hits[0] if hits else None

    def _build_network(self, PGCNetwork):
        """Construct PGCNetwork without a local DINOv2 weight directory.

        Our checkpoint carries the full backbone (`rgb_stream.backbone.*`), so
        only the ARCHITECTURE is needed here; the weights are overwritten by the
        strict load below. We patch the loader rather than rebuild the module
        graph ourselves, so the official __init__ (LoRA injection included) runs
        exactly as upstream wrote it.
        """
        import transformers
        from models.encoder import rgb_stream as rs
        from transformers import Dinov2Config, Dinov2Model

        cfg = Dinov2Config.from_pretrained(f"facebook/{_DINO_VARIANT}")
        orig_resolve, orig_from_pretrained = rs.resolve_local_dino_path, transformers.AutoModel.from_pretrained
        rs.resolve_local_dino_path = lambda name, root: "<in-checkpoint>"
        transformers.AutoModel.from_pretrained = staticmethod(lambda *a, **k: Dinov2Model(cfg))
        rs.AutoModel = transformers.AutoModel
        try:
            return PGCNetwork(dino_variant=_DINO_VARIANT, pretrained_root="<in-checkpoint>")
        finally:
            rs.resolve_local_dino_path = orig_resolve
            transformers.AutoModel.from_pretrained = orig_from_pretrained
            rs.AutoModel = transformers.AutoModel

    def _forward_logit(self, image: Image.Image) -> float:
        tensor = self.preprocess(image).unsqueeze(0).to(self.device)
        with torch.inference_mode():
            out = self.model(tensor)
        return float(out.reshape(-1)[0])

    def predict(self, img: DecodedImage) -> ExpertOutput:
        t0 = time.perf_counter()
        try:
            logit = self._forward_logit(img.image)
        except Exception as exc:
            raise ExpertInferenceError(
                self.expert_id, "inference_failed", f"{type(exc).__name__}: {exc}",
                image_sha256=img.sha256,
            ) from exc
        if not math.isfinite(logit):
            raise ExpertInferenceError(
                self.expert_id, "non_finite_logit", f"logit={logit}",
                image_sha256=img.sha256,
            )
        # Upstream labels fake=1 and trains a single logit with BCE, so higher
        # means more likely generated -- the same polarity as CF-384. Sigmoid is
        # applied exactly once, here.
        p_fake = 1.0 / (1.0 + math.exp(-logit)) if abs(logit) < 60 else float(logit > 0)
        return ExpertOutput(
            expert_id=self.expert_id,
            raw_logit=logit,
            p_fake=p_fake,
            inference_ms=(time.perf_counter() - t0) * 1000.0,
            model_version=self.model_version,
        )


__all__ = ["PGCExpert"]
