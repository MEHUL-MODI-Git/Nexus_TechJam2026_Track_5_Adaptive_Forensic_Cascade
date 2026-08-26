"""Thin CLI over PredictionService (core spec v2 §6a).

Argument parsing, formatting and exit codes ONLY -- no decision logic lives
here. The verdict must come from the same code path that Gradio, infer_dir and
the eval harness use, or the demo and the results table can disagree.

    python scripts/predict.py IMG [--transform cond_id] [--json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.pipeline.decode import DecodeError
from src.pipeline.service import PredictionError, PredictionService
from src.pipeline.transforms import CONDITION_IDS


def main() -> int:
    parser = argparse.ArgumentParser(description="Score one image with the forensic cascade.")
    parser.add_argument("image", type=Path)
    parser.add_argument("--transform", default="clean", choices=CONDITION_IDS,
                        help="apply one official stress condition before scoring")
    parser.add_argument("--json", action="store_true", help="emit prediction.v1 JSON")
    args = parser.parse_args()

    service = PredictionService.from_config()
    try:
        record = service.predict_image(args.image, transform_id=args.transform)
    except DecodeError as exc:
        print(f"decode failed: {exc}", file=sys.stderr)
        return 2
    except PredictionError as exc:
        print(f"no verdict: {exc}", file=sys.stderr)
        return 3

    if args.json:
        print(json.dumps(record.to_json_dict(), indent=2))
        return 0

    print(f"{args.image}  [{record.transform_id}]  "
          f"{record.image['width']}x{record.image['height']}  "
          f"sha256:{record.image['sha256'][:12]}")
    print(f"{'expert':<14}{'p_fake':>10}{'logit':>10}{'ms':>8}  warnings")
    for e in record.experts:
        print(f"{e['expert_id']:<14}{e['p_fake']:>10.4f}{e['raw_logit']:>10.3f}"
              f"{e['inference_ms']:>8.1f}  {','.join(e['warnings']) or '-'}")
    for f in record.expert_failures:
        print(f"{f['expert_id']:<14}{'FAILED':>10}{'-':>10}{'-':>8}  {f['reason_code']}")
    print(f"\nverdict: {record.decision}   p_fake={record.p_fake:.4f}   "
          f"threshold={record.threshold_used} ({record.threshold_provenance})")
    print(f"total {record.inference_ms['total']:.1f} ms   pipeline {record.pipeline_version}")
    if record.threshold_provenance.startswith("PLACEHOLDER"):
        print("NOTE: uncalibrated Phase-0 threshold -- this verdict is a baseline "
              "model output, not a calibrated probability.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
