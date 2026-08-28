"""Score the PGC candidate on the rows the cascade DEFERS — the rescue set.

Rescue is selective by design, so PGC is only ever asked about images the common
path already flagged as unreliable. Scoring the whole cache would measure a
system we are not proposing to build, and would cost 14x more compute for the
privilege.

The transformed pixels are not stored anywhere (the cache holds features, not
images), so each view is reconstructed the same deterministic way the cache
builder made it: decode the source, then apply the named transform seeded by the
source hash.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.experts.pgc import PGCExpert
from src.pipeline.decode import decode_image
from src.pipeline.transforms import FAMILY_OF, apply_transform
from src.router.head import RouterHead
from src.router.train import build_batch, load_cache_rows, load_checkpoint


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cache", type=Path, required=True)
    ap.add_argument("--checkpoint", type=Path,
                    default=Path("results/router-fitting-v2/router_reliability.pt"))
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--split", default=None,
                    help="restrict to a dataset_split (e.g. 'dev'); default all")
    ap.add_argument("--max-rows", type=int, default=12000)
    ap.add_argument("--seed", type=int, default=20260828)
    args = ap.parse_args()

    head = RouterHead.from_checkpoint(args.checkpoint)
    loaded = load_checkpoint(args.checkpoint)
    thr, rel_thr = head.threshold, head.abstain_threshold
    if rel_thr is None:
        print("REFUSING: checkpoint carries no abstention policy", file=sys.stderr)
        return 2

    rows = load_cache_rows(args.cache / "rows.jsonl")
    if args.split:
        rows = [r for r in rows if r.get("dataset_split") == args.split]
    batch = build_batch(rows, loaded.spec, loaded.standardizer, thr)
    with torch.no_grad():
        out = loaded.model(batch.features, batch.expert_logits, batch.available)
    router_p = out.p_fake.numpy()
    rel = out.reliability.numpy()

    deferred = np.flatnonzero(rel < rel_thr)
    rng = np.random.default_rng(args.seed)
    if deferred.size > args.max_rows:
        deferred = np.sort(rng.choice(deferred, size=args.max_rows, replace=False))
    print(f"rows={len(rows)}  deferred={int((rel < rel_thr).sum())}  scoring={deferred.size}",
          file=sys.stderr)

    expert = PGCExpert()
    root = Path(__file__).resolve().parents[1]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    t0, n_fail = time.perf_counter(), 0
    with args.out.open("w") as fh:
        for n, i in enumerate(deferred, 1):
            row = rows[i]
            try:
                decoded = decode_image(root / row["relative_path"])
                image = decoded.image
                if row["condition_id"] != "clean":
                    image = apply_transform(image, row["condition_id"], decoded.sha256)
                from dataclasses import replace
                view = replace(decoded, image=image, width=image.width, height=image.height)
                pred = expert.predict(view)
                rec = {"view_id": row["view_id"], "source_id": row["source_id"],
                       "condition_id": row["condition_id"],
                       "family": row.get("family") or FAMILY_OF[row["condition_id"]],
                       "label": int(row["label"]), "split": row.get("dataset_split"),
                       "router_p_fake": float(router_p[i]), "reliability": float(rel[i]),
                       "pgc_p_fake": pred.p_fake, "pgc_raw_logit": pred.raw_logit}
            except Exception as exc:                       # noqa: BLE001
                n_fail += 1
                rec = {"view_id": row["view_id"], "ok": False,
                       "error": f"{type(exc).__name__}: {exc}"}
            fh.write(json.dumps(rec) + "\n")
            if n % 500 == 0:
                rate = n / (time.perf_counter() - t0)
                print(f"  [{n}/{deferred.size}] {rate:.1f} rows/s "
                      f"eta {(deferred.size - n)/rate/60:.1f} min", file=sys.stderr)
    print(f"done: {deferred.size} rows, {n_fail} failures -> {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
