"""Router training corpus acquisition (Phase 2, training workstream).

Sources BOTH classes from SID-Set, and that is a deliberate methodological
choice rather than a convenience:

If real images came from COCO and synthetic ones from SID-Set, the two classes
would differ in ways that have nothing to do with being AI-generated — encoder
pipeline, resolution distribution, compression history. Our router consumes
quality descriptors (blockiness, noise, resolution) precisely because they carry
signal, which means it could learn "this looks like a COCO file" and post an
excellent dev score that collapses on anything else. Drawing both classes from
one curation pipeline removes that shortcut. SID-Set publishes label 0 (real),
1 (fully synthetic) and 2 (tampered); we take 0 and 1 and drop tampered, since
the track is about fully generated images.

Acquisition reads parquet shards from the Hub directly. The datasets-server
`/rows` endpoint that the smoke set used is anonymously rate-limited (it
returned HTTP 429 during this work) and cannot carry corpus scale.

KNOWN LIMITATION: SID-Set does not expose which generator produced a synthetic
image, so all synthetic rows share one `source_group` and the train/dev split is
a per-source hash split, not a generator-grouped one. Dev scores therefore
measure generalisation to unseen IMAGES, not to unseen GENERATORS. That bound is
recorded in the manifest and must travel with any number derived from it.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DATASET = "saberzl/SID_Set"
REVISION = "dc03ead57929879319ce30a82bfcfb8d317b10bd"
LICENSE_ID = "SID-CC-BY-4.0"
MANIFEST_VERSION = "router-corpus.v1"
N_TRAIN_SHARDS = 249

# label -> (our binary label, class name, source_group). Label 2 (tampered) is
# deliberately absent: partially-edited images are a different problem.
LABEL_MAP = {
    0: (0, "real", "SID-Set-real"),
    1: (1, "fully_synthetic", "SID-Set-full-synthetic"),
}


def extract_shard(shard_index: int, needed: dict[int, int], out_root: Path,
                  purge: bool = True, seen: set[str] | None = None) -> list[dict]:
    """Download one parquet shard, write out the images we still need.

    R19: `seen` carries the exact-SHA dedup ACROSS shards, so `needed` counts
    UNIQUE sources. The previous version deduplicated only after the whole
    acquisition loop had finished, by which time `needed` had already been
    decremented for the duplicate -- which is precisely how a run asked for
    15,000 sources wrote a manifest containing 14,999 and said nothing.
    """
    seen = seen if seen is not None else set()
    import pyarrow.parquet as pq
    from huggingface_hub import hf_hub_download

    name = f"data/train-{shard_index:05d}-of-{N_TRAIN_SHARDS:05d}.parquet"
    path = hf_hub_download(DATASET, name, repo_type="dataset", revision=REVISION)
    # Read only the columns we use — the `mask` column is most of the file size.
    table = pq.read_table(path, columns=["img_id", "image", "label", "width", "height"])
    rows: list[dict] = []
    for i in range(table.num_rows):
        label_raw = table.column("label")[i].as_py()
        if label_raw not in LABEL_MAP or needed.get(label_raw, 0) <= 0:
            continue
        binary, class_name, group = LABEL_MAP[label_raw]
        image_cell = table.column("image")[i].as_py()
        data = image_cell.get("bytes") if isinstance(image_cell, dict) else image_cell
        if not data:
            continue
        try:
            from PIL import Image

            Image.open(io.BytesIO(data)).verify()     # reject corrupt rows now
        except Exception:      # noqa: BLE001, S112 -- a corrupt shard row is an
            continue           # expected upstream condition, not our error to log
        digest = hashlib.sha256(data).hexdigest()
        if digest in seen:
            continue          # already have this exact image; do NOT spend a slot
        seen.add(digest)
        img_id = table.column("img_id")[i].as_py()
        rel = f"data/corpus/images/{class_name}/{digest[:16]}.jpg"
        dest = out_root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        rows.append({
            "dataset": DATASET, "dataset_revision": REVISION, "split_source": "train",
            "shard": name, "row_idx": i, "img_id": img_id,
            "relative_path": rel, "label": binary, "class_name": class_name,
            "source_group": group, "generator": None, "license_id": LICENSE_ID,
            "original_sha256": digest,
            "width": table.column("width")[i].as_py(),
            "height": table.column("height")[i].as_py(),
        })
        needed[label_raw] -= 1
    if purge:
        # Shards are ~490 MB each; keeping 50 of them would cost ~25 GB of cache
        # for data we have already extracted.
        Path(path).unlink(missing_ok=True)
    return rows


def assign_split(rows: list[dict], dev_fraction: float) -> str:
    """Deterministic, label-stratified split keyed on content hash.

    Hash-keyed rather than random so the assignment is reproducible from the
    manifest alone and stable if the corpus is later extended.
    """
    groups = {r["source_group"] for r in rows}
    for label in (0, 1):
        subset = sorted([r for r in rows if r["label"] == label],
                        key=lambda r: r["original_sha256"])
        cut = int(len(subset) * dev_fraction)
        for i, row in enumerate(subset):
            row["dataset_split"] = "dev" if i < cut else "train"
    return ("grouped by source_group" if len(groups) > 2
            else "per-source hash split, label-stratified (generator identity unavailable)")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the router training corpus.")
    parser.add_argument("--per-class", type=int, required=True)
    parser.add_argument("--dev-fraction", type=float, default=0.25)
    parser.add_argument("--max-shards", type=int, default=60)
    parser.add_argument("--keep-shards", action="store_true",
                        help="do not delete downloaded parquet shards (uses ~490MB each)")
    parser.add_argument("--out", type=Path,
                        default=Path("data/manifests/router_corpus_v1.json"))
    parser.add_argument("--augment", type=Path, default=None,
                        help="top up an existing manifest to --per-class instead of "
                             "starting fresh; rows whose image is missing from disk "
                             "are dropped and re-acquired")
    parser.add_argument("--allow-underfill", action="store_true",
                        help="write the manifest even if fewer sources were acquired "
                             "than requested (R19: OFF by default -- a silent "
                             "underfill is what this flag exists to prevent)")
    args = parser.parse_args()

    root = Path.cwd()
    started = time.perf_counter()

    # --augment: keep every existing row whose image is still ON DISK. A row
    # pointing at a deleted file is not a source we have, and counting it as
    # one is how the corpus came to claim 14,999 sources while holding 13,799.
    rows: list[dict] = []
    seen: set[str] = set()
    dropped_missing = 0
    if args.augment:
        existing = json.loads(args.augment.read_text())["images"]
        for row in existing:
            if (root / row["relative_path"]).exists():
                rows.append(row)
                seen.add(row["original_sha256"])
            else:
                dropped_missing += 1
        have = {0: sum(1 for r in rows if r["label"] == 0),
                1: sum(1 for r in rows if r["label"] == 1)}
        print(f"augmenting: kept {len(rows)} on-disk rows "
              f"(real={have[0]} fake={have[1]}), dropped {dropped_missing} whose "
              f"image is gone", file=sys.stderr)
    else:
        have = {0: 0, 1: 0}
    needed = {0: args.per_class - have[0], 1: args.per_class - have[1]}

    for shard in range(args.max_shards):
        if all(v <= 0 for v in needed.values()):
            break
        try:
            got = extract_shard(shard, needed, root, purge=not args.keep_shards,
                                seen=seen)
        except Exception as exc:                       # noqa: BLE001
            print(f"  shard {shard} failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            continue
        rows.extend(got)
        print(f"  shard {shard:03d}: +{len(got):4d} rows · still needed "
              f"real={max(0, needed[0])} fake={max(0, needed[1])} · "
              f"{time.perf_counter() - started:.0f}s", file=sys.stderr)

    # Exact-duplicate guard. Dedup now happens during acquisition (R19), so
    # this is a post-condition check rather than a filter: if it ever removes a
    # row, the in-loop guard failed and the counts below cannot be trusted.
    by_digest: dict[str, str] = {}
    deduped: list[dict] = []
    for row in rows:
        if row["original_sha256"] in by_digest:
            continue
        by_digest[row["original_sha256"]] = row["relative_path"]
        deduped.append(row)
    if len(deduped) != len(rows):
        print(f"FATAL: {len(rows) - len(deduped)} duplicate(s) survived in-loop "
              "dedup; acquisition accounting is wrong", file=sys.stderr)
        return 2

    for i, row in enumerate(deduped):
        row["sample_id"] = f"corpus-{i:06d}"
        row["source_id"] = f"{row['label']}-{row['original_sha256'][:16]}"

    split_method = assign_split(deduped, args.dev_fraction)
    counts = {
        f"{split}_{name}": sum(1 for r in deduped
                               if r["dataset_split"] == split and r["class_name"] == name)
        for split in ("train", "dev") for name in ("real", "fully_synthetic")
    }
    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "dataset": DATASET, "dataset_revision": REVISION, "license_id": LICENSE_ID,
        "requested_per_class": args.per_class,
        "acquired": len(deduped),
        "acquired_per_class": {"real": sum(1 for r in deduped if r["label"] == 0),
                               "fully_synthetic": sum(1 for r in deduped if r["label"] == 1)},
        "augmented_from": str(args.augment) if args.augment else None,
        "rows_dropped_image_missing": dropped_missing,
        "exact_duplicates_dropped": len(rows) - len(deduped),
        "counts": counts,
        "split_method": split_method,
        "dev_fraction": args.dev_fraction,
        "both_classes_from_one_dataset": True,
        "design_note": (
            "Both classes come from SID-Set on purpose: sourcing reals from COCO and "
            "fakes from SID-Set would let the router learn dataset artefacts (encoder, "
            "resolution, compression history) instead of AI-generation, and our quality "
            "descriptors would carry that shortcut straight into the model."
        ),
        "grouping_limitation": (
            "SID-Set does not expose generator identity, so all synthetic rows share one "
            "source_group and the split is per-source, not generator-grouped. Dev scores "
            "measure generalisation to unseen IMAGES, not unseen GENERATORS."
        ),
        "excluded": "SID-Set label 2 (tampered) — partial edits are a different problem",
        "elapsed_seconds": round(time.perf_counter() - started, 1),
        "images": deduped,
    }
    if any("val2017" in json.dumps(r).lower() for r in deduped):
        print("FATAL: val2017 reference in corpus", file=sys.stderr)
        return 2

    # R19: an underfilled corpus must be LOUD. Every downstream document quoted
    # `requested_per_class` as though it were delivered.
    per_class = manifest["acquired_per_class"]
    short = {name: args.per_class - count for name, count in per_class.items()
             if count != args.per_class}
    if short and not args.allow_underfill:
        print(f"FATAL: acquired {per_class}, requested {args.per_class} per class "
              f"(short by {short}). Raise --max-shards, or pass --allow-underfill "
              "to record the shortfall deliberately. Refusing to write a manifest "
              "that silently claims a corpus size it does not have.", file=sys.stderr)
        return 2
    if short:
        manifest["underfilled"] = short
        print(f"WARNING: writing an UNDERFILLED manifest, short by {short}",
              file=sys.stderr)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({k: manifest[k] for k in
                      ("acquired", "counts", "exact_duplicates_dropped",
                       "split_method", "elapsed_seconds")}, indent=2), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
