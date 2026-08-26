"""Quality descriptors (task 1.4, doc 03 step 1).

Cheap, training-free statistics describing HOW an image arrived rather than
what is in it: is it blurry, was it JPEG-compressed hard, how noisy is it, how
big is it. In Phase 2 these become router features -- the router learns when to
trust the primary expert, and "this image is a 200px hard-compressed thumbnail"
is exactly the context that should lower that trust.

Design rules:
- Deterministic and dependency-light (numpy only): these run on every image in
  the feature cache, so they must be fast and reproducible.
- Every descriptor is scale-aware or explicitly normalized, so a 4000px photo
  and a 200px thumbnail produce comparable numbers.
- Computed on the CANONICAL decoded image (post-EXIF, RGB uint8), i.e. the same
  pixels the experts see. Never on the raw file bytes.
- Tiny images must not crash: every kernel guards its own minimum size.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from .decode import DecodedImage

SCHEMA_VERSION = "quality-descriptors.v1"

# Rec. 601 luma weights -- matches the convention used by PIL's "L" conversion.
_LUMA = np.array([0.299, 0.587, 0.114], dtype=np.float64)

# 4-neighbour discrete Laplacian.
_LAPLACIAN = np.array([[0.0, 1.0, 0.0], [1.0, -4.0, 1.0], [0.0, 1.0, 0.0]])


@dataclass(frozen=True)
class QualityDescriptors:
    """Scale-comparable image-quality statistics. All values are finite."""

    schema_version: str
    width: int
    height: int
    megapixels: float
    aspect_ratio: float          # width / height
    is_portrait: bool
    blur_varlap: float           # variance of Laplacian on [0,1] luma; LOW = blurry
    blockiness: float            # JPEG 8x8 grid energy ratio; HIGH = block artifacts
    noise_sigma: float           # robust high-frequency noise estimate, [0,1] units
    luminance_mean: float        # [0,1]
    luminance_std: float         # [0,1] -- global contrast proxy
    saturation_mean: float       # [0,1] mean (max-min)/max over channels
    clipped_low_frac: float      # fraction of pixels at 0 (crushed blacks)
    clipped_high_frac: float     # fraction of pixels at 255 (blown highlights)

    def to_json_dict(self) -> dict:
        return asdict(self)


def _luma01(rgb: np.ndarray) -> np.ndarray:
    """Luma in [0,1] as float64."""
    return (rgb.astype(np.float64) @ _LUMA) / 255.0


def _convolve2d_valid(img: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    """Small 'valid' 2-D correlation via strides -- avoids a scipy dependency."""
    kh, kw = kernel.shape
    h, w = img.shape
    if h < kh or w < kw:
        return np.zeros((0, 0), dtype=np.float64)
    windows = np.lib.stride_tricks.sliding_window_view(img, (kh, kw))
    return np.einsum("ijkl,kl->ij", windows, kernel)


def blur_varlap(luma: np.ndarray) -> float:
    """Variance of the Laplacian: the standard cheap focus measure.

    Low = smooth/blurry, high = sharp detail. Computed on [0,1] luma so the
    value does not depend on bit depth.
    """
    lap = _convolve2d_valid(luma, _LAPLACIAN)
    if lap.size == 0:  # image smaller than the kernel
        return 0.0
    return float(np.var(lap))


def blockiness(luma: np.ndarray) -> float:
    """JPEG blocking proxy: energy on the 8x8 grid vs energy off it.

    JPEG quantizes 8x8 DCT blocks independently, so compression artifacts
    concentrate discontinuities on block boundaries. Ratio near 1.0 = no
    blocking; >1 = boundaries are stronger than interior edges, i.e. blocking.
    Returns 0.0 when the image is too small for a meaningful grid.

    KNOWN LIMITATION (measured, see tests): content that is itself 8-pixel
    periodic and grid-aligned -- fences, blinds, halftone, UI screenshots --
    inflates this metric regardless of compression, and can even make it fall
    as quality drops (JPEG smooths the aliasing). Our own `photo.png` fixture
    does exactly this and scores ~22 while uncompressed. So this is a useful
    ROUTER FEATURE, not a standalone compression detector: the router sees it
    alongside resolution and noise and can learn when it is trustworthy. Do not
    threshold on it directly.
    """
    h, w = luma.shape
    if h < 17 or w < 17:
        return 0.0

    col_diff = np.abs(np.diff(luma, axis=1)).mean(axis=0)  # per-column-boundary
    row_diff = np.abs(np.diff(luma, axis=0)).mean(axis=1)

    # diff index i sits between pixels i and i+1; a JPEG block edge is at i == 7 mod 8.
    col_idx = np.arange(col_diff.size)
    row_idx = np.arange(row_diff.size)
    col_on = col_diff[col_idx % 8 == 7]
    col_off = col_diff[col_idx % 8 != 7]
    row_on = row_diff[row_idx % 8 == 7]
    row_off = row_diff[row_idx % 8 != 7]

    on = np.concatenate([col_on, row_on])
    off = np.concatenate([col_off, row_off])
    if on.size == 0 or off.size == 0:
        return 0.0
    off_mean = float(off.mean())
    if off_mean <= 1e-12:  # perfectly flat image: no edges anywhere, no blocking
        return 0.0
    return float(on.mean() / off_mean)


def noise_sigma(luma: np.ndarray) -> float:
    """Robust noise estimate (Immerkaer): MAD-free median of a Laplacian-like mask.

    Uses the median absolute response rather than the mean so that genuine
    edges -- which are sparse -- do not masquerade as noise. Scaled to the
    standard-deviation units of the [0,1] luma.
    """
    mask = np.array([[1.0, -2.0, 1.0], [-2.0, 4.0, -2.0], [1.0, -2.0, 1.0]])
    response = _convolve2d_valid(luma, mask)
    if response.size == 0:
        return 0.0
    # 0.6745 converts a median absolute deviation to a Gaussian sigma;
    # sqrt(36) = 6 is the L2 norm of the mask above.
    mad = float(np.median(np.abs(response)))
    return float(mad / 0.6745 / 6.0)


def compute_quality(img: DecodedImage) -> QualityDescriptors:
    """Compute all descriptors for one decoded image."""
    rgb = np.array(img.image, dtype=np.uint8)
    if rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError(f"quality descriptors require RGB, got shape {rgb.shape}")

    luma = _luma01(rgb)
    height, width = luma.shape
    rgb_f = rgb.astype(np.float64) / 255.0

    channel_max = rgb_f.max(axis=2)
    channel_min = rgb_f.min(axis=2)
    with np.errstate(divide="ignore", invalid="ignore"):
        sat = np.where(channel_max > 0, (channel_max - channel_min) / channel_max, 0.0)

    return QualityDescriptors(
        schema_version=SCHEMA_VERSION,
        width=width,
        height=height,
        megapixels=float(width * height / 1e6),
        aspect_ratio=float(width / height),
        is_portrait=bool(height > width),
        blur_varlap=blur_varlap(luma),
        blockiness=blockiness(luma),
        noise_sigma=noise_sigma(luma),
        luminance_mean=float(luma.mean()),
        luminance_std=float(luma.std()),
        saturation_mean=float(np.nan_to_num(sat).mean()),
        clipped_low_frac=float((rgb == 0).all(axis=2).mean()),
        clipped_high_frac=float((rgb == 255).all(axis=2).mean()),
    )
