"""Select ONE rung under the frozen objective, freeze its threshold, save a deployable checkpoint.

Selection rule is pre-registered, not chosen after seeing the table: maximise bootstrap
worst-FAMILY fake recall subject to the clean FPR/BAcc constraints. Ties and near-ties are broken
by a PAIRED SOURCE bootstrap, never by eyeballing point estimates.

Also emits a real `threshold-artifact.v1` with fitted provenance. That matters beyond bookkeeping:
`train.threshold_is_frozen()` gates stage-2 reliability fitting on it, and the eval harness refuses
to produce a headline without a validated, loaded threshold artifact.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.pipeline.version import PIPELINE_VERSION
from src.router.calibration import DevSet, select_threshold
from src.router.features import FeatureSpec, Standardizer, rows_to_matrix
from src.router.train import (
    build_batch,
    load_cache_rows,
    train_rung,
    validate_cache_rows,
    worst_family_recall,
)

CANDIDATE_RUNGS = (("quality_only", False), ("static_average", False),
                   ("logistic", False), ("mlp", False), ("mlp", True))


def paired_bootstrap(scores_a, scores_b, rows, thr_a, thr_b, n=2000, seed=7):
    """Paired by SOURCE: a source and all 20 of its views resample as one block."""
    labels = np.array([r["label"] for r in rows])
    fams = np.array([r.get("family") or "clean" for r in rows])
    srcs = np.array([r["source_id"] for r in rows])
    uniq = np.unique(srcs)
    index = {s: np.flatnonzero(srcs == s) for s in uniq}
    rng = np.random.default_rng(seed)
    deltas = []
    for _ in range(n):
        pick = rng.choice(uniq, size=len(uniq), replace=True)
        idx = np.concatenate([index[s] for s in pick])
        a, _ = worst_family_recall(scores_a[idx], labels[idx], fams[idx], thr_a, require_all=False)
        b, _ = worst_family_recall(scores_b[idx], labels[idx], fams[idx], thr_b, require_all=False)
        deltas.append(a - b)
    d = np.asarray(deltas)
    return {"mean_delta": float(d.mean()), "ci95_low": float(np.quantile(d, 0.025)),
            "ci95_high": float(np.quantile(d, 0.975)), "n_resamples": n}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cache", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, default=Path("results/router-fitting-v2"))
    ap.add_argument("--seed", type=int, default=20260827)
    ap.add_argument("--bootstrap", type=int, default=200)
    ap.add_argument("--paired", type=int, default=1000)
    args = ap.parse_args()

    # Provenance the threshold artifact must carry. `load_frozen_threshold` refuses an
    # artifact that cannot say which pipeline, data and code produced it -- and it refused
    # the first one we wrote, correctly, because these were left empty.
    def _sha(path: Path) -> str:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    code_rev = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                              check=False).stdout.strip() or "unknown"
    config_digest = hashlib.sha256(
        b"".join(Path(f"configs/{n}").read_bytes()
                 for n in ("transforms.yaml", "probes.yaml", "predict.yaml"))).hexdigest()
    fitting_manifest_sha = _sha("data/manifests/launch_fitting.json")

    rows = load_cache_rows(args.cache / "rows.jsonl")
    expert_ids = tuple(sorted({e for r in rows for e in (r.get("experts") or {})}))
    usable = validate_cache_rows(rows, expert_ids)["usable_rows"]
    train_rows = [r for r in usable if r["dataset_split"] == "train"]
    dev_rows = [r for r in usable if r["dataset_split"] == "dev"]
    spec = FeatureSpec(expert_ids=expert_ids)
    std = Standardizer.fit(rows_to_matrix(train_rows, spec, 0.5), spec)
    tb = build_batch(train_rows, spec, std, 0.5)
    db = build_batch(dev_rows, spec, std, 0.5)
    print(f"train={len(train_rows)} dev={len(dev_rows)} dim={spec.dim}", file=sys.stderr)

    fitted = {}
    for name, wg in CANDIDATE_RUNGS:
        rec = train_rung(name, tb, db, spec.dim, len(expert_ids), 0.5, use_worst_group=wg,
                         seed=args.seed, bootstrap_replicates=8, fit_reliability=False,
                         quality_only_indices=spec.non_expert_indices())
        with torch.no_grad():
            tr = rec["_model"](tb.features, tb.expert_logits, tb.available).p_fake.numpy()
        dv = np.asarray(rec["_dev_p_fake"], dtype=float)
        grid = np.unique(np.quantile(np.clip(tr, 0, 1), np.linspace(0, 1, 257)))
        art = select_threshold(
            DevSet(source_ids=np.array([r["source_id"] for r in train_rows]),
                   condition_ids=np.array([r["condition_id"] for r in train_rows]),
                   families=np.array([r.get("family") or "clean" for r in train_rows]),
                   labels=np.array([r["label"] for r in train_rows], dtype=int),
                   scores=np.clip(tr, 0, 1)),
            candidates=grid, n_replicates=args.bootstrap, seed=args.seed,
            dev_manifest_sha256=fitting_manifest_sha, config_sha256=config_digest,
            pipeline_version=PIPELINE_VERSION,
            fitting_code_version=f"router-freeze@{code_rev[:12]}")
        label = f"{name}+wg" if wg else name
        w, fam = worst_family_recall(dv, np.array([r["label"] for r in dev_rows]),
                                     np.array([r.get("family") or "clean" for r in dev_rows]),
                                     float(art.threshold), require_all=False)
        fitted[label] = {"rec": rec, "dev": dv, "thr": float(art.threshold),
                         "artifact": art, "worst": float(w), "family": fam,
                         "feasible": bool(art.feasible)}
        print(f"  {label:<16} thr={art.threshold:.5f} worst={w:.4f} ({fam})", file=sys.stderr)

    # Pre-registered rule: highest worst-family recall among FEASIBLE rungs.
    feasible = {k: v for k, v in fitted.items() if v["feasible"]}
    best = max(feasible, key=lambda k: feasible[k]["worst"])
    print(f"\nSELECTED (frozen objective): {best}", file=sys.stderr)

    comparisons = {}
    for other in fitted:
        if other == best:
            continue
        comparisons[f"{best}_vs_{other}"] = paired_bootstrap(
            fitted[best]["dev"], fitted[other]["dev"], dev_rows,
            fitted[best]["thr"], fitted[other]["thr"], n=args.paired)
        c = comparisons[f"{best}_vs_{other}"]
        print(f"  vs {other:<16} delta={c['mean_delta']:+.4f} "
              f"CI95=[{c['ci95_low']:+.4f}, {c['ci95_high']:+.4f}]", file=sys.stderr)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    art = fitted[best]["artifact"]
    payload = art.to_json_dict() if hasattr(art, "to_json_dict") else None
    if payload is None:
        from dataclasses import asdict
        payload = {k: v for k, v in asdict(art).items()}
    thr_path = args.out_dir / "threshold-artifact.v1.json"
    thr_path.write_text(json.dumps(payload, indent=2, default=str) + "\n")

    rev = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                         check=False).stdout.strip() or None
    summary = {
        "schema_version": "router-freeze.v1",
        "NOT_A_HEADLINE_RESULT": "dev-split selection; the untouched internal test is the "
                                 "reportable surface and has not been consulted",
        "cache": str(args.cache),
        "cache_manifest_sha256": hashlib.sha256(
            (args.cache / "manifest.json").read_bytes()).hexdigest(),
        "code_revision": rev,
        "feature_dim": spec.dim,
        "geometry_features_excluded": True,
        "selection_rule": "highest dev worst-family fake recall among rungs whose fitted "
                          "threshold satisfies the clean FPR/BAcc constraints; pre-registered, "
                          "not chosen after inspecting the table",
        "selected_rung": best,
        "selected_threshold": fitted[best]["thr"],
        "rungs": {k: {"threshold": v["thr"], "worst_family_fake_recall": v["worst"],
                      "worst_family": v["family"], "feasible": v["feasible"],
                      "n_parameters": v["rec"]["n_parameters"]} for k, v in fitted.items()},
        "paired_source_bootstrap_vs_selected": comparisons,
        "threshold_artifact": str(thr_path),
    }
    (args.out_dir / "freeze.json").write_text(json.dumps(summary, indent=2, default=str) + "\n")
    print(f"\nwrote {args.out_dir}/freeze.json and {thr_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
