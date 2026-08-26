"""Stress panel tests (task 1.5).

[relay] Claude, while Codex is limit-blocked. Codex owns src/app/ and reviews
this on return.

Beyond behaviour, these assert the chart's *geometry* — marks inside the plot
area, labels inside the viewBox — because a rendering bug in a demo is
discovered by the audience.
"""

import math
import re
from pathlib import Path

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
                 provenance="dev-fitted", decisions=None, thresholds=None,
                 provenances=None):
        self.scores = scores or {}
        self.default = default
        self.fail_on = set(fail_on)
        self.threshold = threshold
        self.provenance = provenance
        self.decisions = decisions or {}
        self.thresholds = thresholds or {}
        self.provenances = provenances or {}

    def predict_image(self, path, transform_id="clean"):
        if transform_id in self.fail_on:
            raise RuntimeError("scripted failure")
        p = self.scores.get(transform_id, self.default)
        threshold = self.thresholds.get(transform_id, self.threshold)
        return {"p_fake": p,
                "decision": self.decisions.get(
                    transform_id, "AI-GENERATED" if p >= threshold else "REAL"
                ),
                "threshold_used": threshold,
                "threshold_provenance": self.provenances.get(
                    transform_id, self.provenance
                )}


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


@pytest.mark.parametrize("bad_score", [float("nan"), float("inf"), -0.01, 1.01])
def test_invalid_transformed_score_is_an_error_gap(bad_score):
    result = run_stress_grid(
        FakeService(scores={"jpeg_q30": bad_score}), "img.png"
    )
    bad = next(p for p in result["points"] if p.condition_id == "jpeg_q30")
    assert bad.error is not None
    assert result["n_errors"] == 1
    assert "nan" not in render_stress_svg(result).lower()


@pytest.mark.parametrize(
    "service",
    [
        FakeService(decisions={"blur_s2.0": "MAYBE"}),
        FakeService(scores={"blur_s2.0": 0.9}, decisions={"blur_s2.0": "REAL"}),
        FakeService(thresholds={"blur_s2.0": 0.4}),
        FakeService(provenances={"blur_s2.0": "different-artifact"}),
    ],
)
def test_invalid_or_inconsistent_transformed_record_is_an_error(service):
    result = run_stress_grid(service, "img.png")
    bad = next(p for p in result["points"] if p.condition_id == "blur_s2.0")
    assert bad.error is not None
    assert result["n_errors"] == 1


def test_invalid_clean_reference_aborts_the_grid():
    with pytest.raises(ValueError, match="clean p_fake"):
        run_stress_grid(FakeService(scores={"clean": float("nan")}), "img.png")


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
    assert result["stable"] is False
    summary = render_stress_summary(result)
    assert "Robustness incomplete" in summary
    assert "no observed verdict flips" in summary
    assert "held under all" not in summary


def test_incomplete_summary_names_observed_flips_without_claiming_stability():
    service = FakeService(
        scores={"noise_s0.10": 0.01},
        fail_on=set(CONDITION_IDS) - {"clean", "noise_s0.10"},
    )
    summary = render_stress_summary(run_stress_grid(service, "img.png"))
    assert "Robustness incomplete" in summary
    assert "1 observed verdict change" in summary
    assert "noise_s0.10" in summary


def test_chart_text_palette_has_normal_text_contrast_on_forced_dark_surface():
    css = Path("src/app/theme.css").read_text(encoding="utf-8")
    assert f"--afc-critical: {CRITICAL}" in css

    def luminance(color):
        rgb = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        linear = [
            c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
            for c in rgb
        ]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    def contrast(foreground, background):
        high, low = sorted((luminance(foreground), luminance(background)), reverse=True)
        return (high + 0.05) / (low + 0.05)

    for foreground in ("#d0cec4", CRITICAL, "#f6c453"):
        assert contrast(foreground, "#111315") >= 4.5


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
