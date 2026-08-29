#!/usr/bin/env python3
"""Acquire the small, reproducible real/fake smoke set (stdlib HTTP only)."""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import tempfile
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from src.pipeline.decode import decode_image

API = "https://datasets-server.huggingface.co/rows"
REAL = ("phiyodr/coco2017", "default", "train", "036f3f8291db64d17faad9b09e59dd30bb65c4d7")
FAKE = ("saberzl/SID_Set", "default", "validation", "dc03ead57929879319ce30a82bfcfb8d317b10bd")
FORBIDDEN = re.compile("val2017", re.IGNORECASE)


def _bad(value) -> bool:
    if isinstance(value, dict):
        return any(_bad(k) or _bad(v) for k, v in value.items())
    if isinstance(value, (list, tuple)):
        return any(_bad(v) for v in value)
    return FORBIDDEN.search(str(value)) is not None


def _page(dataset, config, split, revision, offset, length=100):
    query = urlencode({"dataset": dataset, "config": config, "split": split,
                       "offset": offset, "length": length, "revision": revision})
    uri = API + "?" + query
    last_error = None
    for attempt in range(3):
        try:
            with urlopen(Request(uri, headers={"Accept": "application/json"}), timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
            break
        except Exception as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(0.5 * (attempt + 1))
    else:
        raise RuntimeError(f"dataset page request failed after 3 attempts: {uri}") from last_error
    if _bad(payload):
        raise ValueError("forbidden val2017 occurrence in API response")
    return payload.get("rows", []), uri


def _download(url: str, destination: Path):
    if destination.is_file():
        try:
            return decode_image(destination)
        except Exception:
            destination.unlink()
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=destination.name + ".", suffix=".part", dir=str(destination.parent))
    os.close(fd)
    Path(name).unlink(missing_ok=True)
    part = Path(name)
    try:
        last_error = None
        for attempt in range(3):
            try:
                with urlopen(Request(url, headers={"User-Agent": "TechJam-smoke/1"}), timeout=60) as response:
                    with part.open("wb") as out:
                        while chunk := response.read(1024 * 1024):
                            out.write(chunk)
                decoded = decode_image(part)
                part.replace(destination)
                return decoded
            except Exception as exc:
                last_error = exc
                part.unlink(missing_ok=True)
                if attempt < 2:
                    time.sleep(0.5 * (attempt + 1))
        raise RuntimeError(f"download failed after 3 attempts: {url}") from last_error
    finally:
        part.unlink(missing_ok=True)


def acquire(count=200, seed=20260826, output_root="data/smoke/images", metadata_output=None):
    if count < 1:
        raise ValueError("count must be at least 1")
    root = Path(output_root)
    seen = set()
    metadata = []
    rng = random.Random(seed)
    for label, spec in ((0, REAL), (1, FAKE)):
        dataset, config, split, revision = spec
        # The seeded start makes page selection reproducible while retaining a
        # stable, bounded walk for datasets-server's offset API.
        total_rows = 118_287 if label == 0 else 30_000
        # Page-aligned start over the whole split, not merely its first rows.
        start = rng.randrange(0, max(1, (total_rows - 100) // 100)) * 100
        eligible = []
        page_uri = None
        for page_no in range(1000):
            offset = (start + page_no * 100) % total_rows
            rows, page_uri = _page(dataset, config, split, revision, offset)
            if not rows:
                break
            for item in rows:
                row = item.get("row", item)
                if _bad(row) or _bad(item):
                    raise ValueError("forbidden val2017 occurrence in row metadata")
                if label == 0:
                    url = row.get("coco_url")
                    source_id = str(row.get("image_id", item.get("row_idx", len(eligible))))
                    ok = bool(url)
                else:
                    image = row.get("image") or {}
                    url = image.get("src") if isinstance(image, dict) else None
                    image_id = image.get("id") if isinstance(image, dict) else None
                    source_id = str(
                        row.get("img_id", row.get("source_id", image_id or ""))
                    )
                    ok = row.get("label") == 1 and source_id.startswith("full_synthetic") and bool(url)
                if ok:
                    eligible.append((item, row, source_id, url, page_uri))
            if len(eligible) >= count:
                break
        if len(eligible) < count:
            raise ValueError(f"insufficient eligible rows for {dataset}: requested {count}, found {len(eligible)}")
        rng.shuffle(eligible)
        for index, (item, row, source_id, url, durable_uri) in enumerate(eligible[:count]):
            if _bad(url):
                raise ValueError("forbidden val2017 occurrence in URL")
            suffix = Path(url.split("?", 1)[0]).suffix.lower() or ".jpg"
            relative = Path("real" if label == 0 else "fake") / f"{index:06d}{suffix}"
            path = root / relative
            decoded = _download(url, path)
            if decoded.sha256 in seen:
                raise ValueError(f"exact duplicate SHA256 across classes: {source_id}")
            seen.add(decoded.sha256)
            metadata.append({"dataset": dataset, "revision": revision, "split": split,
                             "row_idx": item.get("row_idx"), "source_id": source_id,
                             "local_relative_path": (Path(output_root) / relative).as_posix(),
                             "license_id": "COCO-TERMS" if label == 0 else "SID-CC-BY-4.0",
                             "label": label, "source_uri": durable_uri})
    result = {"manifest_version": "smoke-acquisition.v1", "seed": seed, "count_per_class": count,
              "images": metadata}
    if metadata_output:
        out = Path(metadata_output); out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--count", type=int, default=200); p.add_argument("--seed", type=int, default=20260826)
    p.add_argument("--output-root", default="data/smoke/images"); p.add_argument("--metadata-output", required=True)
    a = p.parse_args(); acquire(a.count, a.seed, a.output_root, a.metadata_output)


if __name__ == "__main__":
    main()
