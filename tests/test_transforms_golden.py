"""Golden tests (core spec v2 §3, task 0.4).

The tripwire for the whole protocol: if any transform's pixel output changes,
these fail. A change is only legitimate together with a PIPELINE_VERSION bump
plus a cache-version bump -- otherwise cached features and any measured
headline number silently stop meaning what they claim to mean.
"""

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from src.pipeline.decode import decode_image
from src.pipeline.transforms import CONDITION_IDS, apply_transform
from src.pipeline.version import GOLDEN_VERSION, PIPELINE_VERSION

GOLDEN_DIR = Path(__file__).parent / "golden"
SOURCES = GOLDEN_DIR / "sources"
EXPECTED = json.loads((GOLDEN_DIR / "expected.json").read_text())


def _record(img) -> dict:
    arr = np.array(img, dtype=np.uint8)
    return {
        "sha256": hashlib.sha256(arr.tobytes()).hexdigest(),
        "shape": list(arr.shape),
        "mode": img.mode,
    }


def test_golden_file_matches_code_version():
    # A behavior change without a version bump must fail CI here.
    assert EXPECTED["pipeline_version"] == PIPELINE_VERSION
    assert EXPECTED["golden_version"] == GOLDEN_VERSION


def test_golden_covers_all_official_conditions():
    assert EXPECTED["condition_ids"] == CONDITION_IDS
    for src in EXPECTED["sources"].values():
        assert set(src["conditions"]) == set(CONDITION_IDS)


def test_golden_sources_present_and_unmodified():
    names = {p.name for p in SOURCES.glob("*.png")}
    assert names == set(EXPECTED["sources"])
    for name, entry in EXPECTED["sources"].items():
        assert decode_image(SOURCES / name).sha256 == entry["source_sha256"]


@pytest.mark.parametrize("source_name", sorted(EXPECTED["sources"]))
@pytest.mark.parametrize("condition_id", CONDITION_IDS)
def test_transform_output_matches_golden(source_name, condition_id):
    decoded = decode_image(SOURCES / source_name)
    got = _record(apply_transform(decoded.image, condition_id, decoded.sha256))
    want = EXPECTED["sources"][source_name]["conditions"][condition_id]
    assert got == want, (
        f"{source_name}/{condition_id} drifted from golden. If this change is "
        f"intended: bump PIPELINE_VERSION, rerun scripts/regen_golden.py, bump "
        f"the feature-cache version, and record it in DECISIONS.md."
    )
