"""Prediction-service DoD (core spec v2 §6).

The parity test is the one that matters: the CLI and a direct import must
produce the SAME p_fake, because the whole point of the importable service is
that the demo, the batch script and the eval harness cannot drift apart.

Skipped when the CF-384 checkpoint is not available locally (offline CI).
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from src.pipeline.service import PredictionError, PredictionService

ROOT = Path(__file__).resolve().parents[1]
IMAGE = ROOT / "tests" / "golden" / "sources" / "photo.png"


@pytest.fixture(scope="module")
def service():
    try:
        return PredictionService.from_config()
    except Exception as exc:  # checkpoint unavailable / offline
        pytest.skip(f"CF-384 unavailable: {exc}")


def test_record_shape_and_invariants(service):
    r = service.predict_image(IMAGE)
    d = r.to_json_dict()
    assert d["schema_version"] == "prediction.v1"
    assert 0.0 <= d["p_fake"] <= 1.0
    assert d["forced_prediction"] in (0, 1)
    assert d["decision"] in ("REAL", "AI-GENERATED")
    assert d["reliability"] is None          # no validated estimator in Phase 0
    assert d["rescue_invoked"] is False      # rescue lands in Phase 3
    assert d["expert_failures"] == []
    assert d["experts"] and d["experts"][0]["expert_id"] == "commfor_384"
    assert d["pipeline_version"] and d["threshold_provenance"].startswith("PLACEHOLDER")


def test_threshold_boundary_predicts_fake(service):
    # p_fake == threshold must predict AI-generated (matches the eval contract).
    r = service.predict_image(IMAGE)
    service_at = PredictionService(service.experts, threshold=r.p_fake)
    assert service_at.predict_image(IMAGE).forced_prediction == 1


def test_determinism_across_calls(service):
    a = service.predict_image(IMAGE).p_fake
    b = service.predict_image(IMAGE).p_fake
    assert a == b


def test_transform_changes_score_path(service):
    clean = service.predict_image(IMAGE, transform_id="clean")
    blurred = service.predict_image(IMAGE, transform_id="blur_s2.0")
    assert blurred.transform_id == "blur_s2.0"
    assert blurred.inference_ms["components"]["transform"] > 0.0
    assert clean.inference_ms["components"]["transform"] == 0.0


def test_cli_matches_imported_service(service):
    """The parity guarantee: one decision path, two entry points."""
    direct = service.predict_image(IMAGE)
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "predict.py"), str(IMAGE), "--json"],
        capture_output=True, text=True, cwd=ROOT,
    )
    assert proc.returncode == 0, proc.stderr
    cli = json.loads(proc.stdout)
    assert cli["p_fake"] == direct.p_fake
    assert cli["forced_prediction"] == direct.forced_prediction
    assert cli["decision"] == direct.decision


def test_decode_failure_propagates_not_scored(service, tmp_path):
    from src.pipeline.decode import DecodeError

    bad = tmp_path / "bad.png"
    bad.write_bytes(b"not an image")
    with pytest.raises(DecodeError):  # never a fabricated score
        service.predict_image(bad)


def test_all_experts_failing_raises(service, monkeypatch):
    from src.experts.base import ExpertInferenceError

    class Broken:
        expert_id = "broken"
        param_count = 0
        license = "n/a"
        model_version = None

        def predict(self, img):
            raise ExpertInferenceError(self.expert_id, "inference_failed", "boom")

    broken = PredictionService([Broken()], threshold=0.5)
    with pytest.raises(PredictionError):
        broken.predict_image(IMAGE)


def test_service_requires_at_least_one_expert():
    with pytest.raises(ValueError):
        PredictionService([], threshold=0.5)


# --- B-012 review fixes: init-failure handling, warning aggregation, validation ---
class _InitFailingExpert:
    def __init__(self, device=None):
        from src.experts.base import ExpertInitError

        raise ExpertInitError("broken_expert", "load_failed", "scripted failure")


def test_from_config_with_explicit_experts_records_no_init_failures(service):
    """Regression: init_failures was unbound on this path (NameError)."""
    built = PredictionService.from_config(
        config={"threshold": 0.5, "fusion": "naive_mean", "experts": []},
        experts=service.experts,
    )
    assert built.init_failures == []


def test_init_failure_is_survived_when_another_expert_works(service):
    """One failed factory must not abort construction (B-012 #1)."""
    built = PredictionService.from_config(
        config={"threshold": 0.5, "fusion": "naive_mean",
                "experts": [{"id": "broken", "enabled": True},
                            {"id": "good", "enabled": True}]},
        registry={"broken": _InitFailingExpert,
                  "good": lambda device=None: service.experts[0]},
    )
    assert len(built.experts) == 1
    assert [f["expert_id"] for f in built.init_failures] == ["broken_expert"]
    assert built.init_failures[0]["reason_code"] == "load_failed"
    # the surviving expert still produces a real verdict
    assert 0.0 <= built.predict_image(IMAGE).p_fake <= 1.0


def test_zero_surviving_experts_is_fatal():
    """Every expert failing must raise, never yield a scoreless service."""
    from src.experts.base import ExpertInitError

    with pytest.raises(ExpertInitError, match="no_experts_available"):
        PredictionService.from_config(
            config={"threshold": 0.5, "fusion": "naive_mean",
                    "experts": [{"id": "broken", "enabled": True}]},
            registry={"broken": _InitFailingExpert},
        )


def test_disabled_expert_is_not_an_init_failure(service):
    built = PredictionService.from_config(
        config={"threshold": 0.5, "fusion": "naive_mean",
                "experts": [{"id": "broken", "enabled": False},
                            {"id": "good", "enabled": True}]},
        registry={"broken": _InitFailingExpert,
                  "good": lambda device=None: service.experts[0]},
    )
    assert built.init_failures == []


def test_expert_warnings_reach_the_record(service):
    """The 256x192 golden image triggers CF's upsampled_before_crop warning.

    Before this fix the UI showed warnings='none' while the expert was warning
    (B-012 #2).
    """
    record = service.predict_image(IMAGE)
    assert any(w.startswith("commfor_384:") for w in record.warnings)
    assert any("upsampled_before_crop" in w for w in record.warnings)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -0.1, 1.5])
def test_invalid_threshold_fails_closed(service, bad):
    with pytest.raises(ValueError, match="threshold"):
        PredictionService(service.experts, threshold=bad)


def test_unknown_fusion_is_rejected(service):
    with pytest.raises(ValueError, match="unknown fusion"):
        PredictionService(service.experts, threshold=0.5, fusion="router_v2")


def test_entropy_helpers_agree():
    """features.binary_entropy_array must be the canonical scalar, vectorized."""
    import numpy as np

    from src.router.calibration import binary_entropy
    from src.router.features import binary_entropy_array

    probs = np.array([0.0, 0.01, 0.3, 0.5, 0.77, 1.0])
    expected = np.array([binary_entropy(float(p)) for p in probs])
    assert np.allclose(binary_entropy_array(probs), expected)
