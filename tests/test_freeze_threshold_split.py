"""A future freeze fits the threshold on held-out dev, or it fails closed.

Peer review, 2026-08-29. The evaluation protocol requires threshold/calibration fitting on
held-out dev only. The 2026-08-28 freeze passed TRAIN rows to `select_threshold`, so the shipped
artifact's `n_dev_sources: 8998` are in fact the fitting split's train half.

The shipped threshold is deliberately NOT changed -- the sealed reference set was scored once at
it, and refitting would leave our only official benchmark describing a system we do not ship. The
deviation is recorded in `docs/threshold-deviation.md`. What these tests
lock is that the *code path* can no longer do it silently: dev is the default, and train requires
someone to say so out loud.
"""
import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load_freeze_module():
    spec = importlib.util.spec_from_file_location("freeze_router", ROOT / "scripts" / "freeze_router.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["freeze_router"] = mod
    spec.loader.exec_module(mod)
    return mod


FREEZE = _load_freeze_module()

TRAIN_ROWS = [{"source_id": "t1"}, {"source_id": "t2"}]
DEV_ROWS = [{"source_id": "d1"}]
TRAIN_SCORES = np.array([0.1, 0.2])
DEV_SCORES = np.array([0.9])


def test_default_split_is_dev_in_the_cli():
    """The argparse default is what an unattended future freeze actually gets."""
    src = (ROOT / "scripts" / "freeze_router.py").read_text()
    assert '"--threshold-split", choices=("dev", "train"), default="dev"' in src
    assert "--acknowledge-train-threshold-deviation" in src


def test_dev_is_returned_by_default():
    rows, scores = FREEZE.resolve_threshold_rows("dev", TRAIN_ROWS, TRAIN_SCORES, DEV_ROWS, DEV_SCORES)
    assert rows is DEV_ROWS
    assert scores is DEV_SCORES


def test_train_without_acknowledgement_fails_closed():
    with pytest.raises(FREEZE.ThresholdSplitError) as exc:
        FREEZE.resolve_threshold_rows("train", TRAIN_ROWS, TRAIN_SCORES, DEV_ROWS, DEV_SCORES)
    msg = str(exc.value)
    assert "held-out dev" in msg
    assert "docs/threshold-deviation.md" in msg


def test_train_is_reachable_only_by_saying_so():
    rows, scores = FREEZE.resolve_threshold_rows(
        "train", TRAIN_ROWS, TRAIN_SCORES, DEV_ROWS, DEV_SCORES, acknowledge_deviation=True)
    assert rows is TRAIN_ROWS
    assert scores is TRAIN_SCORES


def test_unknown_split_is_refused_rather_than_defaulted():
    with pytest.raises(FREEZE.ThresholdSplitError):
        FREEZE.resolve_threshold_rows("test", TRAIN_ROWS, TRAIN_SCORES, DEV_ROWS, DEV_SCORES)


def test_selection_and_candidate_grid_use_the_same_split():
    """A dev threshold chosen from a grid of TRAIN quantiles would be a subtler version
    of the same bug: the candidate values would still be train-derived."""
    src = (ROOT / "scripts" / "freeze_router.py").read_text()
    assert 'grid_src = tr if args.threshold_split == "train" else dv' in src
    assert "np.quantile(np.clip(grid_src, 0, 1)" in src
    # and the DevSet must be built from the resolved rows, never from train_rows directly
    selection = src.split("art = select_threshold(")[1].split(")")[0]
    assert "thr_rows" in selection
    assert "train_rows" not in selection


def test_the_shipped_artifact_is_untouched_by_this_repair():
    """The guard is for future freezes. The frozen decision must not move."""
    import json
    art = json.loads((ROOT / "results/router-fitting-v2/threshold-artifact.v1.json").read_text())
    assert art["threshold"] == 0.4667367651127279
    assert art["n_dev_sources"] == 8998, "the historical artifact keeps its own (mislabelled) fields"
