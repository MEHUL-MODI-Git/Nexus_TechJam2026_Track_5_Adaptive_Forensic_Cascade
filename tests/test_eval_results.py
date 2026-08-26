"""Results assembly + reporting tests.

[relay] Claude, while Codex is limit-blocked. Codex owns src/eval/ and reviews
this on return.

The tests that matter most here are the boundary ones: a placeholder threshold
must be structurally incapable of producing a headline, and a real artifact must
be structurally incapable of producing a document labelled "diagnostic".
"""

import json

import numpy as np
import pytest

from src.eval.protocol import validate_prediction_rows
from src.eval.report import render_markdown
from src.eval.results import (
    DIAGNOSTIC_SCHEMA,
    EVAL_SCHEMA,
    TRANSFORM_FAMILIES,
    bootstrap_condition_metric,
    build_results,
    write_results,
)

FAMILY_OF = {
    "clean": "clean", "jpeg_q90": "jpeg", "jpeg_q30": "jpeg",
    "blur_s2.0": "blur", "resize_0.5": "resize", "noise_s0.10": "noise",
    "bright_-20": "color", "crop_0.8": "crop",
}
CONDITIONS = list(FAMILY_OF)


def make_rows(n_sources=12, fake_score_by_condition=None, seed=0):
    """Balanced rows across every condition, with controllable difficulty."""
    fake_score_by_condition = fake_score_by_condition or {}
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n_sources):
        label = i % 2
        source_id = f"src-{i}"
        for condition in CONDITIONS:
            base = fake_score_by_condition.get(condition, 0.9) if label == 1 else 0.02
            rows.append({
                "schema_version": "prediction-row.v1",
                "run_id": "run-1", "method_id": "m1",
                "sample_id": f"s{i}:{condition}", "source_id": source_id,
                "image_path": f"img{i}.png",
                "content_sha256": f"{i:064d}"[:64],
                "label": label, "dataset": "TEST", "source_group": "g",
                "condition_id": condition,
                "p_fake": float(np.clip(base + rng.normal(0, 1e-6), 0, 1)),
                "reliability": None, "decision": None, "rescue_invoked": None,
                "inference_ms": 1.0, "warnings": [], "expert_failures": None,
            })
    return validate_prediction_rows(rows, require_full_grid=False)


# --- the diagnostic / headline boundary ----------------------------------
def test_placeholder_provenance_cannot_produce_a_headline():
    with pytest.raises(ValueError, match="may never populate a headline"):
        build_results(make_rows(), 0.5, "PLACEHOLDER-uncalibrated-phase0",
                      diagnostic=False, family_of=FAMILY_OF, bootstrap_replicates=5)


def test_real_artifact_cannot_produce_a_diagnostic_document():
    with pytest.raises(ValueError, match="requires a PLACEHOLDER"):
        build_results(make_rows(), 0.5, "dev-fitted-2026-08-27",
                      diagnostic=True, family_of=FAMILY_OF, bootstrap_replicates=5)


def test_diagnostic_document_has_no_headline_block():
    doc = build_results(make_rows(), 0.5, "PLACEHOLDER-x", diagnostic=True,
                        family_of=FAMILY_OF, bootstrap_replicates=5)
    assert doc["schema_version"] == DIAGNOSTIC_SCHEMA
    assert "headline" not in doc                  # cannot be quoted as a result
    assert "diagnostic_summary" in doc
    assert "NOT_A_HEADLINE_RESULT" in doc
    assert "PLACEHOLDER-x" in doc["NOT_A_HEADLINE_RESULT"]   # verbatim provenance


def test_eval_document_has_a_headline_block():
    doc = build_results(make_rows(), 0.5, "dev-fitted", diagnostic=False,
                        family_of=FAMILY_OF, bootstrap_replicates=5)
    assert doc["schema_version"] == EVAL_SCHEMA
    assert "headline" in doc
    assert doc["protocol"]["threshold_fitted_on_held_out_dev"] is True


# --- objective semantics --------------------------------------------------
def test_clean_is_excluded_from_the_worst_family():
    doc = build_results(make_rows(fake_score_by_condition={"clean": 0.0}),
                        0.5, "dev-fitted", diagnostic=False,
                        family_of=FAMILY_OF, bootstrap_replicates=5)
    assert doc["headline"]["worst_family"]["family"] != "clean"
    assert all(f["family"] in TRANSFORM_FAMILIES for f in doc["families"])


def test_worst_exact_condition_is_reported_and_can_differ_from_family():
    doc = build_results(make_rows(fake_score_by_condition={"jpeg_q30": 0.0}),
                        0.5, "dev-fitted", diagnostic=False,
                        family_of=FAMILY_OF, bootstrap_replicates=5)
    assert doc["headline"]["worst_exact_condition"]["condition_id"] == "jpeg_q30"
    assert doc["headline"]["worst_exact_condition"]["fake_recall"] == 0.0
    # jpeg pools two conditions, so the family value stays above the worst one
    jpeg = next(f for f in doc["families"] if f["family"] == "jpeg")
    assert jpeg["metrics"]["fake_recall"] > 0.0


