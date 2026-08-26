"""ExpertOutput / failure-type contract (core spec v2 §4 DoD)."""

import numpy as np
import pytest

from src.experts.base import (
    MAX_INLINE_PATCH_SCORES,
    ExpertInferenceError,
    ExpertInitError,
    ExpertOutput,
)


def _out(**kw):
    base = dict(expert_id="commfor_384", raw_logit=1.5, p_fake=0.8, inference_ms=10.0)
    return ExpertOutput(**{**base, **kw})


def test_success_fields_are_non_null():
    o = _out()
    assert o.raw_logit is not None and o.p_fake is not None


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_logit_rejected(bad):
    with pytest.raises(ValueError, match="raw_logit"):
        _out(raw_logit=bad)


@pytest.mark.parametrize("bad", [-0.01, 1.01, float("nan")])
def test_p_fake_out_of_range_rejected(bad):
    with pytest.raises(ValueError, match="p_fake"):
        _out(p_fake=bad)


def test_embedding_never_serialized():
    o = _out(embedding=np.zeros((384,), dtype=np.float32))
    d = o.to_json_dict()
    assert "embedding" not in d
    assert d["embedding_present"] is True
    assert d["embedding_dim"] == 384


def test_large_patch_scores_not_inlined():
    o = _out(patch_scores=[0.1] * (MAX_INLINE_PATCH_SCORES + 1))
    d = o.to_json_dict()
    assert d["patch_scores"] is None
    assert d["patch_scores_count"] == MAX_INLINE_PATCH_SCORES + 1


def test_small_patch_scores_inlined():
    o = _out(patch_scores=[0.1, 0.2])
    assert o.to_json_dict()["patch_scores"] == [0.1, 0.2]


def test_model_version_omitted_when_absent():
    assert "model_version" not in _out().to_json_dict()
    assert _out(model_version="x@1").to_json_dict()["model_version"] == "x@1"


def test_failure_types_carry_no_score():
    err = ExpertInferenceError("commfor_384", "inference_failed", "boom", "abc")
    d = err.to_dict()
    assert set(d) == {"expert_id", "reason_code", "message", "image_sha256"}
    assert "p_fake" not in d and "raw_logit" not in d
    assert not hasattr(err, "p_fake")


def test_init_error_is_distinct_from_inference_error():
    assert not issubclass(ExpertInitError, ExpertInferenceError)
    assert not issubclass(ExpertInferenceError, ExpertInitError)
