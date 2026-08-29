"""Regenerate tests/golden/expected.json (core spec v2 §3).

Run this ONLY together with a deliberate PIPELINE_VERSION bump: the golden file
records the version it was generated under, and tests/test_transforms_golden.py
fails if the recorded version differs from the code's. That is the tripwire that
stops a silent transform change from invalidating cached features and any
headline number measured under the old protocol.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from src.pipeline.decode import decode_image
from src.pipeline.transforms import CONDITION_IDS, apply_transform
from src.pipeline.version import GOLDEN_VERSION, PIPELINE_VERSION

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "tests" / "golden" / "sources"
EXPECTED = ROOT / "tests" / "golden" / "expected.json"


def record(img) -> dict:
    """Hash the raw uint8 RGB array; carry shape/mode so the record self-describes."""
    arr = np.array(img, dtype=np.uint8)
    return {
        "sha256": hashlib.sha256(arr.tobytes()).hexdigest(),
        "shape": list(arr.shape),
        "mode": img.mode,
    }


def build() -> dict:
    sources: dict[str, dict] = {}
    for path in sorted(SOURCES.glob("*.png")):
        decoded = decode_image(path)
        sources[path.name] = {
            "source_sha256": decoded.sha256,
            "conditions": {
                cid: record(apply_transform(decoded.image, cid, decoded.sha256))
                for cid in CONDITION_IDS
            },
        }
    return {
        "pipeline_version": PIPELINE_VERSION,
        "golden_version": GOLDEN_VERSION,
        "condition_ids": CONDITION_IDS,
        "sources": sources,
    }


if __name__ == "__main__":
    EXPECTED.write_text(json.dumps(build(), indent=2, sort_keys=False) + "\n")
    print(f"wrote {EXPECTED} for pipeline_version={PIPELINE_VERSION}")
