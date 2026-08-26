import json
from types import SimpleNamespace

import pytest

from scripts import download_smoke_sources as d


def _rows(dataset, config, split, revision, offset):
    if dataset == d.REAL[0]:
        return ([{"row_idx": offset, "row": {"image_id": offset, "coco_url": f"https://x/{offset}.jpg"}}], "https://datasets-server.huggingface.co/rows?dataset=phiyodr%2Fcoco2017")
    return ([{"row_idx": offset, "row": {"img_id": f"full_synthetic_{offset:06d}", "label": 1, "image": {"src": f"https://x/f{offset}.png"}}}], "https://datasets-server.huggingface.co/rows?dataset=saberzl%2FSID_Set")


def test_determinism_filter_and_no_signed_url(monkeypatch, tmp_path):
    monkeypatch.setattr(d, "_page", _rows)
    def fetch(url, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")
        return SimpleNamespace(sha256=str(abs(hash(url))))
    monkeypatch.setattr(d, "_download", fetch)
    a = d.acquire(1, 7, tmp_path / "images")
    b = d.acquire(1, 7, tmp_path / "images")
    assert a == b
    assert all("X-Amz-Signature" not in json.dumps(x) for x in a["images"])
    assert {x["label"] for x in a["images"]} == {0, 1}


def test_val2017_guard(monkeypatch, tmp_path):
    def bad(*args):
        return ([{"row_idx": 0, "row": {"id": "x", "coco_url": "https://x/val2017.jpg"}}], "page")
    monkeypatch.setattr(d, "_page", bad)
    with pytest.raises(ValueError, match="val2017"):
        d.acquire(1, 1, tmp_path)


def test_duplicate_sha_rejected(monkeypatch, tmp_path):
    monkeypatch.setattr(d, "_page", _rows)
    monkeypatch.setattr(d, "_download", lambda url, path: SimpleNamespace(sha256="same"))
    with pytest.raises(ValueError, match="duplicate"):
        d.acquire(1, 2, tmp_path)
