"""Router training (Phase 2) — fit the fusion ladder on cached features.

The ladder from doc 04 is trained rung by rung and compared on the SAME dev
split, because the question is not "does the router work" but "does the router
earn its complexity over a baseline that has none":

    quality_only      one linear layer over FEATURES ONLY, no expert score —
                      the shortcut floor (real=JPEG, fake=PNG) every other
                      rung must beat before any detection claim is credible
    static_average    0 parameters — logit-space mean, the honest baseline
    probability_mean  0 parameters — probability-space mean
    fixed_weights     0 trainable parameters — grid-searched on TRAIN only
    logistic          one linear layer — the complexity control
    mlp               doc 03 step 6
    mlp (worst-group) doc 03 step 6 + the worst-group loss (Codex R11)

If the MLP does not beat logistic, the MLP is unjustified and we say so. If
nothing beats the parameter-free baselines, our original contribution has not
paid off on this data and that is the finding — doc 08's kill criteria are
explicit that a reported negative ablation is a strength, not a failure.

Two guards against fooling ourselves:
- **Standardization statistics come from the TRAIN split only.** Fitting them on
  everything leaks dev into the scaler, which never shows up as an error.
- **Selection is on dev, by the frozen objective's own quantity** (worst-family
  fake recall), not by overall accuracy — otherwise we would tune for something
  we never report.
"""

from __future__ import annotations

import json
import math
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch import nn

from .features import FeatureSpec, Standardizer, rows_to_matrix
from .model import (
    FixedWeightFusion,
    LogisticRouter,
    MLPRouter,
    ProbabilityMeanFusion,
    QualityOnlyRouter,
    StaticAverageFusion,
    group_index,
    reliability_targets,
    worst_group_loss,
)

SCHEMA_VERSION = "router-training-run.v1"
CHECKPOINT_SCHEMA = "router-checkpoint.v2"      # bumped: payload gained provenance fields
DEFAULT_SEED = 20260827
TRANSFORM_FAMILIES = ("jpeg", "blur", "resize", "noise", "color", "crop")
LOGIT_PROB_TOLERANCE = 1e-4    # |sigmoid(raw_logit) - p_fake| must not exceed this
MIN_MEANINGFUL_DELTA = 0.02    # doc 05/08 kill gate: 2 points of worst-family fake recall
VALID_SPLITS = ("train", "dev")
_CACHE_KEY_RE = re.compile(r"^[0-9a-f]{16,64}$")   # the sha256 hex digest feature_cache.py emits


@dataclass
class Batch:
    """Everything a rung needs, already aligned row-for-row."""

    features: torch.Tensor      # (N, F) standardized
    expert_logits: torch.Tensor # (N, E) raw logits — fusion happens in logit space
    available: torch.Tensor     # (N, E) bool
    labels: torch.Tensor        # (N,)
    families: np.ndarray        # (N,) str
    source_ids: np.ndarray      # (N,) str
    condition_ids: np.ndarray   # (N,) str


def load_cache_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def build_batch(rows: list[dict], spec: FeatureSpec, standardizer: Standardizer,
                threshold: float = 0.5) -> Batch:
    """Assemble a training/eval batch. Assumes `rows` already passed
    `validate_cache_rows` (B-018 T1): an `ok: true` expert is guaranteed to
    carry a valid, finite `raw_logit`, so reading it directly can never
    `KeyError` here. Unavailable experts keep the `0.0` placeholder, but it is
    masked out by `available=False` and never reaches the fusion.
    """
    matrix = standardizer.transform(rows_to_matrix(rows, spec, threshold))
    expert_logits, available = [], []
    for row in rows:
        experts = row.get("experts") or {}
        logit_row, ok_row = [], []
        for expert_id in spec.expert_ids:
            block = experts.get(expert_id) or {}
            ok = bool(block.get("ok", False))
            ok_row.append(ok)
            logit_row.append(float(block["raw_logit"]) if ok else 0.0)
        expert_logits.append(logit_row)
        available.append(ok_row)
    return Batch(
        features=torch.tensor(matrix, dtype=torch.float32),
        expert_logits=torch.tensor(expert_logits, dtype=torch.float32),
        available=torch.tensor(available, dtype=torch.bool),
        labels=torch.tensor([float(r["label"]) for r in rows], dtype=torch.float32),
        families=np.array([r.get("family", "clean") for r in rows]),
        source_ids=np.array([r["source_id"] for r in rows]),
        condition_ids=np.array([r["condition_id"] for r in rows]),
    )


