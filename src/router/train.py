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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import torch

from .features import FeatureSpec, Standardizer, rows_to_matrix
from .model import (
    LogisticRouter,
    MLPRouter,
    StaticAverageFusion,
    reliability_targets,
    worst_group_loss,
)

SCHEMA_VERSION = "router-training-run.v1"
TRANSFORM_FAMILIES = ("jpeg", "blur", "resize", "noise", "color", "crop")


@dataclass
class Batch:
    """Everything a rung needs, already aligned row-for-row."""

    features: torch.Tensor      # (N, F) standardized
    expert_p: torch.Tensor      # (N, E)
    available: torch.Tensor     # (N, E) bool
    labels: torch.Tensor        # (N,)
    families: np.ndarray        # (N,) str
    source_ids: np.ndarray      # (N,) str
    condition_ids: np.ndarray   # (N,) str


def load_cache_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def build_batch(rows: list[dict], spec: FeatureSpec, standardizer: Standardizer) -> Batch:
    matrix = standardizer.transform(rows_to_matrix(rows, spec))
    expert_p, available = [], []
    for row in rows:
        experts = row.get("experts") or {}
        p_row, ok_row = [], []
        for expert_id in spec.expert_ids:
            block = experts.get(expert_id) or {}
            ok = bool(block.get("ok", False))
            ok_row.append(ok)
            p_row.append(float(block.get("p_fake", 0.0)) if ok else 0.0)
        expert_p.append(p_row)
        available.append(ok_row)
    return Batch(
        features=torch.tensor(matrix, dtype=torch.float32),
        expert_p=torch.tensor(expert_p, dtype=torch.float32),
        available=torch.tensor(available, dtype=torch.bool),
        labels=torch.tensor([float(r["label"]) for r in rows], dtype=torch.float32),
        families=np.array([r.get("family", "clean") for r in rows]),
        source_ids=np.array([r["source_id"] for r in rows]),
        condition_ids=np.array([r["condition_id"] for r in rows]),
    )


def worst_family_recall(p_fake: np.ndarray, labels: np.ndarray,
                        families: np.ndarray, threshold: float) -> tuple[float, str]:
    """The frozen objective's quantity: min over the six families, clean excluded."""
    worst, worst_family = np.inf, ""
    for family in TRANSFORM_FAMILIES:
        mask = (families == family) & (labels == 1)
        if not mask.any():
            continue
        recall = float((p_fake[mask] >= threshold).mean())
        if recall < worst:
            worst, worst_family = recall, family
    return (worst, worst_family) if worst_family else (float("nan"), "")


def _family_index(families: np.ndarray) -> tuple[torch.Tensor, int]:
    order = {f: i for i, f in enumerate(sorted(set(families.tolist())))}
    return torch.tensor([order[f] for f in families.tolist()], dtype=torch.long), len(order)


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
    seed: int = 20260827,
) -> dict[str, Any]:
    """Train one rung and evaluate it on dev. Returns a comparable record."""
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
        groups, n_groups = _family_index(batch.families)
        for _ in range(epochs):
            optimizer.zero_grad()
            out = model(batch.features, batch.expert_p, batch.available)
            fused = out.p_fake.clamp(1e-6, 1 - 1e-6)
            per_sample = torch.nn.functional.binary_cross_entropy(
                fused, batch.labels, reduction="none"
            )
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
        dev_out = model(dev.features, dev.expert_p, dev.available)
    p = dev_out.p_fake.numpy()
    labels = dev.labels.numpy()
    recall, family = worst_family_recall(p, labels, dev.families, threshold)
    clean = dev.families == "clean"
    return {
        "rung": name,
        "use_worst_group_loss": use_worst_group,
        "n_parameters": sum(p_.numel() for p_ in model.parameters()),
        "dev_worst_family_fake_recall": recall,
        "dev_worst_family": family,
        "dev_clean_fake_recall": float((p[clean & (labels == 1)] >= threshold).mean())
        if (clean & (labels == 1)).any() else float("nan"),
        "dev_clean_fpr": float((p[clean & (labels == 0)] >= threshold).mean())
        if (clean & (labels == 0)).any() else float("nan"),
        "dev_overall_accuracy": float(((p >= threshold) == (labels == 1)).mean()),
        "reliability_head": dev_out.reliability is not None,
    }


def run_ladder(cache_rows: list[dict], threshold: float, expert_ids: tuple[str, ...],
               seed: int = 20260827) -> dict[str, Any]:
    """Train every rung on train, compare on dev, and report honestly."""
    train_rows = [r for r in cache_rows if r.get("dataset_split") == "train"]
    dev_rows = [r for r in cache_rows if r.get("dataset_split") == "dev"]
    if not train_rows or not dev_rows:
        raise ValueError("cache must contain both train and dev rows")

    spec = FeatureSpec(expert_ids=expert_ids)
    # TRAIN-ONLY statistics. Fitting on everything leaks dev into the scaler.
    standardizer = Standardizer.fit(rows_to_matrix(train_rows, spec), spec)
    train_batch = build_batch(train_rows, spec, standardizer)
    dev_batch = build_batch(dev_rows, spec, standardizer)

    results = [
        train_rung(name, train_batch, dev_batch, spec.dim, len(expert_ids), threshold,
                   use_worst_group=wg, seed=seed)
        for name, wg in (("static_average", False), ("logistic", False),
                         ("mlp", False), ("mlp", True))
    ]
    baseline = next(r for r in results if r["rung"] == "static_average")
    best = max(results, key=lambda r: (r["dev_worst_family_fake_recall"]
                                       if not np.isnan(r["dev_worst_family_fake_recall"]) else -1))
    delta = best["dev_worst_family_fake_recall"] - baseline["dev_worst_family_fake_recall"]
    return {
        "schema_version": SCHEMA_VERSION,
        "threshold": threshold,
        "n_train_rows": len(train_rows),
        "n_dev_rows": len(dev_rows),
        "n_train_sources": len({r["source_id"] for r in train_rows}),
        "n_dev_sources": len({r["source_id"] for r in dev_rows}),
        "n_features": spec.dim,
        "expert_ids": list(expert_ids),
        "standardizer_fitted_on": "train split only",
        "selection_metric": "dev worst-transformation-family fake recall (frozen objective)",
        "results": results,
        "baseline_worst_family_recall": baseline["dev_worst_family_fake_recall"],
        "best_rung": best["rung"],
        "best_worst_family_recall": best["dev_worst_family_fake_recall"],
        "improvement_over_baseline": delta,
        "router_earns_its_complexity": bool(delta > 0.0),
        "verdict_note": (
            "If improvement_over_baseline is <= 0 the trained router did NOT beat "
            "parameter-free averaging on this data. That is a reportable negative "
            "ablation (doc 08 kill criteria), not a result to bury."
        ),
    }
