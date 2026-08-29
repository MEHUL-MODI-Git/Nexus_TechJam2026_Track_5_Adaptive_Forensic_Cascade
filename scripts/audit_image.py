"""Full forensic report for ONE image — the whole system in one command.

    python scripts/audit_image.py path/to/image.jpg
    python scripts/audit_image.py path/to/image.jpg --json

Prints, in order: the verdict, what the raw detector would have said, the
system's self-assessed reliability, what appears to have been done to the image,
and a robustness certificate measuring whether the verdict survives all 20
official transformations.

This is AUDIT MODE. It runs the full stress grid: 20 conditions x (1 expert + 3
probes) = **80 CF-384 forward passes, ~3.0 s against 136 ms** for a normal
prediction. `scripts/infer_dir.py` -- the required batch deliverable -- is
untouched and stays on the fast path, as does `--no-audit` here.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.app.certificate import build_certificate
from src.app.stress import run_stress_grid
from src.pipeline.service import PredictionService

BAR = "─" * 66


def _bar(frac: float, width: int = 20) -> str:
    filled = max(0, min(width, round(frac * width)))
    return "█" * filled + "·" * (width - filled)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image", type=Path)
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--no-audit", action="store_true",
                    help="skip the stress grid (fast path, no certificate)")
    args = ap.parse_args()

    if not args.image.exists():
        print(f"no such file: {args.image}", file=sys.stderr)
        return 2

    service = PredictionService.from_config()
    record = service.predict_image(args.image)
    router = record.router or {}

    degradation = None
    if router.get("quality"):
        try:
            from src.pipeline.degradation import DegradationReporter

            degradation = DegradationReporter.load().report(router["quality"])
        except Exception as exc:                       # noqa: BLE001 - optional layer
            degradation = None
            if not args.json:
                print(f"(image-history analysis unavailable: {type(exc).__name__})",
                      file=sys.stderr)

    certificate = None
    if not args.no_audit:
        certificate = build_certificate(run_stress_grid(service, args.image))

    if args.json:
        out = {"image": str(args.image), "prediction": record.to_json_dict(),
               "degradation": degradation.to_json_dict() if degradation else None,
               "certificate": certificate.to_json_dict() if certificate else None}
        print(json.dumps(out, indent=2))
        return 0

    icon = "◆" if record.decision == "AI-GENERATED" else "○"
    print(f"\n{BAR}\n  {args.image.name}\n{BAR}")
    print(f"  VERDICT           {icon} {record.decision}")
    print(f"  score             {record.p_fake:.4f}  {_bar(record.p_fake)}  "
          f"(threshold {record.threshold_used:.4f})")

    primary = router.get("primary_p_fake")
    if primary is not None:
        delta = record.p_fake - float(primary)
        rescued = (float(primary) >= record.threshold_used) != (record.p_fake >= record.threshold_used)
        note = "   <- the router changed this verdict" if rescued else ""
        print(f"  raw detector      {float(primary):.4f}  {_bar(float(primary))}"
              f"  ({delta:+.4f} after correction){note}")

    if record.reliability is not None:
        print(f"  reliability       {record.reliability:.3f}  {_bar(record.reliability)}")
    if record.abstain:
        print("  ⚠ DEFERRED        low self-assessed reliability — recommend human review")

    if degradation is not None:
        weak = "  ⚠ our detector is weakest here" if degradation.detector_is_weak_here else ""
        print(f"\n  IMAGE HISTORY     {degradation.label} "
              f"({degradation.confidence:.0%} confidence){weak}")
        if degradation.caveat:
            print(f"                    note: {degradation.caveat}")

    if certificate is not None:
        print(f"\n{BAR}\n  FORENSIC ROBUSTNESS CERTIFICATE\n{BAR}")
        print(f"  verdict retention {certificate.n_retained} / {certificate.n_scored} "
              f"stress conditions   {_bar(certificate.retention_fraction)}")
        print(f"  grade             {certificate.grade}  — verdicts at this retention were "
              f"correct for\n                    "
              f"{certificate.measured_accuracy_at_grade * 100:.1f}% of held-out sources")
        if certificate.worst_case_condition:
            print(f"  worst case        {certificate.worst_case_p_fake:.3f} "
                  f"at {certificate.worst_case_condition}")
        if certificate.unstable_conditions:
            print("  verdict changes under:")
            for c in certificate.unstable_conditions:
                print(f"      · {c}")
        else:
            print("  verdict held under every condition tested")
    print(f"{BAR}")
    print("  Research prototype. One score is not forensic proof.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