def worst_family_recall(p_fake: np.ndarray, labels: np.ndarray,
                        families: np.ndarray, threshold: float,
                        *, require_all: bool = True) -> tuple[float, str]:
    """The frozen objective's quantity: min over the SIX families, clean excluded.

    `require_all` defaults to True (Codex R10): silently skipping an absent
    family turns the six-family objective into an easier three- or four-family
    one while still calling itself the frozen objective.
    """
    present = {f for f in TRANSFORM_FAMILIES
               if ((families == f) & (labels == 1)).any()}
    missing = set(TRANSFORM_FAMILIES) - present
    if missing and require_all:
        raise ValueError(
            f"the frozen objective needs all six transform families with fake rows; "
            f"missing {sorted(missing)}. Refusing to score a reduced objective."
        )
    worst, worst_family = np.inf, ""
    for family in sorted(present):
        mask = (families == family) & (labels == 1)
        recall = float((p_fake[mask] >= threshold).mean())
        if recall < worst:
            worst, worst_family = recall, family
    return (worst, worst_family) if worst_family else (float("nan"), "")


def bootstrap_worst_family(
    p_fake: np.ndarray, labels: np.ndarray, families: np.ndarray,
    source_ids: np.ndarray, threshold: float, n_replicates: int = 200,
    seed: int = DEFAULT_SEED,
) -> dict[str, float]:
    """Bootstrap-MEAN worst-family recall — what the frozen objective selects on.

    A point estimate of a minimum over six families is downward-biased and
    jumpy; the bootstrap mean is the quantity the frozen threshold objective
    names, and selecting on anything else while calling it the frozen objective
    is simply false (Codex R10).
    """
    from collections import defaultdict

    rng = np.random.default_rng(seed)
    source_label: dict[str, int] = {}
    rows_by_source: dict[str, list[int]] = defaultdict(list)
    for i, (sid, y) in enumerate(zip(source_ids.tolist(), labels.tolist())):
        source_label.setdefault(sid, y)
        rows_by_source[sid].append(i)
    real = np.array([s for s, y in source_label.items() if y == 0], dtype=object)
    fake = np.array([s for s, y in source_label.items() if y == 1], dtype=object)
    if real.size == 0 or fake.size == 0:
        raise ValueError("label-stratified bootstrap requires both classes")
    values = []
    for _ in range(n_replicates):
        picked = np.concatenate([rng.choice(real, real.size, replace=True),
                                 rng.choice(fake, fake.size, replace=True)])
        idx = np.concatenate([rows_by_source[s] for s in picked.tolist()])
        try:
            values.append(worst_family_recall(p_fake[idx], labels[idx],
                                              families[idx], threshold)[0])
        except ValueError:
            continue
    if not values:
        raise ValueError("every bootstrap replicate was degenerate")
    arr = np.array(values)
    return {"mean": float(arr.mean()),
            "ci95_low": float(np.percentile(arr, 2.5)),
            "ci95_high": float(np.percentile(arr, 97.5)),
            "n_replicates": n_replicates, "seed": seed}


def threshold_is_frozen(provenance: str) -> bool:
    """True only for a validated, fitted operating-threshold artifact.

    R22: a reliability head trained against a PLACEHOLDER operating point
    learns a target (`reliability_targets`, defined AT the threshold) that
    changes meaning the moment a real threshold is fitted. This gate is what
    lets `train_rung`/`save_checkpoint` ENFORCE the two-stage ordering instead
    of merely warning about it.
    """
    p = (provenance or "").strip()
    return bool(p) and not p.upper().startswith(("PLACEHOLDER", "UNSPECIFIED")) \
        and p.lower() != "unspecified"


def _construct_router(rung: str, n_features: int, n_experts: int, *,
                      hidden: int = 32, hidden2: int = 16, dropout: float = 0.1,
                      fixed_weights: list[float] | None = None) -> nn.Module:
    """Build a fresh (untrained) module for one ladder rung by name.

    Shared by `train_rung` (fitting) and `load_checkpoint` (reconstruction), so
    the two code paths cannot silently drift into building different modules
    for the same rung name. `fixed_weights` is ignored for every rung but
    `"fixed_weights"`, where `None` falls back to a uniform vector — a
    reasonable placeholder for `load_checkpoint`, which immediately overwrites
    the buffer via `load_state_dict`.
    """
    if rung == "quality_only":
        return QualityOnlyRouter(n_features)
    if rung == "static_average":
        return StaticAverageFusion(n_experts)
    if rung == "probability_mean":
        return ProbabilityMeanFusion(n_experts)
    if rung == "fixed_weights":
        w = fixed_weights if fixed_weights is not None else [1.0 / n_experts] * n_experts
        return FixedWeightFusion(torch.tensor(w, dtype=torch.float32))
    if rung == "logistic":
        return LogisticRouter(n_features, n_experts)
    if rung == "mlp":
        return MLPRouter(n_features, n_experts, hidden=hidden, hidden2=hidden2, dropout=dropout)
    raise ValueError(f"unknown rung {rung!r}")


def _fixed_weight_grid(n_experts: int, step: float = 0.1) -> list[list[float]]:
    """Every weight vector on the simplex at `step` resolution.

    FixedWeightFusion is a baseline, not a real optimizer: the point is to see
    whether ANY fixed weighting captures most of what a learned router buys,
    not to find the global optimum, so a coarse grid (11 points for 2 experts)
    is enough and stays cheap even for a handful of experts.
    """
    resolution = round(1.0 / step)

    def _compositions(remaining_experts: int, remaining_units: int):
        if remaining_experts == 1:
            yield (remaining_units,)
            return
        for units in range(remaining_units + 1):
            for rest in _compositions(remaining_experts - 1, remaining_units - units):
                yield (units,) + rest

    return [[unit / resolution for unit in combo]
            for combo in _compositions(n_experts, resolution)]


