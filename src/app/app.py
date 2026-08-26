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
    html = ("<section class='result-card' role='status'>"
            f"<div class='verdict'>{icon} {_escape(decision)}</div>"
            f"<p class='score-label'>Baseline model score · p_fake <span class='score'>{score}</span></p>"
            "<p class='disclaimer'>Provisional research result — p_fake is not a real-world probability.</p></section>")

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
                 f"Config/threshold provenance: {_field(record, 'threshold_provenance', '—')}")
    return html, cf_text, latency_text, warning_text, technical


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
            def _analyze_uploaded(image_path):
                return analyze_image(image_path, predictor)

            analyze.click(
                _analyze_uploaded,
                inputs=[image],
                outputs=[result, cf, latency, warnings, technical],
                api_name="analyze",
            )
    return demo


__all__ = ["build_app", "analyze_image"]
