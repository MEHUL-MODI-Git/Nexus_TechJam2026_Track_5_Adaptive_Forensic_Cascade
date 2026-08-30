"""Community Forensics 384 adapter (task 0.5, core spec v2 §5).

Primary expert: ViT-Small/16 @384, 21.8M params, MIT (code + weights),
`OwensLab/commfor-model-384`. Paper: Park & Owens, CVPR 2025 (arXiv:2411.04125).
Preprocessing and output semantics verified against the upstream `main` branch
in handoffs/2026-08-26_commfor-integration.md.

Three upstream traps this adapter exists to neutralize:

1. The checkpoint's config.json hardcodes `device: "cuda"`, and
   PyTorchModelHubMixin.from_pretrained re-instantiates the class with those
   saved kwargs -- so the official load path fails on Apple Silicon. We build
   the timm backbone ourselves and load the state dict directly.
2. The model returns a RAW LOGIT (BCEWithLogitsLoss upstream, author-confirmed
   in issue #4). Sigmoid is applied here exactly once; nothing downstream may
   apply it again.
3. Two branches use different normalization constants. `main` uses ImageNet
   norm and the author confirmed that is the correct one (issue #5).

Polarity: upstream label format is real:0 / fake:1, so a high logit already
means AI-generated -- matching our convention, no flip needed.
"""

from __future__ import annotations

import time

import torch
import torchvision.transforms as T
from PIL import Image

from ..pipeline.decode import DecodedImage
from ..pipeline.hf_cache import use_repo_local_cache
from .base import ExpertInferenceError, ExpertInitError, ExpertOutput

use_repo_local_cache()      # HF weights land in data/hf_cache/, not ~/.cache

HF_REPO = "OwensLab/commfor-model-384"
TIMM_ARCH = "vit_small_patch16_384.augreg_in21k_ft_in1k"

# Upstream get_transform(mode="test") for input_size=384 (dataloader.py):
# Resize(440) shorter edge -> CenterCrop(384) -> ToTensor [0,1] -> ImageNet norm.
RESIZE_SHORTER_EDGE = 440
CROP_SIZE = 384
IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]


def _select_device(requested: str | None) -> torch.device:
    if requested:
        return torch.device(requested)
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


class CommForExpert:
    """Adapter implementing the Expert protocol for Community Forensics 384."""

    expert_id = "commfor_384"
    license = "MIT"

    def __init__(self, device: str | None = None, revision: str | None = None) -> None:
        self.device = _select_device(device)
        try:
            import timm
            from huggingface_hub import hf_hub_download
            from safetensors.torch import load_file
        except ImportError as exc:  # missing dependency = expert unavailable, not a crash
            raise ExpertInitError(self.expert_id, "missing_dependency", str(exc)) from exc

        try:
            config_path = hf_hub_download(HF_REPO, "config.json", revision=revision)
            weights_path = hf_hub_download(HF_REPO, "model.safetensors", revision=revision)
            # The HF snapshot directory name IS the resolved commit sha.
            resolved = __import__("pathlib").Path(weights_path).parent.name
            self.revision = resolved
            self.model_version = f"{HF_REPO}@{resolved}"
            # B-032 P0: an unpinned expert means a fresh clone can serve different
            # bytes than the ones every cached feature and published number was
            # computed from. When the caller pins a revision we verify we actually
            # got it, rather than trusting the request.
            if revision is not None and resolved != revision:
                raise ExpertInitError(
                    self.expert_id, "revision_mismatch",
                    f"requested revision {revision!r} but resolved to {resolved!r}; "
                    "refusing to serve weights that are not the frozen ones",
                )

            # pretrained=False: the checkpoint is a COMPLETE state dict, so
            # downloading ImageNet weights only to overwrite them wastes ~85MB.
            # strict=True below is what guarantees nothing is left at init values.
            model = timm.create_model(TIMM_ARCH, pretrained=False, num_classes=1)
            state = load_file(weights_path)
            # Upstream wraps the backbone as self.vit inside ViTClassifier.
            stripped = {k[len("vit.") :]: v for k, v in state.items() if k.startswith("vit.")}
            if len(stripped) != len(state):
                raise ExpertInitError(
                    self.expert_id, "unexpected_state_dict",
                    f"{len(state) - len(stripped)} keys lack the expected 'vit.' prefix",
                )
            # strict=True: any missing/unexpected key is a load failure, which is
            # the guarantee that no layer silently keeps its random init.
            model.load_state_dict(stripped, strict=True)
        except ExpertInitError:
            raise
        except Exception as exc:
            raise ExpertInitError(self.expert_id, "load_failed", f"{type(exc).__name__}: {exc}") from exc

        model.eval().to(self.device)
        self.model = model
        self.param_count = sum(p.numel() for p in model.parameters())
        self.config_path = config_path

        # Applied to the PIL image, exactly as upstream does (torchvision v1
        # transforms on PIL, not on a pre-made tensor -- the resample path differs).
        self.preprocess = T.Compose([
            T.Resize(RESIZE_SHORTER_EDGE),
            T.CenterCrop(CROP_SIZE),
            T.ToTensor(),
            T.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
        ])

    def _forward_logit(self, image: Image.Image, device: torch.device) -> float:
        tensor = self.preprocess(image).unsqueeze(0).to(device)
        with torch.inference_mode():
            out = self.model(tensor)
        return float(out.reshape(-1)[0].item())

    def predict(self, img: DecodedImage) -> ExpertOutput:
        """Score one decoded image. Raises ExpertInferenceError on failure."""
        started = time.perf_counter()
        try:
            logit = self._forward_logit(img.image, self.device)
        except Exception as exc:
            raise ExpertInferenceError(
                self.expert_id, "inference_failed",
                f"{type(exc).__name__}: {exc}", image_sha256=img.sha256,
            ) from exc

        elapsed_ms = (time.perf_counter() - started) * 1000.0
        warnings: list[str] = []
        # Upstream returns a logit; sigmoid belongs here and nowhere else.
        p_fake = float(torch.sigmoid(torch.tensor(logit)).item())

        if img.width < CROP_SIZE or img.height < CROP_SIZE:
            # Resize(440) upsamples such an image before the 384 crop: the
            # verdict is still produced, but the evidence was interpolated.
            warnings.append(f"upsampled_before_crop:{img.width}x{img.height}")

        return ExpertOutput(
            expert_id=self.expert_id,
            raw_logit=logit,
            p_fake=p_fake,
            inference_ms=elapsed_ms,
            warnings=warnings,
            model_version=self.model_version,
        )

    def logit_on_device(self, img: DecodedImage, device: str) -> float:
        """Score on an explicitly chosen device -- used by the MPS-vs-CPU check.

        MPS correctness for this architecture is unverified upstream, so the
        sanity script compares both backends before we trust MPS numbers.
        """
        original = next(self.model.parameters()).device
        target = torch.device(device)
        try:
            self.model.to(target)
            return self._forward_logit(img.image, target)
        finally:
            self.model.to(original)