def _select_fixed_weights(train_batch: Batch, n_experts: int, threshold: float) -> list[float]:
    """Grid-search FixedWeightFusion's weight vector on TRAIN ONLY (doc 05).

    Selecting this on dev would be exactly the leakage the TRAIN-only
    standardizer guard exists to prevent, just moved to a different parameter.
    """
    if n_experts == 1:
        return [1.0]
    labels = train_batch.labels.numpy()
    best_recall, best_weights = -1.0, [1.0 / n_experts] * n_experts
    for candidate in _fixed_weight_grid(n_experts):
        probe = FixedWeightFusion(torch.tensor(candidate, dtype=torch.float32))
        with torch.no_grad():
            out = probe(train_batch.features, train_batch.expert_logits, train_batch.available)
        recall, _ = worst_family_recall(out.p_fake.numpy(), labels, train_batch.families,
                                        threshold, require_all=False)
        if recall > best_recall:
            best_recall, best_weights = recall, candidate
    return best_weights


def _git_revision() -> str | None:
    """`git rev-parse HEAD`, best-effort. A checkpoint should say what code
    produced it, but a missing git binary or a non-repo checkout must never
    block saving a trained model."""
    import subprocess

    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True,
            timeout=5, check=True,
        )
        return out.stdout.strip() or None
    except Exception:      # noqa: BLE001 -- provenance, never a training blocker
        return None


def train_rung(
    name: str,
    batch: Batch,
    dev: Batch,
    n_features: int,
    n_experts: int,
    threshold: float,
    *,
    epochs: int = 200,
    lr: float = 0.02,
    use_worst_group: bool = False,
    seed: int = DEFAULT_SEED,
    bootstrap_replicates: int = 200,
    fit_reliability: bool = True,
    hidden: int = 32,
    hidden2: int = 16,
    dropout: float = 0.1,
    lambda_worst: float = 1.0,
    temperature: float = 0.1,
) -> dict[str, Any]:
    """Train one rung and evaluate it on dev. Returns a comparable record.

    `fit_reliability` implements the R22 two-stage ordering (B-018 T6): when
    False (threshold not yet frozen), the reliability head's parameters are
    excluded from the optimizer entirely and its loss term is skipped, so a
    head trained against a placeholder operating point can never be mistaken
    for a fitted one later.
    """
    torch.manual_seed(seed)
    fixed_weights_chosen = (
        _select_fixed_weights(batch, n_experts, threshold) if name == "fixed_weights" else None
    )
    model = _construct_router(name, n_features, n_experts, hidden=hidden, hidden2=hidden2,
                              dropout=dropout, fixed_weights=fixed_weights_chosen)

    trainable = [
        p for param_name, p in model.named_parameters()
        if p.requires_grad and (fit_reliability or not param_name.startswith("reliability_head"))
    ]
    if trainable:
        optimizer = torch.optim.Adam(trainable, lr=lr)
        groups, n_groups = group_index(batch.families, batch.labels)
        for _ in range(epochs):
            optimizer.zero_grad()
            out = model(batch.features, batch.expert_logits, batch.available)
            # doc 04: BCE WITH LOGITS on the fused logit directly. The previous
            # clamped-probability BCE bent gradients near 0/1 for no reason
            # once the logit was available to a loss that handles the
            # numerics itself.
            per_sample = torch.nn.functional.binary_cross_entropy_with_logits(
                out.fused_logit, batch.labels, reduction="none"
            )
            # R11: BCE + lambda * smooth_logsumexp over CLASS x FAMILY groups,
            # not a hard max over family-only groups.
            loss = (worst_group_loss(per_sample, groups, n_groups,
                                     lambda_worst=lambda_worst, temperature=temperature)
                    if use_worst_group else per_sample.mean())
            if fit_reliability and out.reliability_logit is not None:
                # The reliability head learns whether the fused decision was
                # CORRECT — supervision on outcome, not on confidence.
                target = reliability_targets(out.p_fake.detach(), batch.labels, threshold)
                loss = loss + torch.nn.functional.binary_cross_entropy_with_logits(
                    out.reliability_logit, target
                )
            loss.backward()
            optimizer.step()

    model.eval()
    with torch.no_grad():
        dev_out = model(dev.features, dev.expert_logits, dev.available)
    trained_model = model
    p = dev_out.p_fake.numpy()
    labels = dev.labels.numpy()
    recall, family = worst_family_recall(p, labels, dev.families, threshold)
    boot = bootstrap_worst_family(p, labels, dev.families, dev.source_ids,
                                  threshold, n_replicates=bootstrap_replicates, seed=seed)
    clean = dev.families == "clean"
    clean_fake = clean & (labels == 1)
    clean_real = clean & (labels == 0)

    # T4 checkpoint provenance: only the hyperparameters this rung actually
    # used, never invented defaults for a knob that never touched this rung.
    hyperparameters: dict[str, Any] = {"seed": seed}
    if trainable:
        hyperparameters["epochs"] = epochs
        hyperparameters["lr"] = lr
    if name == "mlp":
        hyperparameters["hidden"] = hidden
        hyperparameters["hidden2"] = hidden2
        hyperparameters["dropout"] = dropout
    if use_worst_group:
        hyperparameters["lambda_worst"] = lambda_worst
        hyperparameters["temperature"] = temperature

    record = {
        "rung": name,
        "dev_worst_family_bootstrap_mean": boot["mean"],
        "dev_worst_family_ci95": [boot["ci95_low"], boot["ci95_high"]],
        "use_worst_group_loss": use_worst_group,
        "n_parameters": sum(p_.numel() for p_ in model.parameters()),
        "dev_worst_family_fake_recall": recall,
        "dev_worst_family": family,
        "dev_clean_fake_recall": float((p[clean_fake] >= threshold).mean())
        if clean_fake.any() else float("nan"),
        "dev_clean_fpr": float((p[clean_real] >= threshold).mean())
        if clean_real.any() else float("nan"),
        "dev_clean_balanced_accuracy": float(
            ((p[clean_fake] >= threshold).mean() + (p[clean_real] < threshold).mean()) / 2
        ) if clean_fake.any() and clean_real.any() else float("nan"),
        "dev_overall_accuracy": float(((p >= threshold) == (labels == 1)).mean()),
        "reliability_head": dev_out.reliability is not None,
        "reliability_head_fitted": fit_reliability,
        "hyperparameters": hyperparameters,
        "_model": trained_model,     # stripped before serialisation; used for checkpointing
        "_dev_p_fake": p,            # stripped before serialisation; feeds T3's measured delta
    }
    if name == "fixed_weights":
        record["fixed_weights"] = fixed_weights_chosen
        record["fixed_weights_selected_on"] = "train split only"
    return record


