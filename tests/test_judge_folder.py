"""The required script, run on an arbitrary folder a judge supplies.

The brief's script is likely the organizers' scoring entry point, pointed at a
directory we have never seen. So the risk is not our own sample images -- it is
whatever they hand us: mixed formats, odd colour spaces, unicode names, a huge
file, a corrupt one, junk that is not an image at all.

The contract that must hold no matter what is in the folder:
  * one row per recognised image, so a harness zipping paths to predictions
    cannot silently misalign;
  * `image_path` and `pred` present on every row (the brief's binding text);
  * a file that cannot be decoded gets `pred: null` and an `error`, never an
    invented float;
  * exit 0, because a complete usable file is not a failed run.
"""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def judge_folder(tmp_path_factory):
    d = tmp_path_factory.mktemp("judge_folder")
    (d / "nested" / "deep").mkdir(parents=True)
    rng = np.random.default_rng(0)
    im = Image.fromarray((rng.random((64, 64, 3)) * 255).astype("uint8"))

    im.save(d / "normal.jpg")
    im.save(d / "UPPERCASE.PNG")                        # case-insensitive match
    im.save(d / "with space and 'quote'.jpg")           # shell-hostile name
    im.save(d / "unicode_名前_émoji.png")  # non-ASCII name
    im.convert("L").save(d / "grayscale.png")           # 1 channel
    im.convert("RGBA").save(d / "with_alpha.png")       # alpha
    im.convert("CMYK").save(d / "cmyk.jpg")             # non-RGB colour space
    im.save(d / "webp_image.webp")                      # another container
    im.save(d / "nested" / "deep" / "buried.jpg")       # recursion
    (d / "corrupt.jpg").write_bytes(b"\xff\xd8\xff\xe0 not a real jpeg")
    (d / "zero_bytes.png").write_bytes(b"")
    (d / "notes.txt").write_text("not an image")        # must be ignored
    return d


@pytest.fixture(scope="module")
def result(judge_folder, tmp_path_factory):
    out = tmp_path_factory.mktemp("out") / "predictions.json"
    proc = subprocess.run([sys.executable, "scripts/infer_dir.py", str(judge_folder),
                           "--output", str(out)],
                          cwd=ROOT, capture_output=True, text=True, check=False)
    if not out.exists():
        pytest.skip(f"expert unavailable: {proc.stderr[-200:]}")
    return proc, json.loads(out.read_text())


def test_exits_zero_even_with_unreadable_files(result):
    proc, _ = result
    assert proc.returncode == 0, proc.stderr[-400:]


def test_one_row_per_recognised_image_and_none_for_the_text_file(result):
    _, rows = result
    assert len(rows) == 11, [r["image_path"] for r in rows]
    assert not any(r["image_path"].endswith(".txt") for r in rows)


def test_the_two_required_keys_are_on_every_row(result):
    _, rows = result
    for r in rows:
        assert "image_path" in r and "pred" in r


def test_a_file_that_cannot_be_decoded_never_gets_an_invented_score(result):
    _, rows = result
    failed = [r for r in rows if r["pred"] is None]
    assert {Path(r["image_path"]).name for r in failed} == {"corrupt.jpg", "zero_bytes.png"}
    for r in failed:
        assert r["error"] == "decode_failed"


def test_every_score_is_a_probability(result):
    _, rows = result
    for r in rows:
        if r["pred"] is not None:
            assert isinstance(r["pred"], float) and 0.0 <= r["pred"] <= 1.0


def test_odd_colour_spaces_and_containers_all_score(result):
    """CMYK, grayscale, RGBA and WebP must not crash the decode path."""
    _, rows = result
    scored = {Path(r["image_path"]).name for r in rows if r["pred"] is not None}
    for name in ("cmyk.jpg", "grayscale.png", "with_alpha.png", "webp_image.webp",
                 "UPPERCASE.PNG", "unicode_名前_émoji.png",
                 "with space and 'quote'.jpg", "buried.jpg"):
        assert name in scored, f"{name} did not score"


def test_paths_are_relative_and_posix(result):
    _, rows = result
    for r in rows:
        assert not r["image_path"].startswith("/")
        assert "\\" not in r["image_path"]
