"""Degradation reporter — what appears to have been done to this image.

The verdict says AI or REAL. The reliability says how much to trust it. Neither
explains WHY the system is unsure. This does: it reads the eight quality
descriptors already computed for every image and names the transformation family
they look like.

It is an EXPLANATION, never an input to the verdict. Nothing here can move a
decision; the router never sees its output.

Honest limits, carried in the report itself rather than a footnote:
  * `clean` and `color` are genuinely hard to separate (dev recall 0.54 / 0.48).
    A +/-20 brightness or saturation shift barely moves blur, blockiness or
    noise, so "untouched" and "mildly recoloured" look alike to these features.
    That is a property of the descriptors, not a bug.
  * Geometry is excluded on purpose. Width and height would make crop and resize
    easy, but a real upload has no known original size, so that accuracy would
    not survive deployment.
  * Trained on singly-transformed images. Real uploads are often chained
    (resize THEN compress), which this has never seen.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
from torch import nn

_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL = _ROOT / "results" / "degradation" / "classifier.pt"

# Wording aimed at someone triaging an image, not at us.
PHRASING = {
    "clean": "no strong degradation detected",
    "jpeg": "JPEG compression",
    "noise": "added noise",
    "blur": "blurring or softening",
    "color": "brightness/contrast/saturation adjustment",
    "crop": "cropping",
    "resize": "resampling (resize)",
}
# Families where our detector is measurably weakest (README section 7).
HARD_FOR_DETECTOR = {"noise", "jpeg"}


@dataclass(frozen=True)
class DegradationReport:
    family: str
    label: str
    confidence: float
    ranked: list[tuple[str, float]]
    detector_is_weak_here: bool
    caveat: str | None

    def to_json_dict(self) -> dict:
        return {"family": self.family, "label": self.label,
                "confidence": self.confidence,
                "ranked": [[f, round(p, 4)] for f, p in self.ranked],
                "detector_is_weak_here": self.detector_is_weak_here,
                "caveat": self.caveat}


class DegradationReporter:
    """Loads the fitted classifier and reports on one image's descriptors."""

    def __init__(self, payload: dict) -> None:
        self.families = list(payload["families"])
        self.quality_keys = list(payload["quality_keys"])
        self.mean = np.asarray(payload["mean"], dtype=np.float64)
        self.scale = np.asarray(payload["scale"], dtype=np.float64)
        n_in = len(self.quality_keys) * 2
        self.model = nn.Sequential(nn.Linear(n_in, 32), nn.ReLU(),
                                   nn.Linear(32, len(self.families)))
        self.model.load_state_dict(payload["state_dict"])
        self.model.eval()
        self.dev_balanced_accuracy = float(payload.get("dev_balanced_accuracy", float("nan")))

    @classmethod
    def load(cls, path: Path | str = DEFAULT_MODEL) -> DegradationReporter:
        return cls(torch.load(Path(path), map_location="cpu", weights_only=False))

    def report(self, quality: dict) -> DegradationReport:
        """`quality` is the descriptor block the pipeline already computes."""
        x = np.zeros(len(self.quality_keys) * 2, dtype=np.float64)
        for j, key in enumerate(self.quality_keys):
            v = (quality or {}).get(key)
            if v is None or not np.isfinite(float(v)):
                continue                      # absent stays absent; never imputed
            x[2 * j] = float(v)
            x[2 * j + 1] = 1.0
        z = torch.tensor(((x - self.mean) / self.scale)[None, :], dtype=torch.float32)
        with torch.no_grad():
            probs = torch.softmax(self.model(z), dim=1).numpy()[0]
        ranked = sorted(zip(self.families, (float(p) for p in probs)),
                        key=lambda kv: -kv[1])
        family, confidence = ranked[0]
        caveat = None
        if {family, ranked[1][0]} == {"clean", "color"}:
            caveat = ("`clean` and mild colour adjustment are not reliably "
                      "separable from these descriptors")
        return DegradationReport(
            family=family, label=PHRASING.get(family, family), confidence=confidence,
            ranked=ranked, detector_is_weak_here=family in HARD_FOR_DETECTOR,
            caveat=caveat,
        )


__all__ = ["DEFAULT_MODEL", "HARD_FOR_DETECTOR", "PHRASING",
           "DegradationReport", "DegradationReporter"]
