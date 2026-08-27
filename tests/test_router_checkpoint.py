"""Router checkpoint round-trip and provenance tests (B-018 T4).

`save_checkpoint` / `load_checkpoint` together are the deployability contract:
a checkpoint that cannot be loaded back into a model producing IDENTICAL
predictions is not a checkpoint, it is metadata that happens to include a
state_dict. `test_save_load_prediction_parity` exercises the REAL ladder
output end to end (not a hand-built module), because a hand-built module
cannot catch a rung the loader reconstructs differently than the trainer
built it.
"""

import numpy as np
import pytest
import torch

from src.router.train import build_batch, load_checkpoint, run_ladder, save_checkpoint

EXPERTS = ("e1", "e2")
FAMILY_CONDITIONS = {
    "clean": ["clean"], "jpeg": ["jpeg_q30"], "blur": ["blur_s2.0"],
    "resize": ["resize_0.5"], "noise": ["noise_s0.10"], "color": ["bright_-20"],
    "crop": ["crop_0.8"],
}
# The canonical sha256 hex digest format `feature_cache.compute_cache_key` emits.
TEST_CACHE_KEY = "f" * 64


def make_rows(n_sources=40, split_at=30, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n_sources):
        label = i % 2
        split = "train" if i < split_at else "dev"
        for family, conditions in FAMILY_CONDITIONS.items():
            for condition in conditions:
                p1 = 0.9 if label == 1 else 0.05
                p1 = float(np.clip(p1 + rng.normal(0, 1e-4), 1e-3, 1 - 1e-3))
                p2 = 0.85 if label == 1 else 0.1
                p2 = float(np.clip(p2 + rng.normal(0, 1e-4), 1e-3, 1 - 1e-3))
                rows.append({
                    "source_id": f"s{i}", "label": label, "dataset_split": split,
                    "condition_id": condition, "family": family,
                    "cache_key": TEST_CACHE_KEY,
                    "experts": {
                        "e1": {"ok": True, "raw_logit": float(np.log(p1 / (1 - p1))),
                               "p_fake": p1},
                        "e2": {"ok": True, "raw_logit": float(np.log(p2 / (1 - p2))),
                               "p_fake": p2},
                    },
                    "probes": {
                        "e1": {"probe_mean": p1, "probe_std": 0.01, "probe_range": 0.02,
                               "probe_max_delta": 0.01, "probe_scores": {"probe_jpeg_q92": p1},
                               "n_probes_ok": 3},
                        "e2": {"probe_mean": p2, "probe_std": 0.01, "probe_range": 0.02,
                               "probe_max_delta": 0.01, "probe_scores": {"probe_jpeg_q92": p2},
                               "n_probes_ok": 3},
                    },
                    "quality": {"width": 512, "height": 512, "aspect_ratio": 1.0,
                                "megapixels": 0.26, "is_portrait": False,
                                "blur_varlap": 0.01, "blockiness": 1.0,
                                "noise_sigma": 0.01, "luminance_mean": 0.5,
                                "luminance_std": 0.2, "saturation_mean": 0.3,
                                "clipped_low_frac": 0.0, "clipped_high_frac": 0.0},
                    "disagreement": None,
                })
    return rows


def test_save_load_prediction_parity(tmp_path):
    """The deployability test: load the checkpoint and run it on the SAME dev
    batch tensors the trainer produced, and require identical predictions."""
    rows = make_rows()
    result = run_ladder(rows, threshold=0.5, expert_ids=EXPERTS,
                        threshold_provenance="fitted-phase4-2026-08-27")
    path = save_checkpoint(result, tmp_path / "router.pt", threshold=0.5)
    loaded = load_checkpoint(path)

    dev_rows = [r for r in rows if r["dataset_split"] == "dev"]
    batch = build_batch(dev_rows, loaded.spec, loaded.standardizer, loaded.threshold)
    with torch.no_grad():
        p_loaded = loaded.model(batch.features, batch.expert_logits, batch.available).p_fake

    original_model = result["_best_model"]
    original_model.eval()
    with torch.no_grad():
        p_original = original_model(
            batch.features, batch.expert_logits, batch.available
        ).p_fake

    assert torch.allclose(p_loaded, p_original, atol=1e-6)


def test_load_rejects_wrong_schema_version(tmp_path):
    rows = make_rows()
    result = run_ladder(rows, threshold=0.5, expert_ids=EXPERTS)
    path = save_checkpoint(result, tmp_path / "router.pt", threshold=0.5)
    payload = torch.load(path, weights_only=False)
    payload["schema_version"] = "router-checkpoint.v0"
    torch.save(payload, path)
    with pytest.raises(ValueError, match="schema"):
        load_checkpoint(path)


def test_load_rejects_missing_key(tmp_path):
    rows = make_rows()
    result = run_ladder(rows, threshold=0.5, expert_ids=EXPERTS)
    path = save_checkpoint(result, tmp_path / "router.pt", threshold=0.5)
    payload = torch.load(path, weights_only=False)
    del payload["threshold"]
    torch.save(payload, path)
    with pytest.raises(ValueError, match="threshold"):
        load_checkpoint(path)


def test_load_rejects_feature_dim_drift(tmp_path):
    rows = make_rows()
    result = run_ladder(rows, threshold=0.5, expert_ids=EXPERTS)
    path = save_checkpoint(result, tmp_path / "router.pt", threshold=0.5)
    payload = torch.load(path, weights_only=False)
    payload["feature_spec"]["dim"] = payload["feature_spec"]["dim"] + 1
    torch.save(payload, path)
    with pytest.raises(ValueError, match="drift"):
        load_checkpoint(path)


def test_save_is_atomic_no_tmp_left_behind(tmp_path):
    rows = make_rows()
    result = run_ladder(rows, threshold=0.5, expert_ids=EXPERTS)
    path = save_checkpoint(result, tmp_path / "router.pt", threshold=0.5)
    assert path.exists()
    assert list(tmp_path.glob("*.tmp")) == []


def test_checkpoint_records_provenance(tmp_path):
    rows = make_rows()
    result = run_ladder(rows, threshold=0.5, expert_ids=EXPERTS,
                        threshold_provenance="fitted-phase4-2026-08-27")
    path = save_checkpoint(result, tmp_path / "router.pt", threshold=0.5,
                           cache_artifact_sha256="a" * 64)
    payload = torch.load(path, weights_only=False)
    for key in ("use_worst_group_loss", "n_parameters", "feature_names",
                "hyperparameters", "reliability_head_fitted",
                "cache_artifact_sha256", "code_revision", "selection"):
        assert key in payload
    best_record = result["_best_record"]
    assert payload["use_worst_group_loss"] == best_record["use_worst_group_loss"]
    assert payload["n_parameters"] == best_record["n_parameters"]
    assert payload["cache_artifact_sha256"] == "a" * 64
    assert payload["selection"]["best_rung"] == result["best_rung"]
