"""The threshold-dependent `probe_flip` feature has known train/serve drift.

R6, Codex review 2026-08-29. `probe_flip` is derived at consumption from the
threshold in force. The freeze trained and selected rungs with feature threshold
**0.5** (no frozen threshold existed yet — that is the R22 two-stage ordering),
while reliability fitting, every evaluation and the live service derive it at the
frozen **0.4667367651**.

The drift is real but small, and it is disclosed rather than hidden. These tests
lock the SERVING semantics so the behaviour cannot change silently, and record
the measured size of the discrepancy so a regression is visible as a number.
"""

import json
from pathlib import Path

import numpy as np
import pytest
import torch

ROOT = Path(__file__).resolve().parents[1]
FROZEN = 0.4667367651127279


@pytest.fixture(scope="module")
def rows():
    path = ROOT / "data" / "feature_cache" / "internal-test-v2" / "rows.jsonl"
    if not path.exists():
        pytest.skip("internal-test cache not present")
    out = []
    with path.open() as fh:
        for line in fh:
            out.append(json.loads(line))
    return out


def test_probe_flip_is_derived_not_cached(rows):
    """The cache is threshold-free by contract: a stored flip would silently
    describe whatever threshold was in force when the row was written."""
    for r in rows[:500]:
        for block in (r.get("probes") or {}).values():
            assert "probe_flip" not in block


def test_serving_derives_probe_flip_at_the_frozen_threshold(rows):
    from src.pipeline.service import PredictionService
    from src.router.features import derive_probe_flip

    try:
        svc = PredictionService.from_config()
    except Exception as exc:                       # noqa: BLE001
        pytest.skip(f"service unavailable: {exc}")
    if svc.fusion != "router":
        pytest.skip("not serving the router")
    assert svc.router.threshold == pytest.approx(FROZEN, abs=1e-12)

    # the helper must key off the threshold it is given, or the drift below is
    # not even measurable
    eid = svc.router.expert_ids[0]
    row = next(r for r in rows if (r.get("probes") or {}).get(eid, {}).get("probe_scores"))
    block = row["probes"][eid]
    base = float(row["experts"][eid]["p_fake"])
    flips = {t: derive_probe_flip(block, base, t) for t in (0.0001, 0.5, 0.9999)}
    assert flips[0.0001] is not None and flips[0.9999] is not None


def test_measured_train_serve_drift_stays_within_the_disclosed_bounds(rows):
    """Locks the MEASURED size of the known discrepancy, not a loose ceiling.

    S3, Codex review 2026-08-29: the first version of this test allowed up to
    1,499 changed rows and 10 verdict changes, and asserted nothing at all about
    the score drift -- so it would have passed through almost three times the
    real discrepancy without complaint, and any growth in magnitude at constant
    row count was invisible to it.

    Independently reproduced by both agents on the 60,000 internal-test rows:
    deriving probe_flip at 0.5 (training semantics) rather than at the frozen
    threshold changes exactly **550 feature rows**, moves p_fake by at most
    **0.298885**, and flips **2 verdicts**, leaving worst-family recall
    identical at 0.8258. The dev-split equivalent (B-029) is 578 / 0.29525 / 3.

    These are deterministic functions of a fixed cache and a frozen checkpoint,
    so they are asserted as values.
    """
    from src.router.train import build_batch, load_checkpoint

    ckpt = ROOT / "results" / "router-fitting-v2" / "router_reliability.pt"
    if not ckpt.exists():
        pytest.skip("shipped checkpoint not present")
    loaded = load_checkpoint(ckpt)

    def score(feature_threshold):
        batch = build_batch(rows, loaded.spec, loaded.standardizer, feature_threshold)
        with torch.no_grad():
            return loaded.model(batch.features, batch.expert_logits,
                                batch.available).p_fake.numpy()

    served = score(FROZEN)
    trained = score(0.5)
    delta = np.abs(served - trained)
    changed_rows = int((delta > 0).sum())
    max_abs_delta = float(delta.max())
    verdict_changes = int(((served >= FROZEN) != (trained >= FROZEN)).sum())

    assert len(rows) == 60000, "the published drift figures describe this cache"
    assert changed_rows == 550, f"feature drift moved to {changed_rows} rows (published 550)"
    assert verdict_changes == 2, f"verdict drift moved to {verdict_changes} (published 2)"
    assert max_abs_delta == pytest.approx(0.298885, abs=5e-6), (
        f"max |delta p_fake| moved to {max_abs_delta:.6f} (published 0.298885)")
    # and the headline must be unaffected either way
    labels = np.array([r["label"] for r in rows])
    fams = np.array([r.get("family") or "clean" for r in rows])
    def worst(s):
        return min(float((s[(fams == f) & (labels == 1)] >= FROZEN).mean())
                   for f in ("blur", "color", "crop", "jpeg", "noise", "resize"))
    assert abs(worst(served) - worst(trained)) < 0.005
