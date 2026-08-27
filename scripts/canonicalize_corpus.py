"""Canonicalize the router corpus through one lossy JPEG re-encode (Phase 2R repair).

WHY. The 15,000-source training corpus has a file-format shortcut baked in at
acquisition time: every `real` source is a JPEG container and every
`fully_synthetic` source is a PNG container (the on-disk bytes, regardless of
the `.jpg` extension some rows carry -- see the acquisition manifest). Container
alone predicts the label with 100% accuracy, and the `blockiness` quality
descriptor rides that shortcut straight to AUROC 0.905. Re-encoding BOTH
classes through the same lossy JPEG pass removes the container tell and has
been measured to drop `blockiness` AUROC to 0.64 (q95) / 0.53 (q75).
Re-encoding to PNG is a proven no-op: lossless repackaging cannot remove
compression history already baked into pixel values, so JPEG is the only
option this script offers.

This script never touches the originals. It decodes each source through the
project's canonical decoder (`src.pipeline.decode.decode_image` -- the exact
same bytes-to-pixels path every expert and the feature cache use), re-encodes
the decoded RGB pixels as JPEG, and writes the result to a separate directory.
Pixels are not resized, cropped, or otherwise altered; the only change is the
encode. A sidecar manifest records enough provenance (per-source original and
canonical hashes, and the pHash shift the re-encode introduced) to audit that
the operation did what it claims and nothing more.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.pipeline.decode import DecodeError, decode_image

SCHEMA = "router-corpus-canonical.v1"
JPEG_MAGIC = b"\xff\xd8\xff"


def _hamming(a: str, b: str) -> int:
    return (int(a, 16) ^ int(b, 16)).bit_count()


def _encode_one(row: dict, out_dir: str, quality: int) -> dict:
    """Decode one original source and re-encode it as JPEG. Runs in a worker process.

    Returns a dict with either the canonicalization result or an `error` key;
    the driver decides what to do with failures, this function only measures.
    """
    source_id = row["source_id"]
    src_path = row["relative_path"]
    try:
        decoded = decode_image(src_path)
    except DecodeError as exc:
        return {"source_id": source_id, "path": src_path, "error": str(exc)}

    out_subdir = Path(out_dir) / row["class_name"]
    out_subdir.mkdir(parents=True, exist_ok=True)
    out_path = out_subdir / f"{row['original_sha256'][:16]}.jpg"
    try:
        decoded.image.save(out_path, format="JPEG", quality=quality,
                            subsampling=0, optimize=False)
    except Exception as exc:  # noqa: BLE001 -- a save failure is as fatal as a decode failure
        return {"source_id": source_id, "path": src_path,
                "error": f"encode failed: {type(exc).__name__}: {exc}"}

    canonical_bytes = out_path.read_bytes()
    canonical_sha256 = hashlib.sha256(canonical_bytes).hexdigest()
    try:
        redecoded = decode_image(out_path)
    except DecodeError as exc:
        return {"source_id": source_id, "path": src_path,
                "error": f"re-decode of canonical file failed: {exc}"}

    return {
        "source_id": source_id,
        "canonical_relative_path": str(out_path),
        "canonical_sha256": canonical_sha256,
        "canonical_phash": redecoded.phash,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", type=Path,
                     default=Path("data/manifests/router_corpus_v2.json"))
    ap.add_argument("--out-dir", type=Path, default=Path("data/corpus/canonical"))
    ap.add_argument("--quality", type=int, default=95)
    ap.add_argument("--out-manifest", type=Path,
                     default=Path("data/manifests/router_corpus_canonical.json"))
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--hashes", type=Path,
                     default=Path("data/manifests/router_corpus_hashes_v2.json"),
                     help="original per-source pHash lookup, keyed by source_id")
    args = ap.parse_args()

    manifest = json.loads(args.manifest.read_text())
    rows = manifest["images"]
    rows_by_id = {row["source_id"]: row for row in rows}
    original_hashes = json.loads(args.hashes.read_text())["hashes"]

    args.out_dir.mkdir(parents=True, exist_ok=True)

    started = time.perf_counter()
    results: dict[str, dict] = {}
    failures: list[dict] = []

    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(_encode_one, row, str(args.out_dir), args.quality)
                   for row in rows]
        for done, future in enumerate(as_completed(futures), start=1):
            result = future.result()
            if "error" in result:
                failures.append(result)
            else:
                results[result["source_id"]] = result
            if done % 1000 == 0:
                rate = done / (time.perf_counter() - started)
                print(f"  {done}/{len(rows)} · {rate:.1f} img/s", file=sys.stderr, flush=True)

    canonical_rows: list[dict] = []
    for source_id, extra in results.items():
        row = rows_by_id[source_id]
        original_phash = original_hashes.get(source_id, {}).get("phash")
        if original_phash is None:
            failures.append({"source_id": source_id, "path": row["relative_path"],
                              "error": "source_id missing from --hashes lookup"})
            continue
        merged = dict(row)
        merged["canonical_relative_path"] = extra["canonical_relative_path"]
        merged["canonical_sha256"] = extra["canonical_sha256"]
        merged["canonical_phash"] = extra["canonical_phash"]
        merged["phash_shift_from_original"] = _hamming(original_phash, extra["canonical_phash"])
        canonical_rows.append(merged)

    counts_per_class: dict[str, int] = {}
    for row in canonical_rows:
        counts_per_class[row["class_name"]] = counts_per_class.get(row["class_name"], 0) + 1

    payload = {
        "schema_version": SCHEMA,
        "source_manifest": str(args.manifest),
        "source_manifest_version": manifest.get("manifest_version"),
        "hashes_manifest": str(args.hashes),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
        "encoder": {"format": "JPEG", "quality": args.quality,
                    "subsampling": 0, "optimize": False},
        "out_dir": str(args.out_dir),
        "n_requested": len(rows),
        "n_sources": len(canonical_rows),
        "counts": counts_per_class,
        "n_failures": len(failures),
        "failures": failures,
        "elapsed_seconds": round(time.perf_counter() - started, 1),
        "images": canonical_rows,
    }
    args.out_manifest.parent.mkdir(parents=True, exist_ok=True)
    args.out_manifest.write_text(json.dumps(payload, indent=2) + "\n")

    # ---- verification: refuse to declare success on a silent problem -------
    ok = True
    print("\n=== verification ===", file=sys.stderr)

    if len(canonical_rows) != len(rows):
        ok = False
        print(f"FAIL: output count {len(canonical_rows)} != input count {len(rows)} "
              f"({len(failures)} failure(s), see {args.out_manifest})", file=sys.stderr)
    else:
        print(f"OK: output count == input count == {len(rows)}", file=sys.stderr)

    input_counts: dict[str, int] = {}
    for row in rows:
        input_counts[row["class_name"]] = input_counts.get(row["class_name"], 0) + 1
    if counts_per_class != input_counts:
        ok = False
        print(f"FAIL: per-class counts {counts_per_class} != input {input_counts}",
              file=sys.stderr)
    else:
        print(f"OK: per-class counts match input: {counts_per_class}", file=sys.stderr)

    bad_magic = []
    for row in canonical_rows:
        with open(row["canonical_relative_path"], "rb") as fh:
            head = fh.read(3)
        if head != JPEG_MAGIC:
            bad_magic.append(row["canonical_relative_path"])
    if bad_magic:
        ok = False
        print(f"FAIL: {len(bad_magic)} output file(s) are not JPEG magic bytes, "
              f"e.g. {bad_magic[:5]}", file=sys.stderr)
    else:
        print(f"OK: all {len(canonical_rows)} output files are JPEG magic bytes "
              f"({JPEG_MAGIC!r})", file=sys.stderr)

    sha_values = [row["canonical_sha256"] for row in canonical_rows]
    n_unique = len(set(sha_values))
    if n_unique != len(sha_values):
        ok = False
        print(f"FAIL: canonical_sha256 collisions: {len(sha_values) - n_unique} "
              f"duplicate(s) among {len(sha_values)} files", file=sys.stderr)
    else:
        print(f"OK: no canonical_sha256 collisions ({n_unique} unique)", file=sys.stderr)

    shifts = sorted(row["phash_shift_from_original"] for row in canonical_rows)
    if shifts:
        mean_shift = sum(shifts) / len(shifts)
        max_shift = shifts[-1]

        def _pct(p: float) -> int:
            idx = min(len(shifts) - 1, round(p * (len(shifts) - 1)))
            return shifts[idx]

        print(f"phash_shift_from_original: mean={mean_shift:.3f} max={max_shift} "
              f"median={_pct(0.5)} p90={_pct(0.9)} p95={_pct(0.95)} p99={_pct(0.99)}",
              file=sys.stderr)
        buckets = [(0, 0), (1, 2), (3, 4), (5, 8), (9, 16), (17, 32), (33, 64)]
        hist = []
        for lo, hi in buckets:
            n = sum(1 for s in shifts if lo <= s <= hi)
            hist.append(f"[{lo}-{hi}]={n}")
        print("phash_shift_from_original distribution: " + " ".join(hist), file=sys.stderr)
    else:
        print("no successful sources; cannot report phash_shift distribution", file=sys.stderr)

    if failures:
        print(f"NOTE: {len(failures)} failure(s) recorded in {args.out_manifest} "
              f"under 'failures'", file=sys.stderr)

    print(json.dumps({"n_requested": len(rows), "n_sources": len(canonical_rows),
                       "counts": counts_per_class, "n_failures": len(failures),
                       "elapsed_seconds": payload["elapsed_seconds"]}, indent=2),
          file=sys.stderr)

    if not ok:
        print("\nVERIFICATION FAILED -- refusing to declare success.", file=sys.stderr)
        return 1
    print("\nVERIFICATION PASSED.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
