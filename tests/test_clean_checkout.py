"""A clean clone must be able to run the system the docs describe.

R1, Codex review 2026-08-29: `configs/predict.yaml` pointed at
`results/router-fitting-v2/router_reliability.pt`, which `*.pt` ignored and which
was absent from HEAD. The live workspace passed because the file existed locally;
a judge's clone would have failed to load the fitted reliability head and the
adopted abstention policy, and the degradation reporter would have silently
vanished from the UI.

Existing-on-disk is therefore not the test. TRACKED-IN-GIT is the test.
"""

import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def _tracked(rel: str) -> bool:
    out = subprocess.run(["git", "ls-files", "--error-unmatch", rel],
                         cwd=ROOT, capture_output=True, text=True, check=False)
    return out.returncode == 0


def _config() -> dict:
    return yaml.safe_load((ROOT / "configs" / "predict.yaml").read_text())


def test_every_artifact_the_serving_config_names_is_tracked():
    cfg = _config()
    router = cfg.get("router") or {}
    referenced = [v for v in (router.get("checkpoint"), router.get("threshold_artifact")) if v]
    assert referenced, "serving config names no router artifacts"
    for rel in referenced:
        assert (ROOT / rel).exists(), f"{rel} missing on disk"
        assert _tracked(rel), (
            f"{rel} is referenced by configs/predict.yaml but is NOT tracked in git; "
            "a clean clone cannot run the shipped system"
        )


def test_the_degradation_model_the_ui_loads_is_tracked():
    """The UI and audit CLI advertise this capability, so it must survive a clone."""
    from src.pipeline.degradation import DEFAULT_MODEL

    rel = DEFAULT_MODEL.relative_to(ROOT).as_posix()
    assert DEFAULT_MODEL.exists(), f"{rel} missing on disk"
    assert _tracked(rel), f"{rel} is loaded by the UI but is not tracked in git"


def test_tracked_weights_stay_small():
    """The narrow exceptions to the blanket *.pt ignore are for OUR small heads.
    If one grows into bulk weights, the exception was the wrong tool."""
    for rel in ("results/router-fitting-v2/router.pt",
                "results/router-fitting-v2/router_reliability.pt",
                "results/degradation/classifier.pt"):
        path = ROOT / rel
        if not path.exists():
            pytest.skip(f"{rel} absent")
        assert path.stat().st_size < 256 * 1024, f"{rel} is too large to track"


def test_shipped_config_serves_the_router_not_the_baseline():
    assert _config().get("fusion") == "router"
