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
    # Stage 2 fitted the reliability head against the frozen threshold, so a
    # calibrated-ish confidence is now reported. It must be a real number in
    # range -- and it must still be None on any checkpoint where the head was
    # NOT fitted, which `test_unfitted_reliability_head_reports_none` covers.
    assert isinstance(d["reliability"], float)
    assert 0.0 <= d["reliability"] <= 1.0
    assert isinstance(d["abstain"], bool)
    assert d["rescue_invoked"] is False      # rescue lands in Phase 3
    assert d["expert_failures"] == []
    assert d["experts"] and d["experts"][0]["expert_id"] == "commfor_384"
    assert d["pipeline_version"]
    # The shipped config serves the FROZEN cascade. The provenance string is the
    # guard that the demo and README section 7 describe the same system: a
    # regression to the placeholder threshold would silently make the demo
    # report the uncalibrated baseline again.
    assert d["fusion"] == "router"
    assert d["threshold_provenance"].startswith("frozen:")
    assert d["router"] and d["router"]["rung"] == "mlp"
    assert d["router"]["n_parameters"] == 1827


def test_threshold_boundary_predicts_fake(service):
    # p_fake == threshold must predict AI-generated (matches the eval contract).
    # The rule under test is the comparison itself (`>=`), so it is checked on
    # the baseline path. The routed path cannot be re-thresholded at all -- see
    # `test_router_refuses_a_threshold_that_is_not_its_frozen_one`, which is the
    # stronger guarantee.
    baseline = PredictionService(service.experts, threshold=0.5, fusion="naive_mean")
    r = baseline.predict_image(IMAGE)
    service_at = PredictionService(service.experts, threshold=r.p_fake,
                                   fusion="naive_mean")
    assert service_at.predict_image(IMAGE).forced_prediction == 1


def test_router_refuses_a_threshold_that_is_not_its_frozen_one(service):
    """The realistic regression: someone edits the YAML threshold and the demo
    silently starts deciding at a boundary the router was never fitted against.
    """
    if service.fusion != "router":
        pytest.skip("shipped config is not serving the router")
    with pytest.raises(ValueError, match="frozen threshold"):
        PredictionService(service.experts, threshold=0.5, fusion="router",
                          router=service.router)


def test_router_fusion_requires_a_router(service):
    with pytest.raises(ValueError, match="requires a loaded RouterHead"):
        PredictionService(service.experts, threshold=0.5, fusion="router")


def test_router_actually_changes_the_decision_path(service):
    """Guards against the exact defect this wiring fixed: the service reporting
    the raw primary while the README reports the cascade."""
    if service.fusion != "router":
        pytest.skip("shipped config is not serving the router")
    routed = service.predict_image(IMAGE)
    baseline = PredictionService(service.experts, threshold=0.5,
                                 fusion="naive_mean").predict_image(IMAGE)
    assert routed.router["primary_p_fake"] == pytest.approx(baseline.p_fake, abs=1e-6)
    # The router is a correction head; on a real image it must not be a no-op.
    assert routed.p_fake != pytest.approx(baseline.p_fake, abs=1e-6)


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


def test_live_path_reproduces_the_evaluated_scores(service):
    """TRAIN/SERVE PARITY -- the guarantee the whole wiring rests on.

    README section 7 reports numbers computed offline from cache rows. Those
    numbers only describe the shipped system if scoring an image through the
    live service lands in the same place. This drives real pixels through
    `PredictionService` and compares against the frozen router run over the
    cached row for the same image, which is what the one-shot evaluator did.
    """
    import json

    import numpy as np
    import torch

    from src.router.train import build_batch, load_checkpoint

    if service.fusion != "router":
        pytest.skip("shipped config is not serving the router")
    rows_path = ROOT / "data" / "feature_cache" / "internal-test-v2" / "rows.jsonl"
    if not rows_path.exists():
        pytest.skip("internal-test cache not present")

    rows = []
    with rows_path.open() as fh:
        for line in fh:
            row = json.loads(line)
            if row["condition_id"] == "clean":
                rows.append(row)
            if len(rows) == 12:
                break
    rows = [r for r in rows if (ROOT / r["relative_path"]).exists()]
    if not rows:
        pytest.skip("corpus images not present")

    loaded = load_checkpoint(ROOT / "results" / "router-fitting-v2" / "router.pt")
    batch = build_batch(rows, loaded.spec, loaded.standardizer, service.threshold)
    with torch.no_grad():
        cached = loaded.model(batch.features, batch.expert_logits,
                              batch.available).p_fake.numpy()
    live = np.array([service.predict_image(ROOT / r["relative_path"]).p_fake
                     for r in rows])

    # float32 batch-vs-single matmul differs in the last bits; a verdict must not.
    assert np.abs(live - cached).max() < 1e-5
    thr = service.threshold
    assert ((live >= thr) == (cached >= thr)).all()


def test_unfitted_reliability_head_reports_none():
    """A checkpoint whose head was never fitted must report null, not
    sigmoid(untrained layer) dressed up as a confidence."""
    from src.router.head import RouterHead

    ckpt = ROOT / "results" / "router-fitting-v2" / "router.pt"
    if not ckpt.exists():
        pytest.skip("stage-1 checkpoint not present")
    head = RouterHead.from_checkpoint(ckpt)
    assert head.reliability_fitted is False
    assert head.abstain_threshold is None


def test_abstention_threshold_is_a_frozen_value_not_a_percentile(service):
    """A percentile recomputed per batch would re-tune the policy to whatever
    data arrived. The policy must be a fixed number chosen on dev."""
    if service.fusion != "router" or not service.router.abstention_adopted:
        pytest.skip("abstention not adopted in the shipped config")
    assert service.router.abstain_threshold == pytest.approx(0.866079568862915)
    policy = service.router.payload["abstention"]
    assert policy["selected_on"] == "dev split of the fitting cache"
