"""Stress panel tests (task 1.5).

[relay] Claude, while Codex is limit-blocked. Codex owns src/app/ and reviews
this on return.

Beyond behaviour, these assert the chart's *geometry* — marks inside the plot
area, labels inside the viewBox — because a rendering bug in a demo is
discovered by the audience.
"""

import math
import re

import pytest

from src.app.stress import (
    CRITICAL,
    StressPoint,
    render_stress_summary,
    render_stress_svg,
    render_stress_table,
    run_stress_grid,
)
from src.pipeline.transforms import CONDITION_IDS


class FakeService:
    """Scores by condition; can be told to fail on specific ones."""

    def __init__(self, scores=None, default=0.9, fail_on=(), threshold=0.5,
                 provenance="dev-fitted"):
        self.scores = scores or {}
        self.default = default
        self.fail_on = set(fail_on)
        self.threshold = threshold
        self.provenance = provenance

    def predict_image(self, path, transform_id="clean"):
        if transform_id in self.fail_on:
            raise RuntimeError("scripted failure")
        p = self.scores.get(transform_id, self.default)
        return {"p_fake": p,
                "decision": "AI-GENERATED" if p >= self.threshold else "REAL",
                "threshold_used": self.threshold,
                "threshold_provenance": self.provenance}


# --- grid execution -------------------------------------------------------
def test_runs_every_official_condition():
    result = run_stress_grid(FakeService(), "img.png")
    assert result["n_scored"] == len(CONDITION_IDS) == 20
    assert {p.condition_id for p in result["points"]} == set(CONDITION_IDS)


def test_stable_image_reports_no_flips():
    result = run_stress_grid(FakeService(default=0.95), "img.png")
    assert result["stable"] is True
    assert result["n_flips"] == 0
    assert "held under all 20" in render_stress_summary(result)


def test_flips_are_detected_and_named():
    service = FakeService(default=0.95, scores={"noise_s0.10": 0.01, "jpeg_q30": 0.02})
    result = run_stress_grid(service, "img.png")
    assert result["stable"] is False
    assert set(result["flips"]) == {"noise_s0.10", "jpeg_q30"}
    summary = render_stress_summary(result)
    assert "noise_s0.10" in summary and "jpeg_q30" in summary


def test_clean_is_the_reference_and_never_a_flip():
    result = run_stress_grid(FakeService(default=0.9), "img.png")
    clean = next(p for p in result["points"] if p.condition_id == "clean")
    assert clean.flipped is False
    assert result["clean_p_fake"] == pytest.approx(0.9)


def test_failed_condition_is_recorded_not_scored():
    result = run_stress_grid(FakeService(fail_on={"blur_s2.0"}), "img.png")
    bad = next(p for p in result["points"] if p.condition_id == "blur_s2.0")
    assert bad.error is not None
    assert math.isnan(bad.p_fake)          # no substituted score
    assert bad.flipped is False
    assert result["n_errors"] == 1 and result["n_scored"] == 19
    assert "no score was substituted" in render_stress_summary(result)


def test_score_spread_reported():
    service = FakeService(default=0.9, scores={"noise_s0.10": 0.1})
    result = run_stress_grid(service, "img.png")
    assert result["score_spread"] == pytest.approx(0.8, abs=1e-6)


def test_placeholder_threshold_is_disclosed_in_the_summary():
    service = FakeService(default=0.95, provenance="PLACEHOLDER-uncalibrated-phase0")
    summary = render_stress_summary(run_stress_grid(service, "img.png"))
    assert "uncalibrated placeholder" in summary
    assert "PLACEHOLDER-uncalibrated-phase0" in summary


def test_real_threshold_shows_no_placeholder_caveat():
    summary = render_stress_summary(run_stress_grid(FakeService(), "img.png"))
    assert "placeholder" not in summary.lower()


# --- chart correctness ----------------------------------------------------
def _svg(result):
    return render_stress_svg(result)


def test_svg_has_one_bar_per_condition():
    svg = _svg(run_stress_grid(FakeService(), "img.png"))
    assert len(re.findall(r'class="afc-bar[^"]*"', svg)) == 20


def test_flipped_bars_use_the_reserved_status_class_and_a_marker():
    result = run_stress_grid(FakeService(default=0.95, scores={"noise_s0.10": 0.01}), "img.png")
    svg = _svg(result)
    assert 'class="afc-bar-flip"' in svg
    # secondary encoding: identity must not rest on colour alone
    assert 'class="afc-flip-mark"' in svg


def test_every_bar_has_a_hover_title():
    svg = _svg(run_stress_grid(FakeService(), "img.png"))
    assert svg.count("<title>") >= 20


def test_reference_rules_present_and_labelled():
    svg = _svg(run_stress_grid(FakeService(), "img.png"))
    assert 'class="afc-threshold"' in svg and 'class="afc-clean"' in svg
    assert "decision threshold" in svg and "clean score" in svg


def test_single_series_needs_no_legend():
    svg = _svg(run_stress_grid(FakeService(), "img.png"))
    assert "legend" not in svg.lower()


def test_svg_is_accessible_and_self_contained():
    svg = _svg(run_stress_grid(FakeService(), "img.png"))
    assert 'role="img"' in svg and "aria-label" in svg
    assert "<script" not in svg
    assert "http://" not in svg and "https://" not in svg   # no external fetches


def test_bars_stay_inside_the_plot_area():
    """Geometry check — a mark escaping the viewBox is invisible in the demo."""
    result = run_stress_grid(FakeService(scores={c: i / 20 for i, c in enumerate(CONDITION_IDS)}),
                             "img.png")
    svg = render_stress_svg(result, width=760, height=300)
    for match in re.finditer(r'<rect x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" '
                             r'height="([\d.]+)"', svg):
        x, y, w, h = (float(g) for g in match.groups())
        assert x >= 0 and y >= 0
        assert x + w <= 760 + 0.5
        assert y + h <= 300 + 0.5
        assert w > 0 and h > 0


def test_extreme_scores_do_not_overflow():
    result = run_stress_grid(FakeService(scores={"clean": 0.0, "jpeg_q30": 1.0}, default=0.5),
                             "img.png")
    svg = render_stress_svg(result)
    for match in re.finditer(r'y="(-?[\d.]+)"', svg):
        assert float(match.group(1)) >= -1


def test_chart_survives_all_conditions_failing():
    result = run_stress_grid(FakeService(fail_on=set(CONDITION_IDS) - {"clean"}), "img.png")
    svg = render_stress_svg(result)
    assert 'class="afc-bar-error"' in svg
    assert result["n_errors"] == 19


# --- table view -----------------------------------------------------------
def test_table_lists_every_condition():
    table = render_stress_table(run_stress_grid(FakeService(), "img.png"))
    for condition in CONDITION_IDS:
        assert condition in table
    assert table.count("<tr>") == 21          # header + 20 rows


def test_table_marks_flips_in_text_not_only_colour():
    result = run_stress_grid(FakeService(default=0.95, scores={"noise_s0.10": 0.01}), "img.png")
    table = render_stress_table(result)
    assert "FLIPPED" in table


def test_table_shows_errors_without_a_score():
    table = render_stress_table(run_stress_grid(FakeService(fail_on={"crop_0.8"}), "img.png"))
    assert "error" in table


def test_html_is_escaped():
    result = run_stress_grid(FakeService(), "img.png")
    result["points"].append(StressPoint("<script>x</script>", "jpeg", 0.5, "REAL", False))
    assert "<script>" not in render_stress_table(result)
