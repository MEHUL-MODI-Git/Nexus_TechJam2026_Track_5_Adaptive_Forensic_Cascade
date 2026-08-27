import copy
import json

import pytest

from src.eval.protocol import (
    load_frozen_threshold,
    load_prediction_rows,
    validate_prediction_rows,
)
from src.pipeline.transforms import CONDITION_IDS, FAMILY_OF


def _row(source, label, condition="clean", method="m1"):
    return {
        "schema_version": "prediction-row.v1",
        "run_id": "run-1",
        "method_id": method,
        "sample_id": f"{source}:{condition}",
        "source_id": source,
        "image_path": f"images/{source}.png",
        "content_sha256": "a" * 64,
        "label": label,
        "dataset": "fixture",
        "source_group": "fixture-group",
        "condition_id": condition,
        "family": FAMILY_OF[condition],
        "p_fake": 0.8 if label else 0.2,
        "reliability": None,
        "decision": None,
        "rescue_invoked": None,
        "inference_ms": 1.0,
        "expert_failures": None,
        "warnings": [],
    }


def _grid():
    return [_row(source, label, condition) for source, label in (("real", 0), ("fake", 1)) for condition in CONDITION_IDS]


def _threshold_artifact():
    return {
        "schema_version": "threshold-artifact.v1",
        "threshold": 0.5,
        "objective": "frozen objective",
        "feasible": True,
        "selection_granularity": "family",
        "objective_value": 0.8,
        "objective_ci95": [0.7, 0.9],
        "worst_family": "noise",
        "worst_exact_condition": "noise_s0.10",
        "worst_exact_condition_recall": 0.7,
        "clean_fpr": 0.01,
        "clean_bacc": 0.9,
        "baseline_clean_fpr": 0.01,
        "baseline_clean_bacc": 0.9,
        "constraint_max_clean_fpr": 0.02,
        "constraint_min_clean_bacc": 0.89,
        "n_dev_sources": 100,
        "n_dev_rows": 2000,
        "n_fake_sources_per_exact_condition_min": 50,
        "bootstrap": {"n_replicates": 1000, "seed": 7, "unit": "source_id",
                       "stratified_by": "label", "interval": "percentile_95"},
        "dev_manifest_sha256": "b" * 64,
        "config_sha256": "c" * 64,
        "pipeline_version": "0.1.0",
        "fitting_code_version": "abc123",
        "created_at": "2026-08-27T00:00:00+00:00",
        "tie_break": "objective > clean_bacc > -clean_fpr > threshold",
        "warnings": [],
    }


def test_valid_full_grid_contract():
    result = validate_prediction_rows(_grid())
    assert result.method_ids == ("m1",)
    assert result.source_ids == ("fake", "real")
    assert result.condition_ids == tuple(CONDITION_IDS)


def test_nullable_does_not_mean_optional():
    rows = _grid()
    del rows[0]["expert_failures"]
    with pytest.raises(ValueError, match="expert_failures"):
        validate_prediction_rows(rows)


def test_duplicate_method_source_condition_is_rejected():
    rows = _grid()
    rows.append(copy.deepcopy(rows[0]))
    with pytest.raises(ValueError, match="duplicate"):
        validate_prediction_rows(rows)


def test_missing_clean_and_incomplete_full_grid_are_rejected():
    rows = [row for row in _grid() if row["condition_id"] != "clean"]
    with pytest.raises(ValueError, match="missing clean"):
        validate_prediction_rows(rows)


def test_inconsistent_source_identity_is_rejected():
    rows = _grid()
    rows[1]["label"] = 1
    with pytest.raises(ValueError, match="inconsistent identity"):
        validate_prediction_rows(rows)


def test_unknown_condition_and_family_mismatch_are_rejected():
    rows = _grid()
    rows[0]["condition_id"] = "unknown"
    with pytest.raises(ValueError, match="unknown official"):
        validate_prediction_rows(rows)
    rows = _grid()
    rows[0]["family"] = "jpeg"
    with pytest.raises(ValueError, match="does not match"):
        validate_prediction_rows(rows)


def test_headline_condition_must_contain_both_classes():
    rows = [row for row in _grid() if not (row["source_id"] == "fake" and row["condition_id"] == "jpeg_q30")]
    with pytest.raises(ValueError, match="not the full grid"):
        validate_prediction_rows(rows)


def test_prediction_jsonl_loader_reports_malformed_line(tmp_path):
    path = tmp_path / "rows.jsonl"
    path.write_text(json.dumps(_grid()[0]) + "\n{" )
    with pytest.raises(ValueError, match="line 2"):
        load_prediction_rows(path)


def test_frozen_threshold_loader_validates_provenance_and_hashes(tmp_path):
    path = tmp_path / "threshold.json"
    path.write_text(json.dumps(_threshold_artifact()))
    artifact = load_frozen_threshold(path)
    assert artifact.value == 0.5
    assert len(artifact.artifact_sha256) == 64
    assert artifact.payload["bootstrap"] == {
        "n_replicates": 1000, "seed": 7, "unit": "source_id",
        "stratified_by": "label", "interval": "percentile_95",
    }


@pytest.mark.parametrize("field", ["dev_manifest_sha256", "config_sha256"])
def test_frozen_threshold_refuses_missing_provenance(tmp_path, field):
    payload = _threshold_artifact()
    payload[field] = ""
    path = tmp_path / "threshold.json"
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match=field):
        load_frozen_threshold(path)


def test_placeholder_config_is_not_a_threshold_artifact(tmp_path):
    path = tmp_path / "placeholder.json"
    path.write_text(json.dumps({"threshold": 0.5, "threshold_provenance": "PLACEHOLDER"}))
    with pytest.raises(ValueError, match="missing required fields"):
        load_frozen_threshold(path)
