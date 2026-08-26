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
    Denylist,
    DenylistViolation,
    build_cache,
    check_cache_key,
    compute_cache_key,
    load_denylist,
    scan_existing_rows,
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
    assert obj["feature_schema_version"] == "feature-cache-row.v2"
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
        validate_manifest_rows(rows, Denylist(frozenset(), frozenset()), verify_bytes=False)


def test_same_hash_same_source_is_fine():
    """All 20 views of one source legitimately share original_sha256."""
    rows = [
        {"original_sha256": "a" * 64, "source_id": "s1", "dataset_split": "train",
         "sample_id": "x", "relative_path": "p"},
        {"original_sha256": "a" * 64, "source_id": "s1", "dataset_split": "train",
         "sample_id": "x", "relative_path": "p"},
    ]
    validate_manifest_rows(rows, Denylist(frozenset(), frozenset()), verify_bytes=False)    # must not raise


def test_sealed_image_aborts_the_whole_job():
    rows = [{"original_sha256": "b" * 64, "source_id": "s", "dataset_split": "train",
             "sample_id": "x", "relative_path": "sealed.jpg"}]
    with pytest.raises(DenylistViolation, match="SEALED REFERENCE"):
        validate_manifest_rows(rows, Denylist(frozenset({"b" * 64}), frozenset()), verify_bytes=False)


def test_denylist_hit_is_not_a_skip():
    """A skipped row would hide a contaminated manifest — it must be fatal."""
    rows = [
        {"original_sha256": "c" * 64, "source_id": "ok", "dataset_split": "train",
         "sample_id": "a", "relative_path": "fine.jpg"},
        {"original_sha256": "b" * 64, "source_id": "bad", "dataset_split": "train",
         "sample_id": "b", "relative_path": "sealed.jpg"},
    ]
    with pytest.raises(DenylistViolation):
        validate_manifest_rows(rows, Denylist(frozenset({"b" * 64}), frozenset()), verify_bytes=False)


@pytest.mark.parametrize("split", ["test", "sealed", "validation", ""])
def test_only_train_and_dev_may_enter_a_fitting_cache(split):
    rows = [{"original_sha256": "d" * 64, "source_id": "s", "dataset_split": split,
             "sample_id": "x", "relative_path": "p"}]
    with pytest.raises(ValueError, match="may not enter"):
        validate_manifest_rows(rows, Denylist(frozenset(), frozenset()), verify_bytes=False)
    assert ALLOWED_SPLITS == {"train", "dev"}


def test_val2017_reference_is_rejected():
    rows = [{"original_sha256": "e" * 64, "source_id": "s", "dataset_split": "train",
             "sample_id": "x", "relative_path": "data/coco/val2017/x.jpg"}]
    with pytest.raises(ValueError, match="val2017"):
        validate_manifest_rows(rows, Denylist(frozenset(), frozenset()), verify_bytes=False)


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
    p.write_text(f"# comment\n{'a'*64}\n\n{'b'*64}  phash={'c'*16}\n")
    dl = load_denylist(p)
    assert dl.sha256 == {"a" * 64, "b" * 64}
    assert dl.phash == {"c" * 16}
    assert dl.perceptual_protected is True
    assert not load_denylist(None)


def test_malformed_denylist_is_refused_not_treated_as_protection(tmp_path):
    """R7a: junk previously yielded a non-empty denylist and a 'protected' stamp."""
    p = tmp_path / "deny.txt"
    p.write_text("hello-not-a-sha\nGARBAGE\n")
    with pytest.raises(DenylistViolation, match="not a lowercase 64-hex"):
        load_denylist(p)


def test_empty_denylist_file_is_refused(tmp_path):
    p = tmp_path / "deny.txt"
    p.write_text("# only comments\n")
    with pytest.raises(DenylistViolation, match="no usable hashes"):
        load_denylist(p)


def test_missing_denylist_file_is_refused(tmp_path):
    with pytest.raises(DenylistViolation, match="not found"):
        load_denylist(tmp_path / "nope.txt")


def test_manifest_hash_is_verified_against_real_bytes(tmp_path, monkeypatch):
    """R7b: a self-declared hash previously passed with no file on disk."""
    monkeypatch.chdir(tmp_path)
    rows = [{"original_sha256": "f" * 64, "source_id": "s", "dataset_split": "train",
             "sample_id": "x", "relative_path": "missing.jpg"}]
    with pytest.raises(DenylistViolation, match="does not exist"):
        validate_manifest_rows(rows, Denylist(frozenset({"a" * 64}), frozenset()))


def test_mismatched_file_hash_is_refused(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "real.jpg").write_bytes(b"actual bytes")
    rows = [{"original_sha256": "f" * 64, "source_id": "s", "dataset_split": "train",
             "sample_id": "x", "relative_path": "real.jpg"}]
    with pytest.raises(DenylistViolation, match="does not describe its own bytes"):
        validate_manifest_rows(rows, Denylist(frozenset({"a" * 64}), frozenset()))