def _stable_sigmoid(x: float) -> float:
    """Overflow-safe sigmoid, used only to CHECK a stored raw_logit/p_fake pair
    agree (B-018 T1). `math.exp` of a large positive argument overflows; every
    branch below only ever exponentiates a non-positive number."""
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    z = math.exp(x)
    return z / (1.0 + z)


_REQUIRED_ROW_FIELDS = ("source_id", "condition_id", "label", "dataset_split",
                        "cache_key", "experts")


def validate_cache_rows(rows: list[dict], expert_ids: tuple[str, ...]) -> dict[str, Any]:
    """Reject a cache the trainer cannot honestly learn from (Codex R21, B-018 T1/T2).

    Two disjoint kinds of "bad row":
    - every expert failed for this row -- a real runtime outcome, counted and
      excluded (R20), not an error;
    - anything else malformed (a missing field, an unknown split, a cache key
      from a different generation, an `ok: true` expert whose `p_fake` and
      `raw_logit` disagree) is CORRUPTION and now ABORTS the whole run. The
      previous version silently dropped some of these, which meant a trainer
      could run for hours on a corrupt cache and never say so.

    Returns a report of what was dropped and why, so the one real exclusion
    kind appears in the training artifact instead of silently shrinking the
    denominator.
    """
    from ..pipeline.transforms import CONDITION_IDS, FAMILY_OF

    if not rows:
        raise ValueError("no cache rows")

    # Required fields first: every other check below reads these directly, and
    # a missing field should be reported as itself, not as a KeyError deep in
    # some later check.
    for row in rows:
        for field_name in _REQUIRED_ROW_FIELDS:
            if field_name not in row:
                raise ValueError(f"row is missing required field {field_name!r}: {row!r}")
        if not isinstance(row["source_id"], str) or not row["source_id"]:
            raise ValueError(f"row has an invalid source_id {row['source_id']!r}")

    keys = {r["cache_key"] for r in rows}
    if len(keys) > 1:
        raise ValueError(f"cache rows span {len(keys)} cache keys; never mix generations")

    # T2: cache_key format -- the canonical sha256 hex digest `compute_cache_key`
    # in feature_cache.py emits, never a placeholder or truncated form.
    for row in rows:
        ck = row["cache_key"]
        if not isinstance(ck, str) or not _CACHE_KEY_RE.match(ck):
            raise ValueError(f"row {row['source_id']!r} has a malformed cache_key {ck!r}")

    # T2: split integrity is fail-CLOSED -- an unknown or missing split aborts,
    # it does not fall through as "not train, so must be dev" or similar.
    for row in rows:
        if row["dataset_split"] not in VALID_SPLITS:
            raise ValueError(
                f"row {row['source_id']!r} has unknown dataset_split "
                f"{row['dataset_split']!r}; expected one of {VALID_SPLITS}"
            )

    # T2: one label, one split, per source_id.
    label_by_source: dict[str, Any] = {}
    split_by_source: dict[str, str] = {}
    for row in rows:
        sid, label, split = row["source_id"], row.get("label"), row["dataset_split"]
        prev_label = label_by_source.setdefault(sid, label)
        if prev_label != label:
            raise ValueError(
                f"source_id {sid!r} has inconsistent labels ({prev_label!r} and {label!r} "
                "across its rows)"
            )
        prev_split = split_by_source.setdefault(sid, split)
        if prev_split != split:
            raise ValueError(
                f"source_id {sid!r} appears in BOTH train and dev "
                f"({prev_split!r} then {split!r} across its rows); dev would measure "
                "memorisation"
            )

    usable, dropped_unavailable = [], 0
    for row in rows:
        condition = row["condition_id"]
        if condition not in CONDITION_IDS:
            raise ValueError(f"unknown condition_id {condition!r}")
        if row.get("family") not in (None, FAMILY_OF[condition]):
            raise ValueError(f"{condition!r} mislabelled as family {row.get('family')!r}")
        if row["label"] not in (0, 1):
            raise ValueError(f"invalid label {row['label']!r}")

        experts = row["experts"] or {}
        any_available = False
        for eid in expert_ids:
            block = experts.get(eid)
            ok = None if block is None else block.get("ok")
            if block is None or ok is False:
                continue        # unavailable: not validated, not an error
            if not isinstance(ok, bool):
                # ValueError, not TypeError (ruff TRY004): every other malformed-cache-row
                # rejection in this function is a ValueError, and callers/tests already
                # match on that -- a type-check exemption here would split the contract.
                raise ValueError(  # noqa: TRY004
                    f"row source_id={row['source_id']!r} condition_id={condition!r} expert "
                    f"{eid!r} has non-bool ok={ok!r}"
                )
            any_available = True
            p_fake = block.get("p_fake")
            valid_p_fake = (
                p_fake is not None and isinstance(p_fake, (int, float))
                and not isinstance(p_fake, bool) and math.isfinite(float(p_fake))
                and 0.0 <= float(p_fake) <= 1.0
            )
            if not valid_p_fake:
                raise ValueError(
                    f"row source_id={row['source_id']!r} condition_id={condition!r} "
                    f"expert {eid!r}: p_fake={p_fake!r} is not a finite probability in [0, 1]"
                )
            raw_logit = block.get("raw_logit")
            valid_raw_logit = (
                "raw_logit" in block and isinstance(raw_logit, (int, float))
                and not isinstance(raw_logit, bool) and math.isfinite(float(raw_logit))
            )
            if not valid_raw_logit:
                raise ValueError(
                    f"row source_id={row['source_id']!r} condition_id={condition!r} "
                    f"expert {eid!r}: raw_logit={raw_logit!r} is missing or not finite"
                )
            predicted_p = _stable_sigmoid(float(raw_logit))
            if abs(predicted_p - float(p_fake)) > LOGIT_PROB_TOLERANCE:
                raise ValueError(
                    f"row source_id={row['source_id']!r} condition_id={condition!r} "
                    f"expert {eid!r}: sigmoid(raw_logit)={predicted_p!r} does not match "
                    f"p_fake={p_fake!r} within tolerance {LOGIT_PROB_TOLERANCE}"
                )
        if not any_available:
            # R20: every expert failed. The fusion weights are all zero, so this
            # row would train as a confident p_fake=0 — a fabricated REAL score
            # no model ever produced. Exclude it and say so.
            dropped_unavailable += 1
            continue
        usable.append(row)

    # Split integrity: a source must not appear on both sides. Subsumed by the
    # per-source split-consistency check above (it can no longer fire), kept
    # as an explicit, separately-tested guarantee on the USABLE rows the
    # trainer actually sees.
    train_src = {r["source_id"] for r in usable if r.get("dataset_split") == "train"}
    dev_src = {r["source_id"] for r in usable if r.get("dataset_split") == "dev"}
    overlap = train_src & dev_src
    if overlap:
        raise ValueError(
            f"{len(overlap)} source(s) appear in BOTH train and dev "
            f"(e.g. {sorted(overlap)[:3]}); dev would measure memorisation"
        )
    return {"usable_rows": usable,
            "dropped_all_experts_unavailable": dropped_unavailable,
            "cache_key": next(iter(keys))}


