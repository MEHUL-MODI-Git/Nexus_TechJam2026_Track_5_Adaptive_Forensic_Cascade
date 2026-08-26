"""The official 20-condition transform grid (task 0.3, core spec v2 §2).

Every parameter comes from configs/transforms.yaml -- this module holds no
duplicate numeric literals, so there is exactly one authoritative value path
and the YAML can be diffed against the protocol manifest we publish.

Two invariants the whole evaluation rests on:

1. Determinism. Same (image, condition_id) -> byte-identical output, always.
   Noise seeds are derived from the image's own content hash, never from a
   global RNG, so a re-run on another machine reproduces the exact pixels.
2. Fidelity to the stated protocol. Blur is a true Gaussian convolution (not
   PIL's box approximation), resize is down-then-back-up (the point is the
   resampling damage, not the final size), and crop STAYS cropped -- each
   expert applies its own input policy afterwards.

Signature is (image, sha256) -> image; the hash is used for seeding only.
"""

from __future__ import annotations

import hashlib
import io
import math
from pathlib import Path
from typing import Callable

import numpy as np
import PIL.Image
import torch
import torchvision.transforms.v2.functional as TF
import yaml

from .version import PIPELINE_VERSION

_CONFIG_PATH = Path(__file__).resolve().parents[2] / "configs" / "transforms.yaml"

# Every computed output dimension passes through this guard (review note N7):
# a 1x1 input must survive all 20 conditions rather than producing a 0-sized axis.
def _dim(value: float) -> int:
    return max(1, int(round(value)))


def load_transform_config(path: Path | None = None) -> dict:
    """Load and validate the protocol config.

    Fails fast on version drift: if the YAML and src/pipeline/version.py
    disagree, cached features and golden hashes can no longer be trusted.
    """
    cfg = yaml.safe_load((path or _CONFIG_PATH).read_text())
    if cfg["pipeline_version"] != PIPELINE_VERSION:
        raise RuntimeError(
            f"transform config version {cfg['pipeline_version']!r} != "
            f"PIPELINE_VERSION {PIPELINE_VERSION!r} -- bump both together"
        )
    return cfg


CONFIG = load_transform_config()
CONDITIONS: dict[str, dict] = CONFIG["conditions"]
MANIFEST: dict[str, dict] = CONFIG["manifest"]

# condition_id -> family, used by the eval threshold objective (6 transform
# families; `clean` is excluded from the objective and enters via constraints).
FAMILY_OF: dict[str, str] = {cid: spec["family"] for cid, spec in CONDITIONS.items()}


# --------------------------------------------------------------------------
# float32 <-> uint8 conversion. The rounding convention is part of the protocol:
# changing it changes every golden hash.
# --------------------------------------------------------------------------
def _to_float_chw(img: PIL.Image.Image) -> torch.Tensor:
    # np.array (not asarray) so the buffer is writable: torch.from_numpy on a
    # read-only PIL buffer warns and yields undefined write behavior.
    arr = np.array(img, dtype=np.uint8)
    return torch.from_numpy(arr).permute(2, 0, 1).to(torch.float32) / 255.0


def _to_pil_uint8(t: torch.Tensor) -> PIL.Image.Image:
    arr = t.clamp(0.0, 1.0).permute(1, 2, 0).numpy()
    arr = np.round(arr * 255.0).clip(0, 255).astype(np.uint8)
    return PIL.Image.fromarray(arr)


def noise_seed(orig_sha256: str, condition_id: str) -> int:
    """Byte-exact per-image/condition seed (review note N5).

    payload = ASCII "<lowercase orig sha256>:<condition_id>" (single 0x3A colon,
    no whitespace); seed = first 16 hex CHARACTERS of the digest parsed as a
    big-endian integer (int(str, 16) is big-endian by definition, so digest
    bytes 0..7 are the high-order bytes).
    """
    payload = f"{orig_sha256.lower()}:{condition_id}".encode("ascii")
    return int(hashlib.sha256(payload).hexdigest()[:16], 16)


# --------------------------------------------------------------------------
# The six transform families
# --------------------------------------------------------------------------
def _clean(img: PIL.Image.Image, sha256: str, spec: dict) -> PIL.Image.Image:
    # Identity: no re-encode, no array round-trip. The clean view must be the
    # decoded pixels exactly, or every drop_M(t) measurement is biased.
    return img


def _jpeg(img: PIL.Image.Image, sha256: str, spec: dict) -> PIL.Image.Image:
    m = MANIFEST["jpeg"]
    buf = io.BytesIO()
    img.save(
        buf,
        format="JPEG",
        quality=int(spec["quality"]),
        subsampling=int(m["subsampling"]),   # 2 == 4:2:0
        optimize=bool(m["optimize"]),
        progressive=bool(m["progressive"]),
    )
    buf.seek(0)
    return PIL.Image.open(buf).convert("RGB")


