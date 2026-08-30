"""ONE-SHOT evaluation on the untouched internal test set.

Nothing has been fitted on these 3,000 sources: not weights, not the threshold, not the feature
set, not the rung choice. That is the whole point of holding them back, so this script LOADS a
frozen checkpoint and a validated threshold artifact and never fits anything.

It reports the comparison that actually matters for the write-up: the frozen router against the
raw primary detector — what you would ship if you did nothing — on identical rows, with paired
source bootstrap.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.eval.protocol import load_frozen_threshold
from src.pipeline.transforms import CONDITION_IDS, FAMILY_OF
from src.router.train import build_batch, load_cache_rows, load_checkpoint


def metrics(scores, labels, fams, conds, threshold):
    pred = scores >= threshold
    out = {}
    clean = fams == "clean"
    cf, ck = clean & (labels == 0), clean & (labels == 1)
    fam_recall = {}
    for f in sorted(set(FAMILY_OF.values()) - {"clean"}):
        m = (fams == f) & (labels == 1)
        if m.any():
            fam_recall[f] = float(pred[m].mean())
    worst_fam = min(fam_recall, key=fam_recall.get) if fam_recall else None
    per_cond = {}
    for c in CONDITION_IDS:
        m = conds == c
        if not m.any():
            continue
        fk, rl = m & (labels == 1), m & (labels == 0)
        per_cond[c] = {
            "fake_recall": float(pred[fk].mean()) if fk.any() else float("nan"),
            "fpr": float(pred[rl].mean()) if rl.any() else float("nan"),
            "n": int(m.sum()),
        }
    out.update({
        "worst_family": worst_fam,
        "worst_family_fake_recall": fam_recall.get(worst_fam) if worst_fam else None,
        "family_fake_recall": fam_recall,
        "clean_fake_recall": float(pred[ck].mean()) if ck.any() else float("nan"),
        "clean_fpr": float(pred[cf].mean()) if cf.any() else float("nan"),
        "overall_fake_recall": float(pred[labels == 1].mean()),
        "overall_fpr": float(pred[labels == 0].mean()),
        "overall_accuracy": float((pred == (labels == 1)).mean()),
        "per_condition": per_cond,
    })
    return out


def flip_rates(scores, labels, fams, conds, srcs, threshold):
    """Among sources decided CORRECTLY when clean, how often does a transform flip them?"""
    pred = scores >= threshold
    clean_ok = {}
    for i in range(len(scores)):
        if conds[i] == "clean":
            clean_ok[srcs[i]] = bool(pred[i] == (labels[i] == 1))
    f2r = t = r2f = u = 0
    for i in range(len(scores)):
        if conds[i] == "clean" or not clean_ok.get(srcs[i], False):
            continue
        if labels[i] == 1:
            t += 1; f2r += int(not pred[i])
        else:
            u += 1; r2f += int(pred[i])
    return {"fake_to_real_flip_rate": f2r / t if t else float("nan"), "n_fake_views": t,
            "real_to_fake_flip_rate": r2f / u if u else float("nan"), "n_real_views": u}


def paired_bootstrap(a, b, labels, fams, srcs, ta, tb, n=2000, seed=11):
    uniq = np.unique(srcs)
    idx = {s: np.flatnonzero(srcs == s) for s in uniq}
    rng = np.random.default_rng(seed)
    def worst(sc, sel, thr):
        best = 1.1
        for f in sorted(set(FAMILY_OF.values()) - {"clean"}):
            m = (fams[sel] == f) & (labels[sel] == 1)
            if m.any():
                best = min(best, float((sc[sel][m] >= thr).mean()))
        return best if best <= 1.0 else float("nan")
    d = []
    for _ in range(n):
        pick = rng.choice(uniq, size=len(uniq), replace=True)
        sel = np.concatenate([idx[s] for s in pick])
        d.append(worst(a, sel, ta) - worst(b, sel, tb))
    d = np.asarray(d)
    return {"mean_delta": float(d.mean()), "ci95_low": float(np.quantile(d, 0.025)),
            "ci95_high": float(np.quantile(d, 0.975)), "n_resamples": n}


def match_threshold_to_fpr(scores, labels, fams, target_fpr):
    """Lowest threshold whose CLEAN FPR does not exceed `target_fpr`.

    Used to hand the primary detector our own operating point. Note this tunes the
    BASELINE on the internal test itself -- a concession we deliberately do not take
    for our own model. It can only shrink our reported gain, never inflate it, which
    is why it is legitimate to add after seeing the headline.
    """
    clean_real = (fams == "clean") & (labels == 0)
    s = np.sort(scores[clean_real])
    if s.size == 0:
        return float("nan")
    # FPR at threshold t is the fraction of clean reals scoring >= t.
    k = int(np.floor(target_fpr * s.size))
    return float(s[s.size - k]) if k > 0 else float(np.nextafter(s[-1], np.inf))


FROZEN_EXPERT_REVISION = "6076002bf0d9dd37537f965ee2f06f826c333b61"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def validate_evaluation_cache(rows, manifest, expert_id):
    """Every reason this cache may not produce a headline. Returns a list of messages.

    B-032 P0, Codex Phase-4 exit audit. This script checked `manifest.role` and nothing
    else: it loaded rows directly, never validated schema or coverage, hashed the MANIFEST
    but not the ROWS, and serialised with JSON's default `allow_nan=True`. Codex copied the
    real complete manifest over a cache holding 39 rows from 2 sources with one condition
    missing, and the script returned rc=0 while writing NaN headline statistics under a
    manifest still claiming 60,000 rows.

    A manifest is a claim. These checks are what make it evidence.
    """
    errors = []
    if manifest.get("status") != "complete":
        errors.append(f"manifest status is {manifest.get('status')!r}, not 'complete'")
    if manifest.get("may_not_be_used_for_fitting") is not True:
        errors.append("manifest does not carry may_not_be_used_for_fitting: true")

    # the manifest's own counts must describe the rows actually present
    expected_rows = manifest.get("rows_total")
    if expected_rows is not None and len(rows) != expected_rows:
        errors.append(f"manifest claims {expected_rows} rows; the file holds {len(rows)}")
    srcs = {r.get("source_id") for r in rows}
    expected_sources = manifest.get("n_sources")
    if expected_sources is not None and len(srcs) != expected_sources:
        errors.append(f"manifest claims {expected_sources} sources; the file holds {len(srcs)}")

    # the frozen expert, by revision, not by name
    declared = manifest.get("experts") or []
    if not any(str(e).startswith(expert_id) for e in declared):
        errors.append(f"manifest experts {declared} do not include {expert_id!r}")
    if not any(FROZEN_EXPERT_REVISION in str(e) for e in declared):
        errors.append(f"manifest experts {declared} were not produced by the frozen "
                      f"expert revision {FROZEN_EXPERT_REVISION[:12]}")

    # exactly one row per (source, condition), across the full official grid
    seen = {}
    for r in rows:
        key = (r.get("source_id"), r.get("condition_id"))
        seen[key] = seen.get(key, 0) + 1
    repeated = [k for k, v in seen.items() if v != 1]
    if repeated:
        errors.append(f"{len(repeated)} (source, condition) pair(s) appear more than once, "
                      f"e.g. {repeated[0]}")
    grid = set(CONDITION_IDS)
    by_source = {}
    for r in rows:
        by_source.setdefault(r.get("source_id"), set()).add(r.get("condition_id"))
    incomplete = {k: sorted(grid - v) for k, v in by_source.items() if v != grid}
    if incomplete:
        k = next(iter(incomplete))
        errors.append(f"{len(incomplete)} source(s) lack the full 20-condition grid, "
                      f"e.g. {k} missing {incomplete[k][:3]}")

    # labels and split must be consistent and well-formed
    labels_by_source = {}
    for r in rows:
        labels_by_source.setdefault(r.get("source_id"), set()).add(r.get("label"))
    conflicted = [k for k, v in labels_by_source.items() if len(v) != 1]
    if conflicted:
        errors.append(f"{len(conflicted)} source(s) carry conflicting labels, e.g. {conflicted[0]}")
    bad_labels = [r.get("label") for r in rows
                  if isinstance(r.get("label"), bool) or r.get("label") not in (0, 1)]
    if bad_labels:
        errors.append(f"{len(bad_labels)} row(s) carry a label that is not 0 or 1, "
                      f"e.g. {bad_labels[0]!r}")
    splits = {r.get("dataset_split") for r in rows}
    if splits - {"test", None}:
        errors.append(f"rows carry unexpected dataset_split values {sorted(s for s in splits if s)}")

    # the expert score every metric is built on must exist and be finite
    missing, nonfinite = 0, 0
    for r in rows:
        block = (r.get("experts") or {}).get(expert_id)
        if not isinstance(block, dict) or block.get("p_fake") is None:
            missing += 1
            continue
        v = block["p_fake"]
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) \
                or not 0.0 <= float(v) <= 1.0:
            nonfinite += 1
    if missing:
        errors.append(f"{missing} row(s) have no {expert_id} score; a failure must never "
                      "become a number")
    if nonfinite:
        errors.append(f"{nonfinite} row(s) carry a non-finite or out-of-range {expert_id} p_fake")
    return errors


def assert_finite(doc, path=""):
    """No NaN or inf may reach a published artifact. Returns offending paths."""
    bad = []
    if isinstance(doc, dict):
        for k, v in doc.items():
            bad += assert_finite(v, f"{path}/{k}")
    elif isinstance(doc, list):
        for i, v in enumerate(doc):
            bad += assert_finite(v, f"{path}[{i}]")
    elif isinstance(doc, float) and not math.isfinite(doc):
        bad.append(path or "<root>")
    return bad


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cache", type=Path, required=True)
    ap.add_argument("--checkpoint", type=Path, required=True)
    ap.add_argument("--threshold-artifact", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=Path("results/internal-test/results.json"))
    ap.add_argument("--bootstrap", type=int, default=2000)
    args = ap.parse_args()

    manifest = json.loads((args.cache / "manifest.json").read_text())
    if manifest.get("role") != "evaluation":
        print(f"REFUSING: cache role is {manifest.get('role')!r}, expected 'evaluation'",
              file=sys.stderr)
        return 2

    frozen = load_frozen_threshold(args.threshold_artifact)   # validates or raises
    loaded = load_checkpoint(args.checkpoint)
    thr = float(frozen.value)
    print(f"frozen threshold {thr:.6f} (artifact {frozen.artifact_sha256[:12]}), "
          f"rung {loaded.payload['rung']}", file=sys.stderr)

    rows_path = args.cache / "rows.jsonl"
    rows = load_cache_rows(rows_path)
    eid_expected = loaded.spec.expert_ids[0]
    problems = validate_evaluation_cache(rows, manifest, eid_expected)
    if problems:
        print("REFUSING: this cache cannot produce a headline:", file=sys.stderr)
        for msg in problems:
            print(f"  - {msg}", file=sys.stderr)
        return 2
    rows_sha256 = _sha256(rows_path)
    labels = np.array([r["label"] for r in rows])
    fams = np.array([r.get("family") or FAMILY_OF.get(r["condition_id"], "clean") for r in rows])
    conds = np.array([r["condition_id"] for r in rows])
    srcs = np.array([r["source_id"] for r in rows])
    print(f"internal test: {len(rows)} rows, {len(set(srcs))} sources", file=sys.stderr)

    batch = build_batch(rows, loaded.spec, loaded.standardizer, thr)
    with torch.no_grad():
        router = loaded.model(batch.features, batch.expert_logits, batch.available).p_fake.numpy()
    eid = loaded.spec.expert_ids[0]
    primary = np.array([float((r["experts"][eid]).get("p_fake", 0.5)) for r in rows])

    router_m = metrics(router, labels, fams, conds, thr)
    # The primary is judged at ITS OWN best-case operating point, not ours: giving the baseline
    # our threshold would be a straw man. 0.5 is its published default.
    primary_m = metrics(primary, labels, fams, conds, 0.5)
    # CONTROL: the router operates at a much higher clean FPR than the primary at 0.5, so the
    # obvious objection is that the gain is bought purely by moving the operating point. Give
    # the primary OUR clean FPR -- fitted on this very test set, in the baseline's favour -- and
    # ask whether it can buy the same worst-family recall that way. If it can, we have no result.
    t_match = match_threshold_to_fpr(primary, labels, fams, router_m["clean_fpr"])
    primary_matched_m = metrics(primary, labels, fams, conds, t_match)
    doc = {
        "schema_version": "internal-test-results.v1",
        "one_shot": "the untouched internal test; nothing was fitted on these sources",
        "cache": str(args.cache), "cache_role": manifest.get("role"),
        "cache_manifest_sha256": hashlib.sha256(
            (args.cache / "manifest.json").read_bytes()).hexdigest(),
        # B-032: the manifest was the only thing hashed, so a complete manifest
        # copied over a truncated rows file produced a document that looked
        # provenanced. The rows are the evidence; hash the rows.
        "cache_rows_sha256": rows_sha256,
        "cache_key": manifest.get("cache_key"),
        "expert_revision": FROZEN_EXPERT_REVISION,
        "validated": "schema, manifest/row count agreement, exactly one of every official "
                     "condition per source, consistent labels and split, finite in-range "
                     "expert scores, and finite output",
        "checkpoint": str(args.checkpoint), "rung": loaded.payload["rung"],
        "n_parameters": loaded.payload.get("n_parameters"),
        "threshold": thr, "threshold_artifact_sha256": frozen.artifact_sha256,
        "n_rows": len(rows), "n_sources": len(set(srcs)),
        "router": router_m, "router_flips": flip_rates(router, labels, fams, conds, srcs, thr),
        "primary_at_0.5": primary_m,
        "primary_flips": flip_rates(primary, labels, fams, conds, srcs, 0.5),
        "paired_bootstrap_router_vs_primary": paired_bootstrap(
            router, primary, labels, fams, srcs, thr, 0.5, n=args.bootstrap),
        "primary_at_matched_clean_fpr": {
            "threshold": t_match,
            "threshold_fitted_on": "THIS TEST SET, in the baseline's favour (see docstring)",
            "target_clean_fpr": router_m["clean_fpr"],
            **primary_matched_m,
        },
        "paired_bootstrap_router_vs_primary_matched": paired_bootstrap(
            router, primary, labels, fams, srcs, thr, t_match, n=args.bootstrap),
    }
    nonfinite = assert_finite(doc)
    if nonfinite:
        print(f"REFUSING: {len(nonfinite)} non-finite value(s) in the result document, "
              f"e.g. {nonfinite[0]}. A NaN headline is not a result.", file=sys.stderr)
        return 2
    args.out.parent.mkdir(parents=True, exist_ok=True)
    # allow_nan=False: json.dumps would otherwise emit bare NaN, which is not
    # valid JSON and which every downstream reader silently accepts.
    args.out.write_text(json.dumps(doc, indent=2, allow_nan=False) + "\n")

    print(f"\n{'':<22}{'worst-fam':>10}{'clean-rec':>11}{'clean-FPR':>11}{'overall-acc':>13}",
          file=sys.stderr)
    for tag, m in (("router (frozen)", router_m), ("primary @0.5", primary_m),
                   (f"primary @{t_match:.4f} (FPR-matched)", primary_matched_m)):
        print(f"{tag:<22}{m['worst_family_fake_recall']:>10.4f}{m['clean_fake_recall']:>11.4f}"
              f"{m['clean_fpr']:>11.4f}{m['overall_accuracy']:>13.4f}", file=sys.stderr)
    for tag, key in (("vs primary @0.5", "paired_bootstrap_router_vs_primary"),
                     ("vs primary FPR-matched", "paired_bootstrap_router_vs_primary_matched")):
        b = doc[key]
        print(f"\npaired source bootstrap, worst-family recall {tag}: {b['mean_delta']:+.4f} "
              f"CI95 [{b['ci95_low']:+.4f}, {b['ci95_high']:+.4f}]", file=sys.stderr)
    print(f"wrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
