"""Results assembly + reporting tests.

Rewritten alongside the R1-R4 fixes. The headline tests here are the ones that
would have caught the original method-pooling bug: a perfect method and an
inverted method must never average into one fictitious method.
"""

import json

import numpy as np
import pytest

from src.eval.protocol import FrozenThreshold, validate_prediction_rows
from src.eval.report import render_markdown
from src.eval.results import (
    DIAGNOSTIC_SCHEMA,
    EVAL_SCHEMA,
    TRANSFORM_FAMILIES,
    CoverageError,
    PlaceholderThreshold,
    build_results,
    write_results,
)
from src.pipeline.transforms import CONDITION_IDS, FAMILY_OF

OFFICIAL = tuple(CONDITION_IDS)
FROZEN = FrozenThreshold(value=0.5, artifact_sha256="a" * 64,
                         payload={"threshold_provenance": "dev-fitted-2026-08-27"})
PLACEHOLDER = PlaceholderThreshold(value=0.5, provenance="PLACEHOLDER-uncalibrated-phase0")


def make_rows(methods=("m1",), n_sources=4, conditions=OFFICIAL, invert=(), seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for method in methods:
        for i in range(n_sources):
            label = i % 2
            for condition in conditions:
                base = (1.0 - label) if method in invert else float(label)
                p = float(np.clip(base * 0.98 + 0.01 + rng.normal(0, 1e-5), 0, 1))
                rows.append({
                    "schema_version": "prediction-row.v1", "run_id": "run-1",
                    "method_id": method, "sample_id": f"s{i}:{condition}:{method}",
                    "source_id": f"src{i}", "image_path": f"img{i}.png",
                    "content_sha256": f"{i:064d}"[:64], "label": label,
                    "dataset": "TEST", "source_group": "g", "condition_id": condition,
                    "p_fake": p, "reliability": None, "decision": None,
                    "rescue_invoked": None, "inference_ms": 1.0, "warnings": [],
                    "expert_failures": None,
                })
    return validate_prediction_rows(rows, require_full_grid=False)


def build(validated, threshold=FROZEN, **kw):
    kw.setdefault("bootstrap_replicates", 8)
    return build_results(validated, threshold, family_of=FAMILY_OF,
                         official_conditions=OFFICIAL, **kw)


# --- R1: methods must never be pooled -------------------------------------
def test_methods_are_never_pooled():
    """A perfect and an inverted method must not average to chance."""
    doc = build(make_rows(methods=("perfect", "inverted"), invert=("inverted",)))
    assert doc["method_ids"] == ["inverted", "perfect"]
    by_id = {m["method_id"]: m for m in doc["methods"]}
    assert by_id["perfect"]["headline"]["clean"]["balanced_accuracy"] == 1.0
    assert by_id["inverted"]["headline"]["clean"]["balanced_accuracy"] == 0.0


def test_each_method_gets_its_own_full_condition_set():
    doc = build(make_rows(methods=("a", "b")))
    for method in doc["methods"]:
        assert len(method["conditions"]) == len(OFFICIAL)


def test_paired_deltas_present_for_multiple_methods():
    doc = build(make_rows(methods=("perfect", "inverted"), invert=("inverted",)))
    assert len(doc["paired_deltas"]) == 1
    delta = doc["paired_deltas"][0]
    assert delta["bootstrap"]["shared_indices"] is True
    assert delta["ci95_low"] <= delta["delta_mean"] <= delta["ci95_high"]


def test_single_method_has_no_paired_deltas():
    assert build(make_rows())["paired_deltas"] == []


# --- R2: a headline structurally requires a threshold artifact ------------
def test_provenance_string_cannot_authorise_a_headline():
    with pytest.raises(TypeError, match="FrozenThreshold"):
        build(make_rows(), threshold="dev-fitted-arbitrary-string")


def test_placeholder_threshold_yields_a_diagnostic_document():
    doc = build(make_rows(), threshold=PLACEHOLDER)
    assert doc["schema_version"] == DIAGNOSTIC_SCHEMA
    assert "NOT_A_HEADLINE_RESULT" in doc
    assert doc["protocol"]["threshold_fitted_on_held_out_dev"] is False


def test_frozen_threshold_yields_a_headline_document():
    doc = build(make_rows())
    assert doc["schema_version"] == EVAL_SCHEMA
    assert doc["protocol"]["threshold_artifact_sha256"] == "a" * 64
    assert doc["protocol"]["threshold_fitted_on_held_out_dev"] is True


def test_placeholder_type_rejects_a_fitted_provenance():
    with pytest.raises(ValueError, match="must start with"):
        PlaceholderThreshold(value=0.5, provenance="dev-fitted")


# --- R3 / R13: coverage ---------------------------------------------------
def test_partial_grid_cannot_produce_a_headline():
    with pytest.raises(CoverageError, match="partial grid"):
        build(make_rows(), require_full_grid=False)


def test_missing_condition_refuses_headline():
    subset = tuple(c for c in OFFICIAL if c != "noise_s0.10")
    with pytest.raises(CoverageError, match="missing conditions"):
        build(make_rows(conditions=subset))


def test_missing_family_refuses_headline():
    subset = tuple(c for c in OFFICIAL if FAMILY_OF[c] not in ("crop",))
    with pytest.raises(CoverageError, match="missing"):
        build(make_rows(conditions=subset))


def test_methods_on_different_sources_refuse_headline():
    a = make_rows(methods=("a",), n_sources=4).rows
    b = make_rows(methods=("b",), n_sources=2).rows
    combined = validate_prediction_rows(list(a) + list(b), require_full_grid=False)
    with pytest.raises(CoverageError, match="different source set"):
        build(combined)


def test_diagnostic_path_tolerates_a_partial_grid():
    subset = tuple(c for c in OFFICIAL if c in ("clean", "jpeg_q30"))
    doc = build(make_rows(conditions=subset), threshold=PLACEHOLDER,
                require_full_grid=False)
    assert doc["schema_version"] == DIAGNOSTIC_SCHEMA


# --- R4: provenance -------------------------------------------------------
def test_document_carries_run_provenance():
    manifest = {"run_id": "grid-x", "pipeline_version": "0.1.0",
                "manifest_sha256": "b" * 64, "decode_failures": 0}
    doc = build(make_rows(), run_manifest=manifest)
    assert doc["run"]["run_id"] == "grid-x"
    assert doc["protocol"]["pipeline_version"] == "0.1.0"
    assert doc["protocol"]["transform_manifest_sha256"] == "b" * 64


def test_decode_failures_raise_a_denominator_warning():
    doc = build(make_rows(), run_manifest={"decode_failures": 7})
    assert any("decode failure" in w for w in doc["warnings"])
    assert doc["dataset"]["decode_failures_reported_by_run"] == 7


def test_input_artifact_is_hashed(tmp_path):
    rows_file = tmp_path / "rows.jsonl"
    rows_file.write_text('{"a": 1}\n')
    doc = build(make_rows(), rows_path=rows_file)
    assert len(doc["artifacts"]["prediction_rows"]["sha256"]) == 64


# --- objective semantics --------------------------------------------------
def test_clean_excluded_from_worst_family():
    doc = build(make_rows())
    method = doc["methods"][0]
    assert method["headline"]["worst_family"]["family"] in TRANSFORM_FAMILIES
    assert all(f["family"] in TRANSFORM_FAMILIES for f in method["families"])


def test_worst_exact_condition_never_clean():
    doc = build(make_rows())
    assert doc["methods"][0]["headline"]["worst_exact_condition"]["condition_id"] != "clean"


def test_selective_and_rescue_explicitly_null():
    headline = build(make_rows())["methods"][0]["headline"]
    assert headline["selective"] is None and headline["rescue"] is None


def test_every_reported_metric_has_a_confidence_interval():
    method = build(make_rows())["methods"][0]
    ci = method["conditions"][0]["ci95"]
    for metric in ("fake_recall", "balanced_accuracy", "false_positive_rate", "auroc"):
        assert ci[metric]["ci95_low"] <= ci[metric]["mean"] <= ci[metric]["ci95_high"]


def test_raw_counts_present_for_audit():
    for entry in build(make_rows())["methods"][0]["conditions"]:
        assert set(entry["counts"]) == {"tp", "fn", "fp", "tn"}


def test_clean_has_no_flip_block():
    method = build(make_rows())["methods"][0]
    clean = next(c for c in method["conditions"] if c["condition_id"] == "clean")
    assert "flips" not in clean


# --- reporting ------------------------------------------------------------
def test_markdown_renders_each_method_separately():
    doc = build(make_rows(methods=("perfect", "inverted"), invert=("inverted",)))
    md = render_markdown(doc)
    assert "`perfect`" in md and "`inverted`" in md
    assert "Paired method deltas" in md


def test_markdown_watermarks_diagnostics():
    md = render_markdown(build(make_rows(), threshold=PLACEHOLDER))
    assert "NOT a result" in md and "PLACEHOLDER-uncalibrated-phase0" in md


def test_markdown_values_trace_to_json():
    doc = build(make_rows())
    recall = doc["methods"][0]["headline"]["clean"]["fake_recall"]
    assert f"{recall:.4f}" in render_markdown(doc)


# --- writing --------------------------------------------------------------
def test_write_is_atomic(tmp_path):
    path = write_results(build(make_rows()), tmp_path / "nested" / "eval-results.json")
    assert json.loads(path.read_text())["schema_version"] == EVAL_SCHEMA
    assert not list(path.parent.glob("*.tmp"))


def test_markdown_surfaces_warnings():
    """A denominator-shrinking decode failure must be visible in the report."""
    md = render_markdown(build(make_rows(), run_manifest={"decode_failures": 3}))
    assert "## Warnings" in md and "decode failure" in md
