"""Results assembly: prediction rows -> eval-results.v1 / diagnostic-results.v1.

[relay] Written by Claude while Codex is limit-blocked (PROTOCOL §6). It builds
on Codex's `protocol.py` (row validation) and `metrics.py` (metric math) and
deliberately does not reimplement either — Codex reviews this on return.

The two output paths are the boundary agreed in B-014/A-021, made structural
rather than conventional:

  eval-results.v1        requires a held-out-dev threshold artifact. Refuses to
                         run against a PLACEHOLDER provenance. This is the only
                         path that may populate a headline table.
  diagnostic-results.v1  requires a PLACEHOLDER provenance. Cannot be mistaken
                         for a result: it is named differently, watermarked with
                         the provenance string verbatim, and carries no headline
                         block.

Neither path can produce the other's output, so the two cannot be swapped by
accident — which was the point.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from .metrics import (
    condition_metrics,
    paired_flip_metrics,
    signed_drop,
    worst_condition,
)
from .protocol import ValidatedPredictionRows

EVAL_SCHEMA = "eval-results.v1"
DIAGNOSTIC_SCHEMA = "diagnostic-results.v1"
PLACEHOLDER_PREFIX = "PLACEHOLDER"

DEFAULT_BOOTSTRAP_REPLICATES = 1000
DEFAULT_SEED = 20260826
DEFAULT_ECE_BINS = 15

# The six transform families of the frozen objective. `clean` is not one of
# them: it enters through the constraints, never through the minimum.
TRANSFORM_FAMILIES = ("jpeg", "blur", "resize", "noise", "color", "crop")


def _index_rows(rows: tuple[dict[str, Any], ...]) -> dict[str, dict]:
    """Group rows by condition, keeping source order aligned for pairing."""
    by_condition: dict[str, dict] = defaultdict(
        lambda: {"labels": [], "scores": [], "source_ids": []}
    )
    for row in rows:
        bucket = by_condition[row["condition_id"]]
        bucket["labels"].append(int(row["label"]))
        bucket["scores"].append(float(row["p_fake"]))
        bucket["source_ids"].append(row["source_id"])
    return by_condition


def _aligned_pair(
    clean: dict, condition: dict
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Align a condition's rows to the clean rows by source_id for flip metrics."""
    clean_by_source = dict(zip(clean["source_ids"], clean["scores"]))
    labels, clean_scores, transformed = [], [], []
    for source_id, score, label in zip(
        condition["source_ids"], condition["scores"], condition["labels"]
    ):
        if source_id not in clean_by_source:
            # The protocol requires a clean row per evaluated source; a missing
            # one is a validation error upstream, not something to paper over.
            raise ValueError(f"source {source_id!r} has no clean row for pairing")
        labels.append(label)
        clean_scores.append(clean_by_source[source_id])
        transformed.append(score)
    return np.array(labels), np.array(clean_scores), np.array(transformed)


def bootstrap_condition_metric(
    labels: np.ndarray,
    scores: np.ndarray,
    source_ids: np.ndarray,
    threshold: float,
    metric: str = "fake_recall",
    n_replicates: int = DEFAULT_BOOTSTRAP_REPLICATES,
    seed: int = DEFAULT_SEED,
) -> dict[str, float]:
    """Label-stratified source bootstrap, 95% percentile interval.

    The resampling unit is the SOURCE: every view of a sampled source travels
    with it. Resampling rows independently would treat 20 transformed views of
    one image as 20 independent observations and shrink the interval by roughly
    sqrt(20) — a confidence interval that is confidently wrong.
    """
    rng = np.random.default_rng(seed)
    source_label: dict[str, int] = {}
    rows_by_source: dict[str, list[int]] = defaultdict(list)
    for i, (sid, label) in enumerate(zip(source_ids.tolist(), labels.tolist())):
        source_label.setdefault(sid, label)
        rows_by_source[sid].append(i)

    real = np.array([s for s, y in source_label.items() if y == 0])
    fake = np.array([s for s, y in source_label.items() if y == 1])
    if real.size == 0 or fake.size == 0:
        raise ValueError("label-stratified bootstrap requires both classes")

    values: list[float] = []
    for _ in range(n_replicates):
        picked = np.concatenate([
            rng.choice(real, size=real.size, replace=True),
            rng.choice(fake, size=fake.size, replace=True),
        ])
        idx = np.concatenate([rows_by_source[s] for s in picked.tolist()])
        sample = condition_metrics(labels[idx], scores[idx], threshold)
        values.append(float(sample[metric]))

    arr = np.array(values, dtype=np.float64)
    return {
        "mean": float(arr.mean()),
        "ci95_low": float(np.percentile(arr, 2.5)),
        "ci95_high": float(np.percentile(arr, 97.5)),
        "n_replicates": n_replicates,
        "seed": seed,
        "unit": "source_id",
        "stratified_by": "label",
        "interval": "percentile_95",
    }


