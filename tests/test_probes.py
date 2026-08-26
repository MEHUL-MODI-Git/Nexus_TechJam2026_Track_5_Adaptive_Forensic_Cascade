"""Self-probe tests (doc 03 step 4).

Feature math is tested against a stub expert with scripted scores so the
assertions are exact; integration with the real adapter is tested separately.
"""

from dataclasses import replace
from pathlib import Path

import pytest
from PIL import Image

from src.experts.base import ExpertInferenceError, ExpertOutput
from src.pipeline.decode import decode_image
from src.pipeline.probes import (
    PROBE_IDS,
    SCHEMA_VERSION,
    apply_probe,
    compute_probe_features,
    load_probe_config,
)
from src.pipeline.transforms import CONDITION_IDS
from src.pipeline.version import PROBE_VERSION

GOLDEN = Path(__file__).parent / "golden" / "sources"


class StubExpert:
    """Returns scripted p_fake values in call order; optionally fails on some."""

    expert_id = "stub"
    param_count = 0
    license = "n/a"
    model_version = None

    def __init__(self, scores, fail_on=()):
        self.scores = list(scores)
        self.fail_on = set(fail_on)
        self.calls = 0

    def predict(self, img):
        i = self.calls
        self.calls += 1
        if i in self.fail_on:
            raise ExpertInferenceError(self.expert_id, "inference_failed", "scripted")
        p = self.scores[i]
        return ExpertOutput(self.expert_id, raw_logit=0.0, p_fake=p, inference_ms=1.0)


@pytest.fixture
def decoded():
    return decode_image(GOLDEN / "photo.png")


# --- namespace separation -------------------------------------------------
def test_exactly_three_probes():
    assert len(PROBE_IDS) == 3


def test_probe_ids_cannot_collide_with_official_conditions():
    assert all(pid.startswith("probe_") for pid in PROBE_IDS)
    assert not set(PROBE_IDS) & set(CONDITION_IDS)


def test_probe_version_drift_is_fatal(tmp_path):
    import yaml

    cfg = dict(load_probe_config(), probe_version="9.9.9")
    bad = tmp_path / "p.yaml"
    bad.write_text(yaml.safe_dump(cfg))
    with pytest.raises(RuntimeError, match="PROBE_VERSION"):
        load_probe_config(bad)


def test_unknown_probe_id_is_hard_error(decoded):
    with pytest.raises(KeyError):
        apply_probe(decoded.image, "probe_nope", decoded.sha256)


# --- probe transforms are MILD -------------------------------------------
def test_probes_are_deterministic(decoded):
    import numpy as np

    for pid in PROBE_IDS:
        a = np.array(apply_probe(decoded.image, pid, decoded.sha256))
        b = np.array(apply_probe(decoded.image, pid, decoded.sha256))
        assert np.array_equal(a, b)


def test_probe_geometry(decoded):
    w, h = decoded.image.size
    assert apply_probe(decoded.image, "probe_crop_0.96", decoded.sha256).size == (
        round(w * 0.96), round(h * 0.96)
    )
    # resize probe goes down then back up, so it returns to the original size
    assert apply_probe(decoded.image, "probe_resize_0.90", decoded.sha256).size == (w, h)
    assert apply_probe(decoded.image, "probe_jpeg_q92", decoded.sha256).size == (w, h)


def test_probes_change_pixels_only_mildly(decoded):
    """A probe must perturb the image, but far less than an official condition."""
    import numpy as np

    from src.pipeline.transforms import apply_transform

    ref = np.array(decoded.image, dtype=np.int32)
    mild = np.abs(np.array(apply_probe(decoded.image, "probe_jpeg_q92", decoded.sha256),
                           dtype=np.int32) - ref).mean()
    harsh = np.abs(np.array(apply_transform(decoded.image, "jpeg_q30", decoded.sha256),
                            dtype=np.int32) - ref).mean()
    assert 0 < mild < harsh


