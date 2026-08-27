"""Results assembly + reporting tests.

Rewritten alongside the R1-R4 fixes. The headline tests here are the ones that
would have caught the original method-pooling bug: a perfect method and an
inverted method must never average into one fictitious method.
"""

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from src.eval.protocol import (
    FrozenThreshold,
    load_frozen_threshold,
    validate_prediction_rows,
)
from src.eval.report import render_markdown, write_markdown
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
ROOT = Path(__file__).resolve().parents[1]
FROZEN = load_frozen_threshold(ROOT / "tests/fixtures/threshold_artifact.v1.json")
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


def _bind_freeze(freeze):
    freeze["manifest_sha256"] = hashlib.sha256(json.dumps(
        {k: v for k, v in freeze.items() if k != "manifest_sha256"},
        sort_keys=True, separators=(",", ":")
    ).encode()).hexdigest()
    return freeze


def _run_manifest(validated, threshold=FROZEN):
    root = Path(__file__).resolve().parents[1]
    threshold_digest = (
        threshold.artifact_sha256 if isinstance(threshold, FrozenThreshold)
        else FROZEN.artifact_sha256
    )

    def digest(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()
    freeze = _bind_freeze({"schema_version": "production-freeze.v1", "manifest_sha256": "",
              "code_revision": "a" * 40, "pipeline_version": "0.1.0", "golden_version": "0.1.0",
              "transform_manifest_sha256": digest(root / "configs/transforms.yaml"),
              "threshold_artifact_sha256": threshold_digest,
              "method_ids": sorted(validated.method_ids),
              "architecture_frozen": True, "sealed_evaluation_authorized": False})
    return {
        "schema_version": "eval-run-manifest.v1", "run_id": "run-1",
        "created_at": "2026-08-27T00:00:00Z", "command": "pytest",
        "code_revision": "a" * 40, "seed": 20260826,
        "dataset": {"name": "fixture", "split": "test", "manifest_path": "tests/fixtures/eval_small_dataset.json",
                    "manifest_sha256": digest(root / "tests/fixtures/eval_small_dataset.json"), "sealed_reference": False},
        "protocol": {"pipeline_version": "0.1.0", "golden_version": "0.1.0",
                     "transform_manifest_path": "configs/transforms.yaml",
                     "transform_manifest_sha256": digest(root / "configs/transforms.yaml"),
                     "golden_manifest_path": "tests/golden/expected.json",
                     "golden_manifest_sha256": digest(root / "tests/golden/expected.json")},
        "methods": [{"method_id": m, "checkpoint_versions": ["fixture"],
                     "preprocessing_versions": ["fixture"], "parameter_count": 0,
                     "config_sha256": "c" * 64} for m in validated.method_ids],
        "coverage": {"expected_source_count": len(validated.source_ids),
                     "expected_view_count": len(set(validated.source_ids)) * len(validated.method_ids) * 20,
                     "successful_view_count": len(validated.rows), "failure_count": 0},
        "failure_ledger": {"path": "tests/fixtures/eval_empty_failure_ledger.json", "sha256": digest(root / "tests/fixtures/eval_empty_failure_ledger.json"), "count": 0},
        "production_freeze": freeze,
    }


def build(validated, threshold=FROZEN, **kw):
    kw.setdefault("bootstrap_replicates", 8)
    manifest = _run_manifest(validated, threshold)
    kw.setdefault("run_manifest", manifest)
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
    assert "headline" not in doc["methods"][0]
    assert "diagnostic_summary" in doc["methods"][0]


def test_frozen_threshold_yields_a_headline_document():
    doc = build(make_rows())
    assert doc["schema_version"] == EVAL_SCHEMA
    assert doc["protocol"]["threshold_artifact_sha256"] == FROZEN.artifact_sha256
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
    doc = build(make_rows())
    assert doc["run"]["run_id"] == "run-1"
    assert doc["protocol"]["pipeline_version"] == "0.1.0"
    assert len(doc["protocol"]["transform_manifest_sha256"]) == 64
    assert doc["dataset"]["class_counts"] == {"0": 2, "1": 2}
    assert doc["dataset"]["group_counts"] == {"g": 4}
    assert doc["methods"][0]["provenance"]["checkpoint_versions"] == ["fixture"]


def test_decode_failures_raise_a_denominator_warning():
    manifest = {"decode_failures": 7}
    with pytest.raises(ValueError, match="eval-run-manifest"):
        build(make_rows(), run_manifest=manifest)


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


def test_markdown_write_is_atomic(tmp_path):
    path = write_markdown(build(make_rows()), tmp_path / "nested" / "eval-results.md")
    assert "Evaluation results" in path.read_text()
    assert not list(path.parent.glob("*.tmp"))


def test_markdown_surfaces_warnings():
    """A denominator-shrinking decode failure must be visible in the report."""
    md = render_markdown(build(make_rows(), threshold=PLACEHOLDER, run_manifest=None))
    assert "## Warnings" in md and "manifest" in md


# --- Phase 2R adversarial boundaries --------------------------------------
def test_sparse_method_source_condition_refuses_reportable_build():
    rows = make_rows(methods=("m1", "m2"), n_sources=4).rows
    rows = [r for r in rows if not (
        r["method_id"] == "m2" and r["source_id"] == "src2" and
        r["condition_id"] == "noise_s0.10"
    )]
    validated = validate_prediction_rows(rows, require_full_grid=False)
    with pytest.raises(CoverageError, match="m2.*src2.*noise_s0.10"):
        build(validated)


def test_caller_cannot_shrink_official_grid():
    with pytest.raises((CoverageError, ValueError, TypeError), match="official|canonical|grid"):
        build(make_rows(), official_conditions=OFFICIAL[:7])


def test_diagnostic_document_has_no_headline_key_recursively():
    doc = build(make_rows(), threshold=PLACEHOLDER)

    def keys(value):
        if isinstance(value, dict):
            yield from value
            for child in value.values():
                yield from keys(child)
        elif isinstance(value, list):
            for child in value:
                yield from keys(child)

    assert "headline" not in set(keys(doc))


def test_pairing_is_invariant_to_method_b_row_order():
    rows = make_rows(methods=("a", "b")).rows
    first = build(validate_prediction_rows(rows, require_full_grid=False))
    a_rows = [r for r in rows if r["method_id"] == "a"]
    b_rows = [r for r in rows if r["method_id"] == "b"]
    shuffled = validate_prediction_rows(a_rows + list(reversed(b_rows)), require_full_grid=False)
    second = build(shuffled)
    assert first["paired_deltas"] == second["paired_deltas"]


def test_diagnostic_pairing_never_uses_positional_rows_for_unequal_keys():
    rows = make_rows(methods=("a", "b")).rows
    rows = [r for r in rows if not (
        r["method_id"] == "b" and r["source_id"] == "src3" and
        r["condition_id"] == "jpeg_q90"
    )]
    validated = validate_prediction_rows(rows, require_full_grid=False)
    doc = build(validated, threshold=PLACEHOLDER, require_full_grid=False)
    assert doc["paired_deltas"] == []
    assert any("canonical key sets differ" in warning for warning in doc["warnings"])


def test_frozen_threshold_cannot_be_fabricated_by_direct_constructor():
    with pytest.raises(TypeError):
        FrozenThreshold(value=0.5, artifact_sha256="a" * 64, payload={})


def test_loaded_threshold_bytes_are_rehashed_during_assembly():
    loaded = load_frozen_threshold(ROOT / "tests/fixtures/threshold_artifact.v1.json")
    object.__setattr__(loaded, "raw_bytes", b"{}")
    with pytest.raises(ValueError, match="digest"):
        build(make_rows(), threshold=loaded)


@pytest.mark.parametrize("replicates", [0, -1, True, 1.5])
def test_invalid_bootstrap_replicates_refuse_before_metric_work(replicates):
    with pytest.raises(ValueError, match="replicate"):
        build(make_rows(), threshold=PLACEHOLDER, bootstrap_replicates=replicates)


def test_all_zero_directional_flips_name_first_canonical_condition():
    doc = build(make_rows(), threshold=PLACEHOLDER)
    summary = doc["methods"][0]["diagnostic_summary"]
    assert summary["max_directional_flip"]["real_to_fake_condition"] == "jpeg_q90"
    assert summary["max_directional_flip"]["fake_to_real_condition"] == "jpeg_q90"


def test_reportable_build_requires_current_run_manifest():
    with pytest.raises(ValueError, match="eval-run-manifest"):
        build_results(make_rows(), FROZEN, run_manifest=None, bootstrap_replicates=8)


def test_dataset_manifest_must_equal_prediction_source_denominator():
    validated = make_rows()
    manifest = _run_manifest(validated)
    path = ROOT / "data/manifests/smoke_v1.json"
    manifest["dataset"]["manifest_path"] = "data/manifests/smoke_v1.json"
    manifest["dataset"]["manifest_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="source IDs"):
        build(validated, run_manifest=manifest)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda m: m["protocol"].__setitem__("transform_manifest_sha256", "0" * 64),
         "transform_manifest.*digest"),
        (lambda m: m["protocol"].__setitem__("golden_version", "stale"),
         "golden_version"),
        (lambda m: m["methods"][0].__setitem__("checkpoint_versions", []),
         "checkpoint_versions"),
        (lambda m: m["coverage"].__setitem__("successful_view_count", 79),
         "successful_view_count"),
        (lambda m: m.__setitem__("run_id", "another-run"), "run_id"),
        (lambda m: m.__setitem__("seed", 7), "seed"),
    ],
)
def test_provenance_mismatch_refuses_reportable_output(mutate, message):
    validated = make_rows()
    manifest = _run_manifest(validated)
    mutate(manifest)
    with pytest.raises(ValueError, match=message):
        build(validated, run_manifest=manifest)


