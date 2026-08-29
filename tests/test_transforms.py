"""Transform-grid property tests (core spec v2 §2 DoD).

These assert the protocol's structural guarantees. Exact pixel values are the
golden tests' job (tests/test_transforms_golden.py).
"""

import hashlib

import numpy as np
import pytest
from PIL import Image

from src.pipeline.transforms import (
    CONDITION_IDS,
    CONFIG,
    FAMILY_OF,
    TRANSFORMS,
    apply_transform,
    load_transform_config,
    noise_seed,
)
from src.pipeline.version import PIPELINE_VERSION


def _img(h=37, w=53, seed=0) -> Image.Image:
    arr = np.random.default_rng(seed).integers(0, 256, (h, w, 3), dtype=np.uint8)
    return Image.fromarray(arr)


SHA = "a" * 64


# --- registry / config integrity ------------------------------------------
def test_exactly_twenty_official_conditions():
    assert len(CONDITION_IDS) == 20
    assert len(set(CONDITION_IDS)) == 20


def test_condition_ids_match_docs05_names():
    expected = {
        "clean", "jpeg_q90", "jpeg_q70", "jpeg_q50", "jpeg_q30",
        "blur_s0.5", "blur_s1.0", "blur_s2.0", "resize_0.5", "resize_0.25",
        "noise_s0.02", "noise_s0.05", "noise_s0.10",
        "bright_-20", "bright_+20", "contrast_-20", "contrast_+20",
        "saturation_-20", "saturation_+20", "crop_0.8",
    }
    assert set(CONDITION_IDS) == expected


def test_yaml_keys_equal_registry_keys():
    assert set(CONFIG["conditions"]) == set(TRANSFORMS)


def test_six_transform_families_plus_clean():
    families = {f for cid, f in FAMILY_OF.items() if f != "clean"}
    assert families == {"jpeg", "blur", "resize", "noise", "color", "crop"}
    counts = {f: sum(1 for x in FAMILY_OF.values() if x == f) for f in families}
    assert counts == {"jpeg": 4, "blur": 3, "resize": 2, "noise": 3, "color": 6, "crop": 1}