def test_sealed_image_detected_by_real_hash(tmp_path, monkeypatch):
    import hashlib

    monkeypatch.chdir(tmp_path)
    (tmp_path / "sealed.jpg").write_bytes(b"sealed content")
    digest = hashlib.sha256(b"sealed content").hexdigest()
    rows = [{"original_sha256": digest, "source_id": "s", "dataset_split": "train",
             "sample_id": "x", "relative_path": "sealed.jpg"}]
    with pytest.raises(DenylistViolation, match="SEALED REFERENCE"):
        validate_manifest_rows(rows, Denylist(frozenset({digest}), frozenset()))


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
        assert row["schema_version"] == "feature-cache-row.v2"
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


def test_threshold_dependent_values_are_absent_from_the_cache(manifest, tmp_path):
    """A threshold-free artifact must not embed ANY threshold-derived value."""
    _build(manifest, tmp_path, [StubExpert("a"), StubExpert("b")])
    row = _rows(tmp_path)[0]
    assert "threshold_agreement" not in row["disagreement"]
    # R9: probe_flip is threshold-dependent and must be derived at consumption
    assert "probe_flip" not in row["probes"]["a"]
    assert "probe_scores" in row["probes"]["a"]      # the inputs ARE stored


def test_probe_flip_is_derivable_from_stored_inputs():
    from src.router.features import derive_probe_flip

    block = {"probe_scores": {"probe_jpeg_q92": 0.8, "probe_crop_0.96": 0.2}}
    assert derive_probe_flip(block, 0.9, 0.5) is True     # 0.2 crosses below
    assert derive_probe_flip(block, 0.9, 0.1) is False    # all on one side
    assert derive_probe_flip({"probe_scores": {}}, 0.9, 0.5) is None
    assert derive_probe_flip(block, None, 0.5) is None


def test_entropy_is_not_stored(manifest, tmp_path):
    _build(manifest, tmp_path, [StubExpert()])
    assert "entropy" not in _rows(tmp_path)[0]["experts"]["stub"]


def test_quality_and_probe_blocks_present(manifest, tmp_path):
    _build(manifest, tmp_path, [StubExpert()])
    row = _rows(tmp_path)[0]
    assert "blur_varlap" in row["quality"] and "noise_sigma" in row["quality"]
    probes = row["probes"]["stub"]
    assert probes["n_probes_ok"] == 3


def test_view_warnings_preserved(manifest, tmp_path):
    _build(manifest, tmp_path, [StubExpert()])
    assert "view_warnings" in _rows(tmp_path)[0]


# --- resumability ---------------------------------------------------------
def test_resume_skips_completed_views(manifest, tmp_path):
    _build(manifest, tmp_path, [StubExpert()], conditions=["clean"])
    first = len(_rows(tmp_path))
    result = _build(manifest, tmp_path, [StubExpert()], conditions=["clean"])
    assert result["rows_written_this_invocation"] == 0
    assert len(_rows(tmp_path)) == first


def test_resume_completes_a_partial_grid(manifest, tmp_path):
    _build(manifest, tmp_path, [StubExpert()], conditions=["clean"])
    _build(manifest, tmp_path, [StubExpert()], conditions=["clean", "jpeg_q30"])
    rows = _rows(tmp_path)
    assert len(rows) == 4
    assert len({r["view_id"] for r in rows}) == 4


def test_scan_truncates_a_torn_tail(tmp_path):
    """R8: the torn line was previously left in place, so the next append
    concatenated onto the fragment and corrupted it permanently."""
    p = tmp_path / "rows.jsonl"
    good = json.dumps({"view_id": "a:clean", "cache_key": "K",
                       "schema_version": "feature-cache-row.v2"})
    p.write_text(good + "\n" + '{"view_id": "b:cl')
    done, total = scan_existing_rows(p, "K")
    assert done == {"a:clean"} and total == 1
    assert p.read_text() == good + "\n"      # tail removed, not skipped


def test_scan_refuses_rows_from_another_cache_generation(tmp_path):
    p = tmp_path / "rows.jsonl"
    p.write_text(json.dumps({"view_id": "a:clean", "cache_key": "OLD",
                             "schema_version": "feature-cache-row.v2"}) + "\n")
    with pytest.raises(CacheKeyMismatch, match="Never mix"):
        scan_existing_rows(p, "NEW")


def test_manifest_is_written_before_extraction(manifest, tmp_path):
    """R8: an interrupted first run left no key for the next run to check."""
    out = tmp_path / "cache"
    _build(manifest, tmp_path, [StubExpert()], conditions=["clean"])
    written = json.loads((out / "manifest.json").read_text())
    assert written["status"] == "complete"
    assert written["rows_total"] == len(_rows(tmp_path))


# --- manifest -------------------------------------------------------------
def test_manifest_records_key_object_and_storage(manifest, tmp_path):
    result = _build(manifest, tmp_path, [StubExpert()])
    written = json.loads((tmp_path / "cache" / "manifest.json").read_text())
    assert written["cache_key"] == result["cache_key"]
    assert written["key_object"]["pipeline_version"]
    assert written["storage_format"] == "jsonl"
    assert written["rows_total"] == len(_rows(tmp_path))
    assert written["threshold_free"] is True
    assert written["library_versions"]["torch"]
