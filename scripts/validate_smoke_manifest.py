#!/usr/bin/env python3
"""Validate smoke-manifest integrity; optionally report perceptual near duplicates."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from src.pipeline.decode import DecodeError, decode_image

SCHEMA = ["manifest_version", "sample_id", "source_id", "relative_path", "label", "class_name", "dataset", "dataset_split", "dataset_revision", "source_uri", "source_group", "generator", "license_id", "original_sha256", "decoded_phash", "width", "height", "format", "selection_seed"]
SUPPORTED = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
LICENSE_IDS = {"COCO-TERMS", "SID-CC-BY-4.0"}

def validate(path: Path, root: Path | None = None, near_threshold: int | None = None) -> list[tuple[str, str, int]]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    rows = doc.get("images") if isinstance(doc, dict) else doc
    if not isinstance(rows, list) or not rows: raise ValueError("manifest images must be a non-empty list")
    if not isinstance(doc, dict) or doc.get("manifest_version") != "smoke.v1":
        raise ValueError("manifest envelope must declare smoke.v1")
    if any(k not in row for row in rows for k in SCHEMA): raise ValueError("row is missing a required schema field")
    if any(row["manifest_version"] != "smoke.v1" for row in rows): raise ValueError("unsupported manifest version")
    if any(row["selection_seed"] != doc.get("selection_seed") for row in rows):
        raise ValueError("selection_seed differs between envelope and row")
    if re.search("val2017", json.dumps(doc, ensure_ascii=False), re.IGNORECASE): raise ValueError("forbidden val2017 occurrence")
    if {int(r["label"]) for r in rows} != {0, 1}: raise ValueError("both labels 0 and 1 are required")
    if sum(r["label"] == 0 for r in rows) != sum(r["label"] == 1 for r in rows): raise ValueError("manifest is not balanced")
    root = root or path.parent.parent.parent
    hashes: set[str] = set(); phashes: list[tuple[str, str]] = []
    if len({r["sample_id"] for r in rows}) != len(rows) or len({r["source_id"] for r in rows}) != len(rows):
        raise ValueError("sample_id and source_id must be unique")
    for row in rows:
        expected_class = {0: "real", 1: "fully_synthetic"}.get(row["label"])
        if expected_class is None or row["class_name"] != expected_class:
            raise ValueError("invalid label/class mapping")
        if row["license_id"] not in LICENSE_IDS: raise ValueError(f"unknown license_id: {row['license_id']}")
        fp = Path(row["relative_path"]); full = fp if fp.is_absolute() else root / fp
        if full.suffix.lower() not in SUPPORTED: raise ValueError(f"unsupported image: {fp}")
        try:
            decoded = decode_image(full)
            sha = decoded.sha256
            width, height = decoded.width, decoded.height
            fmt = (decoded.orig_format or full.suffix[1:]).upper()
            actual_phash = decoded.phash
        except DecodeError as exc:
            raise ValueError(f"unreadable image {fp}: {exc}") from exc
        if sha != row["original_sha256"]: raise ValueError(f"SHA256 mismatch: {fp}")
        if sha in hashes: raise ValueError(f"exact duplicate SHA256: {fp}")
        hashes.add(sha)
        if row["width"] != width or row["height"] != height or row["format"] != fmt or width < 1 or height < 1: raise ValueError(f"dimension/format mismatch: {fp}")
        if not re.fullmatch(r"[0-9a-fA-F]{16}", str(row["decoded_phash"])): raise ValueError(f"invalid decoded_phash: {fp}")
        if str(row["decoded_phash"]).lower() != actual_phash: raise ValueError(f"decoded_phash mismatch: {fp}")
        phashes.append((str(row["relative_path"]), str(row["decoded_phash"])))
    pairs: list[tuple[str, str, int]] = []
    if near_threshold is not None:
        if near_threshold < 0 or near_threshold > 64: raise ValueError("near threshold must be 0..64")
        for i, (name, a) in enumerate(phashes):
            for name2, b in phashes[i + 1:]:
                d = (int(a, 16) ^ int(b, 16)).bit_count()
                if d <= near_threshold: pairs.append((name, name2, d))
    return pairs

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("manifest", type=Path)
    p.add_argument("--root", type=Path)
    p.add_argument("--near-threshold", type=int)
    a = p.parse_args()
    try:
        pairs = validate(a.manifest, a.root, a.near_threshold)
    except (ValueError, OSError, json.JSONDecodeError) as exc: p.error(str(exc))
    rows = json.loads(a.manifest.read_text(encoding="utf-8")).get("images", [])
    print(f"valid: {a.manifest} ({len(rows)} rows)")
    if a.near_threshold is not None:
        print(f"near_duplicates threshold={a.near_threshold}: {len(pairs)}")
        for left, right, distance in pairs:
            print(f"  {left} <-> {right} (hamming={distance})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
