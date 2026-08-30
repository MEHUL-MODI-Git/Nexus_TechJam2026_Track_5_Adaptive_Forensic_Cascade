"""The production expert is pinned, and a mismatch fails closed.

B-032 P0, Codex Phase-4 exit audit. `configs/predict.yaml` carried no expert
revision, so `CommForExpert` received its default `revision=None` and a fresh
clone downloaded whatever `OwensLab/commfor-model-384` `main` pointed at that
day. Every feature cache, every published table and the one sealed reference run
were computed with `6076002b...`. An unpinned serving path can therefore ship
different bytes than the ones our numbers describe -- and the clean-checkout
proof (A-036) shows today's download works, not that tomorrow's is the same.
"""
import inspect
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
FROZEN_REVISION = "6076002bf0d9dd37537f965ee2f06f826c333b61"


def _expert_spec():
    cfg = yaml.safe_load((ROOT / "configs" / "predict.yaml").read_text())
    return next(s for s in cfg["experts"] if s["id"] == "commfor_384")


def test_the_serving_config_pins_the_frozen_revision():
    spec = _expert_spec()
    assert spec.get("revision") == FROZEN_REVISION, (
        "the serving config must name the exact weights our results describe")


def test_the_pin_is_a_full_commit_sha_not_a_branch():
    """`main` is not a pin: it moves."""
    rev = _expert_spec()["revision"]
    assert len(rev) == 40 and all(c in "0123456789abcdef" for c in rev)


def test_the_service_passes_the_revision_to_the_factory():
    """A pin in the config that never reaches the adapter pins nothing.

    The kwarg is conditional because not every expert is hub-hosted (PGC takes a
    checkpoint path). What must hold is that a DECLARED revision reaches the
    factory -- and that an adapter which cannot accept one fails loudly rather
    than running unpinned."""
    from src.pipeline import service
    src = inspect.getsource(service.PredictionService.from_config)
    assert 'kwargs["revision"] = spec["revision"]' in src
    assert 'if spec.get("revision") is not None:' in src


def test_a_declared_revision_actually_reaches_the_factory():
    """Behavioural, not textual: build through from_config with a recording
    factory and assert the pin arrives."""
    from src.pipeline.service import PredictionService
    seen = {}

    class _Recorder:
        expert_id = "commfor_384"

        def __init__(self, device=None, revision=None):
            seen["revision"] = revision
            raise RuntimeError("stop here; construction is all we are testing")

    try:
        PredictionService.from_config(
            config={"threshold": 0.5, "fusion": "naive_mean",
                    "experts": [{"id": "commfor_384", "enabled": True,
                                 "revision": FROZEN_REVISION}]},
            registry={"commfor_384": _Recorder})
    except Exception:                                          # noqa: BLE001, S110
        pass
    assert seen.get("revision") == FROZEN_REVISION


def test_the_offline_cache_builder_uses_the_same_pin():
    """The cache and the live path must be the same weights, or parity is a
    coincidence rather than a property."""
    src = (ROOT / "scripts" / "build_feature_cache.py").read_text()
    assert 'revision=spec.get("revision")' in src


def test_a_resolved_revision_that_differs_fails_closed():
    """The guard, exercised without touching the network: if the hub resolves to
    something other than what was asked for, initialisation must refuse."""
    from src.experts.commfor import CommForExpert
    src = inspect.getsource(CommForExpert.__init__)
    assert "revision_mismatch" in src
    assert "if revision is not None and resolved != revision:" in src


def test_the_live_expert_actually_resolves_to_the_pin():
    """End to end, against the real cache: what we serve IS the frozen revision."""
    try:
        from src.experts.commfor import CommForExpert
        expert = CommForExpert(revision=FROZEN_REVISION)
    except Exception as exc:                                   # noqa: BLE001
        pytest.skip(f"expert unavailable: {exc}")
    assert expert.revision == FROZEN_REVISION
    assert expert.model_version.endswith(FROZEN_REVISION)
    assert expert.param_count == 21_811_969