def build_results(
    validated: ValidatedPredictionRows,
    threshold: float,
    threshold_provenance: str,
    *,
    diagnostic: bool,
    family_of: dict[str, str],
    run_metadata: dict[str, Any] | None = None,
    bootstrap_replicates: int = DEFAULT_BOOTSTRAP_REPLICATES,
    seed: int = DEFAULT_SEED,
    ece_bins: int = DEFAULT_ECE_BINS,
) -> dict[str, Any]:
    """Assemble a results document. `diagnostic` selects which path is legal."""
    is_placeholder = threshold_provenance.startswith(PLACEHOLDER_PREFIX)
    if diagnostic and not is_placeholder:
        raise ValueError(
            "diagnostic-results.v1 requires a PLACEHOLDER threshold provenance; "
            f"got {threshold_provenance!r}. Use the eval-results path for a "
            "held-out-dev artifact."
        )
    if not diagnostic and is_placeholder:
        raise ValueError(
            "eval-results.v1 requires a held-out-dev threshold artifact, but the "
            f"provenance is {threshold_provenance!r}. A placeholder threshold may "
            "never populate a headline table; use --diagnostic instead."
        )

    rows = validated.rows
    by_condition = _index_rows(rows)
    if "clean" not in by_condition:
        raise ValueError("evaluation requires clean rows")
    clean = by_condition["clean"]
    clean_metrics = condition_metrics(
        clean["labels"], clean["scores"], threshold, ece_bins=ece_bins
    )

    conditions: list[dict[str, Any]] = []
    recall_by_condition: dict[str, float] = {}
    family_pool: dict[str, dict] = defaultdict(
        lambda: {"labels": [], "scores": [], "source_ids": []}
    )

    for condition_id in sorted(by_condition):
        bucket = by_condition[condition_id]
        metrics = condition_metrics(
            bucket["labels"], bucket["scores"], threshold, ece_bins=ece_bins
        )
        family = family_of.get(condition_id, "unknown")
        if family in TRANSFORM_FAMILIES:
            pool = family_pool[family]
            pool["labels"].extend(bucket["labels"])
            pool["scores"].extend(bucket["scores"])
            pool["source_ids"].extend(bucket["source_ids"])

        entry: dict[str, Any] = {
            "condition_id": condition_id,
            "family": family,
            "counts": metrics["counts"],
            "metrics": {k: v for k, v in metrics.items() if k != "counts"},
            "drops": {
                name: signed_drop(float(clean_metrics[name]), float(metrics[name]))
                for name in ("fake_recall", "balanced_accuracy", "auroc")
            },
            "ci95": bootstrap_condition_metric(
                np.array(bucket["labels"]), np.array(bucket["scores"]),
                np.array(bucket["source_ids"]), threshold,
                n_replicates=bootstrap_replicates, seed=seed,
            ),
        }
        if condition_id != "clean":
            labels, clean_scores, transformed = _aligned_pair(clean, bucket)
            entry["flips"] = paired_flip_metrics(labels, clean_scores, transformed, threshold)
        conditions.append(entry)
        recall_by_condition[condition_id] = float(metrics["fake_recall"])

    families: list[dict[str, Any]] = []
    recall_by_family: dict[str, float] = {}
    for family in TRANSFORM_FAMILIES:
        if family not in family_pool:
            continue
        pool = family_pool[family]
        metrics = condition_metrics(pool["labels"], pool["scores"], threshold, ece_bins=ece_bins)
        families.append({
            "family": family,
            "n_conditions": sum(1 for c in conditions if c["family"] == family),
            "counts": metrics["counts"],
            "metrics": {k: v for k, v in metrics.items() if k != "counts"},
            "ci95": bootstrap_condition_metric(
                np.array(pool["labels"]), np.array(pool["scores"]),
                np.array(pool["source_ids"]), threshold,
                n_replicates=bootstrap_replicates, seed=seed,
            ),
        })
        recall_by_family[family] = float(metrics["fake_recall"])

    transformed_only = {k: v for k, v in recall_by_condition.items() if k != "clean"}
    worst_cond_id, worst_cond_value = worst_condition(transformed_only)
    worst_fam_id, worst_fam_value = worst_condition(recall_by_family)

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

    document: dict[str, Any] = {
        "schema_version": DIAGNOSTIC_SCHEMA if diagnostic else EVAL_SCHEMA,
        "run": {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "seed": seed,
            **(run_metadata or {}),
        },
        "protocol": {
            "threshold": threshold,
            "threshold_provenance": threshold_provenance,
            "threshold_fitted_on_held_out_dev": not is_placeholder,
            "decision_rule": "p_fake >= threshold predicts AI-generated",
            "bootstrap": {"n_replicates": bootstrap_replicates, "seed": seed,
                          "unit": "source_id", "stratified_by": "label"},
            "ece_bins": ece_bins,
            "families": list(TRANSFORM_FAMILIES),
            "objective_note": (
                "worst-family fake recall is the SELECTION objective (clean excluded, "
                "severities pooled); worst exact condition is reported, never selected on"
            ),
        },
        "dataset": {
            "source_count": len(set(validated.source_ids)),
            "view_count": len(rows),
            "condition_count": len(by_condition),
            "methods": list(validated.method_ids),
            "run_ids": list(validated.run_ids),
        },
        "conditions": conditions,
        "families": families,
        "warnings": [],
    }

    headline = {
        "clean": {"counts": clean_metrics["counts"],
                  **{k: v for k, v in clean_metrics.items() if k != "counts"}},
        "worst_family": {"family": worst_fam_id, "fake_recall": worst_fam_value},
        "worst_exact_condition": {"condition_id": worst_cond_id,
                                  "fake_recall": worst_cond_value},
        "max_directional_flip": max_directional,
        "selective": None,   # no validated abstention estimator yet
        "rescue": None,      # rescue path lands in Phase 3
    }

    if diagnostic:
        # A diagnostic document must be impossible to quote as a result: no
        # headline block, and the placeholder provenance is repeated verbatim
        # so even a stray screenshot carries its own disclaimer.
        document["NOT_A_HEADLINE_RESULT"] = (
            f"Diagnostic only. Threshold provenance is {threshold_provenance!r} — "
            "not fitted on held-out dev. These numbers may not be reported as results."
        )
        document["diagnostic_summary"] = headline
    else:
        document["headline"] = headline
    return document


def write_results(document: dict[str, Any], path: str | Path) -> Path:
    """Atomic write. A half-written results file that still parses is the worst
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
