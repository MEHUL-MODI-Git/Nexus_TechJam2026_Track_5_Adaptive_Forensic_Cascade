"""Feature cache CLI (Phase 2) — see `specs/phase2-feature-cache.md` v2.

    python scripts/build_feature_cache.py --manifest data/manifests/router_corpus_v1.json \
        --out data/feature_cache/v1 --denylist data/manifests/sealed_denylist.txt

Refuses to run without a sealed-reference denylist. That is deliberate: the one
failure this cache must never have is quietly containing organizer reference
images, and a default of "no protection" makes that failure easy to reach by
accident. `--acknowledge-no-denylist` exists for smoke runs and stamps the
resulting cache UNPROTECTED_SMOKE_ONLY in its manifest.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.pipeline.service import load_predict_config
from src.pipeline.transforms import CONDITION_IDS
from src.router.feature_cache import DenylistViolation, build_cache, load_denylist

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the router feature cache.")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--denylist", type=Path, default=None)
    parser.add_argument("--acknowledge-no-denylist", action="store_true",
                        help="build without contamination protection (smoke only)")
    parser.add_argument("--evaluation-cache", action="store_true",
                        help="build a cache of `test` rows to EVALUATE on. The trainer's "
                             "VALID_SPLITS stays (train, dev), so it structurally cannot fit "
                             "on the result; the manifest is stamped role=evaluation.")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--conditions", nargs="*", default=None)
    args = parser.parse_args()

    payload = json.loads(args.manifest.read_text())
    rows = payload["images"] if isinstance(payload, dict) else payload
    if args.limit:
        rows = rows[: args.limit]

    config = load_predict_config()
    from src.experts.commfor import CommForExpert

    experts = [CommForExpert(device=spec.get("device"), revision=spec.get("revision"))
               for spec in config.get("experts", []) if spec.get("enabled", True)]

    conditions = args.conditions or CONDITION_IDS
    try:
        manifest = build_cache(
            rows, args.out, experts,
            {"transforms": ROOT / "configs/transforms.yaml",
             "probes": ROOT / "configs/probes.yaml"},
            conditions=conditions,
            denylist=load_denylist(args.denylist),
            denylist_acknowledged_absent=args.acknowledge_no_denylist,
            evaluation_cache=args.evaluation_cache,
        )
    except DenylistViolation as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 3

    # Report only keys `build_cache` actually emits. The previous list asked for
    # "rows_written"/"decode_failures", which do not exist -- the manifest names
    # them "*_this_invocation" because a resumed run writes fewer rows than the
    # artifact contains. That KeyError fired AFTER extraction finished, so it
    # would have crashed the summary at the end of an 8.5-hour job while leaving
    # a perfectly good cache on disk looking like a failed run.
    summary_keys = ("cache_key", "status", "role", "n_sources", "rows_total",
                    "rows_written_this_invocation", "decode_failures_this_invocation",
                    "denylist_protected", "denylist_perceptual_protected",
                    "UNPROTECTED_SMOKE_ONLY")
    missing = [k for k in summary_keys if k not in manifest]
    if missing:
        print(f"WARNING: cache manifest is missing {missing}", file=sys.stderr)
    print(json.dumps({k: manifest[k] for k in summary_keys if k in manifest}, indent=2),
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
