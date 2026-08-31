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


def _run(pred: Path, out: Path, manifest: Path | None = None):
    cmd = [sys.executable, str(SCRIPT), "--pred", str(pred), "--out", str(out)]
    if manifest is not None:
        cmd += ["--sealed-manifest", str(manifest)]
    return subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT, check=False)


def _manifest_for(rows, path: Path) -> Path:
    """The sealed manifest the fixture rows would have come from: one entry per
    file, i.e. each image repeated `file_multiplicity` times."""
    seen, entries = {}, []
    for r in rows:
        seen.setdefault(r["sha256"], r)
    for sha, r in seen.items():
        for i in range(int(r["file_multiplicity"])):
            entries.append({"path": f"data/sealed/{r['group']}/{sha[:8]}_{i}.jpg",
                            "sha256": sha, "label": int(r["label"]), "group": r["group"]})
    path.write_text(json.dumps(entries))
    return path


@pytest.fixture
def head_rows():
    """One REAL source and one AI source, 20 conditions each.

    B-033 finding 2: this fixture used to be the first 40 lines of the dump, which
    are all COCO reals. Every "valid input" test in this file was therefore
    exercising a dump on which fake recall and AUROC are undefined -- and the
    reporter passed it. A positive fixture that cannot produce the metrics under
    test is not a positive fixture.
    """
    if not DUMP.exists():
        pytest.skip("sealed dump not present (it is git-ignored)")
    by_label = {0: {}, 1: {}}
    with DUMP.open() as fh:
        for line in fh:
            r = json.loads(line)
            lab = int(r["label"])
            chosen = by_label[lab]
            if not chosen:
                chosen["sha"] = r["sha256"]
                chosen["rows"] = []
            if r["sha256"] == chosen["sha"]:
                chosen["rows"].append(line)
            if all(v.get("rows") and len(v["rows"]) == 20 for v in by_label.values()):
                break
    for lab, v in by_label.items():
        if len(v.get("rows", [])) != 20:
            pytest.skip(f"could not assemble a complete label={lab} source from the dump")
    return by_label[0]["rows"] + by_label[1]["rows"]


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
                  "pipeline_version", "summary_code_revision"):
        assert prov.get(field), f"provenance missing {field}"
    assert prov["n_failed_rows"] == 0
    assert prov["n_rows_read"] == prov["unique_view_ids"] == 174_380


def test_the_ledger_says_which_hashes_prove_nothing():
    """S2, Codex review 2026-08-29.

    The v2 ledger hashed the checkpoint and configs that happened to exist when the
    SUMMARY was regenerated, next to the dump's own hash, which read as though those
    files were bound to those rows. They are not: the dump carries no checkpoint,
    config or code identity fields. The honest ledger says so.
    """
    if not ARTIFACT.exists():
        pytest.skip("sealed artifact not present")
    prov = json.loads(ARTIFACT.read_text())["provenance"]
    assert "code_revision" not in prov, "the ambiguous name must not come back"
    binding = prov["binding"]
    assert any("checkpoint_sha256" in x for x in binding["NOT_bound_to_the_rows"])
    assert any("summary_code_revision" in x for x in binding["NOT_bound_to_the_rows"])
    assert "NOT RECORDED" in binding["inference_code_revision"]
    assert any("sealed_files_manifest_sha256" in x for x in binding["bound_to_the_rows"])


def test_refuses_a_repeated_condition_under_a_fresh_view_id(tmp_path, head_rows):
    """S2: "exactly once" was set equality, so this passed and voted twice."""
    dup = json.loads(head_rows[0])
    dup["view_id"] = dup["view_id"] + ":again"        # distinct id, same (sha, condition)
    p = tmp_path / "twice.jsonl"
    p.write_text("".join(head_rows) + json.dumps(dup) + "\n")
    proc = _run(p, tmp_path / "out.json")
    assert proc.returncode == 2
    assert "appear more" in proc.stderr


