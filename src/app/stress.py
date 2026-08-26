"""Stress-test panel (task 1.5) — run the official grid live and plot stability.

[relay] Claude, while Codex is limit-blocked (PROTOCOL §6). Codex owns
`src/app/` and reviews this on return.

This is the demo's central claim made visible: a detector's clean score tells
you very little about whether it survives the transformations a real image
undergoes on the way to a feed. Our own measurements show `noise_s0.10` erasing
half of all correct fake detections and `blur_s2.0` flipping a third of real
photos to "AI-generated" — a single number cannot show that, and a grid of
twenty can.

The chart is rendered as **inline SVG with no plotting dependency**. Gradio's
native plots require altair, which is not in the lockfile; adding a dependency
to a file another agent owns, while it is offline, is not a call to make in
passing. Inline SVG also gives exact control over theming.

Encoding decisions:
- One bar per condition, grouped by family with a gap — severities are not
  comparable ACROSS families, so they are not put on a shared severity axis.
- One measure, therefore one hue and no legend.
- A bar whose verdict DIFFERS from the clean verdict is a flip: it is drawn in
  the reserved `critical` status colour, marked with a caret, AND named in the
  text beneath, so identity never rests on colour alone.
- Two reference rules: the clean score (what the demo would have told you) and
  the decision threshold (where the verdict turns).
"""

from __future__ import annotations

import html
from dataclasses import dataclass
from typing import Any

from ..pipeline.transforms import CONDITION_IDS, FAMILY_OF

# Validated against the data-viz palette in both modes (CVD ΔE 23.8 light /
# 25.7 dark, both well clear of the ≥8 gate).
SERIES_LIGHT = "#2a78d6"
SERIES_DARK = "#3987e5"
CRITICAL = "#d03b3b"          # reserved status colour, never a series hue

FAMILY_ORDER = ("clean", "jpeg", "blur", "resize", "noise", "color", "crop")


@dataclass
class StressPoint:
    condition_id: str
    family: str
    p_fake: float
    decision: str
    flipped: bool
    error: str | None = None


def run_stress_grid(service: Any, image_path, threshold: float | None = None) -> dict:
    """Score one image under all 20 official conditions.

    Returns a dict with the clean reference, the per-condition points, and a
    summary. A condition that fails to score is recorded as an error point —
    never as a score.
    """
    clean_record = service.predict_image(image_path, transform_id="clean")
    clean_p = float(_get(clean_record, "p_fake"))
    clean_decision = str(_get(clean_record, "decision"))
    if threshold is None:
        threshold = float(_get(clean_record, "threshold_used", 0.5))
    provenance = str(_get(clean_record, "threshold_provenance", "unspecified"))

    points: list[StressPoint] = []
    for condition_id in CONDITION_IDS:
        if condition_id == "clean":
            points.append(StressPoint("clean", "clean", clean_p, clean_decision, False))
            continue
        try:
            record = service.predict_image(image_path, transform_id=condition_id)
        except Exception as exc:                     # noqa: BLE001 - surfaced, not scored
            points.append(StressPoint(condition_id, FAMILY_OF[condition_id],
                                      float("nan"), "ERROR", False,
                                      error=f"{type(exc).__name__}: {exc}"))
            continue
        p = float(_get(record, "p_fake"))
        decision = str(_get(record, "decision"))
        points.append(StressPoint(condition_id, FAMILY_OF[condition_id], p, decision,
                                  flipped=decision != clean_decision))

    scored = [p for p in points if p.error is None]
    flips = [p.condition_id for p in scored if p.flipped]
    spread = (max(p.p_fake for p in scored) - min(p.p_fake for p in scored)) if scored else 0.0
    return {
        "clean_p_fake": clean_p,
        "clean_decision": clean_decision,
        "threshold": threshold,
        "threshold_provenance": provenance,
        "points": points,
        "flips": flips,
        "n_flips": len(flips),
        "n_scored": len(scored),
        "n_errors": len(points) - len(scored),
        "score_spread": spread,
        "stable": not flips,
    }


def _get(record: Any, name: str, default=None):
    if isinstance(record, dict):
        return record.get(name, default)
    return getattr(record, name, default)


def _ordered_points(points: list[StressPoint]) -> list[StressPoint]:
    """Group by family in a fixed order; conditions keep their official order."""
    by_family: dict[str, list[StressPoint]] = {f: [] for f in FAMILY_ORDER}
    for point in points:
        by_family.setdefault(point.family, []).append(point)
    ordered: list[StressPoint] = []
    for family in FAMILY_ORDER:
        ordered.extend(by_family.get(family, []))
    return ordered


