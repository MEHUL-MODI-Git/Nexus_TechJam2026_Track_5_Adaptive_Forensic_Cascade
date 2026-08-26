"""Quality descriptor tests (task 1.4).

These pin the DIRECTION of each descriptor under the official conditions --
the property the router will depend on -- rather than exact values, which are
content-dependent by nature.
"""

from dataclasses import replace

import numpy as np
import pytest
from PIL import Image

from src.pipeline.decode import decode_image
from src.pipeline.quality import SCHEMA_VERSION, compute_quality
from src.pipeline.transforms import apply_transform

import io
from pathlib import Path

GOLDEN = Path(__file__).parent / "golden" / "sources"


def _decoded(name: str):
    return decode_image(GOLDEN / f"{name}.png")


def _under(name: str, condition_id: str):
    d = _decoded(name)
    return compute_quality(replace(d, image=apply_transform(d.image, condition_id, d.sha256)))


def _from_array(arr: np.ndarray):
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, "PNG")
    return compute_quality(decode_image(buf.getvalue()))


# --- structure ------------------------------------------------------------
def test_schema_and_geometry():
    q = _decoded("photo")
    d = compute_quality(q)
    assert d.schema_version == SCHEMA_VERSION
    assert (d.width, d.height) == (256, 192)
    assert d.aspect_ratio == pytest.approx(256 / 192)
    assert d.is_portrait is False
    assert d.megapixels == pytest.approx(256 * 192 / 1e6)


def test_portrait_detected():
    assert _from_array(np.zeros((40, 20, 3), dtype=np.uint8)).is_portrait is True


def test_all_values_finite():
    for name in ("photo", "gradient", "texture"):
        for value in compute_quality(_decoded(name)).to_json_dict().values():
            if isinstance(value, float):
                assert np.isfinite(value)


def test_rejects_non_rgb():
    d = _decoded("photo")
    with pytest.raises(ValueError):
        compute_quality(replace(d, image=d.image.convert("L")))


# --- blur -----------------------------------------------------------------
@pytest.mark.parametrize("name", ["photo", "texture"])
def test_blur_reduces_varlap_monotonically(name):
    values = [_under(name, c).blur_varlap for c in ("clean", "blur_s0.5", "blur_s1.0", "blur_s2.0")]
    assert values == sorted(values, reverse=True)


def test_linear_gradient_sits_at_the_varlap_floor():
    """A linear ramp has a zero Laplacian by construction, so blurring cannot
    lower it further -- the residual ~1e-7 is uint8 rounding noise. Pinned so a
    future reader does not mistake this for a broken blur estimate."""
    values = [_under("gradient", c).blur_varlap
              for c in ("clean", "blur_s0.5", "blur_s1.0", "blur_s2.0")]
    assert all(v < 1e-5 for v in values)


@pytest.mark.parametrize("name", ["photo", "texture"])
def test_downscaling_reduces_varlap(name):
    clean = _under(name, "clean").blur_varlap
    assert _under(name, "resize_0.25").blur_varlap < clean


def test_flat_image_has_zero_blur_energy():
    assert _from_array(np.full((32, 32, 3), 100, dtype=np.uint8)).blur_varlap == pytest.approx(0.0)


# --- noise ----------------------------------------------------------------
@pytest.mark.parametrize("name", ["photo", "gradient"])
def test_noise_estimate_increases_with_added_noise(name):
    values = [_under(name, c).noise_sigma
              for c in ("clean", "noise_s0.02", "noise_s0.05", "noise_s0.10")]
    assert values == sorted(values)


def test_noise_estimate_tracks_true_sigma():
    # On flat content the estimator should land in the right ballpark.
    rng = np.random.default_rng(0)
    base = np.full((128, 128, 3), 0.5)
    noisy = np.clip(base + rng.normal(0, 0.05, base.shape), 0, 1)
    est = _from_array((noisy * 255).round().astype(np.uint8)).noise_sigma
    assert 0.02 < est < 0.09


def test_clean_synthetic_image_reads_as_noiseless():
    assert _under("photo", "clean").noise_sigma == pytest.approx(0.0, abs=1e-3)


# --- blockiness -----------------------------------------------------------
@pytest.mark.parametrize("name", ["gradient", "texture"])
def test_blockiness_rises_with_jpeg_compression(name):
    clean = _under(name, "clean").blockiness
    q30 = _under(name, "jpeg_q30").blockiness
    assert q30 > clean
    assert clean == pytest.approx(1.0, abs=0.15)  # no grid energy before JPEG


def test_blockiness_known_limitation_on_8px_periodic_content():
    """Documents a MEASURED weakness, so it cannot be silently relied upon.

    photo.png contains 8-pixel-period bars aligned to the JPEG grid, which
    inflates the metric far above 1.0 with no compression at all. This is why
    blockiness is a router feature, never a standalone compression detector.
    """
    assert _under("photo", "clean").blockiness > 5.0


def test_flat_image_reports_no_blockiness():
    assert _from_array(np.full((64, 64, 3), 200, dtype=np.uint8)).blockiness == 0.0


# --- photometric ----------------------------------------------------------
def test_brightness_conditions_move_luminance():
    base = _under("photo", "clean").luminance_mean
    assert _under("photo", "bright_-20").luminance_mean < base
    assert _under("photo", "bright_+20").luminance_mean > base


def test_contrast_conditions_move_luminance_std():
    base = _under("photo", "clean").luminance_std
    assert _under("photo", "contrast_-20").luminance_std < base
    assert _under("photo", "contrast_+20").luminance_std > base


def test_saturation_conditions_move_saturation():
    base = _under("photo", "clean").saturation_mean
    assert _under("photo", "saturation_-20").saturation_mean < base
    assert _under("photo", "saturation_+20").saturation_mean > base


def test_clipping_fractions():
    arr = np.zeros((10, 10, 3), dtype=np.uint8)
    arr[:5] = 255
    q = _from_array(arr)
    assert q.clipped_high_frac == pytest.approx(0.5)
    assert q.clipped_low_frac == pytest.approx(0.5)


def test_crop_changes_geometry_only_as_expected():
    q = _under("photo", "crop_0.8")
    assert (q.width, q.height) == (round(256 * 0.8), round(192 * 0.8))


# --- robustness -----------------------------------------------------------
@pytest.mark.parametrize("size", [(1, 1), (2, 2), (3, 3), (8, 8), (17, 17)])
def test_tiny_images_do_not_crash(size):
    q = _from_array(np.full((size[0], size[1], 3), 128, dtype=np.uint8))
    assert np.isfinite(q.blur_varlap) and np.isfinite(q.blockiness)
    assert np.isfinite(q.noise_sigma)


def test_determinism():
    d = _decoded("texture")
    assert compute_quality(d).to_json_dict() == compute_quality(d).to_json_dict()
