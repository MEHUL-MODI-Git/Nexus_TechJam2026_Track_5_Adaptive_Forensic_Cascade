"""Full-grid runner tests (task 1.3).

The runner produces the rows every headline robustness number is computed
from, so these tests target the ways a grid run can be quietly wrong: a view
hash that doesn't distinguish conditions, a resume that duplicates or drops
rows, or an expert failure that becomes a fabricated score.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.run_grid import completed_pairs, load_manifest, run, view_sha256
from src.experts.base import ExpertInferenceError, ExpertOutput
from src.pipeline.service import PredictionService
from src.pipeline.transforms import CONDITION_IDS

ROOT = Path(__file__).resolve().parents[1]


class StubExpert:
    """Deterministic scorer; can be told to fail on specific conditions."""

    expert_id = "stub_expert"
    param_count = 42
    license = "n/a"
    model_version = "stub@1"

    def __init__(self, fail_conditions=()):
        self.fail_conditions = set(fail_conditions)
        self.calls = 0

    def predict(self, img):
        self.calls += 1
        if getattr(img, "_condition", None) in self.fail_conditions:
            raise ExpertInferenceError(self.expert_id, "inference_failed", "scripted")
        # score derived from pixel mean so different views score differently
        p = float(np.array(img.image, dtype=np.float64).mean() / 255.0)
        return ExpertOutput(self.expert_id, raw_logit=p * 2 - 1, p_fake=p,
                            inference_ms=1.0, model_version=self.model_version)


@pytest.fixture
def mini_manifest(tmp_path):
    """Two sources (one per class) laid out like the real smoke manifest."""
    images = tmp_path / "data" / "smoke" / "images"
    images.mkdir(parents=True)
    rows = []
    for i, label in enumerate((0, 1)):
        arr = np.full((64, 48, 3), 40 + i * 90, dtype=np.uint8)
        rel = f"data/smoke/images/img{i}.png"
        Image.fromarray(arr).save(tmp_path / rel)
        rows.append({
            "sample_id": f"smoke-{i:06d}", "source_id": f"src-{i}",
            "relative_path": rel, "label": label, "dataset": "TEST",
            "source_group": "grp", "original_sha256": "0" * 64,
        })
    manifest = tmp_path / "data" / "manifests" / "mini.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps({"manifest_version": "smoke.v1", "images": rows}))
    return manifest


@pytest.fixture
def stub_service():
    return PredictionService([StubExpert()], threshold=0.5)


def _read(path):
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


# --- view identity --------------------------------------------------------
def test_view_hash_distinguishes_conditions():
    """A source hash would collide across all 20 views; the view hash must not."""
    base = Image.fromarray(np.random.default_rng(0).integers(
        0, 255, (32, 32, 3), dtype=np.uint8))
    from src.pipeline.transforms import apply_transform

    hashes = {c: view_sha256(apply_transform(base, c, "a" * 64)) for c in CONDITION_IDS}
    # clean/color conditions can coincide only if pixels truly match; jpeg/blur must differ
    assert hashes["clean"] != hashes["jpeg_q30"]
    assert hashes["blur_s0.5"] != hashes["blur_s2.0"]
    assert len(set(hashes.values())) >= 15


def test_view_hash_is_deterministic():
    img = Image.fromarray(np.zeros((8, 8, 3), dtype=np.uint8))
    assert view_sha256(img) == view_sha256(img)


# --- row contract ---------------------------------------------------------
def test_emits_one_row_per_source_condition_expert(mini_manifest, stub_service, tmp_path):
    out = tmp_path / "rows.jsonl"
    manifest = run(mini_manifest, out, CONDITION_IDS, service=stub_service)
    rows = _read(out)
    assert manifest["rows_written"] == len(rows) == 2 * len(CONDITION_IDS)
    assert len({(r["sample_id"], r["condition_id"]) for r in rows}) == len(rows)


def test_row_has_required_prediction_row_fields(mini_manifest, stub_service, tmp_path):
    out = tmp_path / "rows.jsonl"
    run(mini_manifest, out, ["clean", "jpeg_q30"], service=stub_service)
    required = {"schema_version", "run_id", "method_id", "sample_id", "source_id",
                "image_path", "content_sha256", "label", "dataset", "source_group",
                "condition_id", "p_fake", "reliability", "decision",
                "rescue_invoked", "inference_ms", "warnings"}
    for row in _read(out):
        assert required <= set(row)
        assert row["schema_version"] == "prediction-row.v1"
        assert 0.0 <= row["p_fake"] <= 1.0


def test_decision_is_null_so_the_harness_recomputes(mini_manifest, stub_service, tmp_path):
    out = tmp_path / "rows.jsonl"
    run(mini_manifest, out, ["clean"], service=stub_service)
    assert all(r["decision"] is None for r in _read(out))
    assert all(r["reliability"] is None for r in _read(out))


def test_sample_id_is_source_plus_condition(mini_manifest, stub_service, tmp_path):
    out = tmp_path / "rows.jsonl"
    run(mini_manifest, out, ["jpeg_q70"], service=stub_service)
    rows = _read(out)
    assert rows[0]["sample_id"].endswith(":jpeg_q70")
    assert rows[0]["sample_id"].startswith("smoke-")


def test_all_views_of_a_source_share_source_id(mini_manifest, stub_service, tmp_path):
    out = tmp_path / "rows.jsonl"
    run(mini_manifest, out, CONDITION_IDS, service=stub_service)
    rows = [r for r in _read(out) if r["sample_id"].startswith("smoke-000000")]
    assert len({r["source_id"] for r in rows}) == 1     # bootstrap unit stays intact
    assert len({r["content_sha256"] for r in rows}) > 1  # but views are distinguishable


def test_labels_come_from_the_manifest(mini_manifest, stub_service, tmp_path):
    out = tmp_path / "rows.jsonl"
    run(mini_manifest, out, ["clean"], service=stub_service)
    assert sorted(r["label"] for r in _read(out)) == [0, 1]


# --- failure handling -----------------------------------------------------
def test_expert_failure_emits_no_prediction_row(mini_manifest, tmp_path):
    """A failed inference must never produce a fabricated p_fake."""
    service = PredictionService([StubExpert()], threshold=0.5)

    class AlwaysFails(StubExpert):
        def predict(self, img):
            raise ExpertInferenceError(self.expert_id, "inference_failed", "boom")

    service.experts = [AlwaysFails()]
    out = tmp_path / "rows.jsonl"
    manifest = run(mini_manifest, out, ["clean"], service=service)
    rows = _read(out)
    assert manifest["rows_written"] == 0
    assert all(r["schema_version"] == "prediction-failure.v1" for r in rows)
    assert all("p_fake" not in r for r in rows)


def test_undecodable_source_is_counted_not_silently_dropped(mini_manifest, stub_service, tmp_path):
    bad = mini_manifest.parents[1] / "smoke" / "images" / "broken.png"
    bad.write_bytes(b"not an image")
    payload = json.loads(mini_manifest.read_text())
    payload["images"].append({
        "sample_id": "smoke-000099", "source_id": "src-99",
        "relative_path": "data/smoke/images/broken.png", "label": 0,
        "dataset": "TEST", "source_group": "grp", "original_sha256": "0" * 64,
    })
    mini_manifest.write_text(json.dumps(payload))
    out = tmp_path / "rows.jsonl"
    manifest = run(mini_manifest, out, ["clean"], service=stub_service)
    assert manifest["decode_failures"] == 1     # visible in the manifest, not hidden


# --- resumability ---------------------------------------------------------
def test_resume_skips_completed_pairs_without_duplicating(mini_manifest, stub_service, tmp_path):
    out = tmp_path / "rows.jsonl"
    run(mini_manifest, out, ["clean", "jpeg_q30"], service=stub_service)
    first = _read(out)
    manifest = run(mini_manifest, out, ["clean", "jpeg_q30"], service=stub_service)
    second = _read(out)
    assert manifest["rows_written"] == 0        # nothing re-run
    assert len(second) == len(first)            # nothing duplicated


def test_resume_completes_a_partial_grid(mini_manifest, stub_service, tmp_path):
    out = tmp_path / "rows.jsonl"
    run(mini_manifest, out, ["clean"], service=stub_service)
    run(mini_manifest, out, ["clean", "jpeg_q30"], service=stub_service)
    rows = _read(out)
    assert len(rows) == 4
    assert len({(r["sample_id"], r["condition_id"]) for r in rows}) == 4


def test_completed_pairs_tolerates_a_torn_final_line(tmp_path):
    p = tmp_path / "rows.jsonl"
    p.write_text('{"sample_id": "a:clean", "condition_id": "clean"}\n{"sample_id": "b:cl')
    assert completed_pairs(p) == {("a:clean", "clean")}


# --- run manifest ---------------------------------------------------------
def test_run_manifest_records_provenance_and_the_single_expert_caveat(
    mini_manifest, stub_service, tmp_path
):
    out = tmp_path / "rows.jsonl"
    manifest = run(mini_manifest, out, ["clean"], service=stub_service)
    written = json.loads((out.parent / "run_manifest.json").read_text())
    assert written["manifest_sha256"] == load_manifest(mini_manifest)[1]
    assert written["methods"][0]["method_id"] == "stub_expert"
    assert written["pipeline_version"]
    # the caveat must travel with the artifact, not just live in a chat message
    assert "not a multi-method shootout" in written["note"].replace("NOT", "not")


def test_limit_restricts_sources(mini_manifest, stub_service, tmp_path):
    out = tmp_path / "rows.jsonl"
    manifest = run(mini_manifest, out, ["clean"], limit=1, service=stub_service)
    assert manifest["n_sources"] == 1
    assert len(_read(out)) == 1
