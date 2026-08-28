"""Forensic Robustness Certificate — audit mode.

The stress grid was built to EVALUATE the system. Running it per-image turns out
to be the best confidence signal we have: how many of the 20 official conditions
preserve the clean verdict predicts whether that verdict is correct better than
the reliability head does (measured on the untouched internal test, 3,000
sources: retention AUROC 0.8650 against the reliability head's 0.7206).

It matters most where the reliability head is known to fail. Of the 157 sources
the head passes with high confidence but gets WRONG, mean retention is 14.40/20
against 19.00/20 for the high-confidence-and-correct ones. That is the
confidently-wrong tail the error-analysis note documents as our blind spot.

This is AUDIT MODE, not the default path: it costs 20 forward passes. The normal
decision path is untouched.

Grade bands are the measured ones, not invented. On the internal test the clean
verdict was correct for:
    20/20 retention -> 99.1% of sources (61.4% of all)
    18-19           -> 94.9%            (20.9%)
    15-17           -> 84.9%            (10.4%)
    <=14            -> 60.6%            ( 7.4%)
"""

from __future__ import annotations

import html
import math
from dataclasses import asdict, dataclass

# (minimum retained conditions, grade, measured clean-verdict accuracy at this band)
GRADE_BANDS = (
    (20, "HIGH", 0.991),
    (18, "MEDIUM", 0.949),
    (15, "LOW", 0.849),
    (0, "VERY LOW", 0.606),
)


@dataclass(frozen=True)
class Certificate:
    verdict: str
    clean_p_fake: float
    threshold: float
    n_retained: int
    n_scored: int
    retention_fraction: float
    grade: str
    measured_accuracy_at_grade: float
    stable_conditions: list[str]
    unstable_conditions: list[str]
    worst_case_p_fake: float
    worst_case_condition: str | None
    complete: bool
    n_errors: int

    def to_json_dict(self) -> dict:
        return asdict(self)


def grade_for(n_retained: int, n_scored: int) -> tuple[str, float]:
    """Grade from the MEASURED retention/accuracy relationship.

    Scaled to the number actually scored so a partial grid cannot be graded as
    though it were complete.
    """
    if n_scored <= 0:
        return "UNKNOWN", float("nan")
    scaled = n_retained * 20.0 / n_scored
    for minimum, grade, accuracy in GRADE_BANDS:
        if scaled >= minimum:
            return grade, accuracy
    return "VERY LOW", GRADE_BANDS[-1][2]


def build_certificate(result: dict) -> Certificate:
    """Derive the certificate from a `run_stress_grid` result.

    Never invents a value for a condition that failed to score: errors shrink
    `n_scored` and are reported, exactly as the stress panel does.
    """
    points = [p for p in result["points"] if getattr(p, "error", None) is None]
    n_scored = len(points)
    unstable = [p.condition_id for p in points if p.flipped]
    stable = [p.condition_id for p in points if not p.flipped]
    n_retained = len(stable)
    grade, accuracy = grade_for(n_retained, n_scored)

    # "Worst case" is the score furthest AGAINST the clean verdict: for an
    # AI-generated verdict that is the lowest p_fake seen, for REAL the highest.
    clean_is_fake = result["clean_decision"] == "AI-GENERATED"
    worst_p, worst_cond = float("nan"), None
    if points:
        chosen = min(points, key=lambda p: p.p_fake) if clean_is_fake \
            else max(points, key=lambda p: p.p_fake)
        worst_p, worst_cond = chosen.p_fake, chosen.condition_id

    return Certificate(
        verdict=result["clean_decision"],
        clean_p_fake=result["clean_p_fake"],
        threshold=result["threshold"],
        n_retained=n_retained,
        n_scored=n_scored,
        retention_fraction=(n_retained / n_scored) if n_scored else float("nan"),
        grade=grade,
        measured_accuracy_at_grade=accuracy,
        stable_conditions=stable,
        unstable_conditions=unstable,
        worst_case_p_fake=worst_p,
        worst_case_condition=worst_cond,
        complete=bool(result.get("complete", False)),
        n_errors=int(result.get("n_errors", 0)),
    )


_GRADE_CLASS = {"HIGH": "afc-cert-high", "MEDIUM": "afc-cert-medium",
                "LOW": "afc-cert-low", "VERY LOW": "afc-cert-verylow",
                "UNKNOWN": "afc-cert-verylow"}


def render_certificate(cert: Certificate) -> str:
    """Render the certificate. Escapes every interpolated value."""
    e = html.escape
    worst = ("—" if math.isnan(cert.worst_case_p_fake)
             else f"{cert.worst_case_p_fake:.3f}"
                  + (f" at {e(str(cert.worst_case_condition))}" if cert.worst_case_condition else ""))
    unstable = ("".join(f"<li>{e(c)}</li>" for c in cert.unstable_conditions)
                or "<li>none — the verdict held everywhere</li>")
    incomplete = ""
    if not cert.complete:
        incomplete = (f"<p class='afc-caveat'>Grid incomplete: {cert.n_errors} condition(s) "
                      "failed to score. The grade is scaled to what was measured.</p>")
    return (
        "<section class='afc-cert' role='status'>"
        "<div class='afc-cert-head'>Forensic robustness certificate</div>"
        f"<p class='afc-cert-verdict'>Verdict <strong>{e(cert.verdict)}</strong> "
        f"(p_fake {cert.clean_p_fake:.4f}, threshold {cert.threshold:.4f})</p>"
        f"<p class='afc-cert-retention'>Verdict retention "
        f"<strong>{cert.n_retained} / {cert.n_scored}</strong> stress conditions</p>"
        f"<p class='{_GRADE_CLASS.get(cert.grade, 'afc-cert-low')}'>"
        f"Forensic reliability: <strong>{e(cert.grade)}</strong>"
        f" — verdicts at this retention were correct for "
        f"{cert.measured_accuracy_at_grade * 100:.1f}% of held-out sources</p>"
        f"<p class='afc-cert-worst'>Worst-case score against this verdict: {worst}</p>"
        f"<div class='afc-cert-unstable'>Verdict changes under:<ul>{unstable}</ul></div>"
        f"{incomplete}"
        "<p class='afc-caveat'>Audit mode: 20 extra forward passes. The normal "
        "decision path does not run this.</p>"
        "</section>"
    )


__all__ = [
    "GRADE_BANDS",
    "Certificate",
    "build_certificate",
    "grade_for",
    "render_certificate",
]