def render_stress_svg(result: dict, width: int = 760, height: int = 300) -> str:
    """Inline SVG chart. Theme-aware, no external dependency, no script."""
    points = _ordered_points(result["points"])
    if not points:
        return "<p>No stress results.</p>"

    pad_left, pad_right, pad_top, pad_bottom = 46, 14, 18, 58
    plot_w = width - pad_left - pad_right
    plot_h = height - pad_top - pad_bottom

    # 2px surface gap between adjacent bars (mark spec).
    slot = plot_w / len(points)
    bar_w = max(6.0, slot - 6.0)

    def y_of(value: float) -> float:
        return pad_top + plot_h * (1.0 - max(0.0, min(1.0, value)))

    parts: list[str] = []
    # Recessive gridlines + axis labels.
    for tick in (0.0, 0.25, 0.5, 0.75, 1.0):
        y = y_of(tick)
        parts.append(
            f'<line x1="{pad_left}" y1="{y:.1f}" x2="{width - pad_right}" y2="{y:.1f}" '
            f'class="afc-grid"/>'
        )
        parts.append(f'<text x="{pad_left - 8}" y="{y + 3.5:.1f}" class="afc-axis" '
                     f'text-anchor="end">{tick:.2f}</text>')

    # Bars.
    family_spans: dict[str, list[float]] = {}
    for i, point in enumerate(points):
        x = pad_left + i * slot + (slot - bar_w) / 2
        family_spans.setdefault(point.family, []).append(x + bar_w / 2)
        if point.error is not None:
            parts.append(
                f'<rect x="{x:.1f}" y="{pad_top:.1f}" width="{bar_w:.1f}" '
                f'height="{plot_h:.1f}" class="afc-bar-error"><title>'
                f'{html.escape(point.condition_id)}: {html.escape(point.error)}</title></rect>'
            )
            continue
        y = y_of(point.p_fake)
        bar_h = max(1.5, pad_top + plot_h - y)
        cls = "afc-bar-flip" if point.flipped else "afc-bar"
        parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{bar_h:.1f}" '
            f'rx="3" class="{cls}"><title>{html.escape(point.condition_id)} — '
            f'p_fake {point.p_fake:.4f} — {html.escape(point.decision)}'
            f'{" (VERDICT FLIPPED)" if point.flipped else ""}</title></rect>'
        )
        if point.flipped:
            # Secondary encoding: a caret, so a flip is never colour-only.
            cx = x + bar_w / 2
            parts.append(f'<path d="M{cx - 4:.1f} {y - 4:.1f} L{cx:.1f} {y - 10:.1f} '
                         f'L{cx + 4:.1f} {y - 4:.1f} Z" class="afc-flip-mark"/>')

    # Reference rules: threshold (solid) and the clean score (dashed).
    ty = y_of(result["threshold"])
    parts.append(f'<line x1="{pad_left}" y1="{ty:.1f}" x2="{width - pad_right}" '
                 f'y2="{ty:.1f}" class="afc-threshold"/>')
    parts.append(f'<text x="{width - pad_right}" y="{ty - 5:.1f}" class="afc-rule-label" '
                 f'text-anchor="end">decision threshold {result["threshold"]:.3f}</text>')
    cy = y_of(result["clean_p_fake"])
    parts.append(f'<line x1="{pad_left}" y1="{cy:.1f}" x2="{width - pad_right}" '
                 f'y2="{cy:.1f}" class="afc-clean"/>')
    parts.append(f'<text x="{pad_left + 4}" y="{cy - 5:.1f}" class="afc-rule-label">'
                 f'clean score {result["clean_p_fake"]:.3f}</text>')

    # Family labels beneath, centred on each group.
    for family, centres in family_spans.items():
        cx = sum(centres) / len(centres)
        parts.append(f'<text x="{cx:.1f}" y="{height - 34:.1f}" class="afc-family" '
                     f'text-anchor="middle">{html.escape(family)}</text>')

    parts.append(f'<line x1="{pad_left}" y1="{pad_top + plot_h:.1f}" '
                 f'x2="{width - pad_right}" y2="{pad_top + plot_h:.1f}" class="afc-axis-line"/>')
    parts.append(f'<text x="{pad_left}" y="{height - 12:.1f}" class="afc-axis">'
                 f'p(AI-generated) under each official transformation — higher is more likely AI'
                 f'</text>')

    return (f'<svg viewBox="0 0 {width} {height}" width="100%" role="img" '
            f'aria-label="Score under each official transformation" '
            f'class="afc-chart">{"".join(parts)}</svg>')


def render_stress_table(result: dict) -> str:
    """Table view — required so the chart is never the only way to read the data."""
    rows = [
        "<table class='afc-table'><thead><tr><th>condition</th><th>family</th>"
        "<th>p_fake</th><th>verdict</th><th>vs clean</th></tr></thead><tbody>"
    ]
    for point in _ordered_points(result["points"]):
        if point.error is not None:
            rows.append(f"<tr><td>{html.escape(point.condition_id)}</td>"
                        f"<td>{html.escape(point.family)}</td><td>—</td>"
                        f"<td>error</td><td>{html.escape(point.error)}</td></tr>")
            continue
        note = "FLIPPED" if point.flipped else ("reference" if point.condition_id == "clean" else "held")
        rows.append(
            f"<tr><td>{html.escape(point.condition_id)}</td>"
            f"<td>{html.escape(point.family)}</td><td>{point.p_fake:.4f}</td>"
            f"<td>{html.escape(point.decision)}</td><td>{note}</td></tr>"
        )
    rows.append("</tbody></table>")
    return "".join(rows)


def render_stress_summary(result: dict) -> str:
    """The sentence a viewer should leave with."""
    n_flips, n_scored = result["n_flips"], result["n_scored"]
    provenance = result["threshold_provenance"]
    if result["stable"]:
        headline = (f"Verdict held under all {n_scored} conditions "
                    f"(score spread {result['score_spread']:.3f}).")
        tone = "afc-stable"
    else:
        flips = ", ".join(html.escape(c) for c in result["flips"])
        headline = (f"Verdict changed under {n_flips} of {n_scored} conditions: {flips}.")
        tone = "afc-unstable"

    caveat = ""
    if provenance.startswith("PLACEHOLDER"):
        caveat = ("<p class='afc-caveat'>The decision threshold is an uncalibrated "
                  f"placeholder (<code>{html.escape(provenance)}</code>), so flips shown "
                  "here reflect an operating point that has not been fitted. The score "
                  "curve itself is unaffected.</p>")
    errors = ""
    if result["n_errors"]:
        errors = (f"<p class='afc-caveat'>{result['n_errors']} condition(s) failed to "
                  "score and are shown as gaps — no score was substituted.</p>")
    return f"<p class='{tone}'>{headline}</p>{caveat}{errors}"
