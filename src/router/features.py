"""Router feature assembly (doc 03 step 5) — cache rows -> model matrix.

This is where the project's central discipline becomes arithmetic: **record a
missing indicator, never invent a value.** Every optional feature ships as a
(value, is_present) pair, with the value forced to 0.0 when absent. The router
therefore learns "this signal was unavailable" as its own fact, instead of
learning from a fabricated 0.5 that looks exactly like a real measurement.

Why that matters concretely here: with the second expert parked, disagreement
features are absent for every row. If we imputed zeros, the router would read
"the experts agreed perfectly" on every single image. Missing indicators make
that case honest and, later, make single-expert and two-expert rows trainable
in the same matrix.

Standardization statistics are fitted on the TRAIN SPLIT ONLY and carried in
the artifact. Fitting them on all data leaks dev into the scaler, which is the
quiet kind of leakage that never shows up as an error.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .calibration import binary_entropy

SCHEMA_VERSION = "router-features.v1"

# Feature blocks are built in a fixed, documented order. The order is part of
# the artifact: a trained router is meaningless against a reordered vector.
QUALITY_KEYS = (
    "blur_varlap", "blockiness", "noise_sigma",
    "luminance_mean", "luminance_std", "saturation_mean",
    "clipped_low_frac", "clipped_high_frac",
)
PROBE_KEYS = ("probe_mean", "probe_std", "probe_range", "probe_max_delta")


def binary_entropy_array(p: np.ndarray) -> np.ndarray:
    """Vectorized form of the CANONICAL `calibration.binary_entropy`.

    Deliberately not a second implementation: this is the vectorized wrapper
    over the single scalar definition, parity-tested against it. Codex flagged
    (B-013) that I had reimplemented the very helper we agreed to centralize.
    """
    arr = np.clip(np.asarray(p, dtype=np.float64), 0.0, 1.0)
    flat = arr.reshape(-1)
    out = np.array([binary_entropy(float(v)) for v in flat], dtype=np.float64)
    return out.reshape(arr.shape)


def _pair(value, present: bool) -> tuple[float, float]:
    """(value, is_present). Absent values are forced to 0.0, never guessed."""
    if not present or value is None:
        return 0.0, 0.0
    v = float(value)
    if not math.isfinite(v):
        return 0.0, 0.0
    return v, 1.0


@dataclass(frozen=True)
class FeatureSpec:
    """Which experts and probes the vector covers. Frozen into the artifact."""

    expert_ids: tuple[str, ...]
    schema_version: str = SCHEMA_VERSION

    @property
    def names(self) -> list[str]:
        """Human-readable feature names, in vector order. Used in ablations."""
        out: list[str] = []
        for eid in self.expert_ids:
            out += [f"{eid}.raw_logit", f"{eid}.raw_logit__present",
                    f"{eid}.p_fake", f"{eid}.p_fake__present",
                    f"{eid}.entropy", f"{eid}.entropy__present"]
            for key in PROBE_KEYS:
                out += [f"{eid}.{key}", f"{eid}.{key}__present"]
            out += [f"{eid}.probe_flip", f"{eid}.probe_flip__present",
                    f"{eid}.n_probes_ok"]
        out += ["disagreement.max_abs_p_diff", "disagreement.max_abs_p_diff__present",
                "disagreement.mean_abs_p_diff", "disagreement.mean_abs_p_diff__present",
                "disagreement.n_experts_ok"]
        out += ["geom.log_width", "geom.log_height", "geom.aspect_ratio",
                "geom.megapixels", "geom.is_portrait"]
        for key in QUALITY_KEYS:
            out += [f"quality.{key}", f"quality.{key}__present"]
        return out

    @property
    def dim(self) -> int:
        return len(self.names)


def derive_probe_flip(probe_block: dict, base_p_fake: float | None,
                      threshold: float) -> bool | None:
    """Did any probe cross the decision boundary relative to the base score?

    Returns None when it cannot be known — no base score, or no probe scored.
    None must stay distinct from False: telling the router "stable" about an
    image we could not probe is the most dangerous imputation available here.
    """
    scores = (probe_block or {}).get("probe_scores") or {}
    if base_p_fake is None or not scores:
        return None
    base_side = base_p_fake >= threshold
    return any((float(v) >= threshold) != base_side for v in scores.values())


def row_to_vector(row: dict, spec: FeatureSpec, threshold: float = 0.5) -> np.ndarray:
    """Convert one `feature-cache-row.v1` dict into a feature vector.

    Never raises on missing sub-structures: absence is a legitimate outcome and
    is encoded, not treated as corruption.
    """
    values: list[float] = []
    experts = row.get("experts") or {}
    probes = row.get("probes") or {}

    for eid in spec.expert_ids:
        block = experts.get(eid) or {}
        ok = bool(block.get("ok", False))
        values += list(_pair(block.get("raw_logit"), ok))
        p_fake = block.get("p_fake")
        values += list(_pair(p_fake, ok))
        # Entropy is computed HERE from p_fake, never read from the cache -- a
        # stored copy can drift from the score it claims to describe (B-009).
        entropy = binary_entropy_array(np.array([p_fake]))[0] if (ok and p_fake is not None) else None
        values += list(_pair(entropy, ok and p_fake is not None))

        pblock = probes.get(eid) or {}
        for key in PROBE_KEYS:
            v = pblock.get(key)
            values += list(_pair(v, v is not None))
        # R9: probe_flip is DERIVED here, not read from the cache. The cache is
        # threshold-free by contract, and a stored flip would silently describe
        # whatever threshold happened to be in force when the row was written.
        flip = derive_probe_flip(pblock, p_fake if ok else None, threshold)
        # Tri-state: True / False / None(unknown). The indicator keeps "unknown"
        # distinct from "measured and stable".
        values += list(_pair(1.0 if flip else 0.0, flip is not None))
        values.append(float(pblock.get("n_probes_ok", 0) or 0))

    dis = row.get("disagreement")
    if dis:
        values += list(_pair(dis.get("max_abs_p_diff"), True))
        values += list(_pair(dis.get("mean_abs_p_diff"), True))
        values.append(float(dis.get("n_experts_ok", 0) or 0))
    else:
        # Single-expert rows land here. Zeros WITH a zero indicator, so the
        # router cannot read this as "the experts agreed".
        values += [0.0, 0.0, 0.0, 0.0, 0.0]

    q = row.get("quality") or {}
    width = float(q.get("width") or 1.0)
    height = float(q.get("height") or 1.0)
    values += [
        math.log(max(width, 1.0)),
        math.log(max(height, 1.0)),
        float(q.get("aspect_ratio") or (width / max(height, 1.0))),
        float(q.get("megapixels") or 0.0),
        1.0 if q.get("is_portrait") else 0.0,
    ]
    for key in QUALITY_KEYS:
        v = q.get(key)
        values += list(_pair(v, v is not None))

    vector = np.asarray(values, dtype=np.float64)
    if vector.size != spec.dim:
        raise ValueError(f"assembled {vector.size} features, spec declares {spec.dim}")
    return vector


def rows_to_matrix(rows: list[dict], spec: FeatureSpec,
                   threshold: float = 0.5) -> np.ndarray:
    if not rows:
        return np.empty((0, spec.dim), dtype=np.float64)
    return np.vstack([row_to_vector(r, spec, threshold) for r in rows])


@dataclass
class Standardizer:
    """Z-scoring fitted on TRAIN ROWS ONLY (`router-standardizer.v1`).

    Indicator columns are deliberately left untouched: rescaling a 0/1 presence
    flag by its own train-split frequency would make "missing" mean different
    things in different feature blocks.
    """

    mean: np.ndarray
    scale: np.ndarray
    indicator_columns: np.ndarray
    feature_names: list[str] = field(default_factory=list)
    schema_version: str = "router-standardizer.v1"

    @classmethod
    def fit(cls, matrix: np.ndarray, spec: FeatureSpec) -> "Standardizer":
        if matrix.ndim != 2 or matrix.shape[0] == 0:
            raise ValueError("standardizer needs a non-empty 2-D train matrix")
        names = spec.names
        indicator = np.array([n.endswith("__present") for n in names])
        mean = matrix.mean(axis=0)
        scale = matrix.std(axis=0)
        # Zero-variance columns would divide by zero; leave them centered only.
        scale[scale < 1e-8] = 1.0
        mean[indicator] = 0.0
        scale[indicator] = 1.0
        return cls(mean=mean, scale=scale, indicator_columns=indicator, feature_names=names)

    def transform(self, matrix: np.ndarray) -> np.ndarray:
        if matrix.shape[1] != self.mean.size:
            raise ValueError(
                f"matrix has {matrix.shape[1]} columns, standardizer expects {self.mean.size}"
            )
        return (matrix - self.mean) / self.scale

    def to_json_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "mean": self.mean.tolist(),
            "scale": self.scale.tolist(),
            "indicator_columns": self.indicator_columns.tolist(),
            "feature_names": self.feature_names,
        }