def test_refuses_a_non_binary_label(tmp_path, head_rows):
    """`True == 1` in Python, so a bool used to sail through as a 1."""
    for bad in (True, 2, -1):
        row = json.loads(head_rows[0])
        row["view_id"] = "bad:clean"
        row["label"] = bad
        p = tmp_path / f"lab_{bad}.jsonl"
        p.write_text("".join(head_rows) + json.dumps(row) + "\n")
        proc = _run(p, tmp_path / f"out_{bad}.json")
        assert proc.returncode == 2, f"label {bad!r} was accepted"
        assert "is not 0 or 1" in proc.stderr


def test_refuses_a_dump_whose_images_are_not_the_sealed_manifest(tmp_path, head_rows):
    """The dump must be bound to the set it claims to score, not merely to itself."""
    rows = [json.loads(x) for x in head_rows]
    manifest = _manifest_for(rows, tmp_path / "manifest.json")
    # a whole extra image with full condition coverage: completeness passes, identity does not
    first = rows[0]["sha256"]
    ghost = [dict(r, sha256="0" * 64, view_id="ghost:" + r["condition_id"])
             for r in rows if r["sha256"] == first]
    p = tmp_path / "ghost.jsonl"
    p.write_text("".join(head_rows) + "".join(json.dumps(g) + "\n" for g in ghost))
    proc = _run(p, tmp_path / "out.json", manifest)
    assert proc.returncode == 2
    assert "image sets differ" in proc.stderr


def test_refuses_a_multiplicity_that_disagrees_with_the_manifest(tmp_path, head_rows):
    """`file_multiplicity` weights every published per-file number; a wrong one
    silently re-weights them all."""
    rows = [json.loads(x) for x in head_rows]
    manifest = _manifest_for(rows, tmp_path / "manifest.json")
    rows[0]["file_multiplicity"] = int(rows[0]["file_multiplicity"]) + 7
    p = tmp_path / "mult.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows))
    proc = _run(p, tmp_path / "out.json", manifest)
    assert proc.returncode == 2
    assert "sealed manifest on file_multiplicity" in proc.stderr


def test_refuses_a_label_that_disagrees_with_the_manifest(tmp_path, head_rows):
    rows = [json.loads(x) for x in head_rows]
    manifest = _manifest_for(rows, tmp_path / "manifest.json")
    for r in rows:
        if r["sha256"] == rows[0]["sha256"]:
            r["label"] = 1 - int(r["label"])
    p = tmp_path / "lab.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows))
    proc = _run(p, tmp_path / "out.json", manifest)
    assert proc.returncode == 2
    assert "sealed manifest on label" in proc.stderr


def test_refuses_when_the_manifest_is_missing(tmp_path, head_rows):
    p = tmp_path / "d.jsonl"
    p.write_text("".join(head_rows))
    proc = _run(p, tmp_path / "out.json", tmp_path / "nope.json")
    assert proc.returncode == 2
    assert "cannot be bound to the set it claims to score" in proc.stderr


# --------------------------------------------------------------------------
# B-031: fields that CARRY WEIGHT in a published metric are type-checked, not
# merely checked for presence. Codex's two reproductions, as regressions.
# --------------------------------------------------------------------------

def test_refuses_a_fractional_file_multiplicity(tmp_path, head_rows):
    """Codex's reproduction: 1.9 was compared to the manifest as int(1.9) == 1
    and PASSED, then weighted the per-file convention as 1.9 -- moving effective
    weight on a 40-row fixture from 40 to 58."""
    rows = [json.loads(x) for x in head_rows]
    manifest = _manifest_for(rows, tmp_path / "manifest.json")
    rows[0]["file_multiplicity"] = 1.9
    p = tmp_path / "frac.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows))
    proc = _run(p, tmp_path / "out.json", manifest)
    assert proc.returncode == 2
    assert "file_multiplicity" in proc.stderr
    assert "positive integer" in proc.stderr


def test_refuses_a_string_abstain(tmp_path, head_rows):
    """bool("false") is True, so a string flipped coverage 0.525 -> 0.500."""
    rows = [json.loads(x) for x in head_rows]
    manifest = _manifest_for(rows, tmp_path / "manifest.json")
    rows[0]["abstain"] = "false"
    p = tmp_path / "abst.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows))
    proc = _run(p, tmp_path / "out.json", manifest)
    assert proc.returncode == 2
    assert "abstain" in proc.stderr


