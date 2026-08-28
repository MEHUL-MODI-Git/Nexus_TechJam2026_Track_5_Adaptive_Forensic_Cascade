"""Forensic robustness certificate.

The grade bands encode a MEASURED relationship (retention -> clean-verdict
accuracy on the untouched internal test). If someone changes them, these tests
should fail loudly, because the certificate would then be asserting an accuracy
the data does not support.
"""

from dataclasses import dataclass
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

from src.app.certificate import (
    GRADE_BANDS,
    build_certificate,
    grade_for,
    render_certificate,
)


@dataclass
class P:
    condition_id: str
    family: str
    p_fake: float
    decision: str
    flipped: bool
    error: str | None = None


def result(points, clean_decision="AI-GENERATED", clean_p=0.9, complete=True, n_errors=0):
    return {"clean_p_fake": clean_p, "clean_decision": clean_decision,
            "threshold": 0.4667, "threshold_provenance": "frozen:x", "points": points,
            "complete": complete, "n_errors": n_errors}


def grid(n_flip, n=20):
    return [P(f"c{i}", "jpeg", 0.9 if i >= n_flip else 0.1,
              "REAL" if i < n_flip else "AI-GENERATED", i < n_flip) for i in range(n)]


def test_grades_match_the_measured_bands():
    assert grade_for(20, 20)[0] == "HIGH"
    assert grade_for(19, 20)[0] == "MEDIUM"
    assert grade_for(16, 20)[0] == "LOW"
    assert grade_for(10, 20)[0] == "VERY LOW"
    # the accuracies quoted to the user are the measured ones
    assert grade_for(20, 20)[1] == pytest.approx(0.991)
    assert grade_for(10, 20)[1] == pytest.approx(0.606)


def test_grade_is_scaled_so_a_partial_grid_cannot_be_graded_as_complete():
    # 10 of 10 retained is 20/20-equivalent; 5 of 10 is not HIGH.
    assert grade_for(10, 10)[0] == "HIGH"
    assert grade_for(5, 10)[0] == "VERY LOW"
    assert grade_for(0, 0)[0] == "UNKNOWN"


def test_perfect_retention():
    c = build_certificate(result(grid(0)))
    assert (c.n_retained, c.n_scored) == (20, 20)
    assert c.grade == "HIGH"
    assert c.unstable_conditions == []


def test_flips_are_reported_and_downgrade_the_certificate():
    c = build_certificate(result(grid(6)))
    assert c.n_retained == 14
    assert c.grade == "VERY LOW"
    assert len(c.unstable_conditions) == 6


def test_errored_conditions_shrink_the_denominator_never_count_as_retained():
    pts = grid(0)[:18] + [P("bad1", "noise", float("nan"), "ERROR", False, error="boom"),
                          P("bad2", "noise", float("nan"), "ERROR", False, error="boom")]
    c = build_certificate(result(pts, complete=False, n_errors=2))
    assert c.n_scored == 18
    assert c.n_retained == 18
    assert c.complete is False
    assert "Grid incomplete" in render_certificate(c)


def test_worst_case_is_the_score_furthest_against_the_verdict():
    pts = [P("a", "jpeg", 0.95, "AI-GENERATED", False),
           P("b", "noise", 0.20, "REAL", True),
           P("c", "blur", 0.80, "AI-GENERATED", False)]
    fake = build_certificate(result(pts, clean_decision="AI-GENERATED"))
    assert fake.worst_case_p_fake == pytest.approx(0.20)
    assert fake.worst_case_condition == "b"
    real = build_certificate(result(pts, clean_decision="REAL"))
    assert real.worst_case_p_fake == pytest.approx(0.95)


def test_render_escapes_and_reports_the_measured_accuracy():
    pts = grid(0)[:19] + [P("<script>", "noise", 0.1, "REAL", True)]
    html = render_certificate(build_certificate(result(pts)))
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "94.9%" in html          # the MEDIUM band's measured accuracy
    assert "19 / 20" in html


def test_bands_are_monotonic():
    mins = [b[0] for b in GRADE_BANDS]
    accs = [b[2] for b in GRADE_BANDS]
    assert mins == sorted(mins, reverse=True)
    assert accs == sorted(accs, reverse=True)


def test_audit_cost_claim_is_structurally_true():
    """We publish "80 forward passes" for an audit. That number is
    20 conditions x (1 expert + 3 probes), so it must follow from the configs
    rather than from a docstring someone forgot to update -- which is exactly
    what happened the first time: the docs said 20 for several commits.
    """
    from src.pipeline.probes import PROBE_IDS
    from src.pipeline.transforms import CONDITION_IDS

    passes_per_prediction = 1 + len(PROBE_IDS)
    audit_passes = len(CONDITION_IDS) * passes_per_prediction
    assert passes_per_prediction == 4
    assert len(CONDITION_IDS) == 20
    assert audit_passes == 80

    for path in ("src/app/certificate.py", "scripts/audit_image.py", "README.md"):
        text = (ROOT / path).read_text()
        assert "80" in text, f"{path} no longer states the audit cost"


