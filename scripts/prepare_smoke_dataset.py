#!/usr/bin/env python3
"""Build a deterministic, balanced smoke manifest from two local directories."""
from __future__ import annotations

import argparse
import json
import random
import re
from pathlib import Path
from typing import Any

from src.pipeline.decode import DecodeError, decode_image

SUPPORTED = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
SCHEMA = ["manifest_version", "sample_id", "source_id", "relative_path", "label",
          "class_name", "dataset", "dataset_split", "dataset_revision", "source_uri",
          "source_group", "generator", "license_id", "original_sha256", "decoded_phash",
          "width", "height", "format", "selection_seed"]
_FORBIDDEN = re.compile("val2017", re.IGNORECASE)


def _metadata(path: Path) -> tuple[str, str, int, int, str]:
    """Use the canonical decoder so manifest hashes match every later stage."""
    decoded = decode_image(path)
    return (
        decoded.sha256,
        decoded.phash,
        decoded.width,
        decoded.height,
        (decoded.orig_format or path.suffix[1:]).upper(),
    )


def _reject_forbidden(row: dict[str, Any]) -> None:
    encoded = json.dumps(row, ensure_ascii=False)
    if _FORBIDDEN.search(encoded):
        raise ValueError("forbidden val2017 occurrence in path or metadata")


def build_manifest(args: argparse.Namespace) -> dict[str, Any]:
    seed = int(args.seed)
    requested_count = int(args.count)
    if requested_count < 1:
        raise ValueError("count must be at least 1 per class")
    candidates: list[tuple[int, Path]] = []
    for label, root in ((0, Path(args.real_dir)), (1, Path(args.fake_dir))):
        if not root.is_dir():
            raise ValueError(f"source directory does not exist: {root}")
        paths = sorted(
            (p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED),
            key=lambda p: (
                p.relative_to(root).as_posix().lower(),
                p.relative_to(root).as_posix(),
            ),
        )
        if any(_FORBIDDEN.search(p.as_posix()) for p in paths):
            raise ValueError("forbidden val2017 occurrence in path or metadata")
        if len(paths) < requested_count:
            raise ValueError(
                f"requested {requested_count} images but found {len(paths)} in {root}"
            )
        rng = random.Random(seed + label)
        rng.shuffle(paths)
        candidates.extend((label, p) for p in paths[:requested_count])
    if len([x for x in candidates if x[0] == 0]) != len([x for x in candidates if x[0] == 1]):
        raise ValueError("balanced selection failed")

    rows: list[dict[str, Any]] = []
    seen: dict[str, int] = {}
    for index, (label, path) in enumerate(candidates):
        root = Path(args.real_dir) if label == 0 else Path(args.fake_dir)
        try:
            sha, phash, width, height, fmt = _metadata(path)
        except DecodeError as exc:
            raise ValueError(f"cannot decode image {path}: {exc}") from exc
        if sha in seen:
            raise ValueError(f"exact duplicate SHA256: {path} duplicates row {seen[sha]}")
        row = {
            "manifest_version": "smoke.v1", "sample_id": f"smoke-{index:06d}",
            "source_id": f"{label}-{sha[:16]}", "relative_path": path.relative_to(Path.cwd()).as_posix()
            if path.is_relative_to(Path.cwd()) else path.as_posix(), "label": label,
            "class_name": "real" if label == 0 else "fully_synthetic", "dataset": args.dataset_real if label == 0 else args.dataset_fake,
            "dataset_split": args.split_real if label == 0 else args.split_fake,
            "dataset_revision": args.revision_real if label == 0 else args.revision_fake,
            "source_uri": args.uri_real if label == 0 else args.uri_fake,
            "source_group": args.group_real if label == 0 else args.group_fake,
            "generator": "" if label == 0 else args.generator_fake,
            "license_id": args.license_real if label == 0 else args.license_fake,
            "original_sha256": sha, "decoded_phash": phash, "width": width, "height": height,
            "format": fmt, "selection_seed": seed,
        }
        _reject_forbidden(row)
        seen[sha] = index
        rows.append(row)
    rows.sort(key=lambda r: r["relative_path"].lower())
    for i, row in enumerate(rows):
        row["sample_id"] = f"smoke-{i:06d}"
    return {"manifest_version": "smoke.v1", "selection_seed": seed, "images": rows}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--real-dir", required=True); p.add_argument("--fake-dir", required=True)
    p.add_argument("--output", type=Path, required=True); p.add_argument("--count", type=int, default=200)
    p.add_argument("--seed", type=int, default=20260826)
    for name, default in (("dataset-real", "COCO"), ("dataset-fake", "SID-Set"), ("split-real", "train2017"),
                          ("split-fake", "fully_synthetic"), ("revision-real", "unspecified"), ("revision-fake", "unspecified"),
                          ("uri-real", "local"), ("uri-fake", "local"), ("group-real", "coco"), ("group-fake", "sid-set"),
                          ("generator-fake", "unspecified"), ("license-real", "COCO-TERMS"), ("license-fake", "SID-CC-BY-4.0")):
        p.add_argument("--" + name, default=default)
    args = p.parse_args()
    try:
        manifest = build_manifest(args)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    except ValueError as exc:
        p.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
