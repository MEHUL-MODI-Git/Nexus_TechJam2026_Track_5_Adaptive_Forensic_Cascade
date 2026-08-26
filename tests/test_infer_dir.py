"""infer_dir gate smoke (core spec v2 §6b, product spec §5).

This is a STANDING gate item from Phase 1 onward: it is the organizers' likely
scoring entry point, so it gets checked at every phase exit, not once.

Covers the product-spec §5 checklist: valid images of both classes, nested-path
and ordering determinism, corrupt-file behavior in all three modes, JSON schema
and range validation, and equality with direct service predictions.
"""

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from src.pipeline.service import PredictionService

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.infer_dir import SUPPORTED_EXTENSIONS, find_images, run  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "tests" / "golden" / "sources"


@pytest.fixture(scope="module")
def service():
    try:
        return PredictionService.from_config()
    except Exception as exc:
        pytest.skip(f"CF-384 unavailable: {exc}")


@pytest.fixture
def sample_dir(tmp_path):
    """Two valid images at top level, one nested, one corrupt, one non-image."""
    (tmp_path / "nested" / "deep").mkdir(parents=True)
    for name, src in (("a.png", "photo.png"), ("b.jpg", "gradient.png")):
        Image.open(GOLDEN / src).convert("RGB").save(tmp_path / name)
    Image.open(GOLDEN / "texture.png").save(tmp_path / "nested" / "deep" / "c.PNG")
    (tmp_path / "broken.jpg").write_bytes(b"not an image at all")
    (tmp_path / "notes.txt").write_text("ignore me")
    return tmp_path


# --- discovery ------------------------------------------------------------
def test_finds_only_recognized_images_recursively(sample_dir):
    rel = [p.relative_to(sample_dir).as_posix() for p in find_images(sample_dir)]
    assert rel == ["a.png", "b.jpg", "broken.jpg", "nested/deep/c.PNG"]
    assert "notes.txt" not in rel


def test_extension_match_is_case_insensitive(sample_dir):
    names = [p.name for p in find_images(sample_dir)]
    assert "c.PNG" in names
    assert ".png" in SUPPORTED_EXTENSIONS and ".jpeg" in SUPPORTED_EXTENSIONS


def test_non_recursive_stays_top_level(sample_dir):
    rel = [p.relative_to(sample_dir).as_posix() for p in find_images(sample_dir, recursive=False)]
    assert "nested/deep/c.PNG" not in rel


def test_ordering_is_deterministic(sample_dir):
    assert find_images(sample_dir) == find_images(sample_dir)


def test_missing_directory_raises(tmp_path):
    with pytest.raises(NotADirectoryError):
        run(tmp_path / "nope", tmp_path / "out.json")


# --- output contract ------------------------------------------------------
def test_default_emits_row_for_every_recognized_image(sample_dir, service):
    out = sample_dir / "preds.json"
    rows, failures = run(sample_dir, out, service=service, progress_every=0)
    assert failures == 1
    # Alignment guarantee: one row per recognized image, including the corrupt one.
    assert len(rows) == len(find_images(sample_dir))
    written = json.loads(out.read_text())
    assert written == rows


def test_required_keys_and_ranges(sample_dir, service):
    rows, _ = run(sample_dir, sample_dir / "p.json", service=service, progress_every=0)
    for row in rows:
        assert set(row) <= {"image_path", "pred", "error"}
        assert "image_path" in row and "pred" in row      # the binding requirement
        assert isinstance(row["image_path"], str)
        if row["pred"] is None:
            assert row["error"] == "decode_failed"
        else:
            assert isinstance(row["pred"], float)
            assert 0.0 <= row["pred"] <= 1.0              # higher = AI-generated


def test_paths_are_relative_posix_and_never_absolute(sample_dir, service):
    rows, _ = run(sample_dir, sample_dir / "p.json", service=service, progress_every=0)
    paths = [r["image_path"] for r in rows]
    assert "nested/deep/c.PNG" in paths
    assert not any(p.startswith("/") or "\\" in p for p in paths)


def test_never_invents_a_score_for_a_corrupt_file(sample_dir, service):
    rows, _ = run(sample_dir, sample_dir / "p.json", service=service, progress_every=0)
    broken = next(r for r in rows if r["image_path"] == "broken.jpg")
    assert broken["pred"] is None          # not 0.5, not 0.0
    assert broken["error"] == "decode_failed"


# --- error modes ----------------------------------------------------------
def test_skip_mode_omits_failed_rows(sample_dir, service):
    rows, failures = run(sample_dir, sample_dir / "p.json", errors="skip",
                         service=service, progress_every=0)
    assert failures == 1
    assert all(r["pred"] is not None for r in rows)
    assert len(rows) == len(find_images(sample_dir)) - 1


def test_strict_mode_raises(sample_dir, service):
    from src.pipeline.decode import DecodeError

    with pytest.raises(DecodeError):
        run(sample_dir, sample_dir / "p.json", errors="strict",
            service=service, progress_every=0)


def test_strict_mode_cli_exits_nonzero(sample_dir):
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "infer_dir.py"), str(sample_dir),
         "--output", str(sample_dir / "p.json"), "--errors", "strict"],
        capture_output=True, text=True, cwd=ROOT,
    )
    assert proc.returncode != 0


def test_default_cli_exits_zero_despite_a_bad_file(sample_dir):
    # A complete, usable output file must not look like a failed run.
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "infer_dir.py"), str(sample_dir),
         "--output", str(sample_dir / "p.json")],
        capture_output=True, text=True, cwd=ROOT,
    )
    assert proc.returncode == 0, proc.stderr
    assert json.loads((sample_dir / "p.json").read_text())


# --- parity + robustness --------------------------------------------------
def test_matches_direct_service_predictions(sample_dir, service):
    """Batch output must equal what the service returns image-by-image."""
    rows, _ = run(sample_dir, sample_dir / "p.json", service=service, progress_every=0)
    for row in rows:
        if row["pred"] is None:
            continue
        direct = service.predict_image(sample_dir / row["image_path"])
        assert row["pred"] == direct.p_fake


def test_rerun_is_byte_identical(sample_dir, service):
    a = sample_dir / "a.json"
    b = sample_dir / "b.json"
    run(sample_dir, a, service=service, progress_every=0)
    run(sample_dir, b, service=service, progress_every=0)
    assert a.read_bytes() == b.read_bytes()


def test_empty_directory_writes_empty_array(tmp_path, service):
    out = tmp_path / "empty.json"
    rows, failures = run(tmp_path, out, service=service, progress_every=0)
    assert rows == [] and failures == 0
    assert json.loads(out.read_text()) == []


def test_tiny_image_is_scored_not_crashed(tmp_path, service):
    # A 4px thumbnail must produce a real score (blur-clamp / geometry guards).
    Image.fromarray(np.full((4, 4, 3), 128, dtype=np.uint8)).save(tmp_path / "t.png")
    rows, failures = run(tmp_path, tmp_path / "p.json", service=service, progress_every=0)
    assert failures == 0
    assert rows[0]["pred"] is not None


def test_output_write_is_atomic(sample_dir, service):
    out = sample_dir / "sub" / "preds.json"      # parent does not exist yet
    run(sample_dir, out, service=service, progress_every=0)
    assert out.exists()
    assert not list(out.parent.glob("*.tmp"))    # no temp residue
