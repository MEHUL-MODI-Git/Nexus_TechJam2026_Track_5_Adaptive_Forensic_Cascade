"""Score the sealed reference run. Reports only — nothing here is fitted.

Two conventions are reported side by side, per A-029:

* **deduplicated** (primary): one vote per unique image. 5,000 COCO val2017 reals
  and 3,719 unique DALL-E images.
* **per-file** (secondary): each unique image weighted by how many times the
  organizers' archive contains it, so our numbers can be reconciled with any
  computed the naive way over 13,843 files.

This is a REFERENCE BENCHMARK, not our headline. The threshold was frozen on a
different corpus (SID-Set), and COCO val2017 reals plus DALL-E 3 fakes are a
different distribution; a shift in operating point here is a finding to report,
never a reason to re-tune.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.eval.protocol import load_frozen_threshold
from src.pipeline.transforms import CONDITION_IDS, FAMILY_OF
from src.pipeline.version import PIPELINE_VERSION

FAMS = sorted(set(FAMILY_OF.values()) - {"clean"})


def auroc(scores, y, w=None):
    """Weighted AUROC that averages TIE GROUPS, not adjacent rows.

    S2, Codex review 2026-08-29. The previous implementation subtracted half of
    each row's own negative weight, which handles a positive tied with the
    negative sitting at the same sorted index and nothing else. Rows tied at
    equal scores but different indices were counted as fully ordered, so the
    result depended on input order: on a single tied positive/negative pair it
    returned 0.0 or 1.0 rather than 0.5. The real dump has 31,231 p_fake rows
    inside tied-score groups.

    Correct generalisation: for each distinct score value, every positive in the
    group beats all negative weight strictly below it plus HALF the negative
    weight tied with it.

        AUC = sum_g P_g * (C_g + N_g / 2) / (P_total * N_total)

    With unit weights this agrees with `src.eval.metrics.auroc` (the canonical
    tie-aware implementation), which the tests assert directly.
    """
    scores, y = np.asarray(scores, float), np.asarray(y, int)
    w = np.ones_like(scores) if w is None else np.asarray(w, float)
    order = np.argsort(scores, kind="mergesort")
    scores, y, w = scores[order], y[order], w[order]
    pos_w, neg_w = w * (y == 1), w * (y == 0)
    tot_pos, tot_neg = pos_w.sum(), neg_w.sum()
    if tot_pos == 0 or tot_neg == 0:
        return float("nan")
    # group boundaries over the sorted scores
    starts = np.flatnonzero(np.r_[True, scores[1:] != scores[:-1]])
    ends = np.r_[starts[1:], scores.size]
    cum_neg = np.r_[0.0, np.cumsum(neg_w)]
    total = 0.0
    for a, b in zip(starts, ends):
        p_g = pos_w[a:b].sum()
        if p_g == 0.0:
            continue
        n_g = cum_neg[b] - cum_neg[a]          # negative weight tied in this group
        below = cum_neg[a]                     # negative weight strictly below it
        total += p_g * (below + n_g / 2.0)
    return float(total / (tot_pos * tot_neg))


def _is_real_number(v):
    """A number we may do arithmetic with. Bools are ints in Python and strings
    are not numbers, however willing float() is to convert them."""
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _field_error(r):
    """Return a message describing the first schema violation, or None.

    Only fields that can move a published number are checked here; the point is
    that a malformed row is refused rather than silently averaged in.
    """
    sha = r["sha256"]
    if not isinstance(sha, str) or len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
        return f"sha256 {sha!r} is not 64 lowercase hex characters"
    if r["condition_id"] not in CONDITION_IDS:
        return f"condition_id {r['condition_id']!r} is not one of the 20 official conditions"
    if not isinstance(r["group"], str) or not r["group"]:
        return f"group {r['group']!r} is not a non-empty string"
    mult = r["file_multiplicity"]
    if isinstance(mult, bool) or not isinstance(mult, int) or mult < 1:
        return (f"file_multiplicity {mult!r} is not a positive integer "
                "(it weights every per-file metric)")
    p = r["p_fake"]
    if not _is_real_number(p) or not math.isfinite(p) or not 0.0 <= float(p) <= 1.0:
        return f"p_fake {p!r} is not a finite number in [0, 1]"
    if "abstain" in r and r["abstain"] is not None and not isinstance(r["abstain"], bool):
        return (f"abstain {r['abstain']!r} is not a boolean "
                "(it decides coverage; bool('false') is True)")
    rel = r.get("reliability")
    if rel is not None and (not _is_real_number(rel) or not math.isfinite(rel)
                            or not 0.0 <= float(rel) <= 1.0):
        return f"reliability {rel!r} is not a finite number in [0, 1]"
    prim = r.get("primary_p_fake")
    if prim is not None and (not _is_real_number(prim) or not math.isfinite(prim)
                             or not 0.0 <= float(prim) <= 1.0):
        return f"primary_p_fake {prim!r} is not a finite number in [0, 1]"
    return None


def block(scores, labels, weights, thr):
    pred = scores >= thr
    f, r = labels == 1, labels == 0
    return {
        "n_images": len(labels),
        "n_effective": float(weights.sum()),
        "fake_recall": float(np.average(pred[f], weights=weights[f])) if f.any() else float("nan"),
        "fpr": float(np.average(pred[r], weights=weights[r])) if r.any() else float("nan"),
        "accuracy": float(np.average(pred == f, weights=weights)),
        "auroc": auroc(scores, labels, weights),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pred", type=Path, default=Path("results/sealed/predictions.jsonl"))
    ap.add_argument("--out", type=Path, default=Path("results/sealed/reference-results.json"))
    ap.add_argument("--threshold-artifact", type=Path,
                    default=Path("results/router-fitting-v2/threshold-artifact.v1.json"),
                    help="R3: the threshold comes from the VALIDATED artifact. There is "
                         "deliberately no free --threshold flag: a benchmark scored at a "
                         "number typed on the command line proves nothing.")
    ap.add_argument("--checkpoint", type=Path,
                    default=Path("results/router-fitting-v2/router_reliability.pt"))
    ap.add_argument("--sealed-manifest", type=Path,
                    default=Path("data/manifests/sealed_files.json"),
                    help="S2: the dump's image set, labels, groups and file multiplicities "
                         "are cross-checked against this manifest and the run is refused on "
                         "any disagreement.")
    ap.add_argument("--bootstrap", type=int, default=2000)
    args = ap.parse_args()

    # ---- R3: validate the preserved dump, fail closed, never rerun ---------
    failures, rows, seen = [], [], set()
    digest = hashlib.sha256()
    with args.pred.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    predictions_sha256 = digest.hexdigest()
    with args.pred.open() as fh:
        for n, line in enumerate(fh, 1):
            r = json.loads(line)
            if r.get("ok") is False:
                failures.append({"line": n, "view_id": r.get("view_id"),
                                 "error": r.get("error")})
                continue
            vid = r.get("view_id")
            if vid in seen:
                print(f"REFUSING: duplicate view_id {vid!r} at line {n}", file=sys.stderr)
                return 2
            seen.add(vid)
            for field in ("sha256", "label", "condition_id", "p_fake", "group",
                          "file_multiplicity"):
                if r.get(field) is None:
                    print(f"REFUSING: row {n} missing {field!r}", file=sys.stderr)
                    return 2
            # S2: `label` used to accept anything non-None. `True == 1` in Python,
            # so a bool sailed through every downstream comparison as a 1.
            if isinstance(r["label"], bool) or r["label"] not in (0, 1):
                print(f"REFUSING: row {n} label {r['label']!r} is not 0 or 1",
                      file=sys.stderr)
                return 2
            # B-031: every field that CARRIES WEIGHT in a published metric is
            # type-checked, not merely present. Two ways this leaked:
            #   * `file_multiplicity` was compared to the manifest as int(value)
            #     but weighted the per-file convention as the original float, so
            #     1.9 passed as 1 and then counted as 1.9.
            #   * `abstain` was read as bool(value), and bool("false") is True,
            #     so a string flipped a row's coverage.
            bad = _field_error(r)
            if bad:
                print(f"REFUSING: row {n} {bad}", file=sys.stderr)
                return 2
            rows.append(r)
    if failures:
        print(f"REFUSING: {len(failures)} failed row(s) in the dump; a benchmark with "
              "holes is not a benchmark. First: " + json.dumps(failures[0]), file=sys.stderr)
        return 2
    if not rows:
        print("no usable rows", file=sys.stderr)
        return 2

    # completeness: every unique image must carry every condition EXACTLY ONCE.
    # S2: this was set equality, so a second row for the same (sha256,
    # condition_id) under a different view_id passed the "exactly once" check and
    # then voted twice in every average below.
    pair_counts = Counter((r["sha256"], r["condition_id"]) for r in rows)
    repeated = [k for k, v in pair_counts.items() if v != 1]
    if repeated:
        s0, c0 = repeated[0]
        print(f"REFUSING: {len(repeated)} (sha256, condition_id) pair(s) appear more "
              f"than once, e.g. {s0[:12]}… / {c0} x{pair_counts[(s0, c0)]}", file=sys.stderr)
        return 2
    by_source = defaultdict(set)
    labels_by_source = defaultdict(set)
    for r in rows:
        by_source[r["sha256"]].add(r["condition_id"])
        labels_by_source[r["sha256"]].add(int(r["label"]))
    incomplete = {k: sorted(set(CONDITION_IDS) - v) for k, v in by_source.items()
                  if v != set(CONDITION_IDS)}
    if incomplete:
        k = next(iter(incomplete))
        print(f"REFUSING: {len(incomplete)} source(s) lack full condition coverage, "
              f"e.g. {k} missing {incomplete[k][:3]}", file=sys.stderr)
        return 2
    conflicted = [k for k, v in labels_by_source.items() if len(v) != 1]
    if conflicted:
        print(f"REFUSING: {len(conflicted)} source(s) carry conflicting labels",
              file=sys.stderr)
        return 2

    # S2: bind the dump to the sealed manifest's IDENTITY, not just to itself.
    # Hashing whichever files happen to exist at summary time proves nothing about
    # which files produced these rows; the manifest cross-check below is the one
    # binding available from the preserved dump, and it is now enforced.
    manifest_path = Path(args.sealed_manifest)
    if not manifest_path.exists():
        print(f"REFUSING: sealed manifest {manifest_path} not found; the dump cannot be "
              "bound to the set it claims to score", file=sys.stderr)
        return 2
    manifest = json.loads(manifest_path.read_text())
    man_mult = Counter(m["sha256"] for m in manifest)
    man_label = {m["sha256"]: m["label"] for m in manifest}
    man_group = {m["sha256"]: m["group"] for m in manifest}
    dump_shas = set(by_source)
    if dump_shas != set(man_mult):
        only_dump, only_man = dump_shas - set(man_mult), set(man_mult) - dump_shas
        print(f"REFUSING: dump/manifest image sets differ — {len(only_dump)} only in the "
              f"dump, {len(only_man)} only in the manifest", file=sys.stderr)
        return 2
    mismatches = []
    for r in rows:
        sh = r["sha256"]
        if int(r["file_multiplicity"]) != man_mult[sh]:
            mismatches.append((sh, "file_multiplicity", r["file_multiplicity"], man_mult[sh]))
        elif int(r["label"]) != int(man_label[sh]):
            mismatches.append((sh, "label", r["label"], man_label[sh]))
        elif r["group"] != man_group[sh]:
            mismatches.append((sh, "group", r["group"], man_group[sh]))
        if mismatches:
            break
    if mismatches:
        sh, field, got, want = mismatches[0]
        print(f"REFUSING: {sh[:12]}… disagrees with the sealed manifest on {field}: "
              f"dump {got!r} vs manifest {want!r}", file=sys.stderr)
        return 2

    # B-033 finding 2: the reporter's own positive fixture contained only REAL
    # sources, so fake_recall and AUROC were mathematically undefined -- and it
    # returned 0 while writing bare `NaN`, which is not even valid JSON. Every
    # metric this report publishes needs both strata present.
    labels_seen = {int(r["label"]) for r in rows}
    if labels_seen != {0, 1}:
        have = "only real images" if labels_seen == {0} else "only AI images"
        print(f"REFUSING: the dump contains {have}. Fake recall, false-positive rate and "
              "AUROC are undefined without both, and a report of NaN is not a result.",
              file=sys.stderr)
        return 2
    for cid in sorted({r["condition_id"] for r in rows}):
        strata = {int(r["label"]) for r in rows if r["condition_id"] == cid}
        if strata != {0, 1}:
            print(f"REFUSING: condition {cid!r} has no {'AI' if strata == {0} else 'real'} "
                  "images; its per-condition metrics would be undefined", file=sys.stderr)
            return 2

    frozen = load_frozen_threshold(args.threshold_artifact)   # validates or raises
    thr = float(frozen.value)
    sha = np.array([r["sha256"] for r in rows])
    cond = np.array([r["condition_id"] for r in rows])
    fam = np.array([FAMILY_OF[c] for c in cond])
    lab = np.array([r["label"] for r in rows])
    p = np.array([r["p_fake"] for r in rows], float)
    mult = np.array([r["file_multiplicity"] for r in rows], float)
    ones = np.ones_like(mult)
    rel = np.array([np.nan if r.get("reliability") is None else r["reliability"] for r in rows])
    absta = np.array([bool(r.get("abstain")) for r in rows])
    prim = np.array([np.nan if r.get("primary_p_fake") is None else r["primary_p_fake"] for r in rows])

    def _sha(path):
        path = Path(path)
        return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None

    code_rev = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                              text=True, check=False).stdout.strip() or "unknown"
    doc = {
        "schema_version": "sealed-reference-results.v2",
        "status": "REFERENCE BENCHMARK — one run, after freeze; never fitted on, never re-tuned",
        "provenance": {
            "predictions_file": str(args.pred),
            "predictions_sha256": predictions_sha256,
            "n_rows_read": len(rows),
            "n_failed_rows": len(failures),
            "completeness": "every unique image carries all 20 conditions exactly once",
            "unique_view_ids": len(seen),
            "threshold_artifact": str(args.threshold_artifact),
            "threshold_artifact_sha256": frozen.artifact_sha256,
            "checkpoint": str(args.checkpoint),
            "checkpoint_sha256": _sha(args.checkpoint),
            "sealed_files_manifest": str(manifest_path),
            "sealed_files_manifest_sha256": _sha(manifest_path),
            "sealed_denylist_sha256": _sha("data/manifests/sealed_denylist.txt"),
            "transforms_config_sha256": _sha("configs/transforms.yaml"),
            "probes_config_sha256": _sha("configs/probes.yaml"),
            "predict_config_sha256": _sha("configs/predict.yaml"),
            "pipeline_version": PIPELINE_VERSION,
            "summary_code_revision": code_rev,
            "one_run_rule": "the sealed subset is scored exactly once; this report is a "
                            "SUMMARY of the preserved dump and never re-invokes the model",
            # S2, Codex review 2026-08-29. Being precise about what these hashes do
            # and do not prove, rather than letting their presence imply more.
            "binding": {
                "bound_to_the_rows": [
                    "predictions_sha256 — the dump these numbers were computed from",
                    ("sealed_files_manifest_sha256 — enforced: image set, per-image label, "
                     "group and file_multiplicity all cross-checked row by row, run refused "
                     "on any disagreement"),
                    ("threshold_artifact_sha256 — the validated artifact whose value scored "
                     "these rows; no free --threshold flag exists"),
                ],
                "NOT_bound_to_the_rows": [
                    ("checkpoint_sha256, transforms/probes/predict config hashes — these hash "
                     "whichever files exist when this SUMMARY is regenerated. The dump carries "
                     "no checkpoint/config/code identity fields, so nothing here proves those "
                     "files produced these rows."),
                    ("summary_code_revision — the HEAD that regenerated this summary, NOT the "
                     "revision that ran inference. It was previously called 'code_revision', "
                     "which read as the latter."),
                ],
                "inference_code_revision": ("NOT RECORDED IN THE DUMP — the run predates this "
                                            "ledger. Any future sealed-class run must stamp "
                                            "method, checkpoint, config and code identity into "
                                            "each row so the binding is provable rather than "
                                            "asserted."),
            },
        },
        "threshold": thr,
        "n_rows": len(rows),
        "n_unique_images": len(set(sha)),
        "duplication_note": "the DALL-E half ships 8,843 files containing 3,719 unique images; "
                            "deduplicated numbers are primary, per-file reported for reconciliation",
        "conventions": {},
    }

    for name, w in (("deduplicated", ones), ("per_file", mult)):
        clean = cond == "clean"
        conv = {
            "clean": block(p[clean], lab[clean], w[clean], thr),
            "all_conditions": block(p, lab, w, thr),
            "per_family": {},
            "per_condition": {},
        }
        for f in FAMS:
            m = fam == f
            if m.any():
                conv["per_family"][f] = block(p[m], lab[m], w[m], thr)
        for c in sorted(set(cond)):
            m = cond == c
            conv["per_condition"][c] = block(p[m], lab[m], w[m], thr)
        fam_rec = {k: v["fake_recall"] for k, v in conv["per_family"].items()}
        worst = min(fam_rec, key=fam_rec.get)
        conv["worst_family"] = worst
        conv["worst_family_fake_recall"] = fam_rec[worst]
        # primary baseline at its published default, same rows
        if np.isfinite(prim).any():
            conv["primary_at_0.5"] = {
                "clean": block(prim[clean], lab[clean], w[clean], 0.5),
                "all_conditions": block(prim, lab, w, 0.5),
                "worst_family_fake_recall": min(
                    block(prim[fam == f], lab[fam == f], w[fam == f], 0.5)["fake_recall"]
                    for f in FAMS if (fam == f).any()),
            }
        # THE SAME ADVERSARIAL CONTROL WE APPLY TO OURSELVES ELSEWHERE.
        # The cascade runs at a much higher FPR than the primary at 0.5, so the
        # naive gap flatters us. Hand the primary our clean FPR with its
        # threshold fitted ON THIS SET, in its favour, and re-ask.
        if np.isfinite(prim).any():
            clean_real = clean & (lab == 0)
            target = conv["clean"]["fpr"]
            s_sorted = np.sort(prim[clean_real])
            k = int(np.floor(target * s_sorted.size))
            t_match = float(s_sorted[s_sorted.size - k]) if k > 0 else float(
                np.nextafter(s_sorted[-1], np.inf))
            fam_rec = [block(prim[fam == f], lab[fam == f], w[fam == f], t_match)["fake_recall"]
                       for f in FAMS if (fam == f).any()]
            conv["primary_at_matched_clean_fpr"] = {
                "threshold": t_match,
                "threshold_fitted_on": "THIS SEALED SET, in the baseline's favour",
                "target_clean_fpr": target,
                "clean": block(prim[clean], lab[clean], w[clean], t_match),
                "worst_family_fake_recall": min(fam_rec) if fam_rec else float("nan"),
                "cascade_advantage": (conv["worst_family_fake_recall"] - min(fam_rec))
                                     if fam_rec else float("nan"),
            }

        # abstention, using the frozen policy
        if np.isfinite(rel).any():
            keep = ~absta
            conv["abstention"] = {
                "coverage": float(np.average(keep, weights=w)),
                "accuracy_all": block(p, lab, w, thr)["accuracy"],
                "accuracy_kept": float(np.average((p[keep] >= thr) == (lab[keep] == 1),
                                                  weights=w[keep])) if keep.any() else float("nan"),
                "accuracy_deferred": float(np.average((p[~keep] >= thr) == (lab[~keep] == 1),
                                                      weights=w[~keep])) if (~keep).any() else float("nan"),
            }
        doc["conventions"][name] = conv

    # image-level bootstrap on the DEDUPLICATED convention
    uniq = np.unique(sha)
    idx = {s: np.flatnonzero(sha == s) for s in uniq}
    rng = np.random.default_rng(20260828)
    stats = []
    for _ in range(args.bootstrap):
        pick = rng.choice(uniq, size=len(uniq), replace=True)
        sel = np.concatenate([idx[s] for s in pick])
        fr = [float((p[sel][(fam[sel] == f) & (lab[sel] == 1)] >= thr).mean())
              for f in FAMS if ((fam[sel] == f) & (lab[sel] == 1)).any()]
        stats.append(min(fr) if fr else np.nan)
    stats = np.asarray(stats, float)
    doc["worst_family_bootstrap_dedup"] = {
        "mean": float(np.nanmean(stats)),
        "ci95_low": float(np.nanquantile(stats, 0.025)),
        "ci95_high": float(np.nanquantile(stats, 0.975)),
        "n_resamples": args.bootstrap,
        "unit": "unique image (never file), per A-029",
    }

    def _nonfinite(node, path=""):
        bad = []
        if isinstance(node, dict):
            for k, v in node.items():
                bad += _nonfinite(v, f"{path}/{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                bad += _nonfinite(v, f"{path}[{i}]")
        elif isinstance(node, float) and not math.isfinite(node):
            bad.append(path or "<root>")
        return bad

    offenders = _nonfinite(doc)
    if offenders:
        print(f"REFUSING: {len(offenders)} non-finite value(s) in the summary, e.g. "
              f"{offenders[0]}. A NaN is not a measurement.", file=sys.stderr)
        return 2
    args.out.parent.mkdir(parents=True, exist_ok=True)
    # allow_nan=False: json.dumps would otherwise emit bare NaN, which no strict
    # JSON reader accepts and which every lenient one silently swallows.
    args.out.write_text(json.dumps(doc, indent=2, allow_nan=False) + "\n")

    d = doc["conventions"]["deduplicated"]
    pf = doc["conventions"]["per_file"]
    print(f"rows {len(rows)}  unique images {doc['n_unique_images']}\n")
    print(f"{'':<22}{'dedup':>12}{'per-file':>12}")
    for k, lbl in (("clean", "clean"), ("all_conditions", "all conditions")):
        print(f"{lbl+' AUROC':<22}{d[k]['auroc']:>12.4f}{pf[k]['auroc']:>12.4f}")
        print(f"{lbl+' recall':<22}{d[k]['fake_recall']:>12.4f}{pf[k]['fake_recall']:>12.4f}")
        print(f"{lbl+' FPR':<22}{d[k]['fpr']:>12.4f}{pf[k]['fpr']:>12.4f}")
    print(f"{'worst family':<22}{d['worst_family_fake_recall']:>12.4f}"
          f"{pf['worst_family_fake_recall']:>12.4f}   ({d['worst_family']})")
    b = doc["worst_family_bootstrap_dedup"]
    print(f"\nworst-family bootstrap (unique-image unit): {b['mean']:.4f} "
          f"CI95 [{b['ci95_low']:.4f}, {b['ci95_high']:.4f}]")
    if "abstention" in d:
        a = d["abstention"]
        print(f"\nabstention: coverage {a['coverage']:.3f}  "
              f"accuracy {a['accuracy_all']:.4f} -> {a['accuracy_kept']:.4f} "
              f"(deferred {a['accuracy_deferred']:.4f})")
    if "primary_at_0.5" in d:
        pr = d["primary_at_0.5"]
        print(f"\nprimary @0.5 baseline: clean AUROC {pr['clean']['auroc']:.4f}  "
              f"worst-family {pr['worst_family_fake_recall']:.4f}")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
