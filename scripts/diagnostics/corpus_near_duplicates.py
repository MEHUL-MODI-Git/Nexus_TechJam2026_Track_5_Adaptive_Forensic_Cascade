"""Measure perceptual near-duplicate structure in the router corpus (2R.2).

Exact-SHA dedup already ran at acquisition and dropped exactly 1 image. That
only catches byte-identical files. Two images that differ by a resave, a
resize or a light recompression have different SHAs and the SAME picture --
and if one lands in the fitting set and its twin in the internal test set, the
test set is no longer untouched and every number it produces is inflated.

This script only MEASURES. It does not modify manifests: the policy decision
(which member of a cluster keeps its role) belongs to the heavy owner.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

_POPCOUNT = np.array([i.bit_count() for i in range(256)], dtype=np.uint8)


def phash_to_bytes(hex_str: str) -> np.ndarray:
    """16 hex chars -> 8 uint8s. imagehash renders a 64-bit hash as 16 hex."""
    return np.frombuffer(bytes.fromhex(hex_str), dtype=np.uint8)


def cluster(matrix: np.ndarray, threshold: int, chunk: int = 512):
    """Union-find over all pairs within `threshold` Hamming distance.

    O(n^2) in comparisons but vectorised per chunk: at 14k sources that is
    ~190M byte-XOR popcounts, seconds of numpy, and it is exact. An ANN index
    would be faster and would let a true duplicate slip through unranked --
    the wrong trade when the whole point is a contamination guarantee.
    """
    n = len(matrix)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    pairs = []
    for start in range(0, n, chunk):
        block = matrix[start:start + chunk]
        # (chunk, n, 8) XOR -> popcount -> (chunk, n) Hamming distances
        dist = _POPCOUNT[np.bitwise_xor(block[:, None, :], matrix[None, :, :])].sum(axis=2)
        rows, cols = np.nonzero(dist <= threshold)
        for r, c in zip(rows, cols, strict=True):
            i = start + int(r)
            j = int(c)
            if i < j:
                union(i, j)
                pairs.append((i, j, int(dist[r, c])))
    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    return {k: v for k, v in groups.items() if len(v) > 1}, pairs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--hashes", type=Path,
                    default=Path("data/manifests/router_corpus_hashes.json"))
    ap.add_argument("--manifest", type=Path,
                    default=Path("data/manifests/router_corpus_v1.json"))
    ap.add_argument("--threshold", type=int, default=6,
                    help="Hamming distance; matches feature_cache's sealed-denylist default")
    ap.add_argument("--out", type=Path,
                    default=Path("results/corpus/near_duplicates.json"))
    args = ap.parse_args()

    hashes = json.loads(args.hashes.read_text())["hashes"]
    rows = {r["source_id"]: r for r in json.loads(args.manifest.read_text())["images"]}

    source_ids = sorted(hashes)
    matrix = np.stack([phash_to_bytes(hashes[s]["phash"]) for s in source_ids])
    print(f"{len(source_ids)} sources, threshold <= {args.threshold} Hamming",
          file=sys.stderr)

    groups, pairs = cluster(matrix, args.threshold)

    clusters = []
    for members in groups.values():
        ids = [source_ids[i] for i in members]
        labels = {rows[s]["label"] for s in ids}
        splits = {rows[s]["dataset_split"] for s in ids}
        clusters.append({
            "size": len(ids), "source_ids": ids,
            "labels": sorted(labels), "splits": sorted(splits),
            "cross_label": len(labels) > 1,      # a real and a fake that look identical
            "cross_split": len(splits) > 1,      # already leaking train into dev today
        })
    clusters.sort(key=lambda c: -c["size"])

    payload = {
        "schema_version": "corpus-near-duplicates.v1",
        "threshold_hamming": args.threshold,
        "n_sources": len(source_ids),
        "n_pairs_within_threshold": len(pairs),
        "n_clusters": len(clusters),
        "n_sources_in_clusters": sum(c["size"] for c in clusters),
        "n_redundant_sources": sum(c["size"] - 1 for c in clusters),
        "n_cross_label_clusters": sum(1 for c in clusters if c["cross_label"]),
        "n_cross_split_clusters": sum(1 for c in clusters if c["cross_split"]),
        "clusters": clusters,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps({k: v for k, v in payload.items() if k != "clusters"}, indent=2),
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