def test_nonzero_failure_denominator_refuses_reportable_output():
    validated = make_rows()
    manifest = _run_manifest(validated)
    ledger = ROOT / "tests/fixtures/eval_one_failure_ledger.json"
    manifest["failure_ledger"] = {
        "path": "tests/fixtures/eval_one_failure_ledger.json",
        "sha256": hashlib.sha256(ledger.read_bytes()).hexdigest(),
        "count": 1,
    }
    manifest["coverage"]["failure_count"] = 1
    with pytest.raises(ValueError, match="denominator"):
        build(validated, run_manifest=manifest)


def test_unbound_freeze_digest_refuses_reportable_output():
    validated = make_rows()
    manifest = _run_manifest(validated)
    manifest["production_freeze"]["manifest_sha256"] = "d" * 64
    with pytest.raises(ValueError, match="does not bind"):
        build(validated, run_manifest=manifest)


def test_sealed_reference_requires_freeze_authorization():
    validated = make_rows()
    manifest = _run_manifest(validated)
    manifest["dataset"]["sealed_reference"] = True
    with pytest.raises(ValueError, match="sealed evaluation"):
        build(validated, run_manifest=manifest)


def test_sealed_reference_succeeds_only_when_freeze_authorizes_it():
    validated = make_rows()
    manifest = _run_manifest(validated)
    manifest["dataset"]["sealed_reference"] = True
    manifest["production_freeze"]["sealed_evaluation_authorized"] = True
    _bind_freeze(manifest["production_freeze"])
    doc = build(validated, run_manifest=manifest)
    assert doc["dataset"]["sealed_reference"] is True


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"threshold": PlaceholderThreshold(float("nan"), "PLACEHOLDER-bad")}, "finite"),
        ({"threshold": PlaceholderThreshold(1.1, "PLACEHOLDER-bad")}, "finite"),
        ({"threshold": PLACEHOLDER, "seed": True}, "seed"),
        ({"threshold": PLACEHOLDER, "ece_bins": 0}, "ece_bins"),
    ],
)
def test_invalid_eval_controls_refuse(kwargs, message):
    with pytest.raises(ValueError, match=message):
        build(make_rows(), **kwargs)