def run_ladder(cache_rows: list[dict], threshold: float, expert_ids: tuple[str, ...],
               seed: int = DEFAULT_SEED, bootstrap_replicates: int = 200,
               threshold_provenance: str = "unspecified") -> dict[str, Any]:
    """Train every rung on train, compare on dev, and report honestly."""
    report = validate_cache_rows(cache_rows, expert_ids)
    rows = report["usable_rows"]
    train_rows = [r for r in rows if r.get("dataset_split") == "train"]
    dev_rows = [r for r in rows if r.get("dataset_split") == "dev"]
    if not train_rows or not dev_rows:
        raise ValueError("cache must contain both train and dev rows")

    # T2: dev sufficiency, asserted BEFORE training starts. This is the same
    # guarantee `worst_family_recall(require_all=True)` gives on the trained
    # result, raised up front so a malformed dev split fails in milliseconds,
    # not after minutes of training every rung.
    dev_labels = {r.get("label") for r in dev_rows}
    if not {0, 1} <= dev_labels:
        raise ValueError(
            "dev split must contain both labels (0 and 1) before training begins"
        )
    dev_fake_families = {r.get("family") for r in dev_rows if r.get("label") == 1}
    missing_families = set(TRANSFORM_FAMILIES) - dev_fake_families
    if missing_families:
        raise ValueError(
            f"dev split is missing fake rows for family(ies) {sorted(missing_families)}; "
            "the frozen worst-family objective needs all six before training starts"
        )

    spec = FeatureSpec(expert_ids=expert_ids)
    # TRAIN-ONLY statistics. Fitting on everything leaks dev into the scaler.
    standardizer = Standardizer.fit(rows_to_matrix(train_rows, spec, threshold), spec)
    train_batch = build_batch(train_rows, spec, standardizer, threshold)
    dev_batch = build_batch(dev_rows, spec, standardizer, threshold)

    # R22 enforced, not warned about: the reliability head is fitted only once
    # the threshold is a validated, frozen artifact -- otherwise its target
    # changes meaning the moment a real threshold shows up.
    fit_reliability = threshold_is_frozen(threshold_provenance)
    results = [
        train_rung(name, train_batch, dev_batch, spec.dim, len(expert_ids), threshold,
                   use_worst_group=wg, seed=seed, bootstrap_replicates=bootstrap_replicates,
                   fit_reliability=fit_reliability)
        for name, wg in (
            ("quality_only", False), ("static_average", False), ("probability_mean", False),
            ("fixed_weights", False), ("logistic", False),
            ("mlp", False), ("mlp", True),
        )
    ]
    baseline = next(r for r in results if r["rung"] == "static_average")
    quality_only_result = next(r for r in results if r["rung"] == "quality_only")

    # T3: the fusion WEIGHTS are degenerate with one expert (softmax over a
    # single available slot is 1.0 by construction) -- that says nothing about
    # whether the FUSED SCORE changes, because the learned bias/quality
    # correction and reliability head still act on it. Measure the change
    # instead of suppressing it (see `max_abs_p_fake_change_vs_static` below).
    fusion_weight_degenerate = len(expert_ids) < 2
    static_dev_p_fake = baseline["_dev_p_fake"]
    for entry in results:
        entry["max_abs_p_fake_change_vs_static"] = float(
            np.max(np.abs(entry["_dev_p_fake"] - static_dev_p_fake))
        )

    # R10: select on the BOOTSTRAP MEAN under the frozen clean constraints, not a
    # point estimate. A rung that buys worst-family recall by wrecking the clean
    # operating point violates the protocol and must not be selectable.
    max_clean_fpr = baseline["dev_clean_fpr"] + 0.01
    min_clean_bacc = baseline["dev_clean_balanced_accuracy"] - 0.01
    feasible = [r for r in results
                if r["dev_clean_fpr"] <= max_clean_fpr + 1e-12
                and r["dev_clean_balanced_accuracy"] >= min_clean_bacc - 1e-12]
    for entry in results:
        entry["satisfies_clean_constraints"] = entry in feasible
    pool = feasible or [baseline]
    best = max(pool, key=lambda r: r["dev_worst_family_bootstrap_mean"])
    delta = (best["dev_worst_family_bootstrap_mean"]
             - baseline["dev_worst_family_bootstrap_mean"])

    # Kill gate (B-018 T4/§4): a merely-positive delta is not a win. Either it
    # clears the 2-point bar doc 05/08 call meaningful, or the improvement's
    # CI95 sits entirely above the baseline's -- otherwise it is noise.
    meaningful = bool(delta >= MIN_MEANINGFUL_DELTA)
    separated = bool(best["dev_worst_family_ci95"][0] > baseline["dev_worst_family_ci95"][1])

    # The quality-only floor (see model.QualityOnlyRouter docstring): a
    # cascade that cannot clear this by the SAME meaningful-delta bar used
    # against static_average has not demonstrated detection, only image
    # statistics that happen to correlate with the corpus's JPEG/PNG shortcut.
    beats_quality_only = bool(
        best["dev_worst_family_bootstrap_mean"]
        - quality_only_result["dev_worst_family_bootstrap_mean"] >= MIN_MEANINGFUL_DELTA
    )

    # quality_only competes for selection like any other rung, which means it can
    # WIN. If it does, the winning model never looked at an expert, and reporting
    # "the router earns its complexity" would be false in the most flattering
    # possible direction. The flag must not be able to say that.
    best_uses_expert_scores = bool(best["rung"] != "quality_only")

    document = {
        "schema_version": SCHEMA_VERSION,
        "threshold": threshold,
        "n_train_rows": len(train_rows),
        "n_dev_rows": len(dev_rows),
        "n_train_sources": len({r["source_id"] for r in train_rows}),
        "n_dev_sources": len({r["source_id"] for r in dev_rows}),
        "n_features": spec.dim,
        "expert_ids": list(expert_ids),
        "standardizer_fitted_on": "train split only",
        "selection_metric": (
            "bootstrap-mean worst-transformation-family fake recall over six families "
            "(clean excluded), subject to clean FPR <= baseline+1pt and clean BAcc >= "
            "baseline-1pt — the frozen objective"
        ),
        "clean_constraints": {"max_clean_fpr": max_clean_fpr,
                              "min_clean_balanced_accuracy": min_clean_bacc},
        "cache_key": report["cache_key"],
        "threshold_provenance": threshold_provenance,
        "rows_dropped_all_experts_unavailable": report["dropped_all_experts_unavailable"],
        "fusion_space": "logit",
        "threshold_provenance_warning": (
            "reliability targets are defined as correctness AT the operating threshold; "
            "training under a PLACEHOLDER threshold means the target changes meaning once "
            "a real threshold is fitted (Codex R22)"
            if threshold_provenance.startswith("PLACEHOLDER") else None
        ),
        "reliability_fitted": fit_reliability,
        "reliability_stage_note": (
            "reliability/abstention is stage 2 (Codex R22) and is deliberately NOT "
            "fitted until the class threshold is frozen, so no stale target is trained "
            "or saved"
            if not fit_reliability else
            "the class threshold is a frozen artifact, so the reliability/abstention "
            "head is fitted against the real operating point"
        ),
        "results": [{k: v for k, v in r.items() if k not in ("_model", "_dev_p_fake")}
                    for r in results],
        "baseline_worst_family_recall": baseline["dev_worst_family_bootstrap_mean"],
        "quality_only_worst_family_recall": quality_only_result["dev_worst_family_bootstrap_mean"],
        "beats_quality_only": beats_quality_only,
        "quality_only_note": (
            "quality_only uses no expert score at all -- a linear model over the router "
            "feature vector (image-statistics descriptors) alone. This corpus's real=JPEG, "
            "fake=PNG shortcut lets those descriptors separate the classes with no idea "
            "what AI generation is; a cascade that fails to beat this rung has not "
            "demonstrated a detection result."
        ),
        "best_rung": best["rung"],
        "best_worst_family_recall": best["dev_worst_family_bootstrap_mean"],
        "improvement_over_baseline": delta,
        "improvement_is_meaningful": meaningful,
        "improvement_is_outside_uncertainty": separated,
        "best_rung_uses_expert_scores": best_uses_expert_scores,
        # Narrow claim: the learned machinery beat parameter-free fusion AND the
        # winner actually consults an expert. Deliberately NOT folded together
        # with beats_quality_only -- "the fusion machinery is justified" and
        # "the cascade beats plain image statistics" are different questions and
        # collapsing them would hide which one failed.
        "router_earns_its_complexity": bool((meaningful or separated)
                                            and best_uses_expert_scores),
        # The composite headline: both bars cleared.
        "cascade_is_justified": bool((meaningful or separated)
                                     and best_uses_expert_scores and beats_quality_only),
        "kill_gate": {
            "min_meaningful_delta": MIN_MEANINGFUL_DELTA,
            "rule": "delta >= 2 points OR best CI95 low above baseline CI95 high, subject "
                    "to the clean constraints",
        },
        "fusion_weight_degenerate": fusion_weight_degenerate,
        "single_expert_learned_correction": fusion_weight_degenerate,
        "verdict_note": (
            "SINGLE-EXPERT LEARNED CORRECTION, NOT A FUSION TEST: with one expert the "
            "fusion weights are 1.0 by construction, so rungs differ only through the "
            "learned bias/quality correction and the reliability head -- this comparison "
            "tests that correction, not fusion. See max_abs_p_fake_change_vs_static per "
            "rung for the measured (not suppressed) effect. A second expert is required "
            "before any conclusion about fusion is drawn."
            if fusion_weight_degenerate else
            "If improvement_over_baseline is <= 0 the trained router did NOT beat "
            "parameter-free averaging on this data. That is a reportable negative "
            "ablation (doc 08 kill criteria), not a result to bury."
        ),
    }
    document["_best_model"] = best.get("_model")
    document["_best_record"] = best
    document["_standardizer"] = standardizer
    document["_spec"] = spec
    return document