def _blur(img: PIL.Image.Image, sha256: str, spec: dict) -> PIL.Image.Image:
    sigma = float(spec["sigma"])
    # k = 2*ceil(3*sigma)+1 -- odd, and wide enough that truncation is negligible.
    # sigma is passed EXPLICITLY; torchvision would otherwise derive its own from
    # kernel_size, silently changing the amount of blur (review note N6).
    k = 2 * math.ceil(3 * sigma) + 1
    # Reflect padding requires pad < min(H, W), so a kernel wider than the image
    # crashes torchvision. Clamp to the widest legal odd kernel and keep sigma
    # unchanged: the Gaussian is simply truncated harder. This only engages for
    # images smaller than ceil(3*sigma)+1 px (< 7px at sigma=2.0) -- it never
    # touches a normal image, but it stops a thumbnail in judge data from
    # taking down a whole batch run.
    w, h = img.size
    k = min(k, 2 * min(h, w) - 1)
    t = _to_float_chw(img)
    if k <= 1:  # a 1px-wide kernel is the identity; skip the conv entirely
        return img.copy()
    out = TF.gaussian_blur(t, kernel_size=[k, k], sigma=[sigma, sigma])
    return _to_pil_uint8(out)


def _resize(img: PIL.Image.Image, sha256: str, spec: dict) -> PIL.Image.Image:
    m = MANIFEST["resize"]
    scale = float(spec["scale"])
    w, h = img.size
    t = _to_float_chw(img)
    small = TF.resize(
        t, [_dim(h * scale), _dim(w * scale)],
        interpolation=TF.InterpolationMode.BILINEAR, antialias=bool(m["antialias"]),
    )
    # Back up to the ORIGINAL size: the condition models resampling damage, so
    # the output must be comparable pixel-for-pixel with the clean view.
    back = TF.resize(
        small, [_dim(h), _dim(w)],
        interpolation=TF.InterpolationMode.BILINEAR, antialias=bool(m["antialias"]),
    )
    return _to_pil_uint8(back)


def _noise(img: PIL.Image.Image, sha256: str, spec: dict) -> PIL.Image.Image:
    sigma = float(spec["sigma"])  # in [0,1] units (stated assumption, webinar Q5)
    rng = np.random.default_rng(noise_seed(sha256, spec["_condition_id"]))
    arr = np.array(img, dtype=np.float32) / 255.0
    arr = arr + rng.normal(0.0, sigma, arr.shape)  # independent per channel
    arr = np.clip(arr, 0.0, 1.0)
    return PIL.Image.fromarray(np.round(arr * 255.0).clip(0, 255).astype(np.uint8))


_ADJUST = {
    "brightness": TF.adjust_brightness,
    "contrast": TF.adjust_contrast,
    "saturation": TF.adjust_saturation,
}


def _color(img: PIL.Image.Image, sha256: str, spec: dict) -> PIL.Image.Image:
    t = _to_float_chw(img)
    out = _ADJUST[spec["property"]](t, float(spec["factor"]))
    return _to_pil_uint8(out)


def _crop(img: PIL.Image.Image, sha256: str, spec: dict) -> PIL.Image.Image:
    m = MANIFEST["crop"]
    keep = float(spec["keep"])
    w, h = img.size
    th, tw = _dim(h * keep), _dim(w * keep)
    top, left = (h - th) // 2, (w - tw) // 2  # floor((size - target) / 2)
    # Output stays at the cropped size (no resize back) -- adapters own their
    # input policy, and resizing here would double-apply a resampling artifact.
    return img.crop((left, top, left + tw, top + th))


_KIND_DISPATCH: dict[str, Callable] = {
    "identity": _clean, "jpeg": _jpeg, "blur": _blur,
    "resize": _resize, "noise": _noise, "color": _color, "crop": _crop,
}


def _make(condition_id: str, spec: dict) -> Callable[[PIL.Image.Image, str], PIL.Image.Image]:
    fn = _KIND_DISPATCH[spec["kind"]]
    bound = dict(spec, _condition_id=condition_id)  # seeding needs its own id

    def apply(img: PIL.Image.Image, sha256: str) -> PIL.Image.Image:
        if img.mode != "RGB":
            raise ValueError(f"transforms require canonical RGB input, got {img.mode!r}")
        return fn(img, sha256, bound)

    apply.__name__ = f"transform_{condition_id}"
    apply.condition_id = condition_id
    apply.family = spec["family"]
    return apply


TRANSFORMS: dict[str, Callable[[PIL.Image.Image, str], PIL.Image.Image]] = {
    cid: _make(cid, spec) for cid, spec in CONDITIONS.items()
}

# The 20 official condition ids from docs/05, in canonical (stable) order.
CONDITION_IDS: list[str] = list(TRANSFORMS)

assert len(CONDITION_IDS) == 20, f"expected 20 official conditions, got {len(CONDITION_IDS)}"


def apply_transform(img: PIL.Image.Image, condition_id: str, sha256: str) -> PIL.Image.Image:
    """Apply one official condition. Unknown ids are a hard error, never a no-op."""
    try:
        fn = TRANSFORMS[condition_id]
    except KeyError:
        raise KeyError(
            f"unknown condition_id {condition_id!r}; official ids: {CONDITION_IDS}"
        ) from None
    return fn(img, sha256)
