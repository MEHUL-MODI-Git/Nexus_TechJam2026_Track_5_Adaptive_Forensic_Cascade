"""Compute canonical SHA-256 + pHash for every corpus source (2R.2 prerequisite).

Perceptual dedup and the sealed-reference denylist check both need a pHash per
source, and the corpus manifest carries none (only the acquisition-time
`original_sha256`). This computes both through the SAME canonical decode path
the pipeline uses, so a hash here means the same thing as a hash anywhere else
in the system.

Output is a sidecar keyed by `source_id`, never an edit of the acquisition
manifest -- that manifest records what was acquired and must stay as-written.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.pipeline.decode import DecodeError, decode_image

SCHEMA = "corpus-hashes.v1"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", type=Path,
                    default=Path("data/manifests/router_corpus_v1.json"))
    ap.add_argument("--out", type=Path,
                    default=Path("data/manifests/router_corpus_hashes.json"))
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    manifest = json.loads(args.manifest.read_text())
    rows = manifest["images"]
    if args.limit:
        rows = rows[: args.limit]

    started = time.perf_counter()
    hashes: dict[str, dict] = {}
    failures: list[dict] = []
    mismatches: list[dict] = []

    for i, row in enumerate(rows):
        path = Path(row["relative_path"])
        try:
            decoded = decode_image(path)
        except DecodeError as exc:
            # A source we cannot decode is a real acquisition failure. Record it
            # and keep going: the manifest builder decides what to do about it,
            # this script only measures.
            failures.append({"source_id": row["source_id"], "path": str(path),
                             "error": str(exc)})
            continue
        if decoded.sha256 != row["original_sha256"]:
            # The bytes on disk are not the bytes we recorded acquiring.
            mismatches.append({"source_id": row["source_id"], "path": str(path),
                               "manifest_sha256": row["original_sha256"],
                               "disk_sha256": decoded.sha256})
        hashes[row["source_id"]] = {
            "sha256": decoded.sha256,
            "phash": decoded.phash,
            "width": decoded.width,
            "height": decoded.height,
            "warnings": decoded.warnings,
        }
        if (i + 1) % 1000 == 0:
            rate = (i + 1) / (time.perf_counter() - started)
            print(f"  {i + 1}/{len(rows)} · {rate:.1f} img/s", file=sys.stderr, flush=True)

    payload = {
        "schema_version": SCHEMA,
        "source_manifest": str(args.manifest),
        "source_manifest_version": manifest.get("manifest_version"),
        "n_requested": len(rows),
        "n_hashed": len(hashes),
        "n_decode_failures": len(failures),
        "n_sha256_mismatches": len(mismatches),
        "decode_failures": failures,
        "sha256_mismatches": mismatches,
        "elapsed_seconds": round(time.perf_counter() - started, 1),
        "hashes": hashes,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps({k: payload[k] for k in
                      ("n_requested", "n_hashed", "n_decode_failures",
                       "n_sha256_mismatches", "elapsed_seconds")}, indent=2),
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
