"""Decode DoD (core spec v2 §1)."""

import hashlib
import io
import subprocess
from dataclasses import FrozenInstanceError

import numpy as np
import pytest
from PIL import Image

from src.pipeline.decode import DecodeError, decode_image


def _png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_sha256_matches_file_bytes(tmp_path):
    path = tmp_path / "x.png"
    path.write_bytes(_png_bytes(Image.new("RGB", (8, 8), (1, 2, 3))))
    expected = hashlib.sha256(path.read_bytes()).hexdigest()
    assert decode_image(path).sha256 == expected


def test_sha256_matches_shasum_cli(tmp_path):
    path = tmp_path / "y.png"
    path.write_bytes(_png_bytes(Image.new("RGB", (9, 7), (200, 10, 10))))
    out = subprocess.run(["shasum", "-a", "256", str(path)], capture_output=True, text=True)
    assert decode_image(path).sha256 == out.stdout.split()[0]


def test_rgba_composited_on_white():
    # Fully transparent pixel must land on white, not on undefined RGB.
    img = Image.new("RGBA", (4, 4), (255, 0, 0, 0))
    d = decode_image(_png_bytes(img))
    assert d.image.mode == "RGB"
    assert "alpha_discarded" in d.warnings
    assert np.array(d.image)[0, 0].tolist() == [255, 255, 255]
    assert d.orig_mode == "RGBA"


def test_cmyk_converted(tmp_path):
    path = tmp_path / "c.jpg"
    Image.new("CMYK", (8, 8), (0, 0, 0, 0)).save(path, format="JPEG")
    d = decode_image(path)
    assert d.orig_mode == "CMYK"
    assert "cmyk_converted" in d.warnings
    assert d.image.mode == "RGB"


def test_grayscale_converted():
    d = decode_image(_png_bytes(Image.new("L", (6, 5), 128)))
    assert d.image.mode == "RGB"
    assert "mode_converted:L" in d.warnings


def test_16bit_png_records_bit_depth():
    arr = (np.arange(64, dtype=np.uint16) * 1000).reshape(8, 8)
    d = decode_image(_png_bytes(Image.fromarray(arr)))  # uint16 array -> I;16
    assert d.bit_depth == 16
    assert d.image.mode == "RGB"


def test_exif_rotation_applied_and_dims_recorded(tmp_path):
    # Orientation 6 = rotate 90 CW on display: raw dims and canonical dims differ.
    path = tmp_path / "rot.jpg"
    img = Image.new("RGB", (40, 20), (10, 20, 30))
    exif = img.getexif()
    exif[0x0112] = 6
    img.save(path, format="JPEG", exif=exif)
    d = decode_image(path)
    assert (d.raw_width, d.raw_height) == (40, 20)   # pre-transpose
    assert (d.width, d.height) == (20, 40)           # post-transpose (canonical)
    assert any(w.startswith("exif_transposed:6") for w in d.warnings)


def test_no_exif_leaves_dims_equal():
    d = decode_image(_png_bytes(Image.new("RGB", (12, 5), (0, 0, 0))))
    assert (d.raw_width, d.raw_height) == (d.width, d.height) == (12, 5)
    assert not any(w.startswith("exif_transposed") for w in d.warnings)


def test_truncated_file_raises(tmp_path):
    path = tmp_path / "t.png"
    full = _png_bytes(Image.new("RGB", (64, 64), (7, 7, 7)))
    path.write_bytes(full[: len(full) // 2])  # cut mid-stream
    with pytest.raises(DecodeError):
        decode_image(path)


def test_not_an_image_raises(tmp_path):
    path = tmp_path / "n.txt"
    path.write_bytes(b"definitely not an image")
    with pytest.raises(DecodeError):
        decode_image(path)


def test_missing_file_raises(tmp_path):
    with pytest.raises(DecodeError):
        decode_image(tmp_path / "nope.png")


def test_one_by_one_image_decodes():
    d = decode_image(_png_bytes(Image.new("RGB", (1, 1), (5, 5, 5))))
    assert (d.width, d.height) == (1, 1)


def test_decoded_image_is_immutable():
    d = decode_image(_png_bytes(Image.new("RGB", (4, 4), (0, 0, 0))))
    with pytest.raises(FrozenInstanceError):
        d.width = 99  # type: ignore[misc]


def test_decode_does_not_recompress():
    # The canonical image must be the decoded pixels, byte-for-byte.
    src = Image.fromarray(
        np.random.default_rng(0).integers(0, 256, (16, 16, 3), dtype=np.uint8), "RGB"
    )
    d = decode_image(_png_bytes(src))
    assert np.array_equal(np.array(d.image), np.array(src))