def test_worst_exact_condition_never_selects_clean():
    doc = build_results(make_rows(fake_score_by_condition={"clean": 0.0}),
                        0.5, "dev-fitted", diagnostic=False,
                        family_of=FAMILY_OF, bootstrap_replicates=5)
    assert doc["headline"]["worst_exact_condition"]["condition_id"] != "clean"


def test_directional_flips_are_attributed_to_a_condition():
    doc = build_results(make_rows(fake_score_by_condition={"noise_s0.10": 0.0}),
                        0.5, "dev-fitted", diagnostic=False,
                        family_of=FAMILY_OF, bootstrap_replicates=5)
    flip = doc["headline"]["max_directional_flip"]
    assert flip["fake_to_real_flip"] > 0.9
    assert flip["fake_to_real_condition"] == "noise_s0.10"


def test_clean_has_no_flip_block():
    doc = build_results(make_rows(), 0.5, "dev-fitted", diagnostic=False,
                        family_of=FAMILY_OF, bootstrap_replicates=5)
    clean = next(c for c in doc["conditions"] if c["condition_id"] == "clean")
    assert "flips" not in clean          # nothing to pair clean against


def test_selective_and_rescue_are_explicitly_null_not_zero():
    doc = build_results(make_rows(), 0.5, "dev-fitted", diagnostic=False,
                        family_of=FAMILY_OF, bootstrap_replicates=5)
    assert doc["headline"]["selective"] is None
    assert doc["headline"]["rescue"] is None


def test_missing_clean_rows_is_an_error():
    rows = [r for r in make_rows().rows if r["condition_id"] != "clean"]
    with pytest.raises(ValueError, match="clean"):
        build_results(validate_prediction_rows(rows, require_full_grid=False),
                      0.5, "dev-fitted", diagnostic=False,
                      family_of=FAMILY_OF, bootstrap_replicates=5)


def test_raw_counts_are_present_for_audit():
    doc = build_results(make_rows(), 0.5, "dev-fitted", diagnostic=False,
                        family_of=FAMILY_OF, bootstrap_replicates=5)
    for entry in doc["conditions"]:
        assert set(entry["counts"]) == {"tp", "fn", "fp", "tn"}


# --- bootstrap ------------------------------------------------------------
def test_bootstrap_is_deterministic_and_brackets_the_mean():
    v = make_rows()
    labels = np.array([r["label"] for r in v.rows])
    scores = np.array([r["p_fake"] for r in v.rows])
    sources = np.array([r["source_id"] for r in v.rows])
    a = bootstrap_condition_metric(labels, scores, sources, 0.5, n_replicates=50, seed=3)
    b = bootstrap_condition_metric(labels, scores, sources, 0.5, n_replicates=50, seed=3)
    assert a == b
    assert a["ci95_low"] <= a["mean"] <= a["ci95_high"]
    assert a["unit"] == "source_id" and a["stratified_by"] == "label"


def test_bootstrap_requires_both_classes():
    v = make_rows()
    keep = [r for r in v.rows if r["label"] == 1]
    labels = np.array([r["label"] for r in keep])
    scores = np.array([r["p_fake"] for r in keep])
    sources = np.array([r["source_id"] for r in keep])
    with pytest.raises(ValueError, match="both classes"):
        bootstrap_condition_metric(labels, scores, sources, 0.5, n_replicates=5)


# --- reporting ------------------------------------------------------------
def test_markdown_watermarks_a_diagnostic_document():
    doc = build_results(make_rows(), 0.5, "PLACEHOLDER-uncalibrated-phase0",
                        diagnostic=True, family_of=FAMILY_OF, bootstrap_replicates=5)
    md = render_markdown(doc)
    assert "NOT a result" in md
    assert "PLACEHOLDER-uncalibrated-phase0" in md
    assert "DIAGNOSTIC ONLY" in md


def test_markdown_values_trace_to_the_json():
    doc = build_results(make_rows(), 0.5, "dev-fitted", diagnostic=False,
                        family_of=FAMILY_OF, bootstrap_replicates=5)
    md = render_markdown(doc)
    recall = doc["headline"]["clean"]["fake_recall"]
    assert f"{recall:.4f}" in md            # rendered, not recomputed
    assert doc["headline"]["worst_family"]["family"] in md


def test_markdown_reports_absent_selective_metrics_explicitly():
    doc = build_results(make_rows(), 0.5, "dev-fitted", diagnostic=False,
                        family_of=FAMILY_OF, bootstrap_replicates=5)
    assert "not emitted" in render_markdown(doc)


# --- writing --------------------------------------------------------------
def test_write_is_atomic_and_roundtrips(tmp_path):
    doc = build_results(make_rows(), 0.5, "dev-fitted", diagnostic=False,
                        family_of=FAMILY_OF, bootstrap_replicates=5)
    path = write_results(doc, tmp_path / "nested" / "eval-results.json")
    assert json.loads(path.read_text())["schema_version"] == EVAL_SCHEMA
    assert not list(path.parent.glob("*.tmp"))
