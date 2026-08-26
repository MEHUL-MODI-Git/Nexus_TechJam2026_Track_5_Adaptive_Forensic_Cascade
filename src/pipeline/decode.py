"""Canonical decode (task 0.2, core spec v2 §1).

Step 1 of the doc-03 cascade. The one rule that outranks everything here:
we never resize, recompress or otherwise touch pixels before an expert's own
preprocessing -- a forensic detector reads compression and resampling traces,
so a "helpful" normalization upstream would destroy the signal we are measuring.

Decode order is fixed and load-bearing:
    bytes -> sha256 -> open -> record ORIGINAL metadata -> exif_transpose
          -> RGB convert -> record canonical size -> phash
Recording raw_* before the transpose and width/height after it (review note N3)
keeps EXIF-rotated inputs auditable: a 4032x3024 sensor image stored with
orientation 6 is canonically 3024x4032, and both numbers stay visible.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import imagehash
import PIL.Image
import PIL.ImageFile
import PIL.ImageOps

# A truncated file is an error, not a silently zero-padded image. Explicit so
# that no imported library can flip this on us.
PIL.ImageFile.LOAD_TRUNCATED_IMAGES = False

# EXIF tag 0x0112 = Orientation.
_EXIF_ORIENTATION_TAG = 0x0112

# Bits per channel by PIL mode. None => not determinable; recorded only, never
# branched on in Phase 0.
_BIT_DEPTH_BY_MODE = {
    "1": 1, "L": 8, "P": 8, "RGB": 8, "RGBA": 8, "CMYK": 8, "YCbCr": 8,
    "LAB": 8, "HSV": 8, "I;16": 16, "I;16B": 16, "I;16L": 16, "I": 32, "F": 32,
}


class DecodeError(Exception):
    """Raised for an unreadable, truncated or unsupported input file.

    Typed so callers (infer_dir, the prediction service, the eval harness) can
    distinguish "this file is not scoreable" from "the model failed" and record
    the distinction instead of inventing a score.
    """

    def __init__(self, path: str, reason: str) -> None:
        super().__init__(f"{path}: {reason}")
        self.path = path
        self.reason = reason


@dataclass(frozen=True)
class DecodedImage:
    """Canonical decoded image plus the provenance the protocol requires."""

    image: PIL.Image.Image  # RGB uint8, EXIF orientation APPLIED
    sha256: str             # of the ORIGINAL file bytes, lowercase hex
    phash: str              # imagehash.phash of the canonical image, 64-bit hex
    orig_mode: str          # PIL mode before RGB convert ("RGBA", "CMYK", "L", ...)
    orig_format: str | None # "JPEG" | "PNG" | ... ; None when decoded from raw bytes
    raw_width: int          # decoded size BEFORE exif_transpose (note N3)
    raw_height: int
    width: int              # canonical size: post-orientation, post-RGB (note N3)
    height: int
    bit_depth: int | None   # bits per channel when determinable (note N3)
    file_bytes: int
    warnings: list[str] = field(default_factory=list)  # machine-readable codes


def _read_bytes(path_or_bytes) -> tuple[bytes, str]:
    """Return (file bytes, display path). Accepts a path, Path or raw bytes."""
    if isinstance(path_or_bytes, (bytes, bytearray)):
        return bytes(path_or_bytes), "<bytes>"
    path = Path(path_or_bytes)
    try:
        return path.read_bytes(), str(path)
    except OSError as exc:
        raise DecodeError(str(path), f"unreadable: {exc}") from exc


def decode_image(path_or_bytes) -> DecodedImage:
    """Decode to canonical RGB uint8, recording provenance and warnings.

    Raises DecodeError for anything unreadable; never returns a partial image.
    """
    import io

    data, display_path = _read_bytes(path_or_bytes)
    sha256 = hashlib.sha256(data).hexdigest()
    warnings: list[str] = []

    try:
        img = PIL.Image.open(io.BytesIO(data))
        # open() is lazy; force the decode here so truncation surfaces as a
        # DecodeError rather than as a half-filled array later in the pipeline.
        img.load()
    except Exception as exc:  # PIL raises a wide family of errors here
        raise DecodeError(display_path, f"decode failed: {type(exc).__name__}: {exc}") from exc

    orig_mode = img.mode
    orig_format = img.format
    raw_width, raw_height = img.size
    bit_depth = _BIT_DEPTH_BY_MODE.get(orig_mode)

    orientation = None
    try:
        orientation = img.getexif().get(_EXIF_ORIENTATION_TAG)
    except Exception:  # corrupt EXIF must not fail an otherwise valid image
        warnings.append("exif_unreadable")

    img = PIL.ImageOps.exif_transpose(img)
    if orientation not in (None, 1):
        warnings.append(f"exif_transposed:{orientation}")

    if orig_mode in ("RGBA", "LA", "PA") or "transparency" in img.info:
        # Composite on white rather than dropping the alpha channel: discarding
        # it would leave undefined RGB under fully transparent pixels.
        rgba = img.convert("RGBA")
        background = PIL.Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        img = PIL.Image.alpha_composite(background, rgba).convert("RGB")
        warnings.append("alpha_discarded")
    elif orig_mode == "CMYK":
        img = img.convert("RGB")
        warnings.append("cmyk_converted")
    elif orig_mode != "RGB":
        img = img.convert("RGB")
        warnings.append(f"mode_converted:{orig_mode}")

    if img.mode != "RGB":  # belt and braces: the contract is RGB uint8, always
        img = img.convert("RGB")

    width, height = img.size

    return DecodedImage(
        image=img,
        sha256=sha256,
        phash=str(imagehash.phash(img)),
        orig_mode=orig_mode,
        orig_format=orig_format,
        raw_width=raw_width,
        raw_height=raw_height,
        width=width,
        height=height,
        bit_depth=bit_depth,
        file_bytes=len(data),
        warnings=warnings,
    )
