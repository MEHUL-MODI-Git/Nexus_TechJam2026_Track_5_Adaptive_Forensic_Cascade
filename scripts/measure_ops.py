"""Produce the artifact behind README section 9 — parameters, latency, memory.

Section 9 quoted p50/p95 latency and peak RSS with no committed artifact behind
them. That is the same gap that let a wrong audit-cost figure sit in five
documents, so it gets closed the same way: a script, an artifact, and a test.

Run this on an OTHERWISE IDLE machine. Latency measured while another job holds
the GPU is not the number to publish, and the script records what it saw so a
contended run is obvious rather than silently wrong.
"""
from __future__ import annotations

import argparse
import json
import platform
import resource
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.pipeline.probes import PROBE_IDS
from src.pipeline.service import PredictionService, load_predict_config
from src.pipeline.transforms import CONDITION_IDS


def bench(paths, fusion, n_warm=3):
    cfg = load_predict_config()
    cfg["fusion"] = fusion
    svc = PredictionService.from_config(cfg)
    for p in paths[:n_warm]:
        svc.predict_image(p)
    t = []
    for p in paths:
        t0 = time.perf_counter()
        svc.predict_image(p)
        t.append((time.perf_counter() - t0) * 1000.0)
    return np.asarray(t), svc


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--images", type=Path, default=Path("data/feature_cache/internal-test-v2"))
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--out", type=Path, default=Path("results/ops/ops-evidence.json"))
    args = ap.parse_args()

    rows_path = args.images / "rows.jsonl"
    paths = []
    with rows_path.open() as fh:
        for line in fh:
            r = json.loads(line)
            if r["condition_id"] == "clean":
                p = Path(r["relative_path"])
                if p.exists():
                    paths.append(p)
            if len(paths) >= args.n:
                break
    if not paths:
        print("no images found", file=sys.stderr)
        return 2

    # Concurrency check: a contended measurement must not be published silently.
    busy = subprocess.run(["pgrep", "-f", "sealed_reference_run|build_feature_cache|score_pgc"],
                          capture_output=True, text=True, check=False).stdout.strip()
    if busy:
        print("WARNING: another GPU job is running; these latencies are CONTENDED",
              file=sys.stderr)

    t_base, _ = bench(paths, "naive_mean")
    t_router, svc = bench(paths, "router")
    peak_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6

    cf = svc.experts[0]
    router_params = int(svc.router.payload["n_parameters"])
    # R7 (Codex review): the degradation reporter is loaded by the UI and the
    # audit CLI, so it is shipped and belongs in the total.
    degradation_params = 0
    try:
        from src.pipeline.degradation import DegradationReporter

        degradation_params = int(sum(
            p.numel() for p in DegradationReporter.load().model.parameters()))
    except Exception:                              # noqa: BLE001 - optional layer
        degradation_params = 0
    doc = {
        "schema_version": "ops-evidence.v1",
        "contended": bool(busy),
        "contended_note": ("another GPU job was running; latency is inflated and must not "
                           "be published" if busy else "measured on an otherwise idle machine"),
        "host": platform.platform(),
        "device": str(svc.experts[0].device),
        "n_images": len(paths),
        "parameters": {
            "cf_384": int(cf.param_count),
            "router_head": router_params,
            "degradation_reporter": degradation_params,
            "shipped_total": int(cf.param_count) + router_params + degradation_params,
            "limit": 2_000_000_000,
            "fraction_of_limit": (int(cf.param_count) + router_params + degradation_params)
                                 / 2_000_000_000,
            "percent_of_limit": 100.0 * (int(cf.param_count) + router_params
                                         + degradation_params) / 2_000_000_000,
        },
        "forward_passes": {
            "per_prediction": 1 + len(PROBE_IDS),
            "per_audit": len(CONDITION_IDS) * (1 + len(PROBE_IDS)),
            "n_conditions": len(CONDITION_IDS),
            "n_probes": len(PROBE_IDS),
        },
        "latency_ms": {
            "baseline_cf_only": {"p50": float(np.percentile(t_base, 50)),
                                 "p95": float(np.percentile(t_base, 95))},
            "cascade_shipped": {"p50": float(np.percentile(t_router, 50)),
                                "p95": float(np.percentile(t_router, 95))},
            "cascade_over_baseline": float(np.percentile(t_router, 50) /
                                           np.percentile(t_base, 50)),
        },
        "peak_rss_mb": peak_mb,
        "torch": torch.__version__,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, indent=2) + "\n")

    lat = doc["latency_ms"]
    print(f"parameters shipped : {doc['parameters']['shipped_total']:,}")
    print(f"forward passes     : {doc['forward_passes']['per_prediction']} per prediction, "
          f"{doc['forward_passes']['per_audit']} per audit")
    print(f"baseline  p50/p95  : {lat['baseline_cf_only']['p50']:.1f} / "
          f"{lat['baseline_cf_only']['p95']:.1f} ms")
    print(f"cascade   p50/p95  : {lat['cascade_shipped']['p50']:.1f} / "
          f"{lat['cascade_shipped']['p95']:.1f} ms  "
          f"({lat['cascade_over_baseline']:.1f}x)")
    print(f"peak RSS           : {peak_mb:.0f} MB")
    if busy:
        print("\n*** CONTENDED RUN — do not publish these latencies ***")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
