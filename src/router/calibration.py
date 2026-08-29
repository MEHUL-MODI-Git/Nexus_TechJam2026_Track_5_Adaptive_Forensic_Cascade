"""Calibration and threshold selection (training workstream, Claude).

This module implements the FROZEN threshold objective agreed with Codex on
2026-08-26 (DECISIONS: "SPEC FREEZE"). It is deliberately separate from the
eval harness: fitting happens here on held-out dev only, and the harness merely
consumes the frozen threshold artifact. A test or sealed runner never imports
this module -- that separation is what makes "we did not tune on the test set"
an auditable property rather than a promise.

THE OBJECTIVE, stated exactly once, here:

    Maximize   bootstrap-mean worst-transformation-FAMILY fake recall
    subject to clean FPR   <= baseline clean FPR  + 1 percentage point
               clean BAcc  >= baseline clean BAcc - 1 percentage point

with:
  - the minimum taken over the SIX transform families (jpeg, blur, resize,
    noise, color, crop). `clean` is EXCLUDED from the objective and enters only
    through the constraints -- otherwise the clean constraint does double duty
    and the objective stops being a robustness objective;
  - severities POOLED within a family (jpeg pools q90/q70/q50/q30, color pools
    all six endpoints), which is the whole point of the family-level counter:
    it buys sample size versus a noisy per-condition minimum;
  - a LABEL-STRATIFIED bootstrap whose resampling unit is `source_id`, so all
    transformed views of a source travel together and both classes stay defined.

Reporting (not selection) still uses worst EXACT condition at the frozen
threshold. Selection may be upgraded to exact-condition only at >=500 fake dev
sources per exact condition.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

import numpy as np

SCHEMA_VERSION = "threshold-artifact.v1"

# Constraint slack agreed at freeze, in PERCENTAGE POINTS.
DEFAULT_MAX_CLEAN_FPR_INCREASE = 0.01
DEFAULT_MAX_CLEAN_BACC_DROP = 0.01

# Selection upgrades to exact-condition granularity only above this count.
EXACT_CONDITION_UPGRADE_MIN_FAKE_SOURCES = 500


# --------------------------------------------------------------------------
# Canonical scalar helpers (single definition, per Codex B-009)
# --------------------------------------------------------------------------
def binary_entropy(p: float) -> float:
    """Shannon entropy of a Bernoulli(p), in nats. Router feature.

    Defined as 0 at p in {0, 1} (the limit), rather than raising on log(0).
    """
    if not (0.0 <= p <= 1.0) or not math.isfinite(p):
        raise ValueError(f"p must be finite in [0,1], got {p}")
    if p <= 0.0 or p >= 1.0:
        return 0.0
    return float(-(p * math.log(p) + (1.0 - p) * math.log(1.0 - p)))


def sigmoid(x: float | np.ndarray):
    """Numerically stable logistic.

    The naive form overflows `exp(-x)` for large negative x and returns nan
    where the true answer is ~0. Splitting by sign keeps every branch bounded.
    """
    x = np.asarray(x, dtype=np.float64)
    out = np.empty_like(x)
    pos = x >= 0
    out[pos] = 1.0 / (1.0 + np.exp(-x[pos]))
    e = np.exp(x[~pos])
    out[~pos] = e / (1.0 + e)
    return out if out.ndim else float(out)


def logit(p: float | np.ndarray, eps: float = 1e-12):
    """Inverse sigmoid, clipped so that p in {0,1} does not produce +/-inf."""
    p = np.clip(np.asarray(p, dtype=np.float64), eps, 1.0 - eps)
    return np.log(p / (1.0 - p))


# --------------------------------------------------------------------------
# Confusion-based rates. AI-generated (label 1) is the positive class.
# --------------------------------------------------------------------------
def _rates(scores: np.ndarray, labels: np.ndarray, threshold: float) -> tuple[float, float]:
    """Return (fake_recall/TPR, FPR). NaN when a class is absent."""
    pred = scores >= threshold  # `>=` so p == threshold predicts fake (eval contract)
    pos = labels == 1
    neg = ~pos
    tpr = float(pred[pos].mean()) if pos.any() else float("nan")
    fpr = float(pred[neg].mean()) if neg.any() else float("nan")
    return tpr, fpr


def balanced_accuracy(scores: np.ndarray, labels: np.ndarray, threshold: float) -> float:
    tpr, fpr = _rates(scores, labels, threshold)
    return float((tpr + (1.0 - fpr)) / 2.0)


def fake_recall(scores: np.ndarray, labels: np.ndarray, threshold: float) -> float:
    return _rates(scores, labels, threshold)[0]


# --------------------------------------------------------------------------
# Dev-set container
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class DevSet:
    """Dev rows for threshold fitting.

    One entry per (source, condition). `source_id` is the bootstrap unit: all
    views of a source resample together, so transformed views are never treated
    as independent observations.
    """

    source_ids: np.ndarray   # str
    condition_ids: np.ndarray  # str
    families: np.ndarray     # str, one of jpeg/blur/resize/noise/color/crop/clean
    labels: np.ndarray       # int 0/1
    scores: np.ndarray       # float p_fake in [0,1]

    def __post_init__(self) -> None:
        n = len(self.source_ids)
        for name in ("condition_ids", "families", "labels", "scores"):
            if len(getattr(self, name)) != n:
                raise ValueError(f"DevSet field {name!r} has length != source_ids")
        if n == 0:
            raise ValueError("DevSet is empty")
        if not np.isfinite(self.scores).all():
            raise ValueError("DevSet contains non-finite scores")
        if not set(np.unique(self.labels)).issubset({0, 1}):
            raise ValueError("labels must be 0/1")

    @property
    def clean_mask(self) -> np.ndarray:
        return self.families == "clean"

    @property
    def transform_families(self) -> list[str]:
        """The six transform families present, EXCLUDING clean, sorted."""
        return sorted(set(self.families.tolist()) - {"clean"})


# The frozen objective is defined over exactly these six families. If dev is
# missing one, the objective would silently become a five-family minimum -- a
# different (easier) objective wearing the same name.
REQUIRED_FAMILIES = frozenset({"jpeg", "blur", "resize", "noise", "color", "crop"})


def validate_dev_for_selection(dev: DevSet) -> None:
    """Strict protocol validation. Required before ANY artifact is produced.

    Exploratory helpers may tolerate absent groups; artifact-producing
    selection may not (Codex B-013).
    """
    from ..pipeline.transforms import CONDITION_IDS, FAMILY_OF

    if not np.isfinite(dev.scores).all():
        raise ValueError("dev contains non-finite p_fake values")
    if dev.scores.min() < 0.0 or dev.scores.max() > 1.0:
        raise ValueError("dev contains p_fake outside [0,1]")

    unknown = set(dev.condition_ids.tolist()) - set(CONDITION_IDS)
    if unknown:
        raise ValueError(f"unknown condition ids for the official grid: {sorted(unknown)}")
    for condition, family in zip(dev.condition_ids.tolist(), dev.families.tolist()):
        if FAMILY_OF[condition] != family:
            raise ValueError(
                f"condition {condition!r} is labelled family {family!r} but belongs "
                f"to {FAMILY_OF[condition]!r}"
            )

    _source_labels(dev)  # raises on a source whose views disagree about its label

    if not dev.clean_mask.any():
        raise ValueError("dev has no clean rows; the constraints are undefined")
    clean_labels = set(dev.labels[dev.clean_mask].tolist())
    if clean_labels != {0, 1}:
        raise ValueError(f"clean rows must contain both classes, found {sorted(clean_labels)}")

    present = set(dev.families.tolist()) - {"clean"}
    missing = REQUIRED_FAMILIES - present
    if missing:
        raise ValueError(
            f"the frozen objective requires all six transform families; missing {sorted(missing)}. "
            "Selecting on a subset would silently redefine the objective."
        )
    for family in sorted(REQUIRED_FAMILIES):
        if not ((dev.families == family) & (dev.labels == 1)).any():
            raise ValueError(f"family {family!r} has no fake rows; worst-family recall is undefined")


def validate_candidates(candidates: np.ndarray) -> np.ndarray:
    """Candidate thresholds must be finite and inside [0,1]."""
    candidates = np.asarray(candidates, dtype=np.float64)
    if candidates.size == 0:
        raise ValueError("no candidate thresholds supplied")
    if not np.isfinite(candidates).all():
        raise ValueError("candidate thresholds contain non-finite values")
    if candidates.min() < 0.0 or candidates.max() > 1.0:
        raise ValueError("candidate thresholds must lie in [0,1]")
    return np.unique(candidates)


def worst_family_fake_recall(dev: DevSet, threshold: float) -> tuple[float, str]:
    """Minimum fake recall across transform families (severities pooled).

    Returns (value, family attaining it). Families with no fake rows are
    skipped rather than counted as zero -- an absent measurement is not a
    failure to detect.
    """
    worst = math.inf
    worst_family = ""
    for family in dev.transform_families:
        mask = (dev.families == family) & (dev.labels == 1)
        if not mask.any():
            continue
        recall = float((dev.scores[mask] >= threshold).mean())
        if recall < worst:
            worst, worst_family = recall, family
    if not worst_family:
        raise ValueError("no transform family contained fake rows")
    return worst, worst_family


def worst_exact_condition_fake_recall(dev: DevSet, threshold: float) -> tuple[float, str]:
    """Reported (never selected on) worst single condition at a threshold."""
    worst = math.inf
    worst_condition = ""
    for condition in sorted(set(dev.condition_ids.tolist())):
        mask = (dev.condition_ids == condition) & (dev.labels == 1)
        if not mask.any():
            continue
        recall = float((dev.scores[mask] >= threshold).mean())
        if recall < worst:
            worst, worst_condition = recall, condition
    return worst, worst_condition


# --------------------------------------------------------------------------
# Label-stratified source bootstrap
# --------------------------------------------------------------------------
def _source_labels(dev: DevSet) -> dict[str, int]:
    """Map each source_id to its label, asserting the label is consistent."""
    mapping: dict[str, int] = {}
    for sid, label in zip(dev.source_ids.tolist(), dev.labels.tolist()):
        if mapping.setdefault(sid, label) != label:
            raise ValueError(f"source {sid!r} has inconsistent labels across its views")
    return mapping


def bootstrap_worst_family_recall(
    dev: DevSet, threshold: float, n_replicates: int = 1000, seed: int = 20260826
) -> tuple[float, tuple[float, float]]:
    """Bootstrap MEAN worst-family fake recall, plus a 95% percentile interval.

    The mean over replicates (not the point estimate) is what the frozen
    objective selects on: a point estimate of a minimum over families is
    downward-biased and jumpy, which is exactly the instability the
    family-level counter was adopted to avoid.
    """
    rng = np.random.default_rng(seed)
    source_label = _source_labels(dev)
    real_sources = np.array([s for s, y in source_label.items() if y == 0])
    fake_sources = np.array([s for s, y in source_label.items() if y == 1])
    if real_sources.size == 0 or fake_sources.size == 0:
        raise ValueError("label-stratified bootstrap needs both classes")

    rows_by_source: dict[str, list[int]] = defaultdict(list)
    for i, sid in enumerate(dev.source_ids.tolist()):
        rows_by_source[sid].append(i)

    values: list[float] = []
    for _ in range(n_replicates):
        # Label-stratified: resample each class to its own size, so both
        # classes remain defined in every replicate.
        picked = np.concatenate([
            rng.choice(real_sources, size=real_sources.size, replace=True),
            rng.choice(fake_sources, size=fake_sources.size, replace=True),
        ])
        idx = np.concatenate([rows_by_source[s] for s in picked.tolist()])
        replicate = DevSet(
            source_ids=dev.source_ids[idx], condition_ids=dev.condition_ids[idx],
            families=dev.families[idx], labels=dev.labels[idx], scores=dev.scores[idx],
        )
        try:
            values.append(worst_family_fake_recall(replicate, threshold)[0])
        except ValueError:
            continue  # replicate lacked fake rows in every family; skip, never impute

    if not values:
        raise ValueError("every bootstrap replicate was degenerate")
    arr = np.array(values)
    return float(arr.mean()), (float(np.percentile(arr, 2.5)), float(np.percentile(arr, 97.5)))


# --------------------------------------------------------------------------
# The frozen selection procedure
# --------------------------------------------------------------------------
@dataclass
class ThresholdArtifact:
    """`threshold-artifact.v1` -- the ONLY thing a test/sealed runner consumes."""

    schema_version: str
    threshold: float
    objective: str
    feasible: bool
    selection_granularity: str          # "family" | "exact_condition"
    objective_value: float              # bootstrap-mean worst-family recall
    objective_ci95: tuple[float, float]
    worst_family: str
    worst_exact_condition: str          # REPORTED at the frozen threshold
    worst_exact_condition_recall: float
    clean_fpr: float
    clean_bacc: float
    baseline_clean_fpr: float
    baseline_clean_bacc: float
    constraint_max_clean_fpr: float
    constraint_min_clean_bacc: float
    n_dev_sources: int
    n_dev_rows: int
    n_fake_sources_per_exact_condition_min: int
    bootstrap: dict
    dev_manifest_sha256: str
    config_sha256: str
    pipeline_version: str
    fitting_code_version: str
    created_at: str
    tie_break: str = "objective > clean_bacc > -clean_fpr > threshold"
    warnings: list[str] = field(default_factory=list)

    def to_json_dict(self) -> dict:
        return asdict(self)

    def validate(self) -> None:
        """A threshold artifact is consumed by test/sealed runners; it must be
        self-checking, because a corrupt one silently invalidates every number
        computed from it."""
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"unexpected schema_version {self.schema_version!r}")
        if not math.isfinite(self.threshold) or not (0.0 <= self.threshold <= 1.0):
            raise ValueError(f"threshold must be finite in [0,1], got {self.threshold}")
        for name in ("objective_value", "clean_fpr", "clean_bacc"):
            v = getattr(self, name)
            if not math.isfinite(v):
                raise ValueError(f"{name} must be finite, got {v}")
        lo, hi = self.objective_ci95
        if not (math.isfinite(lo) and math.isfinite(hi)) or lo > hi:
            raise ValueError(f"invalid objective_ci95 {self.objective_ci95}")
        if self.selection_granularity not in ("family", "exact_condition"):
            raise ValueError(f"bad selection_granularity {self.selection_granularity!r}")

    def save(self, path) -> None:
        """Validate, then write atomically (temp + rename).

        A half-written artifact that still parses would be the worst possible
        failure here: it looks usable and freezes the wrong operating point.
        """
        import os
        import tempfile
        from pathlib import Path

        self.validate()
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as fh:
                json.dump(self.to_json_dict(), fh, indent=2)
                fh.write("\n")
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    @classmethod
    def load(cls, path) -> ThresholdArtifact:
        """Load and VALIDATE. Never trust an artifact just because it parses."""
        from pathlib import Path

        payload = json.loads(Path(path).read_text())
        payload["objective_ci95"] = tuple(payload["objective_ci95"])
        artifact = cls(**payload)
        artifact.validate()
        return artifact


def select_threshold(
    dev: DevSet,
    baseline_threshold: float = 0.5,
    candidates: np.ndarray | None = None,
    n_replicates: int = 1000,
    seed: int = 20260826,
    max_clean_fpr_increase: float = DEFAULT_MAX_CLEAN_FPR_INCREASE,
    max_clean_bacc_drop: float = DEFAULT_MAX_CLEAN_BACC_DROP,
    dev_manifest_sha256: str = "",
    config_sha256: str = "",
    pipeline_version: str = "",
    fitting_code_version: str = "",
) -> ThresholdArtifact:
    """Select ONE threshold under the frozen objective. Dev data only.

    If no candidate satisfies the clean constraints, the artifact records
    `feasible=False` and falls back to the baseline threshold with a warning,
    rather than silently relaxing a constraint we agreed to.
    """
    # Artifact-producing selection validates the protocol strictly, BEFORE any
    # fitting happens (Codex B-013).
    validate_dev_for_selection(dev)
    clean = dev.clean_mask

    baseline_fpr = _rates(dev.scores[clean], dev.labels[clean], baseline_threshold)[1]
    baseline_bacc = balanced_accuracy(dev.scores[clean], dev.labels[clean], baseline_threshold)
    max_fpr = baseline_fpr + max_clean_fpr_increase
    min_bacc = baseline_bacc - max_clean_bacc_drop

    if candidates is None:
        # Candidate grid over observed scores: only values that actually change
        # a decision can change the objective.
        candidates = np.unique(np.clip(dev.scores, 0.0, 1.0))
    candidates = validate_candidates(candidates)

    warnings: list[str] = []
    best: tuple[float, float, tuple[float, float]] | None = None
    best_key: tuple[float, float, float, float] | None = None
    for threshold in candidates:
        fpr = _rates(dev.scores[clean], dev.labels[clean], threshold)[1]
        bacc = balanced_accuracy(dev.scores[clean], dev.labels[clean], threshold)
        if fpr > max_fpr or bacc < min_bacc:
            continue
        try:
            value, ci = bootstrap_worst_family_recall(dev, threshold, n_replicates, seed)
        except ValueError:
            continue
        # Deterministic tie-break, recorded in the artifact (Codex B-013):
        # objective -> higher clean BAcc -> lower clean FPR -> higher threshold.
        # Without it, ties resolve by candidate iteration order, so an unrelated
        # change to the grid could move the frozen threshold.
        key = (value, bacc, -fpr, float(threshold))
        if best_key is None or key > best_key:
            best_key = key
            best = (float(threshold), value, ci)

    feasible = best is not None
    if not feasible:
        warnings.append(
            "no candidate satisfied the clean constraints; recorded the baseline "
            "threshold and marked the run infeasible rather than relaxing the constraint"
        )
        value, ci = bootstrap_worst_family_recall(dev, baseline_threshold, n_replicates, seed)
        best = (float(baseline_threshold), value, ci)

    threshold, objective_value, ci = best
    worst_fam = worst_family_fake_recall(dev, threshold)[1]
    worst_cond, worst_cond_name = worst_exact_condition_fake_recall(dev, threshold)

    # Granularity check: selection stays at family level until dev is large enough.
    per_condition_fake_sources = defaultdict(set)
    for sid, cond, label in zip(
        dev.source_ids.tolist(), dev.condition_ids.tolist(), dev.labels.tolist()
    ):
        if label == 1:
            per_condition_fake_sources[cond].add(sid)
    min_fake_per_condition = (
        min(len(v) for v in per_condition_fake_sources.values())
        if per_condition_fake_sources else 0
    )
    if min_fake_per_condition >= EXACT_CONDITION_UPGRADE_MIN_FAKE_SOURCES:
        warnings.append(
            f"dev has >={EXACT_CONDITION_UPGRADE_MIN_FAKE_SOURCES} fake sources per exact "
            "condition; the frozen protocol PERMITS upgrading selection to exact-condition "
            "granularity -- this run still selected at family level"
        )

    return ThresholdArtifact(
        schema_version=SCHEMA_VERSION,
        threshold=threshold,
        objective=(
            "maximize bootstrap-mean worst-transformation-FAMILY fake recall "
            "(6 families, clean excluded, severities pooled) subject to "
            "clean FPR <= baseline+1pt and clean BAcc >= baseline-1pt"
        ),
        feasible=feasible,
        selection_granularity="family",
        objective_value=objective_value,
        objective_ci95=ci,
        worst_family=worst_fam,
        worst_exact_condition=worst_cond_name,
        worst_exact_condition_recall=worst_cond,
        clean_fpr=_rates(dev.scores[clean], dev.labels[clean], threshold)[1],
        clean_bacc=balanced_accuracy(dev.scores[clean], dev.labels[clean], threshold),
        baseline_clean_fpr=baseline_fpr,
        baseline_clean_bacc=baseline_bacc,
        constraint_max_clean_fpr=max_fpr,
        constraint_min_clean_bacc=min_bacc,
        n_dev_sources=len(set(dev.source_ids.tolist())),
        n_dev_rows=len(dev.source_ids),
        n_fake_sources_per_exact_condition_min=min_fake_per_condition,
        bootstrap={"n_replicates": n_replicates, "seed": seed,
                   "unit": "source_id", "stratified_by": "label",
                   "interval": "percentile_95"},
        dev_manifest_sha256=dev_manifest_sha256,
        config_sha256=config_sha256,
        pipeline_version=pipeline_version,
        fitting_code_version=fitting_code_version,
        created_at=datetime.now(UTC).isoformat(),
        warnings=warnings,
    )


# --------------------------------------------------------------------------
# Temperature + bias calibration (doc 03 step 7)
# --------------------------------------------------------------------------
def fit_temperature_bias(
    logits: np.ndarray, labels: np.ndarray, max_iter: int = 500, lr: float = 0.05
) -> tuple[float, float]:
    """Fit p = sigmoid(logit / T + b) by NLL on DEV ONLY.

    Two parameters, deliberately: temperature alone cannot fix a prior shift,
    and anything richer would start fitting the dev set's idiosyncrasies.
    """
    logits = np.asarray(logits, dtype=np.float64)
    labels = np.asarray(labels, dtype=np.float64)
    if logits.shape != labels.shape:
        raise ValueError("logits and labels must have the same shape")
    if logits.size == 0:
        raise ValueError("cannot fit calibration on an empty set")
    if not np.isfinite(logits).all():
        raise ValueError("non-finite logits")
    if not np.isin(labels, (0.0, 1.0)).all():
        raise ValueError("labels must be 0/1")
    if len(np.unique(labels)) < 2:
        raise ValueError("calibration needs both classes present")

    log_t, bias = 0.0, 0.0  # optimize log T to keep T > 0
    for _ in range(max_iter):
        temperature = math.exp(log_t)
        z = logits / temperature + bias
        p = sigmoid(z)
        residual = p - labels
        grad_bias = float(residual.mean())
        # d z / d log_t = -logits / T
        grad_log_t = float((residual * (-logits / temperature)).mean())
        log_t -= lr * grad_log_t
        bias -= lr * grad_bias
        if abs(grad_log_t) < 1e-9 and abs(grad_bias) < 1e-9:
            break
    return float(math.exp(log_t)), float(bias)


def apply_temperature_bias(logits, temperature: float, bias: float):
    if temperature <= 0:
        raise ValueError(f"temperature must be > 0, got {temperature}")
    return sigmoid(np.asarray(logits, dtype=np.float64) / temperature + bias)


def expected_calibration_error(
    probs: np.ndarray, labels: np.ndarray, n_bins: int = 15
) -> float:
    """ECE with fixed equal-width bins (eval contract default: 15)."""
    probs = np.asarray(probs, dtype=np.float64)
    labels = np.asarray(labels, dtype=np.float64)
    if probs.shape != labels.shape:
        raise ValueError("probs and labels must have the same shape")
    if probs.size == 0:
        raise ValueError("cannot compute ECE on an empty set")
    if not np.isfinite(probs).all():
        raise ValueError("non-finite probabilities")
    if probs.min() < 0.0 or probs.max() > 1.0:
        raise ValueError("probabilities must lie in [0,1]")
    if not np.isin(labels, (0.0, 1.0)).all():
        raise ValueError("labels must be 0/1")
    if n_bins < 1:
        raise ValueError("n_bins must be >= 1")
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    # Include the left edge in the first bin so p == 0.0 is not dropped.
    idx = np.clip(np.digitize(probs, edges[1:-1], right=False), 0, n_bins - 1)
    ece = 0.0
    for b in range(n_bins):
        mask = idx == b
        if not mask.any():
            continue
        ece += mask.mean() * abs(labels[mask].mean() - probs[mask].mean())
    return float(ece)
