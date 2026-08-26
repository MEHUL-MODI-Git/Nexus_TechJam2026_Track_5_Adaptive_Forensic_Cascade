"""Full-grid baseline run (task 1.3) — the robustness evidence.

Scores every manifest source under all 20 official conditions and emits
`prediction-row.v1` JSONL for Codex's eval harness (task 1.1) to turn into the
headline table. This script deliberately computes NO metrics: metric code is
the harness's, and two implementations of balanced accuracy would eventually
disagree with each other in public.

    python scripts/run_grid.py --manifest data/manifests/smoke_v1.json \
        --output results/<run_id>/prediction_rows.jsonl

Design notes:
- Each source is decoded ONCE and then transformed 20 times. Re-decoding per
  condition would be 20x the JPEG work for identical pixels.
- `content_sha256` is the hash of the TRANSFORMED RGB array (the view), not the
  source file bytes -- a source hash cannot identify a transformed view, so
  every condition would otherwise share one id. (Codex B-009 [F3].)
- Resumable: completed (sample_id, condition_id) pairs are skipped on restart,
  so an interrupted run costs minutes, not the whole grid.
- `decision` is emitted as null. The harness recomputes the binary prediction
  at the frozen threshold; a caller-supplied label would let a stale threshold
  leak into the results.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from src.experts.base import ExpertInferenceError
from src.pipeline.decode import DecodeError, decode_image
from src.pipeline.service import PredictionService
from src.pipeline.transforms import CONDITION_IDS, FAMILY_OF, apply_transform
from src.pipeline.version import PIPELINE_VERSION

SCHEMA_VERSION = "prediction-row.v1"


def view_sha256(image) -> str:
    """Hash of the canonical transformed RGB bytes — identifies THIS view."""
    return hashlib.sha256(np.array(image, dtype=np.uint8).tobytes()).hexdigest()


def load_manifest(path: Path) -> tuple[list[dict], str]:
    payload = json.loads(path.read_text())
    rows = payload["images"] if isinstance(payload, dict) else payload
    manifest_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    return rows, manifest_sha


def completed_pairs(output: Path) -> set[tuple[str, str]]:
    """Read back an interrupted run so it can resume without duplicating rows."""
    done: set[tuple[str, str]] = set()
    if not output.exists():
        return done
    for line in output.read_text().splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue  # a torn final line from a kill; it will be rewritten
        done.add((row["sample_id"], row["condition_id"]))
    return done


def run(
    manifest_path: Path,
    output: Path,
    conditions: list[str],
    limit: int | None = None,
    service: PredictionService | None = None,
    run_id: str | None = None,
) -> dict:
    rows, manifest_sha = load_manifest(manifest_path)
    if limit:
        rows = rows[:limit]
    service = service or PredictionService.from_config()
    experts = service.experts
    run_id = run_id or f"grid-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"

    output.parent.mkdir(parents=True, exist_ok=True)
    done = completed_pairs(output)
    if done:
        print(f"resuming: {len(done)} rows already present", file=sys.stderr)

    root = manifest_path.resolve().parents[2]
    started = time.perf_counter()
    written = decode_failures = expert_failures = 0

    with output.open("a") as fh:
        for i, source in enumerate(rows, start=1):
            image_path = root / source["relative_path"]
            try:
                decoded = decode_image(image_path)
            except DecodeError as exc:
                # A source we cannot read is recorded and skipped; it must not
                # silently shrink the denominator of a robustness claim.
                decode_failures += 1
                print(f"  decode failed {source['relative_path']}: {exc}", file=sys.stderr)
                continue

            for condition_id in conditions:
                sample_id = f"{source['sample_id']}:{condition_id}"
                if (sample_id, condition_id) in done:
                    continue
                view = apply_transform(decoded.image, condition_id, decoded.sha256)
                view_hash = view_sha256(view)
                from dataclasses import replace

                view_decoded = replace(
                    decoded, image=view, width=view.width, height=view.height
                )
                # Run every expert on the view FIRST, so each emitted row can
                # carry the failures of its siblings on the same view. With one
                # expert this is always empty; with two, a row must say that the
                # other expert was unavailable rather than leaving it inferable
                # only from a missing row.
                outputs, failures = [], []
                for expert in experts:
                    try:
                        outputs.append(expert.predict(view_decoded))
                    except ExpertInferenceError as exc:
                        expert_failures += 1
                        failures.append(exc.to_dict())
                        fh.write(json.dumps({
                            "schema_version": "prediction-failure.v1",
                            "run_id": run_id, "method_id": exc.expert_id,
                            "sample_id": sample_id, "source_id": source["source_id"],
                            "condition_id": condition_id, **exc.to_dict(),
                        }) + "\n")

                for out in outputs:
                    warnings = list(decoded.warnings)
                    warnings.extend(f"{out.expert_id}:{w}" for w in out.warnings)
                    fh.write(json.dumps({
                        "schema_version": SCHEMA_VERSION,
                        "run_id": run_id,
                        "method_id": out.expert_id,
                        "sample_id": sample_id,
                        "source_id": source["source_id"],
                        "image_path": source["relative_path"],
                        "content_sha256": view_hash,
                        "label": int(source["label"]),
                        "dataset": source["dataset"],
                        "source_group": source["source_group"],
                        "condition_id": condition_id,
                        "family": FAMILY_OF[condition_id],
                        "p_fake": out.p_fake,
                        "raw_logit": out.raw_logit,
                        "reliability": None,
                        "decision": None,       # harness recomputes at the frozen threshold
                        "rescue_invoked": None,
                        "inference_ms": out.inference_ms,
                        # Present-with-null-or-list: the frozen eval spec makes this
                        # field REQUIRED, and nullable is not the same as optional.
                        "expert_failures": failures or None,
                        "warnings": warnings,
                        "pipeline_version": PIPELINE_VERSION,
                    }) + "\n")
                    written += 1
            if i % 25 == 0 or i == len(rows):
                rate = i / max(time.perf_counter() - started, 1e-9)
                print(f"  [{i}/{len(rows)}] sources  {written} rows  "
                      f"{rate:.2f} src/s", file=sys.stderr)
            fh.flush()

    elapsed = time.perf_counter() - started
    manifest = {
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "manifest_path": str(manifest_path),
        "manifest_sha256": manifest_sha,
        "conditions": conditions,
        "methods": [{"method_id": e.expert_id, "model_version": e.model_version,
                     "param_count": e.param_count} for e in experts],
        "pipeline_version": PIPELINE_VERSION,
        "n_sources": len(rows),
        "rows_written": written,
        "decode_failures": decode_failures,
        "expert_failures": expert_failures,
        "elapsed_seconds": round(elapsed, 2),
        "note": ("single-expert baseline: LOTA is parked, so this run is NOT a "
                 "multi-method shootout and no cross-method comparison may be "
                 "drawn from it"),
    }
    (output.parent / "run_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({k: manifest[k] for k in
                      ("run_id", "rows_written", "decode_failures",
                       "expert_failures", "elapsed_seconds")}, indent=2), file=sys.stderr)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Full-grid baseline run (task 1.3).")
    parser.add_argument("--manifest", type=Path, default=Path("data/manifests/smoke_v1.json"))
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=None, help="first N sources only")
    parser.add_argument("--conditions", nargs="*", default=None,
                        help="subset of official condition ids (default: all 20)")
    args = parser.parse_args()

    conditions = args.conditions or CONDITION_IDS
    unknown = set(conditions) - set(CONDITION_IDS)
    if unknown:
        print(f"unknown condition ids: {sorted(unknown)}", file=sys.stderr)
        return 2

    run_id = f"grid-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    output = args.output or Path("results") / run_id / "prediction_rows.jsonl"
    run(args.manifest, output, conditions, limit=args.limit, run_id=run_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
