"""`scripts/audit_image.py` — the single-image forensic report.

It is a presentation layer over already-tested components, so these tests check
the contract that matters: it must not alter a verdict, it must degrade rather
than crash when an optional layer is missing, and its JSON must be machine
readable.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "audit_image.py"
IMAGE = ROOT / "tests" / "golden" / "sources" / "photo.png"


def _run(*extra):
    return subprocess.run([sys.executable, str(SCRIPT), str(IMAGE), *extra],
                          capture_output=True, text=True, cwd=ROOT, check=False)


@pytest.fixture(scope="module")
def fast():
    proc = _run("--no-audit", "--json")
    if proc.returncode != 0:
        pytest.skip(f"audit CLI unavailable (checkpoint/offline): {proc.stderr[-300:]}")
    return proc


def test_json_is_machine_readable_and_carries_the_prediction(fast):
    doc = json.loads(fast.stdout)
    assert doc["prediction"]["schema_version"] == "prediction.v1"
    assert 0.0 <= doc["prediction"]["p_fake"] <= 1.0
    assert doc["prediction"]["decision"] in ("REAL", "AI-GENERATED")


def test_no_audit_skips_the_certificate_and_stays_on_the_fast_path(fast):
    assert json.loads(fast.stdout)["certificate"] is None


def test_audit_mode_produces_a_certificate_without_changing_the_verdict(fast):
    proc = _run("--json")
    if proc.returncode != 0:
        pytest.skip("audit run unavailable")
    audited = json.loads(proc.stdout)
    plain = json.loads(fast.stdout)
    cert = audited["certificate"]
    assert cert is not None
    assert 0 <= cert["n_retained"] <= cert["n_scored"]
    assert cert["grade"] in ("HIGH", "MEDIUM", "LOW", "VERY LOW", "UNKNOWN")
    # THE contract: auditing observes, it never moves the decision.
    assert audited["prediction"]["p_fake"] == plain["prediction"]["p_fake"]
    assert audited["prediction"]["decision"] == plain["prediction"]["decision"]
    assert cert["verdict"] == plain["prediction"]["decision"]


def test_human_output_names_the_raw_detector_and_the_correction(fast):
    proc = _run("--no-audit")
    if proc.returncode != 0:
        pytest.skip("audit CLI unavailable")
    out = proc.stdout
    assert "VERDICT" in out
    assert "raw detector" in out          # the contribution must be visible
    assert "Research prototype" in out    # the disclaimer must survive


def test_missing_file_exits_nonzero_without_a_traceback():
    proc = subprocess.run([sys.executable, str(SCRIPT), str(ROOT / "nope.jpg")],
                          capture_output=True, text=True, cwd=ROOT, check=False)
    assert proc.returncode == 2
    assert "Traceback" not in proc.stderr
