"""Degradation reporter — the explanation layer.

It must never be able to influence a verdict, must never impute a missing
descriptor, and must carry its own honest caveat about the clean/colour
confusion rather than presenting a coin flip as an explanation.
"""

from pathlib import Path

import numpy as np
import pytest

from src.pipeline.degradation import (
    DEFAULT_MODEL,
    HARD_FOR_DETECTOR,
    PHRASING,
    DegradationReporter,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def reporter():
    if not DEFAULT_MODEL.exists():
        pytest.skip("degradation classifier not fitted")
    return DegradationReporter.load()


def test_geometry_is_excluded_so_the_accuracy_survives_deployment(reporter):
    """Width/height would make crop and resize easy, but a real upload has no
    known original size. If geometry ever appears here the reported accuracy
    stops being achievable in production."""
    banned = {"width", "height", "megapixels", "aspect_ratio", "is_portrait"}
    assert not (set(reporter.quality_keys) & banned)


def test_every_family_has_human_phrasing(reporter):
    for fam in reporter.families:
        assert PHRASING.get(fam)


def test_report_is_a_valid_distribution(reporter):
    q = {"blur_varlap": 0.02, "blockiness": 0.1, "noise_sigma": 1.2,
         "luminance_mean": 0.4, "luminance_std": 0.2, "saturation_mean": 0.3,
         "clipped_low_frac": 0.0, "clipped_high_frac": 0.0}
    rep = reporter.report(q)
    total = sum(p for _, p in rep.ranked)
    assert total == pytest.approx(1.0, abs=1e-5)
    assert 0.0 <= rep.confidence <= 1.0
    assert rep.ranked[0][0] == rep.family
    assert rep.ranked == sorted(rep.ranked, key=lambda kv: -kv[1])


def test_missing_descriptors_are_absent_not_imputed(reporter):
    """An absent descriptor must land as (0.0, indicator 0) — the same
    missing-value discipline the router uses — not as a plausible number."""
    full = reporter.report({"blur_varlap": 0.02, "blockiness": 0.1,
                            "noise_sigma": 1.2, "luminance_mean": 0.4,
                            "luminance_std": 0.2, "saturation_mean": 0.3,
                            "clipped_low_frac": 0.0, "clipped_high_frac": 0.0})
    partial = reporter.report({"blur_varlap": 0.02})
    empty = reporter.report({})
    # All three must produce a valid distribution and not raise.
    for rep in (full, partial, empty):
        assert sum(p for _, p in rep.ranked) == pytest.approx(1.0, abs=1e-5)
    # Dropping evidence must actually change the answer's distribution.
    assert full.ranked != empty.ranked


def test_non_finite_values_are_treated_as_absent(reporter):
    rep = reporter.report({"noise_sigma": float("nan"), "blur_varlap": float("inf")})
    assert sum(p for _, p in rep.ranked) == pytest.approx(1.0, abs=1e-5)


def test_flags_the_families_where_our_detector_is_measurably_weakest():
    # README section 7: noise and jpeg are where the cascade's advantage lives
    # and where recall is lowest. The UI warns on exactly those.
    assert HARD_FOR_DETECTOR == {"noise", "jpeg"}


def test_clean_colour_confusion_is_disclosed_not_hidden(reporter):
    """Whenever clean and colour are the top pair, the report must say they are
    not reliably separable rather than present a near-coin-flip as an answer."""
    rng = np.random.default_rng(0)
    fired = checked = 0
    for _ in range(400):
        q = {"blur_varlap": float(rng.uniform(0, 0.05)),
             "blockiness": float(rng.uniform(0, 0.3)),
             "noise_sigma": float(rng.uniform(0.8, 1.4)),
             "luminance_mean": float(rng.uniform(0.2, 0.7)),
             "luminance_std": float(rng.uniform(0.1, 0.3)),
             "saturation_mean": float(rng.uniform(0.1, 0.5)),
             "clipped_low_frac": 0.0, "clipped_high_frac": 0.0}
        rep = reporter.report(q)
        if {rep.family, rep.ranked[1][0]} == {"clean", "color"}:
            checked += 1
            fired += rep.caveat is not None
    if checked == 0:
        pytest.skip("no clean/colour top-pair drawn")
    assert fired == checked


def test_reporter_cannot_reach_the_verdict():
    """Structural: the router's feature builder must not import or consume the
    degradation reporter. An explanation that feeds the decision is not an
    explanation."""
    src = (ROOT / "src" / "router" / "features.py").read_text()
    assert "degradation" not in src.lower()
    train = (ROOT / "src" / "router" / "train.py").read_text()
    assert "degradation" not in train.lower()