def test_refuses_out_of_range_or_non_finite_metric_fields(tmp_path, head_rows):
    """p_fake, reliability and primary_p_fake all reach published numbers."""
    for field, bad in (("p_fake", 1.5), ("p_fake", "0.5"),
                       ("reliability", -0.1), ("primary_p_fake", 2.0)):
        rows = [json.loads(x) for x in head_rows]
        manifest = _manifest_for(rows, tmp_path / f"m_{field}.json")
        rows[0][field] = bad
        p = tmp_path / f"{field}_{bad}.jsonl"
        p.write_text("".join(json.dumps(r) + "\n" for r in rows))
        proc = _run(p, tmp_path / f"o_{field}_{bad}.json", manifest)
        assert proc.returncode == 2, f"{field}={bad!r} was accepted"
        assert field in proc.stderr


def test_refuses_a_condition_id_outside_the_official_grid(tmp_path, head_rows):
    rows = [json.loads(x) for x in head_rows]
    manifest = _manifest_for(rows, tmp_path / "manifest.json")
    rows[0]["condition_id"] = "jpeg_q7"          # not one of the 20
    p = tmp_path / "cond.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows))
    proc = _run(p, tmp_path / "out.json", manifest)
    assert proc.returncode == 2
    assert "condition_id" in proc.stderr or "full condition coverage" in proc.stderr


def test_the_real_dump_still_passes_every_strict_check(tmp_path, head_rows):
    """The guards must bind malformed input without rejecting the real run."""
    rows = [json.loads(x) for x in head_rows]
    manifest = _manifest_for(rows, tmp_path / "manifest.json")
    p = tmp_path / "clean.jsonl"
    p.write_text("".join(head_rows))
    proc = _run(p, tmp_path / "out.json", manifest)
    assert proc.returncode == 0, proc.stderr


# --------------------------------------------------------------------------
# B-033 finding 2: the reporter's own 40-row fixture contained only REAL
# sources. Fake recall and AUROC are undefined without both strata, and it
# returned rc=0 while writing bare `NaN` -- which is not valid JSON, and which
# lenient readers accept in silence.
# --------------------------------------------------------------------------

def test_refuses_a_dump_with_no_ai_images(tmp_path, head_rows):
    rows = [json.loads(x) for x in head_rows]
    for r in rows:
        r["label"] = 0
    manifest = _manifest_for(rows, tmp_path / "m.json")   # manifest AFTER the edit,
    # so the stratum guard is what fires rather than the manifest cross-check
    p = tmp_path / "reals_only.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows))
    proc = _run(p, tmp_path / "out.json", manifest)
    assert proc.returncode == 2
    assert "only real images" in proc.stderr
    assert "NaN is not a result" in proc.stderr


def test_refuses_a_dump_with_no_real_images(tmp_path, head_rows):
    rows = [json.loads(x) for x in head_rows]
    for r in rows:
        r["label"] = 1
    manifest = _manifest_for(rows, tmp_path / "m.json")
    p = tmp_path / "fakes_only.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows))
    proc = _run(p, tmp_path / "out.json", manifest)
    assert proc.returncode == 2
    assert "only AI images" in proc.stderr


def test_refuses_a_condition_missing_one_stratum(tmp_path, head_rows):
    """Per-condition metrics are published too, so each condition needs both."""
    rows = [json.loads(x) for x in head_rows]
    manifest = _manifest_for(rows, tmp_path / "m.json")
    for r in rows:
        if r["condition_id"] == "jpeg_q30":
            r["label"] = 1
    p = tmp_path / "onesided.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows))
    proc = _run(p, tmp_path / "out.json", manifest)
    assert proc.returncode == 2
    assert "would be undefined" in proc.stderr or "conflicting labels" in proc.stderr


def test_a_nan_can_never_reach_the_committed_artifact():
    src = SCRIPT.read_text()
    assert "allow_nan=False" in src
    assert "_nonfinite(doc)" in src


def test_the_committed_sealed_artifact_holds_no_nan():
    if not ARTIFACT.exists():
        pytest.skip("sealed artifact not present")
    raw = ARTIFACT.read_text()
    assert "NaN" not in raw and "Infinity" not in raw
    json.loads(raw)   # strict parse: would raise on bare NaN
