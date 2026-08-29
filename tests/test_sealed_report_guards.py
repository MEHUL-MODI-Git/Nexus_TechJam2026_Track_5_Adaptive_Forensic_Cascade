"""The sealed summary must fail closed. R3, Codex review 2026-08-29.

The reporter was an ad-hoc evaluator: it silently skipped `ok:false` rows,
accepted incomplete or duplicated runs, took a free `--threshold` from the command
line, and emitted an artifact with no provenance. The numbers happened to be
right, but the committed artifact could not prove which run produced them.

The sealed subset may be scored exactly ONCE, so the repair is summary-only: the
preserved dump is validated, its SHA-256 and a full provenance ledger are
recorded, and any malformed or incomplete input is refused rather than averaged.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "sealed_reference_report.py"
DUMP = ROOT / "results" / "sealed" / "predictions.jsonl"
ARTIFACT = ROOT / "results" / "sealed" / "reference-results.json"


def _run(pred: Path, out: Path):
    return subprocess.run([sys.executable, str(SCRIPT), "--pred", str(pred),
                           "--out", str(out)],
                          capture_output=True, text=True, cwd=ROOT, check=False)


@pytest.fixture
def head_rows():
    if not DUMP.exists():
        pytest.skip("sealed dump not present (it is git-ignored)")
    with DUMP.open() as fh:
        return [next(fh) for _ in range(40)]


def test_refuses_incomplete_condition_coverage(tmp_path, head_rows):
    p = tmp_path / "holed.jsonl"
    p.write_text("".join(head_rows[:35]))          # last source lacks conditions
    proc = _run(p, tmp_path / "out.json")
    assert proc.returncode == 2
    assert "full condition coverage" in proc.stderr


def test_refuses_duplicate_view_ids(tmp_path, head_rows):
    p = tmp_path / "dup.jsonl"
    p.write_text("".join(head_rows) + head_rows[0])
    proc = _run(p, tmp_path / "out.json")
    assert proc.returncode == 2
    assert "duplicate view_id" in proc.stderr


def test_refuses_a_dump_containing_failed_rows(tmp_path, head_rows):
    p = tmp_path / "fail.jsonl"
    p.write_text("".join(head_rows)
                 + json.dumps({"view_id": "z:clean", "ok": False, "error": "boom"}) + "\n")
    proc = _run(p, tmp_path / "out.json")
    assert proc.returncode == 2
    assert "failed row" in proc.stderr


def test_there_is_no_free_threshold_flag():
    """A benchmark scored at a number typed on the command line proves nothing."""
    text = SCRIPT.read_text()
    assert '"--threshold"' not in text
    assert "--threshold-artifact" in text
    assert "load_frozen_threshold" in text


def test_committed_artifact_carries_a_full_provenance_ledger():
    if not ARTIFACT.exists():
        pytest.skip("sealed artifact not present")
    prov = json.loads(ARTIFACT.read_text()).get("provenance")
    assert prov, "the sealed artifact must carry provenance"
    for field in ("predictions_sha256", "threshold_artifact_sha256", "checkpoint_sha256",
                  "sealed_files_manifest_sha256", "sealed_denylist_sha256",
                  "transforms_config_sha256", "probes_config_sha256",
                  "pipeline_version", "code_revision"):
        assert prov.get(field), f"provenance missing {field}"
    assert prov["n_failed_rows"] == 0
    assert prov["n_rows_read"] == prov["unique_view_ids"] == 174_380
