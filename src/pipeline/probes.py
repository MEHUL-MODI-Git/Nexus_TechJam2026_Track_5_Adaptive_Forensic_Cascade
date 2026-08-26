"""Mild self-probes (doc 03 step 4) -- the router's reliability signal.

The idea in one line: if a tiny, label-preserving change makes an expert's
score swing, that expert's evidence is locally fragile ON THIS INPUT.

Stability is evidence about reliability, NOT a class label. A stable detector
can be confidently and consistently wrong -- which is exactly why the router
also consumes expert scores, disagreement, quality descriptors and supervised
outcomes rather than probe features alone.

Two design constraints carried straight from doc 03:
- **Three probes, not a grid.** Re-running the official severity grid at
  inference would multiply latency and turn evaluation transforms into
  expensive test-time augmentation.
- **Separate namespace.** Probe ids are prefixed `probe_` and live in their own
  config and version key, so a diagnostic can never be mistaken for one of the
  20 official conditions or leak into the stress-matrix table.

Probe pixel operations reuse the OFFICIAL transform primitives, so probe JPEG
encoding cannot silently drift from official JPEG encoding.
"""

from __future__ import annotations

import statistics
from dataclasses import asdict, dataclass
from pathlib import Path

import PIL.Image
import yaml

from ..experts.base import Expert, ExpertInferenceError
from .decode import DecodedImage
# Reusing the official primitives is deliberate: one implementation of the
# JPEG/crop/resize pixel math, so probes and conditions cannot diverge.
from .transforms import _crop, _jpeg, _resize
from .version import PROBE_VERSION

_CONFIG_PATH = Path(__file__).resolve().parents[2] / "configs" / "probes.yaml"

SCHEMA_VERSION = "probe-features.v1"

_KIND_DISPATCH = {"jpeg": _jpeg, "crop": _crop, "resize": _resize}


def load_probe_config(path: Path | None = None) -> dict:
    cfg = yaml.safe_load((path or _CONFIG_PATH).read_text())
    if cfg["probe_version"] != PROBE_VERSION:
        raise RuntimeError(
            f"probe config version {cfg['probe_version']!r} != PROBE_VERSION "
            f"{PROBE_VERSION!r} -- bump both together (invalidates router features)"
        )
    return cfg


CONFIG = load_probe_config()
PROBE_SPECS: dict[str, dict] = CONFIG["probes"]
PROBE_IDS: list[str] = list(PROBE_SPECS)

assert all(pid.startswith("probe_") for pid in PROBE_IDS), (
    "probe ids must be prefixed 'probe_' so they cannot collide with official condition ids"
)


def apply_probe(img: PIL.Image.Image, probe_id: str, sha256: str) -> PIL.Image.Image:
    """Apply one mild probe transform. Unknown ids are a hard error."""
    try:
        spec = PROBE_SPECS[probe_id]
    except KeyError:
        raise KeyError(f"unknown probe_id {probe_id!r}; known: {PROBE_IDS}") from None
    fn = _KIND_DISPATCH[spec["kind"]]
    return fn(img, sha256, dict(spec, _condition_id=probe_id))


@dataclass(frozen=True)
class ProbeFeatures:
    """Per-expert stability features over the mild probes.

    Missing-value discipline (doc 03 step 5): when a probe fails we record the
    failure and shrink `n_probes_ok` rather than substituting a value. A router
    trained on invented numbers would learn from fiction.
    """

    schema_version: str
    probe_version: str
    expert_id: str
    base_p_fake: float
    probe_scores: dict[str, float]     # probe_id -> p_fake (successful probes only)
    probe_failures: list[dict]         # typed failure records, never scores
    n_probes_ok: int
    probe_mean: float | None
    probe_std: float | None
    probe_range: float | None
    probe_max_delta: float | None      # max |p(x) - p(Ti(x))|
    probe_flip: bool | None            # any thresholded label differs from base
    threshold_used: float

    def to_json_dict(self) -> dict:
        return asdict(self)


def compute_probe_features(
    expert: Expert,
    img: DecodedImage,
    threshold: float,
    base_p_fake: float | None = None,
) -> ProbeFeatures:
    """Score `img` under each mild probe and summarize the expert's stability.

    `base_p_fake` may be passed in to avoid re-running the clean forward pass
    when the caller already has it (the prediction service does).
    """
    from dataclasses import replace

    if base_p_fake is None:
        base_p_fake = expert.predict(img).p_fake

    scores: dict[str, float] = {}
    failures: list[dict] = []
    for probe_id in PROBE_IDS:
        probed = apply_probe(img.image, probe_id, img.sha256)
        view = replace(img, image=probed, width=probed.width, height=probed.height)
        try:
            scores[probe_id] = expert.predict(view).p_fake
        except ExpertInferenceError as exc:
            # Recoverable: record it, do not invent a score for this probe.
            failures.append({"probe_id": probe_id, **exc.to_dict()})

    values = list(scores.values())
    n_ok = len(values)
    # All summary features are computed over base + successful probes, so a
    # partially failed probe set still yields honest (if noisier) statistics.
    population = [base_p_fake, *values]

    return ProbeFeatures(
        schema_version=SCHEMA_VERSION,
        probe_version=PROBE_VERSION,
        expert_id=expert.expert_id,
        base_p_fake=base_p_fake,
        probe_scores=scores,
        probe_failures=failures,
        n_probes_ok=n_ok,
        probe_mean=statistics.fmean(population) if n_ok else None,
        # Population (not sample) stdev: these are all the probes there are,
        # not a sample drawn from a larger probe distribution.
        probe_std=statistics.pstdev(population) if n_ok else None,
        probe_range=max(population) - min(population) if n_ok else None,
        probe_max_delta=max(abs(base_p_fake - v) for v in values) if n_ok else None,
        probe_flip=any((v >= threshold) != (base_p_fake >= threshold) for v in values)
        if n_ok else None,
        threshold_used=threshold,
    )
