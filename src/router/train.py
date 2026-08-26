"""Router training (Phase 2) — fit the fusion ladder on cached features.

The ladder from doc 04 is trained rung by rung and compared on the SAME dev
split, because the question is not "does the router work" but "does the router
earn its complexity over a baseline that has none":

    static_average   0 parameters — the honest baseline
    logistic         one linear layer — the complexity control
    mlp              doc 03 step 6

If the MLP does not beat logistic, the MLP is unjustified and we say so. If
neither beats static averaging, our original contribution has not paid off on
this data and that is the finding — doc 08's kill criteria are explicit that a
reported negative ablation is a strength, not a failure.

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
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import torch

from .features import FeatureSpec, Standardizer, rows_to_matrix
from .model import (
    LogisticRouter,
    group_index,
    MLPRouter,
    StaticAverageFusion,
    reliability_targets,
    worst_group_loss,
)

SCHEMA_VERSION = "router-training-run.v1"
CHECKPOINT_SCHEMA = "router-checkpoint.v1"
DEFAULT_SEED = 20260827
TRANSFORM_FAMILIES = ("jpeg", "blur", "resize", "noise", "color", "crop")


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
    matrix = standardizer.transform(rows_to_matrix(rows, spec, threshold))
    expert_logits, available = [], []
    for row in rows:
        experts = row.get("experts") or {}
        logit_row, ok_row = [], []
        for expert_id in spec.expert_ids:
            block = experts.get(expert_id) or {}
            ok = bool(block.get("ok", False))
            ok_row.append(ok)
            logit_row.append(float(block.get("raw_logit", 0.0)) if ok else 0.0)
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
) -> dict[str, Any]:
    """Train one rung and evaluate it on dev. Returns a comparable record."""
    import copy
    torch.manual_seed(seed)
    if name == "static_average":
        model = StaticAverageFusion(n_experts)
    elif name == "logistic":
        model = LogisticRouter(n_features, n_experts)
    elif name == "mlp":
        model = MLPRouter(n_features, n_experts)
    else:
        raise ValueError(f"unknown rung {name!r}")

    trainable = [p for p in model.parameters() if p.requires_grad]
    if trainable:
        optimizer = torch.optim.Adam(trainable, lr=lr)
        groups, n_groups = group_index(batch.families, batch.labels)
        for _ in range(epochs):
            optimizer.zero_grad()
            out = model(batch.features, batch.expert_logits, batch.available)
            fused = out.p_fake.clamp(1e-6, 1 - 1e-6)
            per_sample = torch.nn.functional.binary_cross_entropy(
                fused, batch.labels, reduction="none"
            )
            # R11: BCE + lambda * smooth_logsumexp over CLASS x FAMILY groups,
            # not a hard max over family-only groups.
            loss = (worst_group_loss(per_sample, groups, n_groups)
                    if use_worst_group else per_sample.mean())
            if out.reliability is not None:
                # The reliability head learns whether the fused decision was
                # CORRECT — supervision on outcome, not on confidence.
                target = reliability_targets(fused.detach(), batch.labels, threshold)
                loss = loss + torch.nn.functional.binary_cross_entropy(
                    out.reliability.clamp(1e-6, 1 - 1e-6), target
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
    return {
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
        "_model": trained_model,     # stripped before serialisation; used for checkpointing
    }


def validate_cache_rows(rows: list[dict], expert_ids: tuple[str, ...]) -> dict[str, Any]:
    """Reject a cache the trainer cannot honestly learn from (Codex R21).

    Returns a report of what was dropped and why, so exclusions appear in the
    training artifact instead of silently shrinking the denominator.
    """
    from ..pipeline.transforms import CONDITION_IDS, FAMILY_OF

    if not rows:
        raise ValueError("no cache rows")
    keys = {r.get("cache_key") for r in rows}
    if len(keys) > 1:
        raise ValueError(f"cache rows span {len(keys)} cache keys; never mix generations")

    usable, dropped_unavailable, dropped_invalid = [], 0, 0
    for row in rows:
        condition = row.get("condition_id")
        if condition not in CONDITION_IDS:
            raise ValueError(f"unknown condition_id {condition!r}")
        if row.get("family") not in (None, FAMILY_OF[condition]):
            raise ValueError(f"{condition!r} mislabelled as family {row.get('family')!r}")
        if row.get("label") not in (0, 1):
            raise ValueError(f"invalid label {row.get('label')!r}")
        experts = row.get("experts") or {}
        ok_scores = [
            b.get("p_fake") for eid in expert_ids
            if (b := experts.get(eid) or {}).get("ok")
        ]
        if any(s is None or not math.isfinite(float(s)) or not 0.0 <= float(s) <= 1.0
               for s in ok_scores):
            dropped_invalid += 1
            continue
        if not ok_scores:
            # R20: every expert failed. The fusion weights are all zero, so this
            # row would train as a confident p_fake=0 — a fabricated REAL score
            # no model ever produced. Exclude it and say so.
            dropped_unavailable += 1
            continue
        usable.append(row)

    # Split integrity: a source must not appear on both sides.
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
            "dropped_invalid_scores": dropped_invalid,
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

    spec = FeatureSpec(expert_ids=expert_ids)
    # TRAIN-ONLY statistics. Fitting on everything leaks dev into the scaler.
    standardizer = Standardizer.fit(rows_to_matrix(train_rows, spec, threshold), spec)
    train_batch = build_batch(train_rows, spec, standardizer, threshold)
    dev_batch = build_batch(dev_rows, spec, standardizer, threshold)

    results = [
        train_rung(name, train_batch, dev_batch, spec.dim, len(expert_ids), threshold,
                   use_worst_group=wg, seed=seed, bootstrap_replicates=bootstrap_replicates)
        for name, wg in (("static_average", False), ("logistic", False),
                         ("mlp", False), ("mlp", True))
    ]
    # DEGENERACY GUARD. With one expert, softmax over a single available slot is
    # 1.0 by construction, so every rung emits the primary score exactly and the
    # comparison is vacuous. Reporting that as "the router did not beat the
    # baseline" would look like a scientific finding when it is a configuration
    # artefact — the fusion head had nothing to fuse.
    fusion_degenerate = len(expert_ids) < 2
    baseline = next(r for r in results if r["rung"] == "static_average")
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
        "rows_dropped_invalid_scores": report["dropped_invalid_scores"],
        "fusion_space": "logit",
        "threshold_provenance_warning": (
            "reliability targets are defined as correctness AT the operating threshold; "
            "training under a PLACEHOLDER threshold means the target changes meaning once "
            "a real threshold is fitted (Codex R22)"
            if threshold_provenance.startswith("PLACEHOLDER") else None
        ),
        "results": [{k: v for k, v in r.items() if k != "_model"} for r in results],
        "baseline_worst_family_recall": baseline["dev_worst_family_bootstrap_mean"],
        "best_rung": best["rung"],
        "best_worst_family_recall": best["dev_worst_family_bootstrap_mean"],
        "improvement_over_baseline": delta,
        "router_earns_its_complexity": bool(delta > 0.0) and not fusion_degenerate,
        "fusion_comparison_degenerate": fusion_degenerate,
        "verdict_note": (
            "FUSION COMPARISON IS VACUOUS: only one expert is available, so the fusion "
            "head's softmax weight is 1.0 by construction and every rung necessarily "
            "emits the primary expert's score unchanged. The identical rows below are "
            "an artefact of expert count, NOT evidence about the router. With N=1 the "
            "router's only possible contribution is the reliability/abstention head, "
            "which must be judged by selective metrics (coverage vs accuracy on the "
            "accepted set), not by fused-score recall. Add a second expert before "
            "drawing any conclusion about fusion."
            if fusion_degenerate else
            "If improvement_over_baseline is <= 0 the trained router did NOT beat "
            "parameter-free averaging on this data. That is a reportable negative "
            "ablation (doc 08 kill criteria), not a result to bury."
        ),
    }
    document["_best_model"] = best.get("_model")
    document["_standardizer"] = standardizer
    document["_spec"] = spec
    return document


def save_checkpoint(document: dict[str, Any], path: Path, threshold: float) -> Path:
    """Persist a DEPLOYABLE router (Codex R12).

    The trainer previously returned metrics only, so the selected rung could not
    be loaded into the prediction service or reproduced at all.
    """
    model = document.get("_best_model")
    standardizer = document["_standardizer"]
    spec = document["_spec"]
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": CHECKPOINT_SCHEMA,
        "rung": document["best_rung"],
        "state_dict": (model.state_dict() if model is not None else {}),
        "feature_spec": {"expert_ids": list(spec.expert_ids),
                         "schema_version": spec.schema_version,
                         "feature_names": spec.names, "dim": spec.dim},
        "standardizer": standardizer.to_json_dict(),
        "expert_order": list(spec.expert_ids),
        "threshold": threshold,
        "threshold_provenance": document.get("threshold_provenance"),
        "cache_key": document.get("cache_key"),
        "fusion_space": "logit",
        "selection_metric": document["selection_metric"],
        "dev_worst_family_bootstrap_mean": document["best_worst_family_recall"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    torch.save(payload, path)
    return path