def save_checkpoint(document: dict[str, Any], path: Path, threshold: float, *,
                    cache_artifact_sha256: str | None = None) -> Path:
    """Persist a DEPLOYABLE router (Codex R12), atomically, with provenance (B-018 T4).

    Two failure modes the previous version allowed:
    - a reliability head fitted under a placeholder threshold could be saved
      and later loaded as if it meant something (R22) -- refused BEFORE any
      bytes are written;
    - a crash mid-`torch.save` could leave a truncated, unloadable file at the
      path a caller expects to find a checkpoint -- fixed by writing to a
      `.tmp` sibling and `os.replace`-ing it into place, which is atomic on
      the same filesystem.
    """
    model = document.get("_best_model")
    standardizer = document["_standardizer"]
    spec = document["_spec"]
    best = document.get("_best_record") or {}
    threshold_provenance = document.get("threshold_provenance")

    if best.get("reliability_head_fitted") and not threshold_is_frozen(threshold_provenance):
        raise ValueError(
            "refusing to save a checkpoint whose reliability head was fitted while "
            f"threshold_provenance={threshold_provenance!r} is not a frozen threshold "
            "(Codex R22): the reliability target would silently change meaning."
        )

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": CHECKPOINT_SCHEMA,
        "rung": document["best_rung"],
        "state_dict": (model.state_dict() if model is not None else {}),
        "feature_spec": {"expert_ids": list(spec.expert_ids),
                         "schema_version": spec.schema_version,
                         "feature_names": spec.names, "dim": spec.dim},
        "feature_names": spec.names,
        "standardizer": standardizer.to_json_dict(),
        "expert_order": list(spec.expert_ids),
        "threshold": threshold,
        "threshold_provenance": threshold_provenance,
        "cache_key": document.get("cache_key"),
        "fusion_space": "logit",
        "selection_metric": document["selection_metric"],
        "dev_worst_family_bootstrap_mean": document["best_worst_family_recall"],
        "created_at": datetime.now(UTC).isoformat(),
        "use_worst_group_loss": best.get("use_worst_group_loss"),
        "n_parameters": best.get("n_parameters"),
        "hyperparameters": best.get("hyperparameters", {}),
        "reliability_head_fitted": bool(best.get("reliability_head_fitted")),
        "cache_artifact_sha256": cache_artifact_sha256,
        "code_revision": _git_revision(),
        "selection": {
            "best_rung": document["best_rung"],
            "improvement_over_baseline": document["improvement_over_baseline"],
            "router_earns_its_complexity": document["router_earns_its_complexity"],
            "improvement_is_meaningful": document["improvement_is_meaningful"],
            "improvement_is_outside_uncertainty": document["improvement_is_outside_uncertainty"],
        },
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    torch.save(payload, tmp)
    os.replace(tmp, path)
    return path