def test_config_version_drift_is_fatal(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text((CONFIG and "") or "")
    import yaml
    cfg = dict(CONFIG, pipeline_version="9.9.9")
    bad.write_text(yaml.safe_dump(cfg))
    with pytest.raises(RuntimeError, match="PIPELINE_VERSION"):
        load_transform_config(bad)


def test_unknown_condition_is_hard_error():
    with pytest.raises(KeyError):
        apply_transform(_img(), "jpeg_q42", SHA)


# --- universal output properties ------------------------------------------
@pytest.mark.parametrize("cid", CONDITION_IDS)
def test_output_is_rgb_uint8(cid):
    out = apply_transform(_img(), cid, SHA)
    assert out.mode == "RGB"
    assert np.array(out).dtype == np.uint8


@pytest.mark.parametrize("cid", CONDITION_IDS)
def test_determinism_byte_identical(cid):
    img = _img()
    a = np.array(apply_transform(img, cid, SHA))
    b = np.array(apply_transform(img, cid, SHA))
    assert np.array_equal(a, b)


@pytest.mark.parametrize("cid", CONDITION_IDS)
def test_size_rule(cid):
    img = _img(h=37, w=53)
    out = apply_transform(img, cid, SHA)
    if cid == "crop_0.8":
        assert out.size == (round(53 * 0.8), round(37 * 0.8))  # stays cropped
    else:
        assert out.size == img.size  # resize goes down THEN back up


@pytest.mark.parametrize("size", [(1, 1), (3, 3), (2, 5)])
@pytest.mark.parametrize("cid", CONDITION_IDS)
def test_tiny_images_survive_every_condition(cid, size):
    # max(1, round(...)) guard: no condition may produce a zero-sized axis.
    out = apply_transform(_img(h=size[0], w=size[1]), cid, SHA)
    assert out.size[0] >= 1 and out.size[1] >= 1


def test_non_rgb_input_rejected():
    with pytest.raises(ValueError, match="canonical RGB"):
        apply_transform(Image.new("L", (8, 8), 4), "clean", SHA)


# --- per-family semantics -------------------------------------------------
def test_clean_is_exact_identity():
    img = _img()
    assert np.array_equal(np.array(apply_transform(img, "clean", SHA)), np.array(img))


def test_jpeg_quality_monotonic_damage():
    # Lower quality must not be closer to the original than higher quality.
    img = _img(seed=3)
    ref = np.array(img, dtype=np.int32)
    errs = [
        np.abs(np.array(apply_transform(img, f"jpeg_q{q}", SHA), dtype=np.int32) - ref).mean()
        for q in (90, 70, 50, 30)
    ]
    assert errs == sorted(errs)


def test_jpeg_uses_420_subsampling():
    assert CONFIG["manifest"]["jpeg"]["subsampling"] == 2
    assert CONFIG["manifest"]["jpeg"]["optimize"] is False
    assert CONFIG["manifest"]["jpeg"]["progressive"] is False


def test_blur_is_true_gaussian_not_box():
    # A true Gaussian on a delta impulse gives a strictly decreasing profile
    # away from the centre; a box blur gives a flat plateau.
    arr = np.zeros((41, 41, 3), dtype=np.uint8)
    arr[20, 20] = 255
    out = np.array(apply_transform(Image.fromarray(arr), "blur_s2.0", SHA), dtype=np.float64)
    row = out[20, 20:26, 0]
    assert np.all(np.diff(row) <= 0)
    assert row[0] > row[1] > row[2]  # not a plateau


def test_blur_severity_ordering():
    img = _img(seed=5)
    ref = np.array(img, dtype=np.int32)
    errs = [
        np.abs(np.array(apply_transform(img, f"blur_s{s}", SHA), dtype=np.int32) - ref).mean()
        for s in ("0.5", "1.0", "2.0")
    ]
    assert errs == sorted(errs)


def test_blur_padding_mode_recorded():
    # docs/05 requires the boundary mode to be stated in the manifest.
    assert CONFIG["manifest"]["blur"]["padding_mode"] == "reflect"
    assert CONFIG["manifest"]["blur"]["sigma_passed_explicitly"] is True


def test_resize_returns_to_original_size_and_loses_detail():
    img = _img(seed=7)
    for cid in ("resize_0.5", "resize_0.25"):
        out = apply_transform(img, cid, SHA)
        assert out.size == img.size
        assert not np.array_equal(np.array(out), np.array(img))


def test_noise_seed_is_byte_exact():
    payload = f"{SHA}:noise_s0.05".encode("ascii")
    assert noise_seed(SHA, "noise_s0.05") == int(hashlib.sha256(payload).hexdigest()[:16], 16)


def test_noise_differs_per_condition_and_per_image():
    img = _img(seed=11)
    a = np.array(apply_transform(img, "noise_s0.05", SHA))
    b = np.array(apply_transform(img, "noise_s0.10", SHA))
    c = np.array(apply_transform(img, "noise_s0.05", "b" * 64))
    assert not np.array_equal(a, b)   # condition id enters the seed
    assert not np.array_equal(a, c)   # image hash enters the seed


def test_noise_severity_ordering():
    img = _img(seed=13)
    ref = np.array(img, dtype=np.int32)
    errs = [
        np.abs(np.array(apply_transform(img, f"noise_s{s}", SHA), dtype=np.int32) - ref).mean()
        for s in ("0.02", "0.05", "0.10")
    ]
    assert errs == sorted(errs)


def test_brightness_direction():
    img = _img(seed=17)
    base = np.array(img, dtype=np.float64).mean()
    assert np.array(apply_transform(img, "bright_-20", SHA), dtype=np.float64).mean() < base
    assert np.array(apply_transform(img, "bright_+20", SHA), dtype=np.float64).mean() > base


def test_contrast_direction():
    img = _img(seed=19)
    base = np.array(img, dtype=np.float64).std()
    assert np.array(apply_transform(img, "contrast_-20", SHA), dtype=np.float64).std() < base
    assert np.array(apply_transform(img, "contrast_+20", SHA), dtype=np.float64).std() > base


def test_saturation_direction():
    img = _img(seed=23)

    def chroma(x):
        a = np.array(x, dtype=np.float64)
        return (a.max(axis=2) - a.min(axis=2)).mean()

    base = chroma(img)
    assert chroma(apply_transform(img, "saturation_-20", SHA)) < base
    assert chroma(apply_transform(img, "saturation_+20", SHA)) > base


def test_color_changes_one_property_only():
    # brightness must not alter a pure-gray image's chroma, etc.
    gray = Image.fromarray(np.full((16, 16, 3), 120, dtype=np.uint8))
    out = np.array(apply_transform(gray, "saturation_+20", SHA))
    assert np.array_equal(out, np.array(gray))  # gray has no saturation to boost


def test_crop_is_centered_and_stays_cropped():
    h, w = 40, 60
    arr = np.zeros((h, w, 3), dtype=np.uint8)
    arr[16:24, 24:36] = 255  # centred marker block
    out = apply_transform(Image.fromarray(arr), "crop_0.8", SHA)
    th, tw = round(h * 0.8), round(w * 0.8)
    assert out.size == (tw, th)
    expected = arr[(h - th) // 2 : (h - th) // 2 + th, (w - tw) // 2 : (w - tw) // 2 + tw]
    assert np.array_equal(np.array(out), expected)


def test_crop_keeps_80_percent_per_side_not_area():
    out = apply_transform(_img(h=100, w=100), "crop_0.8", SHA)
    assert out.size == (80, 80)  # 64% area, per the stated assumption


def test_pipeline_version_is_single_sourced():
    assert CONFIG["pipeline_version"] == PIPELINE_VERSION
