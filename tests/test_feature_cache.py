"""Feature cache tests — `specs/phase2-feature-cache.md` v2.

Weighted toward the failure modes that would silently corrupt Phase 2: a stale
cache being reused, a sealed image entering a fitting corpus, and any form of
imputation.
"""

import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from src.experts.base import ExpertInferenceError, ExpertOutput
from src.router.feature_cache import (
    ALLOWED_SPLITS,
    CacheKeyMismatch,
    DenylistViolation,
    build_cache,
    check_cache_key,
    compute_cache_key,
    completed_view_ids,
    load_denylist,
    validate_manifest_rows,
)

CONFIGS = {"transforms": Path("configs/transforms.yaml"), "probes": Path("configs/probes.yaml")}


class StubExpert:
    def __init__(self, expert_id="stub", fail=False, score=0.7):
        self.expert_id = expert_id
        self.param_count = 1
        self.license = "n/a"
        self.model_version = f"{expert_id}@v1"
        self.fail = fail
        self.score = score

    def predict(self, img):
        if self.fail:
            raise ExpertInferenceError(self.expert_id, "inference_failed", "scripted")
        return ExpertOutput(self.expert_id, raw_logit=0.4, p_fake=self.score, inference_ms=1.0)


@pytest.fixture
def manifest(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    images = tmp_path / "img"
    images.mkdir()
    rows = []
    for i in range(2):
        rel = f"img/{i}.png"
        # Textured, not flat: JPEG reproduces a uniform image exactly, so a flat
        # fixture would make clean and jpeg_q30 genuinely identical and mask
        # whether view hashes distinguish conditions at all.
        arr = np.random.default_rng(i).integers(0, 256, (48, 48, 3), dtype=np.uint8)
        Image.fromarray(arr).save(tmp_path / rel)
        import hashlib
        rows.append({
            "sample_id": f"s{i}", "source_id": f"src{i}", "relative_path": rel,
            "label": i % 2, "dataset": "TEST", "dataset_split": "train",
            "source_group": "g", "generator": None,
            "original_sha256": hashlib.sha256((tmp_path / rel).read_bytes()).hexdigest(),
            "decoded_phash": "0" * 16, "license_id": "TEST-LIC",
        })
    return rows


def _configs(tmp_path):
    root = Path(__file__).resolve().parents[1]
    return {"transforms": root / "configs/transforms.yaml", "probes": root / "configs/probes.yaml"}


# --- cache key ------------------------------------------------------------
def test_cache_key_is_canonical_json_and_rederivable():
    key, obj = compute_cache_key(["a@1"], _configs(None))
    again, obj2 = compute_cache_key(["a@1"], _configs(None))
    assert key == again and obj == obj2
    assert obj["feature_schema_version"] == "feature-cache-row.v1"
    assert "pipeline_version" in obj and "probe_version" in obj


def test_cache_key_is_order_independent_in_expert_list():
    a, _ = compute_cache_key(["a@1", "b@2"], _configs(None))
    b, _ = compute_cache_key(["b@2", "a@1"], _configs(None))
    assert a == b          # fingerprints are sorted


def test_cache_key_changes_with_expert_checkpoint():
    a, _ = compute_cache_key(["a@1"], _configs(None))
    b, _ = compute_cache_key(["a@2"], _configs(None))
    assert a != b


def test_mismatched_key_refuses_to_append(tmp_path):
    (tmp_path / "manifest.json").write_text(json.dumps({"cache_key": "old"}))
    with pytest.raises(CacheKeyMismatch, match="never mix"):
        check_cache_key(tmp_path, "new")


def test_matching_key_is_accepted(tmp_path):
    (tmp_path / "manifest.json").write_text(json.dumps({"cache_key": "same"}))
    check_cache_key(tmp_path, "same")      # no raise


# --- hard constraints -----------------------------------------------------
def test_duplicate_hash_across_sources_is_rejected():
    rows = [
        {"original_sha256": "a" * 64, "source_id": "s1", "dataset_split": "train",
         "sample_id": "x", "relative_path": "p"},
        {"original_sha256": "a" * 64, "source_id": "s2", "dataset_split": "train",
         "sample_id": "y", "relative_path": "q"},
    ]
    with pytest.raises(ValueError, match="multiple source_ids"):
        validate_manifest_rows(rows, set())


def test_same_hash_same_source_is_fine():
    """All 20 views of one source legitimately share original_sha256."""
    rows = [
        {"original_sha256": "a" * 64, "source_id": "s1", "dataset_split": "train",
         "sample_id": "x", "relative_path": "p"},
        {"original_sha256": "a" * 64, "source_id": "s1", "dataset_split": "train",
         "sample_id": "x", "relative_path": "p"},
    ]
    validate_manifest_rows(rows, set())    # must not raise


def test_sealed_image_aborts_the_whole_job():
    rows = [{"original_sha256": "b" * 64, "source_id": "s", "dataset_split": "train",
             "sample_id": "x", "relative_path": "sealed.jpg"}]
    with pytest.raises(DenylistViolation, match="SEALED REFERENCE"):
        validate_manifest_rows(rows, {"b" * 64})


def test_denylist_hit_is_not_a_skip():
    """A skipped row would hide a contaminated manifest — it must be fatal."""
    rows = [
        {"original_sha256": "c" * 64, "source_id": "ok", "dataset_split": "train",
         "sample_id": "a", "relative_path": "fine.jpg"},
        {"original_sha256": "b" * 64, "source_id": "bad", "dataset_split": "train",
         "sample_id": "b", "relative_path": "sealed.jpg"},
    ]
    with pytest.raises(DenylistViolation):
        validate_manifest_rows(rows, {"b" * 64})


@pytest.mark.parametrize("split", ["test", "sealed", "validation", ""])
def test_only_train_and_dev_may_enter_a_fitting_cache(split):
    rows = [{"original_sha256": "d" * 64, "source_id": "s", "dataset_split": split,
             "sample_id": "x", "relative_path": "p"}]
    with pytest.raises(ValueError, match="may not enter"):
        validate_manifest_rows(rows, set())
    assert ALLOWED_SPLITS == {"train", "dev"}


def test_val2017_reference_is_rejected():
    rows = [{"original_sha256": "e" * 64, "source_id": "s", "dataset_split": "train",
             "sample_id": "x", "relative_path": "data/coco/val2017/x.jpg"}]
    with pytest.raises(ValueError, match="val2017"):
        validate_manifest_rows(rows, set())


def test_missing_denylist_fails_closed(manifest, tmp_path):
    with pytest.raises(DenylistViolation, match="Refusing to build"):
        build_cache(manifest, tmp_path / "cache", [StubExpert()], _configs(tmp_path),
                    conditions=["clean"])


def test_unprotected_cache_must_be_explicitly_acknowledged(manifest, tmp_path):
    result = build_cache(manifest, tmp_path / "cache", [StubExpert()], _configs(tmp_path),
                         conditions=["clean"], denylist_acknowledged_absent=True)
    assert result["UNPROTECTED_SMOKE_ONLY"] is True
    assert result["denylist_protected"] is False


def test_denylist_file_parsing(tmp_path):
    p = tmp_path / "deny.txt"
    p.write_text("# comment\nAABB\n\nccdd  some note\n")
    assert load_denylist(p) == {"aabb", "ccdd"}
    assert load_denylist(None) == set()


# --- row content ----------------------------------------------------------
def _build(manifest, tmp_path, experts, conditions=("clean", "jpeg_q30")):
    return build_cache(manifest, tmp_path / "cache", experts, _configs(tmp_path),
                       conditions=list(conditions), denylist_acknowledged_absent=True)


def _rows(tmp_path):
    return [json.loads(l) for l in (tmp_path / "cache" / "rows.jsonl").read_text().splitlines() if l.strip()]


def test_row_identity_fields(manifest, tmp_path):
    _build(manifest, tmp_path, [StubExpert()])
    rows = _rows(tmp_path)
    assert len(rows) == 4
    for row in rows:
        assert row["view_id"] == f"{row['source_sample_id']}:{row['condition_id']}"
        assert row["schema_version"] == "feature-cache-row.v1"
        assert len(row["view_rgb_sha256"]) == 64


def test_view_hash_distinguishes_conditions_but_source_hash_does_not(manifest, tmp_path):
    """Source hash is shared across views by design; the view hash must not be.

    Note this needs textured fixtures: JPEG-compressing a flat image is a no-op,
    so a uniform fixture would pass this vacuously.
    """
    _build(manifest, tmp_path, [StubExpert()])
    rows = [r for r in _rows(tmp_path) if r["source_id"] == "src0"]
    assert len({r["original_sha256"] for r in rows}) == 1     # shared, as designed
    assert len({r["view_rgb_sha256"] for r in rows}) == 2     # views distinguishable


def test_failed_expert_block_carries_no_score(manifest, tmp_path):
    _build(manifest, tmp_path, [StubExpert(fail=True)])
    for row in _rows(tmp_path):
        block = row["experts"]["stub"]
        assert block["ok"] is False
        assert "p_fake" not in block and "raw_logit" not in block


def test_single_expert_yields_null_disagreement(manifest, tmp_path):
    _build(manifest, tmp_path, [StubExpert()])
    assert all(r["disagreement"] is None for r in _rows(tmp_path))


def test_two_experts_yield_pairwise_disagreement(manifest, tmp_path):
    _build(manifest, tmp_path, [StubExpert("a", score=0.2), StubExpert("b", score=0.9)])
    row = _rows(tmp_path)[0]
    dis = row["disagreement"]
    assert dis["n_experts_ok"] == 2
    assert dis["max_abs_p_diff"] == pytest.approx(0.7)
    assert list(dis["pairwise_abs_p_diff"]) == ["a|b"]


def test_threshold_dependent_value_is_absent_from_the_cache(manifest, tmp_path):
    """A threshold-free artifact must not embed a threshold-derived value."""
    _build(manifest, tmp_path, [StubExpert("a"), StubExpert("b")])
    dis = _rows(tmp_path)[0]["disagreement"]
    assert "threshold_agreement" not in dis


def test_entropy_is_not_stored(manifest, tmp_path):
    _build(manifest, tmp_path, [StubExpert()])
    assert "entropy" not in _rows(tmp_path)[0]["experts"]["stub"]


def test_quality_and_probe_blocks_present(manifest, tmp_path):
    _build(manifest, tmp_path, [StubExpert()])
    row = _rows(tmp_path)[0]
    assert "blur_varlap" in row["quality"] and "noise_sigma" in row["quality"]
    probes = row["probes"]["stub"]
    assert probes["n_probes_ok"] == 3
    assert probes["probe_flip"] in (True, False)


def test_view_warnings_preserved(manifest, tmp_path):
    _build(manifest, tmp_path, [StubExpert()])
    assert "view_warnings" in _rows(tmp_path)[0]


# --- resumability ---------------------------------------------------------
def test_resume_skips_completed_views(manifest, tmp_path):
    _build(manifest, tmp_path, [StubExpert()], conditions=["clean"])
    first = len(_rows(tmp_path))
    result = _build(manifest, tmp_path, [StubExpert()], conditions=["clean"])
    assert result["rows_written"] == 0
    assert len(_rows(tmp_path)) == first


def test_resume_completes_a_partial_grid(manifest, tmp_path):
    _build(manifest, tmp_path, [StubExpert()], conditions=["clean"])
    _build(manifest, tmp_path, [StubExpert()], conditions=["clean", "jpeg_q30"])
    rows = _rows(tmp_path)
    assert len(rows) == 4
    assert len({r["view_id"] for r in rows}) == 4


def test_completed_view_ids_tolerates_torn_line(tmp_path):
    p = tmp_path / "rows.jsonl"
    p.write_text('{"view_id": "a:clean"}\n{"view_id": "b:cl')
    assert completed_view_ids(p) == {"a:clean"}


# --- manifest -------------------------------------------------------------
def test_manifest_records_key_object_and_storage(manifest, tmp_path):
    result = _build(manifest, tmp_path, [StubExpert()])
    written = json.loads((tmp_path / "cache" / "manifest.json").read_text())
    assert written["cache_key"] == result["cache_key"]
    assert written["key_object"]["pipeline_version"]
    assert written["storage_format"] == "jsonl"
    assert "Parquet" in written["storage_note"]
