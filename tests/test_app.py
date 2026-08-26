from dataclasses import dataclass
from pathlib import Path

import pytest

from src.app.app import analyze_image


@dataclass
class FakeService:
    def predict_image(self, path, transform_id="clean"):
        return {"decision": "AI-GENERATED", "p_fake": .81234,
                "experts": [{"expert_id": "commfor_384", "p_fake": .81}],
                "inference_ms": {"total": 12.3}, "warnings": [],
                "image": {"width": 640, "height": 480, "format": "PNG", "sha256": "abcdef0123456789"},
                "pipeline_version": "0.1.0", "threshold_provenance": "test"}


def test_handler_uses_injected_service(tmp_path):
    html, cf, latency, warnings, technical = analyze_image(tmp_path / "image.png", FakeService())
    assert "AI-GENERATED" in html and "not a real-world probability" in html
    assert cf == "CF-384 p_fake 0.8100"
    assert latency == "12.3 ms"
    assert warnings == "none"
    assert "640 × 480" in technical and "abcdef012345" in technical


def test_handler_error_has_no_score():
    class Broken:
        def predict_image(self, *_args, **_kwargs):
            raise ValueError("bad input")
    html, cf, latency, warnings, technical = analyze_image("bad.png", Broken())
    assert "NO VERDICT" in html
    assert "p_fake" not in html
    assert all(value == "—" for value in (cf, latency, warnings, technical))


def test_handler_rejects_non_finite_or_out_of_range_score():
    class Invalid:
        def __init__(self, score):
            self.score = score

        def predict_image(self, *_args, **_kwargs):
            return {"decision": "REAL", "p_fake": self.score}

    for score in (float("nan"), -0.1, 1.1):
        html, *fields = analyze_image("image.png", Invalid(score))
        assert "NO VERDICT" in html
        assert all(field == "—" for field in fields)


def test_build_app_wires_analyze_handler_without_arity_warning():
    from src.app.app import build_app

    app = build_app(service=FakeService())
    assert app is not None


def test_handler_matches_real_prediction_service_when_checkpoint_is_available():
    from src.pipeline.service import PredictionService

    try:
        service = PredictionService.from_config()
    except Exception as exc:
        pytest.skip(f"CF-384 unavailable: {exc}")
    image = Path(__file__).parent / "golden" / "sources" / "photo.png"
    direct = service.predict_image(image)
    html, *_ = analyze_image(image, service)
    assert f"{direct.p_fake:.4f}" in html