_REQUIRED_CHECKPOINT_KEYS = (
    "schema_version", "rung", "state_dict", "feature_spec", "standardizer",
    "expert_order", "threshold",
)


@dataclass
class LoadedRouter:
    """What a caller needs to run a saved router: model, spec, scaler, threshold."""

    model: nn.Module
    spec: FeatureSpec
    standardizer: Standardizer
    threshold: float
    payload: dict[str, Any]


def load_checkpoint(path: Path) -> LoadedRouter:
    """Load a checkpoint written by `save_checkpoint`, fail CLOSED (B-018 T4).

    `weights_only=True` restricts unpickling to a small safe-type allowlist; a
    checkpoint that needs anything outside it is not a trusted artifact this
    trainer produced, and retrying with `weights_only=False` would defeat the
    entire point of asking for the safe loader in the first place.
    """
    path = Path(path)
    try:
        payload = torch.load(path, map_location="cpu", weights_only=True)
    except Exception as exc:
        raise ValueError(
            f"{path} failed to load under weights_only=True; treating it as an "
            f"untrusted checkpoint rather than retrying unsafely: {exc}"
        ) from exc

    for key in _REQUIRED_CHECKPOINT_KEYS:
        if key not in payload:
            raise ValueError(f"checkpoint {path} is missing required key {key!r}")

    if payload["schema_version"] != CHECKPOINT_SCHEMA:
        raise ValueError(
            f"checkpoint schema {payload['schema_version']!r} != expected "
            f"{CHECKPOINT_SCHEMA!r} (code has moved on; retrain or use a matching checkout)"
        )

    feature_spec = payload["feature_spec"]
    spec = FeatureSpec(expert_ids=tuple(payload["expert_order"]))
    if spec.dim != feature_spec["dim"] or spec.names != feature_spec["feature_names"]:
        raise ValueError(
            f"checkpoint feature spec has drifted from the code that built it: code "
            f"computes dim={spec.dim}, checkpoint recorded dim={feature_spec.get('dim')}"
        )

    hyperparameters = payload.get("hyperparameters") or {}
    model = _construct_router(
        payload["rung"], feature_spec["dim"], len(payload["expert_order"]),
        hidden=hyperparameters.get("hidden", 32),
        hidden2=hyperparameters.get("hidden2", 16),
        dropout=hyperparameters.get("dropout", 0.1),
    )
    model.load_state_dict(payload["state_dict"], strict=True)
    model.eval()

    std = payload["standardizer"]
    standardizer = Standardizer(
        mean=np.array(std["mean"], dtype=np.float64),
        scale=np.array(std["scale"], dtype=np.float64),
        indicator_columns=np.array(std["indicator_columns"], dtype=bool),
        feature_names=list(std["feature_names"]),
        schema_version=std.get("schema_version", "router-standardizer.v1"),
    )
    return LoadedRouter(model=model, spec=spec, standardizer=standardizer,
                        threshold=payload["threshold"], payload=payload)
