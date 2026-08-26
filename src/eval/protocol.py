"""Strict consumers for frozen prediction-row and threshold contracts.

This module contains no fitting path.  Evaluation reads a pre-existing
threshold artifact and fails closed on provenance or row-schema drift.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Iterable, Mapping

from src.pipeline.transforms import CONDITION_IDS, FAMILY_OF


PREDICTION_ROW_SCHEMA = "prediction-row.v1"
THRESHOLD_ARTIFACT_SCHEMA = "threshold-artifact.v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")

_ROW_FIELDS = {
    "schema_version",
    "run_id",
    "method_id",
    "sample_id",
    "source_id",
    "image_path",
    "content_sha256",
    "label",
    "dataset",
    "source_group",
    "condition_id",
    "p_fake",
    "reliability",
    "decision",
    "rescue_invoked",
    "inference_ms",
    "expert_failures",
    "warnings",
}

_THRESHOLD_FIELDS = {
    "schema_version",
    "threshold",
    "objective",
    "feasible",
    "selection_granularity",
    "objective_value",
    "objective_ci95",
    "worst_family",
    "worst_exact_condition",
    "worst_exact_condition_recall",
    "clean_fpr",
    "clean_bacc",
    "baseline_clean_fpr",
    "baseline_clean_bacc",
    "constraint_max_clean_fpr",
    "constraint_min_clean_bacc",
    "n_dev_sources",
    "n_dev_rows",
    "n_fake_sources_per_exact_condition_min",
    "bootstrap",
    "dev_manifest_sha256",
    "config_sha256",
    "pipeline_version",
    "fitting_code_version",
    "created_at",
    "tie_break",
    "warnings",
}


@dataclass(frozen=True)
class ValidatedPredictionRows:
    rows: tuple[dict[str, Any], ...]
    run_ids: tuple[str, ...]
    method_ids: tuple[str, ...]
    source_ids: tuple[str, ...]
    condition_ids: tuple[str, ...]


@dataclass(frozen=True)
class FrozenThreshold:
    value: float
    artifact_sha256: str
    payload: dict[str, Any]


def _finite_probability(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be numeric")
    result = float(value)
    if not math.isfinite(result) or not 0.0 <= result <= 1.0:
        raise ValueError(f"{field} must be finite and lie in [0,1]")
    return result


def _nonempty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _validate_optional_probability(value: Any, field: str) -> None:
    if value is not None:
        _finite_probability(value, field)


def _validate_expert_failures(value: Any, row_number: int) -> None:
    if value is None:
        return
    if not isinstance(value, list):
        raise ValueError(f"row {row_number}: expert_failures must be null or a list")
    for failure in value:
        if not isinstance(failure, dict):
            raise ValueError(f"row {row_number}: every expert failure must be an object")
        _nonempty_string(failure.get("expert_id"), "expert_failures[].expert_id")
        _nonempty_string(failure.get("reason_code"), "expert_failures[].reason_code")


def _validate_row(row: Mapping[str, Any], row_number: int) -> dict[str, Any]:
    if not isinstance(row, Mapping):
        raise ValueError(f"row {row_number}: expected a JSON object")
    missing = _ROW_FIELDS - set(row)
    if missing:
        raise ValueError(f"row {row_number}: missing required fields {sorted(missing)}")
    if row["schema_version"] != PREDICTION_ROW_SCHEMA:
        raise ValueError(f"row {row_number}: unexpected schema_version {row['schema_version']!r}")
    for field in (
        "run_id",
        "method_id",
        "sample_id",
        "source_id",
        "image_path",
        "dataset",
        "source_group",
        "condition_id",
    ):
        _nonempty_string(row[field], f"row {row_number}.{field}")
    if not isinstance(row["label"], int) or isinstance(row["label"], bool) or row["label"] not in (0, 1):
        raise ValueError(f"row {row_number}: label must be integer 0 or 1")
    if not isinstance(row["content_sha256"], str) or not _SHA256.fullmatch(row["content_sha256"]):
        raise ValueError(f"row {row_number}: content_sha256 must be 64 lowercase hex characters")
    _finite_probability(row["p_fake"], f"row {row_number}.p_fake")
    _validate_optional_probability(row["reliability"], f"row {row_number}.reliability")
    if row["decision"] is not None and not isinstance(row["decision"], str):
        raise ValueError(f"row {row_number}: decision must be null or a string")
    if row["rescue_invoked"] is not None and not isinstance(row["rescue_invoked"], bool):
        raise ValueError(f"row {row_number}: rescue_invoked must be null or boolean")
    if row["inference_ms"] is not None:
        latency = row["inference_ms"]
        if isinstance(latency, bool) or not isinstance(latency, (int, float)):
            raise ValueError(f"row {row_number}: inference_ms must be null or numeric")
        if not math.isfinite(float(latency)) or float(latency) < 0.0:
            raise ValueError(f"row {row_number}: inference_ms must be finite and non-negative")
    _validate_expert_failures(row["expert_failures"], row_number)
    if not isinstance(row["warnings"], list) or not all(isinstance(item, str) for item in row["warnings"]):
        raise ValueError(f"row {row_number}: warnings must be a list of strings")

    condition = row["condition_id"]
    if condition not in CONDITION_IDS:
        raise ValueError(f"row {row_number}: unknown official condition_id {condition!r}")
    if "family" in row and row["family"] != FAMILY_OF[condition]:
        raise ValueError(
            f"row {row_number}: family {row['family']!r} does not match condition {condition!r}"
        )
    return dict(row)


def validate_prediction_rows(
    rows: Iterable[Mapping[str, Any]],
    *,
    require_full_grid: bool = True,
) -> ValidatedPredictionRows:
    """Validate row schema, uniqueness, source consistency, and coverage."""
    validated = tuple(_validate_row(row, index) for index, row in enumerate(rows, start=1))
    if not validated:
        raise ValueError("prediction rows are empty")

    seen_keys: set[tuple[str, str, str]] = set()
    source_identity: dict[tuple[str, str], tuple[Any, ...]] = {}
    source_conditions: dict[tuple[str, str, str], set[str]] = {}
    condition_labels: dict[tuple[str, str], set[int]] = {}
    sample_identity: dict[str, tuple[str, str]] = {}
    for row in validated:
        key = (row["method_id"], row["source_id"], row["condition_id"])
        if key in seen_keys:
            raise ValueError(f"duplicate method/source/condition row: {key}")
        seen_keys.add(key)

        sample_key = (row["source_id"], row["condition_id"])
        prior_sample = sample_identity.setdefault(row["sample_id"], sample_key)
        if prior_sample != sample_key:
            raise ValueError(f"sample_id {row['sample_id']!r} maps to multiple source views")

        source_key = (row["run_id"], row["source_id"])
        identity = (row["label"], row["dataset"], row["source_group"], row["image_path"])
        prior_identity = source_identity.setdefault(source_key, identity)
        if prior_identity != identity:
            raise ValueError(f"source {source_key!r} has inconsistent identity fields across views")

        coverage_key = (row["run_id"], row["method_id"], row["source_id"])
        source_conditions.setdefault(coverage_key, set()).add(row["condition_id"])
        condition_labels.setdefault((row["method_id"], row["condition_id"]), set()).add(row["label"])

    official = set(CONDITION_IDS)
    for key, conditions in source_conditions.items():
        if "clean" not in conditions:
            raise ValueError(f"source coverage {key!r} is missing clean")
        if require_full_grid and conditions != official:
            missing = sorted(official - conditions)
            extra = sorted(conditions - official)
            raise ValueError(f"source coverage {key!r} is not the full grid; missing={missing}, extra={extra}")
    for key, labels in condition_labels.items():
        if labels != {0, 1}:
            raise ValueError(f"headline condition {key!r} must contain both classes, found {sorted(labels)}")

    return ValidatedPredictionRows(
        rows=validated,
        run_ids=tuple(sorted({row["run_id"] for row in validated})),
        method_ids=tuple(sorted({row["method_id"] for row in validated})),
        source_ids=tuple(sorted({row["source_id"] for row in validated})),
        condition_ids=tuple(condition for condition in CONDITION_IDS if condition in {row["condition_id"] for row in validated}),
    )


def load_prediction_rows(path: str | Path, *, require_full_grid: bool = True) -> ValidatedPredictionRows:
    """Load JSONL, rejecting malformed lines and non-prediction records."""
    path = Path(path)
    rows: list[dict[str, Any]] = []
    with path.open() as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON on line {line_number}: {exc.msg}") from exc
    return validate_prediction_rows(rows, require_full_grid=require_full_grid)


def load_frozen_threshold(path: str | Path) -> FrozenThreshold:
    """Read a fully-provenanced threshold artifact without importing fit code."""
    path = Path(path)
    raw = path.read_bytes()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid threshold artifact JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ValueError("threshold artifact must be a JSON object")
    missing = _THRESHOLD_FIELDS - set(payload)
    if missing:
        raise ValueError(f"threshold artifact missing required fields {sorted(missing)}")
    if payload["schema_version"] != THRESHOLD_ARTIFACT_SCHEMA:
        raise ValueError(f"unexpected threshold schema {payload['schema_version']!r}")
    threshold = _finite_probability(payload["threshold"], "threshold")
    for field in ("objective", "pipeline_version", "fitting_code_version", "created_at", "tie_break"):
        _nonempty_string(payload[field], field)
    for field in ("dev_manifest_sha256", "config_sha256"):
        if not isinstance(payload[field], str) or not _SHA256.fullmatch(payload[field]):
            raise ValueError(f"{field} must be a non-empty SHA-256 hex digest")
    if payload["selection_granularity"] not in {"family", "exact_condition"}:
        raise ValueError("selection_granularity must be family or exact_condition")
    if not isinstance(payload["feasible"], bool):
        raise ValueError("feasible must be boolean")
    if not isinstance(payload["bootstrap"], dict):
        raise ValueError("bootstrap must be an object")
    if not isinstance(payload["warnings"], list) or not all(
        isinstance(item, str) for item in payload["warnings"]
    ):
        raise ValueError("threshold warnings must be a list of strings")
    return FrozenThreshold(
        value=threshold,
        artifact_sha256=hashlib.sha256(raw).hexdigest(),
        payload=payload,
    )
