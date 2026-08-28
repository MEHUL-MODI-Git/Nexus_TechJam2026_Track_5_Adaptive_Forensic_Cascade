"""THE SEALED REFERENCE RUN — Phase 4.3. One run, authorised by Mehul, 2026-08-28.

Hard constraints this script exists to honour:

* The organizers' reference subset has NEVER been fitted on. Verified directly, not
  asserted: zero SHA-256 overlap with the 11,998 fitting sources and the 3,000
  internal-test sources.
* It is scored ONCE, after the architecture was frozen, and it never changes the
  system. Nothing here fits, tunes, calibrates or selects.
* Output goes to `results/sealed/`, deliberately NOT into `data/feature_cache/`,
  so no future fitting job can pick it up by accident.

Scoring goes through `PredictionService` itself, so what is measured is exactly
what ships — the same code path as the demo and the CLI.

A-029 duplication protocol: the DALL-E half contains 8,843 files but only 3,719
unique images (some repeated five times). Metrics are computed on DEDUPLICATED
images, and the naive per-file numbers are reported alongside so the two
conventions can be reconciled.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.pipeline.decode import decode_image
from src.pipeline.service import PredictionService
from src.pipeline.transforms import CONDITION_IDS
from src.router.head import (
    RouterHead,  # noqa: F401  (import surfaces load errors early)
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--files", type=Path, default=Path("data/manifests/sealed_files.json"))
    ap.add_argument("--out", type=Path, default=Path("results/sealed/predictions.jsonl"))
    ap.add_argument("--conditions", default="all",
                    help="'all' for the full 20-condition grid, or a comma list")
    ap.add_argument("--limit", type=int, default=0, help="debug only; 0 = every source")
    args = ap.parse_args()

    recs = json.loads(args.files.read_text())
    # A-029: deduplicate by content hash BEFORE scoring. Keep the first path per hash.
    seen, uniq = set(), []
    for r in recs:
        if r["sha256"] in seen:
            continue
        seen.add(r["sha256"])
        uniq.append(r)
    counts = {}
    for r in recs:
        counts[r["sha256"]] = counts.get(r["sha256"], 0) + 1
    if args.limit:
        uniq = uniq[:args.limit]

    conditions = list(CONDITION_IDS) if args.conditions == "all" else args.conditions.split(",")
    print(f"sealed files {len(recs)}  unique images {len(uniq)}  "
          f"conditions {len(conditions)}  rows {len(uniq)*len(conditions)}", file=sys.stderr)

    service = PredictionService.from_config()
    if service.fusion != "router":
        print("REFUSING: the shipped config is not serving the router; the sealed run "
              "must measure the system we ship", file=sys.stderr)
        return 2
    print(f"fusion={service.fusion} threshold={service.threshold!r} "
          f"provenance={service.threshold_provenance}", file=sys.stderr)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if args.out.exists():                      # resumable: a 6-hour job must survive a hiccup
        with args.out.open() as fh:
            for line in fh:
                try:
                    done.add(json.loads(line)["view_id"])
                except Exception:              # noqa: BLE001, S112
                    continue
        print(f"resuming: {len(done)} rows already written", file=sys.stderr)

    t0, n, fails = time.perf_counter(), 0, 0
    with args.out.open("a") as fh:
        for src in uniq:
            pending = [c for c in conditions if f"{src['sha256'][:16]}:{c}" not in done]
            if not pending:
                continue
            try:
                decoded = decode_image(Path(src["path"]))
            except Exception as exc:           # noqa: BLE001
                fails += 1
                fh.write(json.dumps({"view_id": f"{src['sha256'][:16]}:decode",
                                     "ok": False, "error": str(exc)}) + "\n")
                continue
            for cond in pending:
                try:
                    rec = service.predict_decoded(decoded, transform_id=cond)
                    fh.write(json.dumps({
                        "view_id": f"{src['sha256'][:16]}:{cond}",
                        "sha256": src["sha256"], "group": src["group"],
                        "label": src["label"], "condition_id": cond,
                        "file_multiplicity": counts[src["sha256"]],
                        "p_fake": rec.p_fake, "decision": rec.decision,
                        "reliability": rec.reliability, "abstain": rec.abstain,
                        "primary_p_fake": (rec.router or {}).get("primary_p_fake"),
                    }) + "\n")
                except Exception as exc:       # noqa: BLE001
                    fails += 1
                    fh.write(json.dumps({"view_id": f"{src['sha256'][:16]}:{cond}",
                                         "ok": False, "error": f"{type(exc).__name__}: {exc}"}) + "\n")
                n += 1
            if n and n % 2000 < len(conditions):
                fh.flush()
                rate = n / (time.perf_counter() - t0)
                remaining = len(uniq) * len(conditions) - len(done) - n
                print(f"  {n} rows  {rate:.1f} rows/s  eta {remaining/rate/3600:.2f} h",
                      file=sys.stderr)
    print(f"DONE: {n} rows this invocation, {fails} failures -> {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
