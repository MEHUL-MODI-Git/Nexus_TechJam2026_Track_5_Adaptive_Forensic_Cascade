"""Generate the three golden source images (core spec v2 §3).

Self-made and fully deterministic -- no third-party content can enter the repo
this way, and anyone can regenerate byte-identical fixtures. The three cover
the failure modes that matter for transform correctness:

  photo   -- structured edges + smooth regions (JPEG blocking, blur)
  gradient-- near-flat smooth ramp (banding, quantization, color adjust)
  texture -- high-frequency noise (antialiasing, resampling, noise addition)
"""

from pathlib import Path

import numpy as np
from PIL import Image

OUT = Path(__file__).resolve().parents[1] / "tests" / "golden" / "sources"


def photo_like(h: int = 192, w: int = 256) -> np.ndarray:
    """Synthetic scene: sky ramp, ground plane, a disc and hard-edged bars."""
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    img = np.zeros((h, w, 3), dtype=np.float32)
    sky = yy / h
    img[..., 0] = 0.30 + 0.35 * sky
    img[..., 1] = 0.45 + 0.35 * sky
    img[..., 2] = 0.75 + 0.20 * sky
    ground = yy > h * 0.62
    img[ground] = np.array([0.28, 0.36, 0.18], dtype=np.float32)
    disc = (xx - w * 0.30) ** 2 + (yy - h * 0.30) ** 2 < (h * 0.16) ** 2
    img[disc] = np.array([0.95, 0.85, 0.30], dtype=np.float32)
    bars = (xx.astype(int) // 8) % 2 == 0
    img[bars & ground] *= 0.75
    return (img * 255).round().clip(0, 255).astype(np.uint8)


def smooth_gradient(h: int = 128, w: int = 128) -> np.ndarray:
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    img = np.stack([xx / w, yy / h, (xx / w + yy / h) / 2.0], axis=-1)
    return (img * 255).round().clip(0, 255).astype(np.uint8)


def texture(h: int = 128, w: int = 160, seed: int = 20260826) -> np.ndarray:
    rng = np.random.default_rng(seed)
    base = rng.integers(0, 256, size=(h, w, 3), dtype=np.uint16)
    # Mild horizontal correlation so it is textured rather than pure static.
    base[:, 1:, :] = (base[:, 1:, :] + base[:, :-1, :]) // 2
    return base.astype(np.uint8)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, arr in (
        ("photo", photo_like()),
        ("gradient", smooth_gradient()),
        ("texture", texture()),
    ):
        path = OUT / f"{name}.png"
        Image.fromarray(arr).save(path, format="PNG", optimize=False)
        print(f"wrote {path}  {arr.shape}")


if __name__ == "__main__":
    main()
