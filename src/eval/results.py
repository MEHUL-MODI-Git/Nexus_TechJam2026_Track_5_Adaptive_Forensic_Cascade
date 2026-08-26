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

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from .metrics import condition_metrics, paired_flip_metrics, signed_drop, worst_condition
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


def _key_rows(rows: tuple[dict[str, Any], ...]) -> dict[tuple[str, str], dict]:
    """Group by (method_id, condition_id) — never by condition alone (R1)."""
    grouped: dict[tuple[str, str], dict] = defaultdict(
        lambda: {"labels": [], "scores": [], "source_ids": []}
    )
    for row in rows:
        bucket = grouped[(row["method_id"], row["condition_id"])]
        bucket["labels"].append(int(row["label"]))
        bucket["scores"].append(float(row["p_fake"]))
        bucket["source_ids"].append(row["source_id"])
    return grouped


def _as_arrays(bucket: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    return (np.array(bucket["labels"]), np.array(bucket["scores"]),
            np.array(bucket["source_ids"], dtype=object))


def validate_headline_coverage(
    grouped: dict[tuple[str, str], dict], family_of: dict[str, str],
    official_conditions: tuple[str, ...],
) -> None:
    """Exact method x condition x source coverage, or refuse to emit a headline."""
    methods = sorted({m for m, _ in grouped})
    for method in methods:
        present = {c for m, c in grouped if m == method}
        missing = set(official_conditions) - present
        if missing:
            raise CoverageError(
                f"method {method!r} is missing conditions {sorted(missing)}. A headline "
                "requires the complete official grid — a missing condition is usually "
                "the hardest one."
            )
        families = {family_of.get(c, "unknown") for c in present} - {"clean"}
        missing_families = set(TRANSFORM_FAMILIES) - families
        if missing_families:
            raise CoverageError(
                f"method {method!r} is missing transform families {sorted(missing_families)}; "
                "the frozen six-family objective cannot silently become fewer."
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
    rng = np.random.default_rng(seed)
    source_label: dict[Any, int] = {}
    rows_by_source: dict[Any, list[int]] = defaultdict(list)
    for i, (sid, label) in enumerate(zip(source_ids.tolist(), labels.tolist())):
        source_label.setdefault(sid, label)
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
) -> dict[str, Any]:
    conditions_present = sorted({c for m, c in grouped if m == method_id})
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

    return {
        "method_id": method_id,
        "conditions": conditions,
        "families": families,
        "headline": {
            "clean": {"counts": clean_metrics["counts"],
                      **{k: v for k, v in clean_metrics.items() if k != "counts"}},
            "worst_family": {"family": worst_fam_id, "fake_recall": worst_fam_value},
            "worst_exact_condition": {"condition_id": worst_cond_id,
                                      "fake_recall": worst_cond_value},
            "max_directional_flip": max_directional,
            "selective": None,   # no validated abstention estimator yet
            "rescue": None,      # rescue path lands in Phase 3
        },
    }


def _paired_deltas(method_ids: list[str], grouped: dict[tuple[str, str], dict],
                   family_of: dict[str, str], threshold: float,
                   n_replicates: int, seed: int) -> list[dict[str, Any]]:
    """Between-method deltas on IDENTICAL resamples (R14)."""
    deltas: list[dict[str, Any]] = []
    for i, a in enumerate(method_ids):
        for b in method_ids[i + 1:]:
            per_method: dict[str, dict[str, Any]] = {}
            for method in (a, b):
                pooled = {"labels": [], "scores": [], "source_ids": [], "families": []}
                for (m, c), bucket in grouped.items():
                    if m != method or family_of.get(c) == "clean":
                        continue
                    pooled["labels"].extend(bucket["labels"])
                    pooled["scores"].extend(bucket["scores"])
                    pooled["source_ids"].extend(bucket["source_ids"])
                    pooled["families"].extend([family_of.get(c, "unknown")] * len(bucket["labels"]))
                per_method[method] = pooled
            labels = np.array(per_method[a]["labels"])
            sources = np.array(per_method[a]["source_ids"], dtype=object)
            indices = _bootstrap_indices(sources, labels, n_replicates, seed)
            samples = []
            for idx in indices:
                ra = condition_metrics(np.array(per_method[a]["labels"])[idx],
                                       np.array(per_method[a]["scores"])[idx], threshold)
                rb = condition_metrics(np.array(per_method[b]["labels"])[idx],
                                       np.array(per_method[b]["scores"])[idx], threshold)
                samples.append(float(rb["fake_recall"]) - float(ra["fake_recall"]))
            deltas.append({
                "metric": "fake_recall_transformed_pooled",
                "method_a": a, "method_b": b,
                "delta_mean": float(np.mean(samples)),
                "ci95_low": float(np.percentile(samples, 2.5)),
                "ci95_high": float(np.percentile(samples, 97.5)),
                "bootstrap": {"n_replicates": n_replicates, "seed": seed,
                              "unit": "source_id", "shared_indices": True},
            })
    return deltas


def build_results(
    validated: ValidatedPredictionRows,
    threshold_source: FrozenThreshold | PlaceholderThreshold,
    *,
    family_of: dict[str, str],
    official_conditions: tuple[str, ...],
    run_manifest: dict[str, Any] | None = None,
    rows_path: Path | None = None,
    bootstrap_replicates: int = DEFAULT_BOOTSTRAP_REPLICATES,
    seed: int = DEFAULT_SEED,
    ece_bins: int = DEFAULT_ECE_BINS,
    require_full_grid: bool = True,
) -> dict[str, Any]:
    """Assemble a results document. The THRESHOLD TYPE selects the path (R2)."""
    diagnostic = isinstance(threshold_source, PlaceholderThreshold)
    if not diagnostic and not isinstance(threshold_source, FrozenThreshold):
        raise TypeError(
            "eval-results.v1 requires a FrozenThreshold loaded from a threshold "
            f"artifact; got {type(threshold_source).__name__}. A provenance string "
            "cannot authorise a headline."
        )
    threshold = float(threshold_source.value)
    provenance = (threshold_source.provenance if diagnostic
                  else threshold_source.payload.get("threshold_provenance", "held-out-dev"))

    grouped = _key_rows(validated.rows)
    method_ids = sorted({m for m, _ in grouped})

    if not diagnostic:
        if not require_full_grid:
            raise CoverageError(
                "eval-results.v1 cannot be produced from a partial grid; "
                "use the diagnostic path (R3)."
            )
        validate_headline_coverage(grouped, family_of, official_conditions)

    methods = [_method_document(m, grouped, family_of, threshold,
                                bootstrap_replicates, seed, ece_bins)
               for m in method_ids]
    deltas = (_paired_deltas(method_ids, grouped, family_of, threshold,
                             bootstrap_replicates, seed)
              if len(method_ids) > 1 else [])

    manifest = run_manifest or {}
    artifacts: dict[str, Any] = {}
    if rows_path and Path(rows_path).exists():
        artifacts["prediction_rows"] = {
            "path": str(rows_path),
            "sha256": hashlib.sha256(Path(rows_path).read_bytes()).hexdigest(),
        }

    document: dict[str, Any] = {
        "schema_version": DIAGNOSTIC_SCHEMA if diagnostic else EVAL_SCHEMA,
        "run": {
            "run_id": manifest.get("run_id"),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "seed": seed,
            "command": " ".join(os.sys.argv) if hasattr(os, "sys") else None,
            "source_run_ids": list(validated.run_ids),
        },
        "protocol": {
            "threshold": threshold,
            "threshold_provenance": provenance,
            "threshold_fitted_on_held_out_dev": not diagnostic,
            "threshold_artifact_sha256": (None if diagnostic
                                          else threshold_source.artifact_sha256),
            "decision_rule": "p_fake >= threshold predicts AI-generated",
            "pipeline_version": manifest.get("pipeline_version"),
            "transform_manifest_sha256": manifest.get("manifest_sha256"),
            "bootstrap": {"n_replicates": bootstrap_replicates, "seed": seed,
                          "unit": "source_id", "stratified_by": "label"},
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
            "sealed_reference": False,
            "decode_failures_reported_by_run": manifest.get("decode_failures"),
            "expert_failures_reported_by_run": manifest.get("expert_failures"),
        },
        "methods": methods,
        "method_ids": method_ids,
        "paired_deltas": deltas,
        "artifacts": artifacts,
        "warnings": [],
    }

    if manifest.get("decode_failures"):
        document["warnings"].append(
            f"the producing run reported {manifest['decode_failures']} decode failure(s); "
            "the denominator here is smaller than the source manifest (R16)"
        )
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
