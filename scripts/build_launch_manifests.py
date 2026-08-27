"""Join the role split with the canonicalized images into launch-ready manifests (2R.2).

The feature-cache builder re-hashes the bytes at `relative_path` and REFUSES any manifest whose
`original_sha256` does not describe those bytes (R7b). So pointing the extraction at canonicalized
images is not a matter of adding a column: `relative_path` and `original_sha256` must refer to the
files that will actually be read. The pre-canonicalization values are preserved under
`acquired_relative_path` / `acquired_sha256` so provenance is not lost, and both pHashes are kept so
the shift introduced by the re-encode stays auditable.

Emits one manifest per role. The fitting manifest is what the long extraction consumes; the
internal-test manifest is never given to it.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

SCHEMA = "router-launch-manifest.v1"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--canonical", type=Path,
                    default=Path("data/manifests/router_corpus_canonical.json"))
    ap.add_argument("--roles", nargs="*",
                    default=["data/manifests/router_corpus_fitting.json",
                             "data/manifests/router_corpus_internal_test.json"])
    ap.add_argument("--out-dir", type=Path, default=Path("data/manifests"))
    args = ap.parse_args()

    canonical = json.loads(args.canonical.read_text())
    by_source = {r["source_id"]: r for r in canonical["images"]}

    for role_path in args.roles:
        role_path = Path(role_path)
        payload = json.loads(role_path.read_text())
        rows, rewired = [], 0
        for row in payload["images"]:
            canon = by_source.get(row["source_id"])
            if canon is None:
                raise SystemExit(f"{row['source_id']} has no canonical image; "
                                 "run scripts/canonicalize_corpus.py first")
            new = dict(row)
            new["acquired_relative_path"] = row["relative_path"]
            new["acquired_sha256"] = row["original_sha256"]
            new["acquired_phash"] = row.get("decoded_phash")
            # The two fields the extractor actually reads and verifies:
            new["relative_path"] = canon["canonical_relative_path"]
            new["original_sha256"] = canon["canonical_sha256"]
            new["decoded_phash"] = canon["canonical_phash"]
            new["phash_shift_from_acquired"] = canon.get("phash_shift_from_original")
            new["canonicalization"] = {
                "applied": True,
                "encoder": canonical.get("encoder"),
                "reason": "class-correlated container removed; see A-027. Training data only - "
                          "the inference pipeline is deliberately unchanged.",
            }
            rows.append(new)
            rewired += 1

        missing = [r["source_id"] for r in rows if not Path(r["relative_path"]).exists()]
        if missing:
            raise SystemExit(f"{len(missing)} canonical files missing on disk, e.g. {missing[:3]}")
        shas = {r["original_sha256"] for r in rows}
        if len(shas) != len(rows):
            raise SystemExit(f"canonical sha collision: {len(rows)} rows, {len(shas)} hashes")

        out = args.out_dir / f"launch_{role_path.stem.replace('router_corpus_', '')}.json"
        payload["images"] = rows
        payload["schema_version"] = SCHEMA
        payload["canonical_manifest"] = str(args.canonical)
        out.write_text(json.dumps(payload, indent=2) + "\n")
        print(f"wrote {out}: {rewired} rows rewired to canonical images")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
