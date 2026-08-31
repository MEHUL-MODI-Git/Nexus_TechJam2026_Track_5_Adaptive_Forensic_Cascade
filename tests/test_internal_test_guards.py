"""The one-shot internal-test reporter must refuse a cache it cannot honestly score.

B-032 P0, Codex Phase-4 exit audit. `evaluate_internal_test.py` checked only
`manifest.role`. It loaded rows directly, validated neither schema nor coverage,
hashed the MANIFEST but never the ROWS, and serialised with JSON's default
`allow_nan=True`.

Codex's reproduction: copy the real complete manifest over a cache holding 39
rows from 2 sources with one condition missing, point the script at the frozen
checkpoint and artifact, and it returns rc=0 while writing NaN headline
statistics under a manifest still claiming 60,000 rows.

That is the exact boundary the accepted `src.eval` harness exists to refuse, and
this file is that reproduction, kept as a regression.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "evaluate_internal_test.py"
CACHE = ROOT / "data" / "feature_cache" / "internal-test-v2"
CKPT = ROOT / "results" / "router-fitting-v2" / "router_reliability.pt"
ART = ROOT / "results" / "router-fitting-v2" / "threshold-artifact.v1.json"


def _run(cache: Path, out: Path, bootstrap: int = 2):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--cache", str(cache), "--checkpoint", str(CKPT),
         "--threshold-artifact", str(ART), "--out", str(out), "--bootstrap", str(bootstrap)],
        capture_output=True, text=True, cwd=ROOT, check=False)


@pytest.fixture
def real_cache():
    if not (CACHE / "rows.jsonl").exists() or not CKPT.exists():
        pytest.skip("internal-test cache or checkpoint not present")
    return CACHE


def _truncated(tmp_path, real_cache, n_sources=2, drop_condition=True):
    """The real manifest, over a handful of rows: Codex's reproduction."""
    cache = tmp_path / "cache"
    cache.mkdir()
    shutil.copy(real_cache / "manifest.json", cache / "manifest.json")
    rows, sources = [], []
    with (real_cache / "rows.jsonl").open() as fh:
        for line in fh:
            r = json.loads(line)
            if r["source_id"] not in sources:
                if len(sources) == n_sources:
                    break
                sources.append(r["source_id"])
            rows.append(r)
    if drop_condition:
        for i in range(len(rows) - 1, -1, -1):
            if rows[i]["source_id"] == sources[-1]:
                del rows[i]
                break
    (cache / "rows.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    return cache, len(rows)


def test_refuses_a_complete_manifest_over_a_truncated_rows_file(tmp_path, real_cache):
    """The headline finding: rc=0 and NaN, under a manifest claiming 60,000 rows."""
    cache, n_rows = _truncated(tmp_path, real_cache)
    out = tmp_path / "out.json"
    proc = _run(cache, out)
    assert proc.returncode == 2, f"accepted a {n_rows}-row cache: {proc.stdout}"
    assert "cannot produce a headline" in proc.stderr
    assert "rows" in proc.stderr
    assert not out.exists(), "a refused run must not write a results document"


def test_names_every_reason_not_just_the_first(tmp_path, real_cache):
    """A reviewer fixing one problem should see the rest in the same run."""
    cache, _ = _truncated(tmp_path, real_cache)
    proc = _run(cache, tmp_path / "out.json")
    reasons = [ln for ln in proc.stderr.splitlines() if ln.strip().startswith("- ")]
    assert len(reasons) >= 3, proc.stderr
    joined = " ".join(reasons)
    assert "rows" in joined and "sources" in joined
    assert "20-condition grid" in joined


def test_refuses_a_cache_whose_rows_were_made_by_another_expert_revision(tmp_path, real_cache):
    """Rows from different weights than the frozen ones are not this system's rows."""
    cache = tmp_path / "cache"
    cache.mkdir()
    manifest = json.loads((real_cache / "manifest.json").read_text())
    manifest["experts"] = ["commfor_384@OwensLab/commfor-model-384@" + "0" * 40]
    (cache / "manifest.json").write_text(json.dumps(manifest))
    shutil.copy(real_cache / "rows.jsonl", cache / "rows.jsonl")
    proc = _run(cache, tmp_path / "out.json")
    assert proc.returncode == 2
    assert "frozen expert revision" in proc.stderr


def test_refuses_an_incomplete_manifest_status(tmp_path, real_cache):
    cache = tmp_path / "cache"
    cache.mkdir()
    manifest = json.loads((real_cache / "manifest.json").read_text())
    manifest["status"] = "running"
    (cache / "manifest.json").write_text(json.dumps(manifest))
    shutil.copy(real_cache / "rows.jsonl", cache / "rows.jsonl")
    proc = _run(cache, tmp_path / "out.json")
    assert proc.returncode == 2
    assert "not 'complete'" in proc.stderr


def test_a_nan_can_never_be_serialised():
    """`json.dumps` emits bare NaN by default, which is not valid JSON and which
    most readers accept in silence."""
    src = SCRIPT.read_text()
    assert "allow_nan=False" in src
    assert "assert_finite(doc)" in src


def test_the_published_document_records_row_identity_not_only_the_manifest():
    """Hashing the manifest proves nothing about the rows it claims to describe."""
    src = SCRIPT.read_text()
    assert '"cache_rows_sha256"' in src
    results = ROOT / "results" / "internal-test" / "results.json"
    if not results.exists():
        pytest.skip("internal-test results not present")
    doc = json.loads(results.read_text())
    assert len(doc.get("cache_rows_sha256", "")) == 64
    assert doc.get("expert_revision") == "6076002bf0d9dd37537f965ee2f06f826c333b61"


# --------------------------------------------------------------------------
# B-033 finding 1: `family` is metric-bearing, so it must be derived from
# condition_id, never trusted from the row. Codex relabelled the 4,500 fake
# noise rows as `blur`; the reporter returned rc=0 and moved worst-family recall
# from 0.8258 to 0.8864 by silently dropping noise out of the set of families.
# --------------------------------------------------------------------------

def _rows_of(real_cache):
    with (real_cache / "rows.jsonl").open() as fh:
        return [json.loads(line) for line in fh]


def _cache_from(tmp_path, real_cache, rows, name="cache"):
    cache = tmp_path / name
    cache.mkdir()
    shutil.copy(real_cache / "manifest.json", cache / "manifest.json")
    (cache / "rows.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    return cache


def test_refuses_rows_whose_family_contradicts_their_condition(tmp_path, real_cache):
    """Codex's reproduction, exactly: relabel every fake noise row as blur."""
    rows = _rows_of(real_cache)
    n = 0
    for r in rows:
        if r["label"] == 1 and r["condition_id"].startswith("noise_"):
            r["family"] = "blur"
            n += 1
    assert n == 4500, f"expected 4,500 fake noise rows, found {n}"
    proc = _run(_cache_from(tmp_path, real_cache, rows), tmp_path / "out.json")
    assert proc.returncode == 2, "the relabelled cache was accepted"
    assert "contradicts their condition_id" in proc.stderr


def test_the_headline_is_computed_from_condition_id_not_the_stored_family():
    """Even if a mislabelled row slipped past, the metric must not read it."""
    src = SCRIPT.read_text()
    assert 'fams = np.array([FAMILY_OF[r["condition_id"]] for r in rows])' in src
    assert 'r.get("family") or FAMILY_OF' not in src, "the trusting form is back"


def test_requires_every_row_to_be_the_test_split(tmp_path, real_cache):
    rows = _rows_of(real_cache)
    rows[0]["dataset_split"] = "train"
    proc = _run(_cache_from(tmp_path, real_cache, rows), tmp_path / "out.json")
    assert proc.returncode == 2
    assert "dataset_split='test'" in proc.stderr


def test_refuses_rows_that_did_not_come_from_this_extraction(tmp_path, real_cache):
    """The manifest header is not evidence about the rows beneath it.

    feature-cache-row.v2 records no per-row expert revision, so the binding used
    is `cache_key` -- a digest over the extraction inputs, expert included. Rows
    carrying a foreign key were produced by a different extraction and must not be
    scored under this manifest."""
    rows = _rows_of(real_cache)
    for r in rows[:50]:
        r["cache_key"] = "0" * 64
    proc = _run(_cache_from(tmp_path, real_cache, rows), tmp_path / "out.json")
    assert proc.returncode == 2
    assert "not produced by this extraction" in proc.stderr