# --- feature math ---------------------------------------------------------
def test_feature_math_exact(decoded):
    # base 0.40, probes 0.50 / 0.30 / 0.40
    expert = StubExpert([0.40, 0.50, 0.30, 0.40])
    f = compute_probe_features(expert, decoded, threshold=0.5)
    assert f.schema_version == SCHEMA_VERSION and f.probe_version == PROBE_VERSION
    assert f.base_p_fake == 0.40
    assert f.n_probes_ok == 3
    assert f.probe_mean == pytest.approx(0.40)          # mean of [.4,.5,.3,.4]
    assert f.probe_range == pytest.approx(0.20)         # .5 - .3
    assert f.probe_max_delta == pytest.approx(0.10)     # |.4 - .5|
    assert f.probe_std == pytest.approx(0.0707106781, abs=1e-6)  # population stdev
    assert f.threshold_used == 0.5


def test_probe_flip_detected_when_label_changes(decoded):
    # base 0.49 -> REAL; one probe 0.51 -> AI-GENERATED at threshold 0.5
    f = compute_probe_features(StubExpert([0.49, 0.51, 0.49, 0.49]), decoded, threshold=0.5)
    assert f.probe_flip is True


def test_no_flip_when_all_on_same_side(decoded):
    f = compute_probe_features(StubExpert([0.10, 0.20, 0.05, 0.30]), decoded, threshold=0.5)
    assert f.probe_flip is False


def test_stable_expert_has_zero_spread(decoded):
    f = compute_probe_features(StubExpert([0.8] * 4), decoded, threshold=0.5)
    assert f.probe_std == pytest.approx(0.0)
    assert f.probe_range == pytest.approx(0.0)
    assert f.probe_max_delta == pytest.approx(0.0)
    assert f.probe_flip is False


def test_base_score_reused_when_supplied(decoded):
    expert = StubExpert([0.11, 0.22, 0.33])  # no clean call scripted
    f = compute_probe_features(expert, decoded, threshold=0.5, base_p_fake=0.99)
    assert f.base_p_fake == 0.99
    assert expert.calls == 3  # clean forward pass skipped


# --- failure discipline ---------------------------------------------------
def test_failed_probe_is_recorded_not_invented(decoded):
    expert = StubExpert([0.40, 0.50, 0.30, 0.40], fail_on={2})
    f = compute_probe_features(expert, decoded, threshold=0.5)
    assert f.n_probes_ok == 2
    assert len(f.probe_failures) == 1
    assert f.probe_failures[0]["probe_id"] in PROBE_IDS
    assert "p_fake" not in f.probe_failures[0]
    assert len(f.probe_scores) == 2                 # no placeholder entry
    assert f.probe_mean is not None                 # still honest over what worked


def test_all_probes_failing_yields_null_features_not_zeros(decoded):
    expert = StubExpert([0.40, 0.0, 0.0, 0.0], fail_on={1, 2, 3})
    f = compute_probe_features(expert, decoded, threshold=0.5)
    assert f.n_probes_ok == 0
    assert f.probe_mean is None and f.probe_std is None
    assert f.probe_range is None and f.probe_max_delta is None
    assert f.probe_flip is None                     # unknown, NOT False
    assert len(f.probe_failures) == 3


def test_json_dict_is_serializable(decoded):
    import json

    f = compute_probe_features(StubExpert([0.4, 0.5, 0.3, 0.4]), decoded, threshold=0.5)
    assert json.loads(json.dumps(f.to_json_dict()))["expert_id"] == "stub"


# --- integration with the real adapter ------------------------------------
@pytest.fixture(scope="module")
def real_expert():
    try:
        from src.experts.commfor import CommForExpert

        return CommForExpert()
    except Exception as exc:
        pytest.skip(f"CF-384 unavailable: {exc}")


def test_real_expert_probe_features_are_sane(real_expert, decoded):
    f = compute_probe_features(real_expert, decoded, threshold=0.5)
    assert f.n_probes_ok == 3
    assert set(f.probe_scores) == set(PROBE_IDS)
    assert all(0.0 <= v <= 1.0 for v in f.probe_scores.values())
    assert f.probe_range >= 0.0


def test_tiny_image_survives_all_probes(real_expert, tmp_path):
    import numpy as np

    p = tmp_path / "t.png"
    Image.fromarray(np.full((6, 6, 3), 128, dtype=np.uint8)).save(p)
    f = compute_probe_features(real_expert, decode_image(p), threshold=0.5)
    assert f.n_probes_ok == 3
