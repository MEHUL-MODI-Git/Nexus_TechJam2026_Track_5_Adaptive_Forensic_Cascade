"""Evaluation runner: prediction rows -> results JSON -> markdown tables.

[relay] Claude, while Codex is limit-blocked (PROTOCOL §6). Codex owns
`src/eval/` and reviews this on return.

    # Phase-1 diagnostic (placeholder threshold; cannot produce a headline)
    python scripts/run_eval.py --rows results/<run>/prediction_rows.jsonl --diagnostic

    # Real evaluation (requires a held-out-dev threshold artifact)
    python scripts/run_eval.py --rows ... --threshold-artifact results/threshold.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.eval.protocol import load_frozen_threshold, load_prediction_rows
from src.eval.report import render_markdown
from src.eval.results import (CoverageError, PlaceholderThreshold,
                              build_results, write_results)
from src.pipeline.transforms import CONDITION_IDS, FAMILY_OF


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the evaluation protocol.")
    parser.add_argument("--rows", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--threshold-artifact", type=Path, default=None,
                        help="held-out-dev threshold-artifact.v1 (required unless --diagnostic)")
    parser.add_argument("--diagnostic", action="store_true",
                        help="emit diagnostic-results.v1 from a placeholder threshold")
    parser.add_argument("--threshold", type=float, default=None,
                        help="placeholder threshold value; only valid with --diagnostic")
    parser.add_argument("--provenance", default=None,
                        help="placeholder provenance string; only valid with --diagnostic")
    parser.add_argument("--replicates", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=20260826)
    parser.add_argument("--allow-partial-grid", action="store_true")
    args = parser.parse_args()

    if args.diagnostic == bool(args.threshold_artifact):
        print("choose exactly one of --diagnostic or --threshold-artifact", file=sys.stderr)
        return 2

    if args.diagnostic and args.allow_partial_grid is False:
        pass
    if args.diagnostic:
        # Read the placeholder from the live config rather than inventing one,
        # so the demo and the diagnostic always describe the same operating point.
        if args.threshold is None or args.provenance is None:
            from src.pipeline.service import load_predict_config

            cfg = load_predict_config()
            threshold = args.threshold if args.threshold is not None else float(cfg["threshold"])
            provenance = args.provenance or cfg.get("threshold_provenance", "unspecified")
        else:
            threshold, provenance = args.threshold, args.provenance
        threshold_source = PlaceholderThreshold(value=threshold, provenance=provenance)
    else:
        # A headline needs the artifact OBJECT, never a provenance string (R2).
        threshold_source = load_frozen_threshold(args.threshold_artifact)
        if args.allow_partial_grid:
            print("--allow-partial-grid cannot be combined with a real threshold "
                  "artifact: a headline requires the complete grid (R3)", file=sys.stderr)
            return 2

    validated = load_prediction_rows(args.rows, require_full_grid=not args.allow_partial_grid)
    print(f"validated {len(validated.rows)} rows "
          f"({len(set(validated.source_ids))} sources)", file=sys.stderr)

    manifest_path = args.rows.parent / "run_manifest.json"
    run_manifest = (json.loads(manifest_path.read_text())
                    if manifest_path.exists() else None)
    try:
        document = build_results(
            validated, threshold_source,
            family_of=FAMILY_OF, official_conditions=tuple(CONDITION_IDS),
            run_manifest=run_manifest, rows_path=args.rows,
            bootstrap_replicates=args.replicates, seed=args.seed,
            require_full_grid=not args.allow_partial_grid,
        )
    except CoverageError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 3

    out_dir = args.out_dir or args.rows.parent
    name = "diagnostic-results" if args.diagnostic else "eval-results"
    json_path = write_results(document, out_dir / f"{name}.json")
    md_path = out_dir / f"{name}.md"
    md_path.write_text(render_markdown(document))
    print(f"wrote {json_path}\nwrote {md_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
