"""Split the corpus into a protected FITTING role and an UNTOUCHED INTERNAL TEST role (2R.2).

Three separation rules, all enforced here rather than trusted:

1. **Exact duplicates.** One SHA-256 belongs to exactly one source. Verified, not assumed.
2. **Perceptual near-duplicates.** Two images of the same scene must never straddle a role
   boundary, or the "untouched" test set is not untouched. Threshold is Hamming <= 4 on the
   64-bit pHash, CALIBRATED by opening images rather than taken from a default: at distance 0
   and 4 the pairs are the same scene (two samples of one prompt), while at distance 6 they are
   a girl in a paddling pool and an AI puppy. The `feature_cache` sealed-denylist default of 6
   stays as it is -- for contamination a false positive is cheap and a false negative is fatal,
   which is the opposite asymmetry to this one.
3. **Source atomicity.** A source's clean and transformed views always share a split, which the
   role assignment preserves by construction because it assigns SOURCES, never views.

Near-duplicate clusters are assigned WHOLE to one role. Nothing is deleted: the cluster is the
unit of assignment, exactly as `source_id` already is, so the leak closes at zero data cost.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

POPCOUNT = np.array([i.bit_count() for i in range(256)], dtype=np.uint8)
SCHEMA = "router-role-manifest.v1"


def cluster_near_duplicates(phashes: list[str], threshold: int, chunk: int = 512) -> list[int]:
    """Union-find over all pairs within `threshold`. Returns a cluster id per index."""
    matrix = np.stack([np.frombuffer(bytes.fromhex(h), dtype=np.uint8) for h in phashes])
    parent = list(range(len(matrix)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for start in range(0, len(matrix), chunk):
        block = matrix[start:start + chunk]
        dist = POPCOUNT[np.bitwise_xor(block[:, None, :], matrix[None, :, :])].sum(axis=2)
        for r, c in zip(*np.nonzero(dist <= threshold), strict=True):
            i, j = start + int(r), int(c)
            if i < j:
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[max(ri, rj)] = min(ri, rj)
    return [find(i) for i in range(len(matrix))]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", type=Path, default=Path("data/manifests/router_corpus_v2.json"))
    ap.add_argument("--hashes", type=Path,
                    default=Path("data/manifests/router_corpus_hashes_v2.json"))
    ap.add_argument("--test-size", type=int, default=3000, help="untouched internal test sources")
    ap.add_argument("--dev-fraction", type=float, default=0.25, help="of the FITTING role")
    ap.add_argument("--phash-threshold", type=int, default=4)
    ap.add_argument("--seed", type=int, default=20260827)
    ap.add_argument("--denylist", type=Path, default=Path("data/manifests/sealed_denylist.txt"),
                    help="pre-exclude any source the sealed-denylist rule would flag")
    ap.add_argument("--denylist-phash-threshold", type=int, default=6,
                    help="must match feature_cache's default; the CACHE aborts on a hit, so a "
                         "source it would reject must never reach a role manifest")
    ap.add_argument("--out-dir", type=Path, default=Path("data/manifests"))
    args = ap.parse_args()

    manifest = json.loads(args.manifest.read_text())
    hashes = json.loads(args.hashes.read_text())["hashes"]
    rows = manifest["images"]

    missing = [r["source_id"] for r in rows if r["source_id"] not in hashes]
    if missing:
        raise SystemExit(f"{len(missing)} sources have no hash; run scripts/hash_corpus.py first")

    # Rule 1: exact-duplicate check on the CANONICAL decoded hash, not the acquisition hash.
    by_sha: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        by_sha[hashes[row["source_id"]]["sha256"]].append(row["source_id"])
    collisions = {k: v for k, v in by_sha.items() if len(v) > 1}
    if collisions:
        raise SystemExit(f"{len(collisions)} SHA-256 collisions across sources: "
                         f"{list(collisions.items())[:3]}")

    # Pre-exclude anything the sealed-denylist rule would flag. `feature_cache`
    # ABORTS the whole extraction on a hit rather than skipping the row -- correct
    # behaviour, but it means a single flagged source kills an 8.5-hour job at
    # startup. Two of ours are known false positives at distance exactly 6 (a
    # Nokia phone matched against a glittery toilet; a crow on white sky against
    # a skier in snow), both opened and confirmed unrelated. We drop them anyway:
    # arguing with a contamination guard to keep 2 sources out of 15,000 is a
    # terrible trade, and lowering the threshold to accommodate them would weaken
    # the one check standing between us and a disqualifying result.
    excluded: list[dict] = []
    if args.denylist and args.denylist.exists():
        sealed_ph = []
        for line in args.denylist.read_text().splitlines():
            body = line.split("#", 1)[0].strip()
            if body:
                for field in body.split()[1:]:
                    if field.startswith("phash="):
                        sealed_ph.append(field.split("=", 1)[1])
        if sealed_ph:
            sealed = np.stack([np.frombuffer(bytes.fromhex(h), dtype=np.uint8)
                               for h in sealed_ph])
            keep = []
            for row in rows:
                own = np.frombuffer(bytes.fromhex(hashes[row["source_id"]]["phash"]),
                                    dtype=np.uint8)
                dist = int(POPCOUNT[np.bitwise_xor(own[None, :], sealed)].sum(axis=1).min())
                if dist <= args.denylist_phash_threshold:
                    excluded.append({"source_id": row["source_id"], "phash_distance": dist})
                else:
                    keep.append(row)
            if excluded:
                print(f"excluded {len(excluded)} source(s) the sealed denylist would flag: "
                      f"{[e['source_id'] for e in excluded]}")
            rows = keep

    source_ids = [r["source_id"] for r in rows]
    labels = {r["source_id"]: r["label"] for r in rows}
    cluster_of = cluster_near_duplicates(
        [hashes[s]["phash"] for s in source_ids], args.phash_threshold)

    clusters: dict[int, list[str]] = defaultdict(list)
    for sid, cid in zip(source_ids, cluster_of, strict=True):
        clusters[cid].append(sid)

    # A cluster spanning both labels cannot help class balance and must never sit in the test
    # set, where a mislabelled near-twin would corrupt the one number we report.
    pure: dict[int, list[list[str]]] = {0: [], 1: []}
    mixed: list[list[str]] = []
    for members in clusters.values():
        member_labels = {labels[s] for s in members}
        if len(member_labels) == 1:
            pure[next(iter(member_labels))].append(members)
        else:
            mixed.append(members)

    rng = np.random.default_rng(args.seed)
    per_class_test = args.test_size // 2
    role: dict[str, str] = {}

    for label in (0, 1):
        groups = sorted(pure[label], key=lambda g: (-len(g), g[0]))   # deterministic order
        order = rng.permutation(len(groups))
        taken = 0
        for idx in order:
            group = groups[idx]
            # Only take a cluster whole and only while it fits exactly.
            if taken + len(group) <= per_class_test:
                for sid in group:
                    role[sid] = "internal_test"
                taken += len(group)
        if taken != per_class_test:
            raise SystemExit(f"label {label}: could only place {taken}/{per_class_test} test "
                             "sources with whole clusters; lower --test-size")
    for members in mixed:                       # cross-label clusters -> fitting, never test
        for sid in members:
            role.setdefault(sid, "fitting")
    for sid in source_ids:
        role.setdefault(sid, "fitting")

    # train/dev inside the FITTING role only, again cluster-atomic and label-stratified.
    split: dict[str, str] = {}
    for label in (0, 1):
        groups = [g for g in pure[label] if role[g[0]] == "fitting"]
        groups = sorted(groups, key=lambda g: g[0])
        order = rng.permutation(len(groups))
        n_fitting = sum(len(g) for g in groups)
        want_dev = round(n_fitting * args.dev_fraction)
        taken = 0
        for idx in order:
            group = groups[idx]
            target = "dev" if taken + len(group) <= want_dev else "train"
            if target == "dev":
                taken += len(group)
            for sid in group:
                split[sid] = target
    for members in mixed:
        for sid in members:
            split.setdefault(sid, "train")
    for sid in source_ids:
        split.setdefault(sid, "train")

    # ---- verification: assert the separation instead of hoping for it -------
    cluster_roles = {cid: {role[s] for s in members} for cid, members in clusters.items()}
    straddling = [cid for cid, rs in cluster_roles.items() if len(rs) > 1]
    cluster_splits = {cid: {split[s] for s in members if role[s] == "fitting"}
                      for cid, members in clusters.items()}
    split_straddling = [cid for cid, ss in cluster_splits.items() if len(ss) > 1]
    if straddling or split_straddling:
        raise SystemExit(f"FATAL: {len(straddling)} clusters straddle roles and "
                         f"{len(split_straddling)} straddle train/dev")

    def counts(predicate):
        return {"real": sum(1 for r in rows if predicate(r["source_id"]) and r["label"] == 0),
                "fake": sum(1 for r in rows if predicate(r["source_id"]) and r["label"] == 1)}

    summary = {
        "schema_version": SCHEMA,
        "source_manifest": str(args.manifest),
        "phash_threshold": args.phash_threshold,
        "seed": args.seed,
        "n_sources": len(rows),
        "excluded_by_sealed_denylist": excluded,
        "denylist_phash_threshold": args.denylist_phash_threshold,
        "n_clusters": len(clusters),
        "n_multi_source_clusters": sum(1 for m in clusters.values() if len(m) > 1),
        "n_cross_label_clusters": len(mixed),
        "clusters_straddling_roles": 0,
        "clusters_straddling_train_dev": 0,
        "internal_test": counts(lambda s: role[s] == "internal_test"),
        "fitting": counts(lambda s: role[s] == "fitting"),
        "fitting_train": counts(lambda s: role[s] == "fitting" and split[s] == "train"),
        "fitting_dev": counts(lambda s: role[s] == "fitting" and split[s] == "dev"),
    }

    for role_name in ("fitting", "internal_test"):
        subset = [dict(r, dataset_split=(split[r["source_id"]] if role_name == "fitting" else "test"),
                       role=role_name,
                       decoded_sha256=hashes[r["source_id"]]["sha256"],
                       decoded_phash=hashes[r["source_id"]]["phash"],
                       near_duplicate_cluster=cluster_of[source_ids.index(r["source_id"])])
                  for r in rows if role[r["source_id"]] == role_name]
        out = args.out_dir / f"router_corpus_{role_name}.json"
        payload = {k: v for k, v in manifest.items() if k != "images"}
        payload.update({"schema_version": SCHEMA, "role": role_name,
                        "role_summary": summary, "images": subset})
        out.write_text(json.dumps(payload, indent=2) + "\n")
        print(f"wrote {out} ({len(subset)} sources)")

    (args.out_dir / "router_corpus_roles_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
