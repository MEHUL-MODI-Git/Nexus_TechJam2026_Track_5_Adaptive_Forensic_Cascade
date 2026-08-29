"""Gradio v0 shell; all prediction decisions remain in ``PredictionService``."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

_SERVICE_IMPORT_ERROR: Exception | None = None
try:
    # Keep the UI handler importable for lightweight UI tests even when the
    # optional model/runtime dependencies are not installed yet.
    from src.pipeline.service import DecodeError, PredictionError, PredictionService
except ModuleNotFoundError as _service_import_error:  # pragma: no cover - environment dependent
    _SERVICE_IMPORT_ERROR = _service_import_error
    PredictionService = None  # type: ignore[assignment,misc]
    DecodeError = type("DecodeError", (Exception,), {})
    PredictionError = type("PredictionError", (Exception,), {})

THEME_PATH = Path(__file__).with_name("theme.css")

_DEGRADATION_REPORTER = None
_DEGRADATION_TRIED = False


def _degradation_reporter():
    """Lazy, fail-soft. An explanation is a nice-to-have: if the model is not
    present the UI simply omits the line rather than breaking a verdict."""
    global _DEGRADATION_REPORTER, _DEGRADATION_TRIED
    if not _DEGRADATION_TRIED:
        _DEGRADATION_TRIED = True
        try:
            from ..pipeline.degradation import DegradationReporter

            _DEGRADATION_REPORTER = DegradationReporter.load()
        except Exception:                     # noqa: BLE001 - explanation is optional
            _DEGRADATION_REPORTER = None
    return _DEGRADATION_REPORTER


class _UnavailableService:
    """Keeps the default UI launchable when local model setup is incomplete."""

    def __init__(self, error: Exception):
        self.error = error

    def predict_image(self, *_args, **_kwargs):
        raise PredictionError(f"Prediction service setup unavailable: {self.error}")


def _default_service() -> PredictionService | _UnavailableService:
    if PredictionService is None:
        return _UnavailableService(_SERVICE_IMPORT_ERROR or RuntimeError("service import failed"))
    try:
        return PredictionService.from_config()
    except Exception as exc:  # setup errors belong in the UI, not a fake verdict
        return _UnavailableService(exc)


def _field(record: Any, name: str, default=None):
    return record.get(name, default) if isinstance(record, dict) else getattr(record, name, default)


def _render_error(exc: Exception):
    if isinstance(exc, DecodeError):
        message = f"Image could not be decoded: {exc.reason}"
    elif isinstance(exc, PredictionError):
        message = str(exc)
    else:
        message = f"Analysis failed: {type(exc).__name__}: {exc}"
    html = ("<section class='result-card error-card' role='alert'>"
            "<div class='verdict'>⚠ NO VERDICT</div>"
            f"<p>{_escape(message)}</p><p class='disclaimer'>No score was produced.</p></section>")
    return html, "—", "—", "—", "—"


def _escape(value: Any) -> str:
    import html
    return html.escape(str(value))


def analyze_image(image_path: str | Path | None, service: Any):
    """Handler kept independent of Gradio for deterministic tests."""
    if not image_path:
        return _render_error(ValueError("Upload an image to begin."))
    try:
        record = service.predict_image(str(image_path), transform_id="clean")
    except Exception as exc:
        return _render_error(exc)

    decision = str(_field(record, "decision", "")).upper()
    if decision not in {"REAL", "AI-GENERATED"}:
        return _render_error(PredictionError("Service returned an invalid decision."))
    icon = "✦" if decision == "AI-GENERATED" else "◉"
    p_fake = _field(record, "p_fake")
    try:
        numeric_score = float(p_fake)
    except (TypeError, ValueError):
        return _render_error(PredictionError("Service returned an invalid score."))
    if not math.isfinite(numeric_score) or not 0.0 <= numeric_score <= 1.0:
        return _render_error(PredictionError("Service returned an out-of-range score."))
    score = f"{numeric_score:.4f}"
    threshold_provenance = str(_field(record, "threshold_provenance", ""))
    placeholder_threshold = threshold_provenance.upper().startswith("PLACEHOLDER")
    if placeholder_threshold:
        html = (
            "<section class='result-card placeholder-card' role='status'>"
            "<div class='verdict'>⌁ BASELINE SIGNAL</div>"
            f"<p class='score-label'>Model score · p_fake <span class='score'>{score}</span></p>"
            f"<p class='placeholder-verdict'>Placeholder verdict: <strong>{icon} {_escape(decision)}</strong>"
            " — operating point not calibrated.</p>"
            "<p class='disclaimer'>Provisional research result — p_fake is not a real-world probability. "
            "A held-out development set will set the operating point.</p></section>"
        )
    else:
        html = (
            "<section class='result-card' role='status'>"
            f"<div class='verdict'>{icon} {_escape(decision)}</div>"
            f"<p class='score-label'>Model score · p_fake <span class='score'>{score}</span></p>"
            "<p class='disclaimer'>Research prototype output; do not treat one score as forensic proof.</p>"
            "</section>"
        )

    # --- [relay] Phase 3: show the cascade's own reasoning, not just a score ---
    # Three things a viewer needs and could not previously see: what the raw
    # primary would have said, how reliable the system judges its own answer,
    # and whether it is declining to decide at all.
    router_block = _field(record, "router", None)
    reliability = _field(record, "reliability", None)
    abstain = bool(_field(record, "abstain", False))
    extra = ""
    if router_block is not None:
        primary_p = _field(router_block, "primary_p_fake", None)
        try:
            primary_f = float(primary_p)
            moved = numeric_score - primary_f
            extra += (
                "<p class='router-line'>Primary CF-384 alone: "
                f"<strong>{primary_f:.4f}</strong> &rarr; after router correction: "
                f"<strong>{numeric_score:.4f}</strong> "
                f"<span class='delta'>({moved:+.4f})</span></p>"
            )
        except (TypeError, ValueError):
            pass
    try:
        rel_f = float(reliability)
        extra += (
            f"<p class='router-line'>Self-assessed reliability: <strong>{rel_f:.3f}</strong></p>"
        )
    except (TypeError, ValueError):
        pass
    # Why is it unsure? Read the degradation the image already carries. This is
    # an EXPLANATION and never touches the verdict.
    quality = _field(router_block, "quality", None) if router_block is not None else None
    reporter = _degradation_reporter()
    if quality and reporter is not None:
        try:
            rep = reporter.report(quality)
            weak = ("  <span class='degr-weak'>&#9888; our detector is measurably "
                    "weakest under this condition</span>" if rep.detector_is_weak_here else "")
            caveat = (f"<br><span class='degr-caveat'>{_escape(rep.caveat)}</span>"
                      if rep.caveat else "")
            extra += (f"<p class='router-line degr-line'>Detected image history: "
                      f"<strong>{_escape(rep.label)}</strong> "
                      f"({rep.confidence:.0%} confidence){weak}{caveat}</p>")
        except Exception as exc:              # noqa: BLE001 - explanation is optional
            # A failed EXPLANATION must never cost the user their verdict, so it
            # degrades to a visible note rather than an exception or a silence.
            extra += ("<p class='router-line degr-caveat'>Image-history analysis "
                      f"unavailable ({_escape(type(exc).__name__)}).</p>")

    if abstain:
        reason = _escape(str(_field(record, "abstain_reason", "") or ""))
        extra += (
            # R8 (Codex review): this said "unstable under probes", but the probe
            # ablation shows probes buy nothing and abstention is triggered by the
            # fitted reliability value, not a probe-instability rule.
            "<p class='abstain-banner'><strong>&#9888; DEFERRED — low self-assessed "
            "reliability.</strong> The system declines to decide this image and "
            "recommends human review."
            + (f"<br><span class='abstain-reason'>{reason}</span>" if reason else "")
            + "</p>"
        )
    if extra:
        html = html.replace("</section>", extra + "</section>", 1)

    experts = _field(record, "experts", []) or []
    cf_score = None
    for expert in experts:
        eid = _field(expert, "expert_id", "")
        if "cf" in str(eid).lower() or "commfor" in str(eid).lower():
            cf_score = _field(expert, "p_fake")
            break
    try:
        numeric_cf = float(cf_score)
        cf_text = (
            f"CF-384 p_fake {numeric_cf:.4f}"
            if math.isfinite(numeric_cf) and 0.0 <= numeric_cf <= 1.0
            else "CF-384 score unavailable"
        )
    except (TypeError, ValueError):
        cf_text = "CF-384 score unavailable"
    latency = _field(record, "inference_ms", {}) or {}
    latency_text = f"{float(_field(latency, 'total', 0)):.1f} ms"
    warnings = _field(record, "warnings", []) or []
    warning_text = ", ".join(map(str, warnings)) if warnings else "none"
    image = _field(record, "image", {}) or {}
    technical = (f"Dimensions: {_field(image, 'width', '—')} × {_field(image, 'height', '—')}\n"
                 f"Format: {_field(image, 'format', '—') or 'unknown'}\n"
                 f"Content hash: {str(_field(image, 'sha256', '—'))[:12]}…\n"
                 f"Pipeline version: {_field(record, 'pipeline_version', '—')}\n"
                 f"Config/threshold provenance: {threshold_provenance or '—'}\n"
                 f"Fusion: {_field(record, 'fusion', '—')}"
                 + (f" (rung {_field(router_block, 'rung', '—')}, "
                    f"{_field(router_block, 'n_parameters', '—')} params)"
                    if router_block is not None else ""))
    return html, cf_text, latency_text, warning_text, technical


def stress_test_image(image_path: str | Path | None, service: Any):
    """[relay] Task 1.5 handler: run the official grid live and render the panel.

    Mirrors `analyze_image`'s contract — returns display strings only, raises
    nothing at the UI boundary, and never fabricates a score for a condition
    that failed.
    """
    from .stress import (
        render_stress_summary,
        render_stress_svg,
        render_stress_table,
        run_stress_grid,
    )

    if image_path is None:
        return ("<p class='afc-idle'>Upload an image, then run the stress test.</p>", "", "")
    try:
        result = run_stress_grid(service, image_path)
    except Exception as exc:  # noqa: BLE001 - the UI must not crash on a bad file
        message = _render_error(exc)
        html_message = message[0] if isinstance(message, tuple) else str(message)
        return (html_message, "", "")
    # The certificate leads: it is the sentence a moderator can act on, and its
    # grade is a measured retention->accuracy relationship, not a label we chose.
    from .certificate import build_certificate, render_certificate

    certificate = render_certificate(build_certificate(result))
    return (certificate + render_stress_summary(result), render_stress_svg(result),
            render_stress_table(result))


def build_app(service=None):
    """Build the UI using an injected service (or the configured local service)."""
    try:
        import gradio as gr
    except ImportError as exc:
        raise RuntimeError("Gradio is required to build the app (install gradio).") from exc
    predictor = service if service is not None else _default_service()
    # Accept a factory as well as an already-built service. This keeps model
    # construction outside the UI and makes tests able to inject a tiny fake.
    if callable(predictor) and not hasattr(predictor, "predict_image"):
        try:
            predictor = predictor()
        except Exception as exc:
            predictor = _UnavailableService(exc)
    css = THEME_PATH.read_text(encoding="utf-8")
    with gr.Blocks(title="Adaptive Forensic Cascade", css=css, theme=gr.themes.Base()) as demo:
        with gr.Column(elem_classes="lab-shell"):
            gr.HTML("<header class='lab-header'><div class='lab-kicker'>Adaptive Forensic Cascade / CF-384</div><div class='lab-title'>Forensic Lab</div><div class='lab-scope'>A robust AI-image detection prototype for investigating synthetic-image signals.</div></header>")
            gr.Markdown("Upload an image for local analysis. Supported formats: JPEG, PNG, WEBP, and other formats accepted by the decoder.")
            image = gr.Image(label="Image to analyze", type="filepath", sources=["upload"])
            analyze = gr.Button("Analyze image", variant="primary")
            result = gr.HTML(label="Analysis result", value="<section class='result-card'><div class='verdict'>Awaiting image</div><p class='disclaimer'>No image has been analyzed.</p></section>")
            with gr.Row(elem_classes="evidence"):
                cf = gr.Textbox(label="CF-384 score", value="—", interactive=False)
                latency = gr.Textbox(label="Inference latency", value="—", interactive=False)
                warnings = gr.Textbox(label="Decode / preprocessing warnings", value="—", interactive=False)
            with gr.Accordion("Technical details", open=False):
                technical = gr.Textbox(label="Provenance", value="—", interactive=False, lines=5)

            # [relay] Task 1.5 — the stress panel. Runs all 20 official
            # conditions on the uploaded image (~0.7 s) and shows whether the
            # verdict survives them. This is the demo's central claim: a clean
            # score does not tell you whether a detector holds up.
            gr.HTML("<h2 class='afc-heading'>Robustness stress test</h2>"
                    "<p class='afc-intro'>Re-scores this image under all 20 official "
                    "transformations — compression, blur, resizing, noise, colour "
                    "shifts and cropping — and reports whether the verdict survives "
                    "them. A detector can be confident on a clean image and still "
                    "change its mind after a re-post.</p>")
            stress_button = gr.Button("Stress-test this image", variant="secondary")
            stress_summary = gr.HTML(value="<p class='afc-idle'>Not run yet.</p>")
            stress_chart = gr.HTML(value="")
            with gr.Accordion("Stress results table", open=False):
                stress_table = gr.HTML(value="")

            def _analyze_uploaded(image_path):
                return analyze_image(image_path, predictor)

            def _stress_uploaded(image_path):
                return stress_test_image(image_path, predictor)

            analyze.click(
                _analyze_uploaded,
                inputs=[image],
                outputs=[result, cf, latency, warnings, technical],
                api_name="analyze",
            )
            stress_button.click(
                _stress_uploaded,
                inputs=[image],
                outputs=[stress_summary, stress_chart, stress_table],
                api_name="stress_test",
            )
    return demo


__all__ = ["analyze_image", "build_app", "stress_test_image"]
