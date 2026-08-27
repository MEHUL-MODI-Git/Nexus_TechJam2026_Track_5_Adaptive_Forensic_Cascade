"""Results assembly: prediction rows -> eval-results.v1 / diagnostic-results.v1.

Rewritten after Codex's review (R1-R4, R13). The previous version pooled every
`method_id` into a single fictitious method: a perfect detector and an inverted
one averaged to balanced accuracy 0.5. The single-method smoke artifact happened
to be correct, which is exactly why the bug would have survived to the first
real ablation and silently corrupted it.

Three structural rules now hold:

1. **Everything is per-method.** Rows are keyed by `(method_id, condition_id)`,
   each method gets its own conditions/families/headline, and cross-method
   comparison happens only through explicit paired deltas computed on identical
   bootstrap resamples.
2. **A headline requires a real threshold artifact.** The API takes a
   `FrozenThreshold` object, not a string. No string can talk its way into
   `eval-results.v1`; a placeholder is a different type with a different name.
3. **A headline requires complete coverage.** Every method must have every one
   of the 20 official conditions and all six transform families, over the same
   source set. Partial grids are diagnostic-only, because a missing condition is
   usually the hardest one.
"""

# Protocol validation consistently reports malformed artifacts as ValueError.
# ruff: noqa: TRY004

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from src.pipeline.transforms import CONDITION_IDS, FAMILY_OF
from src.pipeline.version import GOLDEN_VERSION, PIPELINE_VERSION

from .metrics import (
    condition_metrics,
    paired_flip_metrics,
    signed_drop,
    worst_condition,
)
from .protocol import FrozenThreshold, ValidatedPredictionRows

EVAL_SCHEMA = "eval-results.v1"
DIAGNOSTIC_SCHEMA = "diagnostic-results.v1"
PLACEHOLDER_PREFIX = "PLACEHOLDER"

DEFAULT_BOOTSTRAP_REPLICATES = 1000
DEFAULT_SEED = 20260826
DEFAULT_ECE_BINS = 15

TRANSFORM_FAMILIES = ("jpeg", "blur", "resize", "noise", "color", "crop")
# Metrics that receive a source-level bootstrap interval (Codex R14).
CI_METRICS = ("fake_recall", "balanced_accuracy", "false_positive_rate", "auroc")


@dataclass(frozen=True)
class PlaceholderThreshold:
    """An explicitly unfitted operating point. Structurally cannot be a headline."""

    value: float
    provenance: str

    def __post_init__(self) -> None:
        if not self.provenance.startswith(PLACEHOLDER_PREFIX):
            raise ValueError(
                f"PlaceholderThreshold provenance must start with {PLACEHOLDER_PREFIX!r}; "
                f"got {self.provenance!r}. A fitted threshold belongs in FrozenThreshold."
            )


class CoverageError(Exception):
    """Headline evaluation attempted on an incomplete grid."""


_MANIFEST_SCHEMA = "eval-run-manifest.v1"
_FREEZE_SCHEMA = "production-freeze.v1"
_MANIFEST_FIELDS = {
    "schema_version", "run_id", "created_at", "command", "code_revision", "seed",
    "dataset", "protocol", "methods", "coverage", "failure_ledger", "production_freeze",
}
_ROOT = Path(__file__).resolve().parents[2]
_HEX64 = __import__("re").compile(r"^[0-9a-f]{64}$")
_HEX40 = __import__("re").compile(r"^[0-9a-f]{40}$")


def _manifest_digest(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _HEX64.fullmatch(value):
        raise ValueError(f"{field} must be a 64-character lowercase SHA-256 digest")
    return value


def _manifest_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _repo_path(value: Any, field: str) -> Path:
    path = _manifest_string(value, field)
    candidate = Path(path)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"{field} must be repository-relative")
    resolved = (_ROOT / candidate).resolve()
    if resolved != _ROOT and _ROOT not in resolved.parents:
        raise ValueError(f"{field} escapes the repository")
    if not resolved.is_file():
        raise ValueError(f"{field} does not name an existing repository file: {path!r}")
    return resolved


def _verify_manifest_file(path_value: Any, digest_value: Any, field: str) -> str:
    path = _repo_path(path_value, field + ".path")
    digest = _manifest_digest(digest_value, field + ".sha256")
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != digest:
        raise ValueError(f"{field} digest does not match {path_value!r}")
    return digest


def _validate_run_manifest(
    manifest: dict[str, Any] | None,
    *, diagnostic: bool,
    validated: ValidatedPredictionRows,
    method_ids: list[str],
    threshold: FrozenThreshold | PlaceholderThreshold,
    build_seed: int,
) -> tuple[dict[str, Any], list[str]]:
    """Validate provenance and denominator claims, strictly for headlines."""
    if not isinstance(manifest, dict) or manifest.get("schema_version") != _MANIFEST_SCHEMA:
        if diagnostic:
            return manifest or {}, ["missing or legacy eval-run-manifest.v1; diagnostic only"]
        raise ValueError("reportable eval-results.v1 requires eval-run-manifest.v1")
    missing = _MANIFEST_FIELDS - set(manifest)
    extra = set(manifest) - _MANIFEST_FIELDS
    if missing:
        raise ValueError(f"run manifest missing required fields {sorted(missing)}")
    if extra:
        raise ValueError(f"run manifest has unexpected fields {sorted(extra)}")
    for field in ("run_id", "created_at", "command"):
        _manifest_string(manifest[field], field)
    if validated.run_ids != (manifest["run_id"],):
        raise ValueError("manifest run_id must equal the sole prediction run_id")
    if not isinstance(manifest["code_revision"], str) or not _HEX40.fullmatch(manifest["code_revision"]):
        raise ValueError("code_revision must be 40 lowercase hex characters")
    if isinstance(manifest["seed"], bool) or not isinstance(manifest["seed"], int):
        raise ValueError("manifest seed must be an integer")
    if manifest["seed"] != build_seed:
        raise ValueError("manifest seed does not equal evaluation seed")
    dataset = manifest["dataset"]
    if not isinstance(dataset, dict):
        raise ValueError("manifest dataset must be an object")
    for field in ("name", "split", "manifest_path"):
        _manifest_string(dataset.get(field), "dataset." + field)
    dataset_digest = _verify_manifest_file(
        dataset["manifest_path"], dataset.get("manifest_sha256"), "dataset.manifest"
    )
    if not isinstance(dataset.get("sealed_reference"), bool):
        raise ValueError("dataset.sealed_reference must be boolean")
    dataset_path = _ROOT / dataset["manifest_path"]
    try:
        dataset_data = json.loads(dataset_path.read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("dataset manifest must be valid JSON") from exc
    images = dataset_data.get("images") if isinstance(dataset_data, dict) else None
    if not isinstance(images, list):
        raise ValueError("dataset manifest must contain an images list")
    manifest_rows: dict[str, tuple[Any, ...]] = {}
    for image in images:
        if not isinstance(image, dict):
            raise ValueError("dataset manifest images must be objects")
        source_id = image.get("source_id")
        if not isinstance(source_id, str) or not source_id:
            raise ValueError("dataset manifest image source_id must be non-empty")
        identity = (image.get("label"), image.get("dataset"), image.get("source_group"),
                    image.get("relative_path", image.get("image_path")))
        if source_id in manifest_rows:
            raise ValueError(f"dataset manifest has duplicate source_id {source_id!r}")
        manifest_rows[source_id] = identity
    observed_rows: dict[str, tuple[Any, ...]] = {}
    for row in validated.rows:
        identity = (row["label"], row["dataset"], row["source_group"], row["image_path"])
        prior = observed_rows.setdefault(row["source_id"], identity)
        if prior != identity:
            raise ValueError(f"prediction source {row['source_id']!r} has inconsistent identity")
    if set(manifest_rows) != set(observed_rows):
        raise ValueError("dataset manifest source IDs do not equal prediction rows")
    for source_id, identity in observed_rows.items():
        if manifest_rows[source_id] != identity:
            raise ValueError(f"dataset manifest identity mismatch for source {source_id!r}")

    protocol = manifest["protocol"]
    if not isinstance(protocol, dict):
        raise ValueError("manifest protocol must be an object")
    if protocol.get("pipeline_version") != PIPELINE_VERSION:
        raise ValueError("manifest pipeline_version does not match live pipeline")
    if protocol.get("golden_version") != GOLDEN_VERSION:
        raise ValueError("manifest golden_version does not match live golden")
    transform_digest = _verify_manifest_file(
        protocol.get("transform_manifest_path"), protocol.get("transform_manifest_sha256"),
        "protocol.transform_manifest",
    )
    golden_digest = _verify_manifest_file(
        protocol.get("golden_manifest_path"), protocol.get("golden_manifest_sha256"),
        "protocol.golden_manifest",
    )
    # The canonical files must also report the live versions.  The repository
    # currently stores YAML transforms and JSON golden metadata.
    transform_path = _ROOT / protocol["transform_manifest_path"]
    if transform_path.suffix in {".yaml", ".yml"}:
        import yaml
        transform_data = yaml.safe_load(transform_path.read_text())
        if transform_data.get("pipeline_version") != PIPELINE_VERSION:
            raise ValueError("transform manifest version does not match live pipeline")
    golden_data = json.loads((_ROOT / protocol["golden_manifest_path"]).read_bytes())
    if golden_data.get("golden_version") != GOLDEN_VERSION:
        raise ValueError("golden manifest version does not match live golden")

    methods = manifest["methods"]
    if not isinstance(methods, list) or not methods:
        raise ValueError("manifest methods must be a non-empty list")
    provenance_ids: list[str] = []
    for index, item in enumerate(methods):
        if not isinstance(item, dict):
            raise ValueError(f"methods[{index}] must be an object")
        method_id = _manifest_string(item.get("method_id"), f"methods[{index}].method_id")
        provenance_ids.append(method_id)
        versions = item.get("checkpoint_versions")
        preprocess = item.get("preprocessing_versions")
        if (not isinstance(versions, list) or not versions or
                not all(isinstance(v, str) and v for v in versions)):
            raise ValueError(f"methods[{index}].checkpoint_versions is incomplete")
        if (not isinstance(preprocess, list) or not preprocess or
                not all(isinstance(v, str) and v for v in preprocess)):
            raise ValueError(f"methods[{index}].preprocessing_versions is incomplete")
        count = item.get("parameter_count")
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError(f"methods[{index}].parameter_count must be a non-negative integer")
        _manifest_digest(item.get("config_sha256"), f"methods[{index}].config_sha256")
    if len(set(provenance_ids)) != len(provenance_ids):
        raise ValueError("manifest method IDs must be unique")
    if sorted(provenance_ids) != method_ids:
        raise ValueError("manifest method IDs do not equal prediction rows")

    coverage = manifest["coverage"]
    if not isinstance(coverage, dict):
        raise ValueError("manifest coverage must be an object")
    observed_sources = len(set(validated.source_ids))
    expected = observed_sources * len(method_ids) * len(CONDITION_IDS)
    for field in ("expected_source_count", "expected_view_count", "successful_view_count", "failure_count"):
        count = coverage.get(field)
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError(f"coverage.{field} must be a non-negative integer")
    if diagnostic and (
        coverage.get("expected_source_count") != observed_sources or
        coverage.get("expected_view_count") != expected or
        coverage.get("successful_view_count") != len(validated.rows)
    ):
        return manifest, ["diagnostic manifest coverage does not match observed rows"]
    if coverage.get("expected_source_count") != observed_sources:
        raise ValueError("coverage.expected_source_count does not equal observed sources")
    if coverage.get("expected_view_count") != expected:
        raise ValueError("coverage.expected_view_count is inconsistent")
    if coverage.get("successful_view_count") != len(validated.rows):
        raise ValueError("coverage.successful_view_count does not equal observed rows")
    failure_count = coverage.get("failure_count")
    ledger = manifest["failure_ledger"]
    if not isinstance(ledger, dict):
        raise ValueError("failure_ledger must be an object")
    ledger_digest = _verify_manifest_file(ledger.get("path"), ledger.get("sha256"), "failure_ledger")
    ledger_path = _ROOT / ledger["path"]
    try:
        ledger_data = json.loads(ledger_path.read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("failure ledger must be valid JSON") from exc
    if not isinstance(ledger_data, dict) or ledger_data.get("schema_version") != "eval-failure-ledger.v1":
        raise ValueError("failure ledger schema must be eval-failure-ledger.v1")
    failures = ledger_data.get("failures")
    ledger_declared_count = ledger_data.get("count")
    if (not isinstance(failures, list) or isinstance(ledger_declared_count, bool) or
            not isinstance(ledger_declared_count, int) or ledger_declared_count != len(failures)):
        raise ValueError("failure ledger count must equal its failures list length")
    if ledger.get("count") != ledger_declared_count or ledger.get("count") != failure_count:
        raise ValueError("failure ledger count does not match coverage.failure_count")
    if coverage["successful_view_count"] + failure_count != expected:
        if diagnostic:
            return manifest, ["diagnostic manifest denominator does not match canonical grid"]
        raise ValueError("coverage denominator is inconsistent")
    if not diagnostic and failure_count != 0:
        raise CoverageError("reportable output refuses a non-zero failure denominator")

    freeze = manifest["production_freeze"]
    if not isinstance(freeze, dict) or freeze.get("schema_version") != _FREEZE_SCHEMA:
        raise ValueError("missing or mismatched production-freeze.v1")
    freeze_digest = _manifest_digest(freeze.get("manifest_sha256"), "production_freeze.manifest_sha256")
    freeze_without_digest = {
        key: value for key, value in freeze.items() if key != "manifest_sha256"
    }
    expected_freeze_digest = hashlib.sha256(
        json.dumps(freeze_without_digest, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if freeze_digest != expected_freeze_digest:
        raise ValueError("production freeze manifest_sha256 does not bind freeze payload")
    checks = {
        "code_revision": manifest["code_revision"],
        "pipeline_version": PIPELINE_VERSION,
        "golden_version": GOLDEN_VERSION,
        "transform_manifest_sha256": transform_digest,
        "method_ids": method_ids,
    }
    if not diagnostic:
        checks["threshold_artifact_sha256"] = threshold.artifact_sha256
    for field, expected_value in checks.items():
        if freeze.get(field) != expected_value:
            raise ValueError(f"production freeze {field} does not match run")
    if freeze.get("architecture_frozen") is not True:
        raise ValueError("production freeze architecture_frozen must be true")
    if not isinstance(freeze.get("sealed_evaluation_authorized"), bool):
        raise ValueError("production freeze sealed_evaluation_authorized must be boolean")
    if dataset["sealed_reference"] and freeze.get("sealed_evaluation_authorized") is not True:
        raise ValueError("sealed evaluation is not authorized by production freeze")

    provenance = dict(manifest)
    provenance["_dataset_manifest_sha256"] = dataset_digest
    provenance["_failure_ledger_sha256"] = ledger_digest
    provenance["_transform_manifest_sha256"] = transform_digest
    provenance["_golden_manifest_sha256"] = golden_digest
    return provenance, []


def _validate_metric_controls(bootstrap_replicates: Any, seed: Any, ece_bins: Any) -> None:
    if (isinstance(bootstrap_replicates, bool) or
            not isinstance(bootstrap_replicates, int) or bootstrap_replicates <= 0):
        raise ValueError("bootstrap_replicates must be a positive integer")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("seed must be an integer")
    if isinstance(ece_bins, bool) or not isinstance(ece_bins, int) or ece_bins <= 0:
        raise ValueError("ece_bins must be a positive integer")


def _validate_placeholder(source: PlaceholderThreshold) -> None:
    if isinstance(source.value, bool) or not isinstance(source.value, (int, float)):
        raise ValueError("PlaceholderThreshold.value must be numeric")
    if not np.isfinite(float(source.value)) or not 0.0 <= float(source.value) <= 1.0:
        raise ValueError("PlaceholderThreshold.value must be finite and lie in [0,1]")


def _validate_loaded_threshold(source: FrozenThreshold) -> None:
    if not source._is_loader_capability() or not isinstance(source.payload, dict):
        raise TypeError("FrozenThreshold must be created by load_frozen_threshold")
    if not isinstance(source.raw_bytes, bytes):
        raise TypeError("FrozenThreshold is missing its exact loaded bytes")
    digest = hashlib.sha256(source.raw_bytes).hexdigest()
    if source.artifact_sha256 != digest or not _HEX64.fullmatch(source.artifact_sha256):
        raise ValueError("FrozenThreshold artifact digest does not match loaded bytes")
    try:
        reparsed = json.loads(source.raw_bytes)
    except json.JSONDecodeError as exc:
        raise ValueError("FrozenThreshold loaded bytes are not valid JSON") from exc
    if reparsed != source.payload:
        raise ValueError("FrozenThreshold payload differs from its exact loaded bytes")
    if source.payload.get("threshold") != source.value:
        raise ValueError("FrozenThreshold value differs from its validated payload")


def _key_rows(rows: tuple[dict[str, Any], ...]) -> dict[tuple[str, str], dict]:
    """Group by (method_id, condition_id) — never by condition alone (R1)."""
    grouped: dict[tuple[str, str], dict] = defaultdict(
        lambda: {"labels": [], "scores": [], "source_ids": []}
    )
    for row in sorted(rows, key=lambda r: (r["method_id"], r["condition_id"], r["source_id"])):
        bucket = grouped[(row["method_id"], row["condition_id"])]
        bucket["labels"].append(int(row["label"]))
        bucket["scores"].append(float(row["p_fake"]))
        bucket["source_ids"].append(row["source_id"])
    return grouped


def _as_arrays(bucket: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    return (np.array(bucket["labels"]), np.array(bucket["scores"]),
            np.array(bucket["source_ids"], dtype=object))


def validate_headline_coverage(
    grouped: dict[tuple[str, str], dict], family_of: Mapping[str, str] | None = None,
    official_conditions: Sequence[str] | None = None,
) -> None:
    """Exact method x condition x source coverage, or refuse to emit a headline."""
    if family_of is not None and dict(family_of) != FAMILY_OF:
        raise CoverageError("caller-controlled family registry is not the official canonical registry")
    if official_conditions is not None and tuple(official_conditions) != tuple(CONDITION_IDS):
        raise CoverageError("caller-controlled condition grid is not the official canonical grid")
    family_of = FAMILY_OF
    official_conditions = tuple(CONDITION_IDS)
    methods = sorted({m for m, _ in grouped})
    if not methods:
        raise CoverageError("no methods were supplied")
    for method in methods:
        method_buckets = {c: b for (m, c), b in grouped.items() if m == method}
        all_sources = {s for b in method_buckets.values() for s in b["source_ids"]}
        for condition in official_conditions:
            bucket = method_buckets.get(condition)
            if bucket is None:
                raise CoverageError(
                    f"method {method!r}, source {min(all_sources) if all_sources else '<all>'!r}, "
                    f"condition {condition!r} coverage is missing conditions"
                )
            sources = set(bucket["source_ids"])
            # Check the exact method/source/condition Cartesian product.  This
            # catches a sparse view even when the condition exists elsewhere.
            missing_sources = sorted(all_sources - sources)
            if missing_sources:
                raise CoverageError(
                    f"method {method!r}, source {missing_sources[0]!r}, condition {condition!r} "
                    "coverage is missing conditions"
                )
        families = {family_of[c] for c in official_conditions} - {"clean"}
        if families != set(TRANSFORM_FAMILIES):
            raise CoverageError("official canonical grid does not cover all transform families")
        # Every source has exactly the official set, including no duplicate
        # (duplicates are rejected by row validation).
        source_sets = {
            source: {c for c, bucket in method_buckets.items() if source in bucket["source_ids"]}
            for source in {s for b in method_buckets.values() for s in b["source_ids"]}
        }
        for source, conditions in source_sets.items():
            if conditions != set(official_conditions):
                missing = sorted(set(official_conditions) - conditions)
                raise CoverageError(
                    f"method {method!r}, source {source!r}, condition {missing[0] if missing else '<unknown>'!r} "
                    "coverage is missing conditions"
                )
    # Every method must be scored on the same sources, or deltas are not paired.
    per_method_sources = {
        m: {s for (mm, _), b in grouped.items() if mm == m for s in b["source_ids"]}
        for m in methods
    }
    reference = per_method_sources[methods[0]]
    for method, sources in per_method_sources.items():
        if sources != reference:
            raise CoverageError(
                f"method {method!r} covers a different source set than {methods[0]!r}; "
                "paired comparison requires identical sources."
            )


def _bootstrap_indices(source_ids: np.ndarray, labels: np.ndarray,
                       n_replicates: int, seed: int) -> list[np.ndarray]:
    """Label-stratified source resamples, reusable across methods (R14).

    Returning the index sets rather than the metric lets every method and every
    paired delta be computed on IDENTICAL resamples, which is what makes a
    delta's interval meaningful.
    """
    _validate_metric_controls(n_replicates, seed, 1)
    rng = np.random.default_rng(seed)
    source_label: dict[Any, int] = {}
    rows_by_source: dict[Any, list[int]] = defaultdict(list)
    for i, (sid, label) in enumerate(zip(source_ids.tolist(), labels.tolist())):
        prior = source_label.setdefault(sid, label)
        if prior != label:
            raise ValueError(f"source {sid!r} has inconsistent labels")
        rows_by_source[sid].append(i)
    real = np.array([s for s, y in source_label.items() if y == 0], dtype=object)
    fake = np.array([s for s, y in source_label.items() if y == 1], dtype=object)
    if real.size == 0 or fake.size == 0:
        raise ValueError("label-stratified bootstrap requires both classes")
    out = []
    for _ in range(n_replicates):
        picked = np.concatenate([
            rng.choice(real, size=real.size, replace=True),
            rng.choice(fake, size=fake.size, replace=True),
        ])
        out.append(np.concatenate([rows_by_source[s] for s in picked.tolist()]))
    return out


def _ci_block(labels: np.ndarray, scores: np.ndarray, source_ids: np.ndarray,
              threshold: float, n_replicates: int, seed: int) -> dict[str, Any]:
    """Source-level bootstrap CI for every reported metric (R14)."""
    indices = _bootstrap_indices(source_ids, labels, n_replicates, seed)
    samples: dict[str, list[float]] = {m: [] for m in CI_METRICS}
    for idx in indices:
        metrics = condition_metrics(labels[idx], scores[idx], threshold)
        for name in CI_METRICS:
            samples[name].append(float(metrics[name]))
    block = {name: {
        "mean": float(np.mean(v)),
        "ci95_low": float(np.percentile(v, 2.5)),
        "ci95_high": float(np.percentile(v, 97.5)),
    } for name, v in samples.items()}
    block["bootstrap"] = {"n_replicates": n_replicates, "seed": seed,
                          "unit": "source_id", "stratified_by": "label",
                          "interval": "percentile_95"}
    return block


def _method_document(
    method_id: str, grouped: dict[tuple[str, str], dict], family_of: dict[str, str],
    threshold: float, n_replicates: int, seed: int, ece_bins: int,
    *, diagnostic: bool = False,
    provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    family_of = family_of or FAMILY_OF
    conditions_present = [c for c in CONDITION_IDS if (method_id, c) in grouped]
    clean_bucket = grouped.get((method_id, "clean"))
    if clean_bucket is None:
        raise ValueError(f"method {method_id!r} has no clean rows")
    clean_labels, clean_scores, _ = _as_arrays(clean_bucket)
    clean_metrics = condition_metrics(clean_labels, clean_scores, threshold, ece_bins=ece_bins)
    clean_by_source = dict(zip(clean_bucket["source_ids"], clean_bucket["scores"]))

    conditions: list[dict[str, Any]] = []
    family_pool: dict[str, dict] = defaultdict(
        lambda: {"labels": [], "scores": [], "source_ids": []}
    )
    recall_by_condition: dict[str, float] = {}

    for condition_id in conditions_present:
        bucket = grouped[(method_id, condition_id)]
        labels, scores, sources = _as_arrays(bucket)
        metrics = condition_metrics(labels, scores, threshold, ece_bins=ece_bins)
        family = family_of.get(condition_id, "unknown")
        if family in TRANSFORM_FAMILIES:
            pool = family_pool[family]
            pool["labels"].extend(bucket["labels"])
            pool["scores"].extend(bucket["scores"])
            pool["source_ids"].extend(bucket["source_ids"])
        entry: dict[str, Any] = {
            "condition_id": condition_id, "family": family,
            "counts": metrics["counts"],
            "metrics": {k: v for k, v in metrics.items() if k != "counts"},
            "drops": {n: signed_drop(float(clean_metrics[n]), float(metrics[n]))
                      for n in ("fake_recall", "balanced_accuracy", "auroc")},
            "ci95": _ci_block(labels, scores, sources, threshold, n_replicates, seed),
        }
        if condition_id != "clean":
            paired = [(clean_by_source[s], p, y)
                      for s, p, y in zip(bucket["source_ids"], bucket["scores"], bucket["labels"])
                      if s in clean_by_source]
            if len(paired) != len(bucket["source_ids"]):
                raise ValueError(
                    f"{method_id}/{condition_id}: some sources have no clean row; "
                    "paired flips are undefined"
                )
            entry["flips"] = paired_flip_metrics(
                np.array([y for _, _, y in paired]),
                np.array([c for c, _, _ in paired]),
                np.array([t for _, t, _ in paired]), threshold,
            )
        conditions.append(entry)
        if condition_id != "clean":
            recall_by_condition[condition_id] = float(metrics["fake_recall"])

    families: list[dict[str, Any]] = []
    recall_by_family: dict[str, float] = {}
    for family in TRANSFORM_FAMILIES:
        if family not in family_pool:
            continue
        pool = family_pool[family]
        labels, scores, sources = _as_arrays(pool)
        metrics = condition_metrics(labels, scores, threshold, ece_bins=ece_bins)
        families.append({
            "family": family,
            "n_conditions": sum(1 for c in conditions if c["family"] == family),
            "counts": metrics["counts"],
            "metrics": {k: v for k, v in metrics.items() if k != "counts"},
            "ci95": _ci_block(labels, scores, sources, threshold, n_replicates, seed),
        })
        recall_by_family[family] = float(metrics["fake_recall"])

    worst_fam_id, worst_fam_value = (worst_condition(recall_by_family)
                                     if recall_by_family else ("", float("nan")))
    worst_cond_id, worst_cond_value = (worst_condition(recall_by_condition)
                                       if recall_by_condition else ("", float("nan")))
    max_directional = {"real_to_fake_flip": 0.0, "fake_to_real_flip": 0.0,
                       "real_to_fake_condition": None, "fake_to_real_condition": None}
    for entry in conditions:
        flips = entry.get("flips")
        if not flips:
            continue
        for direction in ("real_to_fake_flip", "fake_to_real_flip"):
            if flips[direction] > max_directional[direction]:
                max_directional[direction] = flips[direction]
                max_directional[direction.replace("_flip", "_condition")] = entry["condition_id"]

    # A zero rate is still a measured result.  Name its deterministic first
    # canonical condition rather than emitting a misleading null condition.
    for direction in ("real_to_fake_flip", "fake_to_real_flip"):
        condition_key = direction.replace("_flip", "_condition")
        if max_directional[condition_key] is None:
            for entry in conditions:
                if entry["condition_id"] != "clean" and entry.get("flips", {}).get(direction) == 0.0:
                    max_directional[condition_key] = entry["condition_id"]
                    break

    summary = {
        "clean": {"counts": clean_metrics["counts"],
                   **{k: v for k, v in clean_metrics.items() if k != "counts"}},
        "worst_family": {"family": worst_fam_id, "fake_recall": worst_fam_value},
        "worst_exact_condition": {"condition_id": worst_cond_id,
                                   "fake_recall": worst_cond_value},
        "max_directional_flip": max_directional,
        "selective": None,
        "rescue": None,
    }
    method_document = {
        "method_id": method_id,
        "conditions": conditions,
        "families": families,
        "diagnostic_summary" if diagnostic else "headline": summary,
    }
    if provenance is not None:
        method_document["provenance"] = {
            key: provenance[key] for key in (
                "checkpoint_versions", "preprocessing_versions", "parameter_count", "config_sha256"
            ) if key in provenance
        }
    return method_document


def _paired_deltas(method_ids: list[str], grouped: dict[tuple[str, str], dict],
                   family_of: dict[str, str], threshold: float,
                   n_replicates: int, seed: int,
                   *, diagnostic: bool = False, warnings: list[str] | None = None) -> list[dict[str, Any]]:
    """Between-method deltas aligned by sorted canonical keys (E5)."""
    family_of = family_of or FAMILY_OF
    deltas: list[dict[str, Any]] = []
    for i, a in enumerate(method_ids):
        for b in method_ids[i + 1:]:
            per_method: dict[str, dict[tuple[str, str], tuple[int, float]]] = {}
            for method in (a, b):
                mapping: dict[tuple[str, str], tuple[int, float]] = {}
                for condition in CONDITION_IDS:
                    bucket = grouped.get((method, condition), {})
                    for source, label, score in zip(bucket.get("source_ids", []),
                                                    bucket.get("labels", []),
                                                    bucket.get("scores", [])):
                        mapping[(source, condition)] = (int(label), float(score))
                per_method[method] = mapping
            all_keys_a, all_keys_b = set(per_method[a]), set(per_method[b])
            keys_a = {key for key in all_keys_a if key[1] != "clean"}
            keys_b = {key for key in all_keys_b if key[1] != "clean"}
            if all_keys_a != all_keys_b:
                message = f"cannot pair {a!r} and {b!r}: canonical key sets differ"
                if diagnostic:
                    if warnings is not None:
                        warnings.append(message)
                    continue
                raise CoverageError(message)
            if keys_a != keys_b:
                message = f"cannot pair {a!r} and {b!r}: canonical key sets differ"
                if diagnostic:
                    if warnings is not None:
                        warnings.append(message)
                    continue
                raise CoverageError(message)
            keys = sorted(keys_a)
            all_keys = sorted(all_keys_a)
            if any(per_method[a][key][0] != per_method[b][key][0] for key in all_keys):
                message = f"cannot pair {a!r} and {b!r}: canonical key labels differ"
                if diagnostic:
                    if warnings is not None:
                        warnings.append(message)
                    continue
                raise CoverageError(message)
            labels_a = np.array([per_method[a][key][0] for key in keys])
            labels_b = np.array([per_method[b][key][0] for key in keys])
            if not np.array_equal(labels_a, labels_b):
                message = f"cannot pair {a!r} and {b!r}: canonical key labels differ"
                if diagnostic:
                    if warnings is not None:
                        warnings.append(message)
                    continue
                raise CoverageError(message)
            labels = labels_a
            sources = np.array([key[0] for key in keys], dtype=object)
            indices = _bootstrap_indices(sources, labels, n_replicates, seed)
            samples = []
            scores_a = np.array([per_method[a][key][1] for key in keys])
            scores_b = np.array([per_method[b][key][1] for key in keys])
            for idx in indices:
                ra = condition_metrics(labels[idx], scores_a[idx], threshold)
                rb = condition_metrics(labels[idx], scores_b[idx], threshold)
                samples.append(float(rb["fake_recall"]) - float(ra["fake_recall"]))
            deltas.append({
                "metric": "fake_recall_transformed_pooled",
                "method_a": a, "method_b": b,
                "delta_mean": float(np.mean(samples)),
                "ci95_low": float(np.percentile(samples, 2.5)),
                "ci95_high": float(np.percentile(samples, 97.5)),
                "bootstrap": {"n_replicates": n_replicates, "seed": seed,
                              "unit": "source_id", "stratified_by": "label",
                              "interval": "percentile_95", "shared_indices": True},
            })
    return deltas


def build_results(
    validated: ValidatedPredictionRows,
    threshold_source: FrozenThreshold | PlaceholderThreshold,
    *,
    family_of: Mapping[str, str] | None = None,
    official_conditions: Sequence[str] | None = None,
    run_manifest: dict[str, Any] | None = None,
    rows_path: Path | None = None,
    bootstrap_replicates: int = DEFAULT_BOOTSTRAP_REPLICATES,
    seed: int = DEFAULT_SEED,
    ece_bins: int = DEFAULT_ECE_BINS,
    require_full_grid: bool = True,
) -> dict[str, Any]:
    """Assemble a results document. The THRESHOLD TYPE selects the path (R2)."""
    diagnostic = isinstance(threshold_source, PlaceholderThreshold)
    if diagnostic:
        _validate_placeholder(threshold_source)
    if not diagnostic and not isinstance(threshold_source, FrozenThreshold):
        raise TypeError(
            "eval-results.v1 requires a FrozenThreshold loaded from a threshold "
            f"artifact; got {type(threshold_source).__name__}. A provenance string "
            "cannot authorise a headline."
        )
    if not diagnostic:
        _validate_loaded_threshold(threshold_source)
    _validate_metric_controls(bootstrap_replicates, seed, ece_bins)
    threshold = float(threshold_source.value)
    provenance = (threshold_source.provenance if diagnostic
                  else threshold_source.payload.get("threshold_provenance", "held-out-dev"))

    grouped = _key_rows(validated.rows)
    method_ids = sorted({m for m, _ in grouped})

    if family_of is not None and dict(family_of) != FAMILY_OF:
        raise CoverageError("caller-controlled family registry is not the official canonical registry")
    if official_conditions is not None and tuple(official_conditions) != tuple(CONDITION_IDS):
        raise CoverageError("caller-controlled condition grid is not the official canonical grid")

    if not diagnostic:
        if not require_full_grid:
            raise CoverageError(
                "eval-results.v1 cannot be produced from a partial grid; "
                "use the diagnostic path (R3)."
            )
        validate_headline_coverage(grouped)

    warnings: list[str] = []
    manifest, manifest_warnings = _validate_run_manifest(
        run_manifest, diagnostic=diagnostic, validated=validated,
        method_ids=method_ids, threshold=threshold_source, build_seed=seed,
    )
    warnings.extend(manifest_warnings)
    manifest_method_provenance = {
        item["method_id"]: item for item in manifest.get("methods", [])
        if isinstance(item, dict) and isinstance(item.get("method_id"), str)
    }
    methods = [_method_document(
        m, grouped, family_of, threshold, bootstrap_replicates, seed, ece_bins,
        diagnostic=diagnostic, provenance=manifest_method_provenance.get(m),
    ) for m in method_ids]
    deltas = (_paired_deltas(method_ids, grouped, family_of, threshold,
                             bootstrap_replicates, seed, diagnostic=diagnostic,
                             warnings=warnings)
              if len(method_ids) > 1 else [])

    artifacts: dict[str, Any] = {}
    if rows_path and Path(rows_path).exists():
        artifacts["prediction_rows"] = {
            "path": str(rows_path),
            "sha256": hashlib.sha256(Path(rows_path).read_bytes()).hexdigest(),
        }
    # Dataset composition is counted in independent SOURCE units, never in the
    # 20 correlated transform views per source (or once again per method).
    source_identity = {
        row["source_id"]: (int(row["label"]), row["source_group"])
        for row in validated.rows
    }
    class_counts = Counter(str(label) for label, _ in source_identity.values())
    group_counts = Counter(group for _, group in source_identity.values())

    document: dict[str, Any] = {
        "schema_version": DIAGNOSTIC_SCHEMA if diagnostic else EVAL_SCHEMA,
        "run": {
            "run_id": manifest.get("run_id"),
            "created_at": manifest.get("created_at", datetime.now(UTC).isoformat()),
            "seed": seed,
            "command": manifest.get("command", " ".join(os.sys.argv) if hasattr(os, "sys") else None),
            "code_revision": manifest.get("code_revision"),
            "source_run_ids": list(validated.run_ids),
        },
        "protocol": {
            "threshold": threshold,
            "threshold_provenance": provenance,
            "threshold_fitted_on_held_out_dev": not diagnostic,
            "threshold_artifact_sha256": (None if diagnostic
                                          else threshold_source.artifact_sha256),
            "decision_rule": "p_fake >= threshold predicts AI-generated",
            "pipeline_version": manifest.get("protocol", {}).get("pipeline_version"),
            "golden_version": manifest.get("protocol", {}).get("golden_version"),
            "transform_manifest_path": manifest.get("protocol", {}).get("transform_manifest_path"),
            "transform_manifest_sha256": manifest.get("_transform_manifest_sha256"),
            "golden_manifest_path": manifest.get("protocol", {}).get("golden_manifest_path"),
            "golden_manifest_sha256": manifest.get("_golden_manifest_sha256"),
            "bootstrap": {"n_replicates": bootstrap_replicates, "seed": seed,
                          "unit": "source_id", "stratified_by": "label",
                          "interval": "percentile_95"},
            "ece_bins": ece_bins,
            "families": list(TRANSFORM_FAMILIES),
            "full_grid_required": not diagnostic,
            "objective_note": (
                "worst-family fake recall is the SELECTION objective (clean excluded, "
                "severities pooled); worst exact condition is reported, never selected on"
            ),
        },
        "dataset": {
            "source_count": len(set(validated.source_ids)),
            "view_count": len(validated.rows),
            "condition_count": len({c for _, c in grouped}),
            "manifest_sha256": manifest.get("dataset", {}).get("manifest_sha256"),
            "manifest_path": manifest.get("dataset", {}).get("manifest_path"),
            "name": manifest.get("dataset", {}).get("name"),
            "split": manifest.get("dataset", {}).get("split"),
            "sealed_reference": manifest.get("dataset", {}).get("sealed_reference"),
            "class_counts": dict(sorted(class_counts.items())),
            "group_counts": dict(sorted(group_counts.items())),
        },
        "methods": methods,
        "method_ids": method_ids,
        "paired_deltas": deltas,
        "artifacts": artifacts,
        "provenance": {
            "code_revision": manifest.get("code_revision"),
            "dataset": manifest.get("dataset"),
            "protocol": manifest.get("protocol"),
            "methods": manifest.get("methods"),
            "coverage": manifest.get("coverage"),
            "failure_ledger": manifest.get("failure_ledger"),
            "production_freeze": manifest.get("production_freeze"),
        },
        "warnings": warnings,
    }

    if diagnostic:
        document["NOT_A_HEADLINE_RESULT"] = (
            f"Diagnostic only. Threshold provenance is {provenance!r} — not fitted on "
            "held-out dev. These numbers may not be reported as results."
        )
    return document


def write_results(document: dict[str, Any], path: str | Path) -> Path:
    """Atomic write — a half-written results file that still parses is the worst
    possible artifact: it looks complete and is silently truncated."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(document, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return path
