"""Build the robustness evaluation summary and representative error cases.

PRELIMINARY ARTIFACT -- see CAVEAT below.

This script reads `results/grid-smoke-v1/prediction_rows.jsonl` (400 sources
x the 20 official transform conditions, task 0.3 grid) and computes, per
condition and per family, AUROC (rank-based, no sklearn), fake recall and
false-positive rate at the current placeholder threshold, balanced accuracy,
a clean-relative fake-recall delta, and flip rates (correct-when-clean
sources that flip to the wrong side under a transform). It also selects and
copies representative false-negative, false-positive, and "flip" error
cases into `results/robustness/cases/` for the Error Analysis Note.

Nothing here trains, fits, or tunes anything -- it only aggregates existing
prediction rows and copies existing image files. It does not import
src.experts and does not run inference.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.pipeline.transforms import CONDITION_IDS, FAMILY_OF

THRESHOLD = 0.5

CAVEAT = (
    "PRELIMINARY. Computed with an unfitted PLACEHOLDER decision threshold "
    "(0.5, not calibrated) on the grid-smoke-v1 smoke set, whose real half "
    "is COCO images and fake half is SID-Set full-synthetic images. This is "
    "not a headline or final result -- it is a robustness triage artifact "
    "for internal use pending real threshold calibration and the sealed "
    "Phase 4 evaluation."
)

DEFAULT_ROWS = Path("results/grid-smoke-v1/prediction_rows.jsonl")
DEFAULT_OUT_DIR = Path("results/robustness")


def load_rows(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open() as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def auroc(scores: np.ndarray, labels: np.ndarray) -> float | None:
    """Rank-based AUROC = (sum of positive ranks - n_pos*(n_pos+1)/2) / (n_pos*n_neg).

    Ties share the average rank of their block (standard Mann-Whitney U
    treatment), matching sklearn's roc_auc_score without needing sklearn.
    """
    n_pos = int((labels == 1).sum())
    n_neg = int((labels == 0).sum())
    if n_pos == 0 or n_neg == 0:
        return None
    order = np.argsort(scores, kind="mergesort")
    sorted_scores = scores[order]
    ranks = np.empty(len(scores), dtype=np.float64)
    n = len(scores)
    i = 0
    while i < n:
        j = i
        while j + 1 < n and sorted_scores[j + 1] == sorted_scores[i]:
            j += 1
        avg_rank = (i + 1 + j + 1) / 2.0  # 1-indexed, inclusive of tie block [i, j]
        ranks[order[i : j + 1]] = avg_rank
        i = j + 1
    sum_ranks_pos = float(ranks[labels == 1].sum())
    u_stat = sum_ranks_pos - n_pos * (n_pos + 1) / 2.0
    return u_stat / (n_pos * n_neg)


def confusion_metrics(scores: np.ndarray, labels: np.ndarray, threshold: float) -> dict[str, Any]:
    pred = (scores >= threshold).astype(int)
    pos = labels == 1
    neg = labels == 0
    n_pos = int(pos.sum())
    n_neg = int(neg.sum())
    tp = int((pred[pos] == 1).sum()) if n_pos else 0
    fn = int((pred[pos] == 0).sum()) if n_pos else 0
    fp = int((pred[neg] == 1).sum()) if n_neg else 0
    tn = int((pred[neg] == 0).sum()) if n_neg else 0
    fake_recall = (tp / n_pos) if n_pos else None
    fpr = (fp / n_neg) if n_neg else None
    specificity = (1.0 - fpr) if fpr is not None else None
    if fake_recall is not None and specificity is not None:
        bal_acc = (fake_recall + specificity) / 2.0
    else:
        bal_acc = None
    return {
        "n": len(scores),
        "n_fake": n_pos,
        "n_real": n_neg,
        "tp": tp,
        "fn": fn,
        "fp": fp,
        "tn": tn,
        "fake_recall_at_0.5": fake_recall,
        "false_positive_rate_at_0.5": fpr,
        "balanced_accuracy_at_0.5": bal_acc,
    }


def group_metrics(rows: list[dict[str, Any]], threshold: float) -> dict[str, Any]:
    scores = np.array([r["p_fake"] for r in rows], dtype=np.float64)
    labels = np.array([r["label"] for r in rows], dtype=np.int64)
    out = confusion_metrics(scores, labels, threshold)
    out["auroc"] = auroc(scores, labels)
    return out


def build_by_source(rows: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
    by_source: dict[str, dict[str, dict[str, Any]]] = {}
    for r in rows:
        by_source.setdefault(r["source_id"], {})[r["condition_id"]] = r
    return by_source


def flip_counts(
    by_source: dict[str, dict[str, dict[str, Any]]], condition_id: str, threshold: float
) -> dict[str, int]:
    """Counts (not rates) so callers can pool across conditions before dividing."""
    fn_flip = fn_total = 0
    fp_flip = fp_total = 0
    for conds in by_source.values():
        clean_row = conds.get("clean")
        cond_row = conds.get(condition_id)
        if clean_row is None or cond_row is None:
            continue
        label = clean_row["label"]
        clean_p = clean_row["p_fake"]
        if label == 1:
            if clean_p < threshold:
                continue  # not correctly caught when clean
            fn_total += 1
            if cond_row["p_fake"] < threshold:
                fn_flip += 1
        else:
            if clean_p >= threshold:
                continue  # not correctly identified as real when clean
            fp_total += 1
            if cond_row["p_fake"] >= threshold:
                fp_flip += 1
    return {
        "fake_to_real_flips": fn_flip,
        "fake_to_real_total": fn_total,
        "real_to_fake_flips": fp_flip,
        "real_to_fake_total": fp_total,
    }


def rate_or_none(numerator: int, denominator: int) -> float | None:
    return (numerator / denominator) if denominator else None


def summarize_condition(
    condition_id: str,
    rows_by_condition: dict[str, list[dict[str, Any]]],
    by_source: dict[str, dict[str, dict[str, Any]]],
    clean_fake_recall: float | None,
    threshold: float,
) -> dict[str, Any]:
    metrics = group_metrics(rows_by_condition[condition_id], threshold)
    metrics["family"] = FAMILY_OF[condition_id]
    if condition_id == "clean":
        metrics["clean_relative_delta_fake_recall"] = 0.0
        metrics["fake_to_real_flip_rate"] = None
        metrics["real_to_fake_flip_rate"] = None
        metrics["flip_counts"] = None
    else:
        fr = metrics["fake_recall_at_0.5"]
        metrics["clean_relative_delta_fake_recall"] = (
            (fr - clean_fake_recall) if (fr is not None and clean_fake_recall is not None) else None
        )
        counts = flip_counts(by_source, condition_id, threshold)
        metrics["fake_to_real_flip_rate"] = rate_or_none(
            counts["fake_to_real_flips"], counts["fake_to_real_total"]
        )
        metrics["real_to_fake_flip_rate"] = rate_or_none(
            counts["real_to_fake_flips"], counts["real_to_fake_total"]
        )
        metrics["flip_counts"] = counts
    return metrics


def summarize_family(
    family: str,
    condition_ids: list[str],
    rows_by_condition: dict[str, list[dict[str, Any]]],
    by_source: dict[str, dict[str, dict[str, Any]]],
    clean_fake_recall: float | None,
    threshold: float,
) -> dict[str, Any]:
    pooled_rows = [r for cid in condition_ids for r in rows_by_condition[cid]]
    metrics = group_metrics(pooled_rows, threshold)
    metrics["conditions"] = condition_ids
    if family == "clean":
        metrics["clean_relative_delta_fake_recall"] = 0.0
        metrics["fake_to_real_flip_rate"] = None
        metrics["real_to_fake_flip_rate"] = None
        metrics["flip_counts"] = None
    else:
        fr = metrics["fake_recall_at_0.5"]
        metrics["clean_relative_delta_fake_recall"] = (
            (fr - clean_fake_recall) if (fr is not None and clean_fake_recall is not None) else None
        )
        pooled_counts = {
            "fake_to_real_flips": 0,
            "fake_to_real_total": 0,
            "real_to_fake_flips": 0,
            "real_to_fake_total": 0,
        }
        for cid in condition_ids:
            c = flip_counts(by_source, cid, threshold)
            for k in pooled_counts:
                pooled_counts[k] += c[k]
        metrics["fake_to_real_flip_rate"] = rate_or_none(
            pooled_counts["fake_to_real_flips"], pooled_counts["fake_to_real_total"]
        )
        metrics["real_to_fake_flip_rate"] = rate_or_none(
            pooled_counts["real_to_fake_flips"], pooled_counts["real_to_fake_total"]
        )
        metrics["flip_counts"] = pooled_counts
    return metrics


def fmt_pct(x: float | None) -> str:
    return f"{x * 100:.1f}%" if x is not None else "n/a"


def fmt_num(x: float | None, digits: int = 3) -> str:
    return f"{x:.{digits}f}" if x is not None else "n/a"


def build_markdown_table(by_condition: dict[str, Any]) -> str:
    header = (
        "| Condition | Family | N | AUROC | Fake recall @0.5 | FPR @0.5 | "
        "Balanced acc | Delta vs clean | Fake to real flip | Real to fake flip |\n"
        "|---|---|---|---|---|---|---|---|---|---|\n"
    )
    ordered = sorted(
        by_condition.items(),
        key=lambda kv: (
            kv[1]["fake_recall_at_0.5"] if kv[1]["fake_recall_at_0.5"] is not None else 1.0
        ),
    )
    lines = []
    for cid, m in ordered:
        lines.append(
            "| {cid} | {fam} | {n} | {auroc} | {recall} | {fpr} | {bal} | {delta} | {f2r} | {r2f} |".format(
                cid=cid,
                fam=m["family"],
                n=m["n"],
                auroc=fmt_num(m["auroc"]),
                recall=fmt_pct(m["fake_recall_at_0.5"]),
                fpr=fmt_pct(m["false_positive_rate_at_0.5"]),
                bal=fmt_pct(m["balanced_accuracy_at_0.5"]),
                delta=(
                    f"{m['clean_relative_delta_fake_recall'] * 100:+.1f}pp"
                    if m["clean_relative_delta_fake_recall"] is not None
                    else "n/a"
                ),
                f2r=fmt_pct(m["fake_to_real_flip_rate"]),
                r2f=fmt_pct(m["real_to_fake_flip_rate"]),
            )
        )
    return header + "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# Part 2: representative error cases
# --------------------------------------------------------------------------
def select_top_by_source(
    rows: list[dict[str, Any]], key: Any, reverse: bool, k: int
) -> list[dict[str, Any]]:
    """Sort rows by key, then keep the first (best-ranked) row per source_id,
    preserving diversity so the same source doesn't fill all k slots."""
    ordered = sorted(rows, key=key, reverse=reverse)
    seen: set[str] = set()
    picked = []
    for r in ordered:
        if r["source_id"] in seen:
            continue
        seen.add(r["source_id"])
        picked.append(r)
        if len(picked) >= k:
            break
    return picked


def select_false_negatives(rows: list[dict[str, Any]], threshold: float, k: int) -> list[dict[str, Any]]:
    candidates = [
        r for r in rows if r["condition_id"] != "clean" and r["label"] == 1 and r["p_fake"] < threshold
    ]
    return select_top_by_source(candidates, key=lambda r: r["p_fake"], reverse=False, k=k)


def select_false_positives(rows: list[dict[str, Any]], threshold: float, k: int) -> list[dict[str, Any]]:
    candidates = [
        r for r in rows if r["condition_id"] != "clean" and r["label"] == 0 and r["p_fake"] >= threshold
    ]
    return select_top_by_source(candidates, key=lambda r: r["p_fake"], reverse=True, k=k)


def select_flips(
    by_source: dict[str, dict[str, dict[str, Any]]], threshold: float, k: int
) -> list[dict[str, Any]]:
    candidates = []
    for sid, conds in by_source.items():
        clean_row = conds.get("clean")
        if clean_row is None:
            continue
        label = clean_row["label"]
        clean_p = clean_row["p_fake"]
        clean_correct = (clean_p >= threshold) if label == 1 else (clean_p < threshold)
        if not clean_correct:
            continue
        best = None
        for cid, row in conds.items():
            if cid == "clean":
                continue
            cond_correct = (row["p_fake"] >= threshold) if label == 1 else (row["p_fake"] < threshold)
            if cond_correct:
                continue
            shift = abs(row["p_fake"] - clean_p)
            if best is None or shift > best[0]:
                best = (shift, row)
        if best is not None:
            shift, row = best
            candidates.append({"source_id": sid, "shift": shift, "clean_row": clean_row, "flip_row": row})
    candidates.sort(key=lambda c: c["shift"], reverse=True)
    return candidates[:k]


def copy_case_image(image_path: str, dest_dir: Path, dest_name: str) -> str:
    src = Path(image_path)
    dest_dir.mkdir(parents=True, exist_ok=True)
    ext = src.suffix or ".jpg"
    dest = dest_dir / f"{dest_name}{ext}"
    shutil.copy2(src, dest)
    return str(dest)


SOURCE_IMAGE_NOTE = (
    "Copied file is the ORIGINAL, undistorted source image referenced by "
    "image_path -- transformed pixels were not regenerated in this script. "
    "condition_id names the transform that was applied when this p_fake was "
    "scored."
)


def build_error_cases(
    rows: list[dict[str, Any]],
    by_source: dict[str, dict[str, dict[str, Any]]],
    cases_dir: Path,
    threshold: float,
    k: int,
) -> dict[str, Any]:
    fns = select_false_negatives(rows, threshold, k)
    fps = select_false_positives(rows, threshold, k)
    flips = select_flips(by_source, threshold, k)

    fn_out = []
    for i, r in enumerate(fns, start=1):
        dest = copy_case_image(
            r["image_path"], cases_dir / "false_negatives", f"fn_{i}_{r['source_id']}_{r['condition_id']}"
        )
        fn_out.append(
            {
                "rank": i,
                "source_id": r["source_id"],
                "condition_id": r["condition_id"],
                "label": r["label"],
                "dataset": r["dataset"],
                "p_fake_transformed": r["p_fake"],
                "copied_file": dest,
                "note": SOURCE_IMAGE_NOTE,
            }
        )

    fp_out = []
    for i, r in enumerate(fps, start=1):
        dest = copy_case_image(
            r["image_path"], cases_dir / "false_positives", f"fp_{i}_{r['source_id']}_{r['condition_id']}"
        )
        fp_out.append(
            {
                "rank": i,
                "source_id": r["source_id"],
                "condition_id": r["condition_id"],
                "label": r["label"],
                "dataset": r["dataset"],
                "p_fake_transformed": r["p_fake"],
                "copied_file": dest,
                "note": SOURCE_IMAGE_NOTE,
            }
        )

    flip_out = []
    for i, c in enumerate(flips, start=1):
        clean_row = c["clean_row"]
        flip_row = c["flip_row"]
        sid = c["source_id"]
        clean_dest = copy_case_image(
            clean_row["image_path"], cases_dir / "flips", f"flip_{i}_{sid}_clean"
        )
        flip_dest = copy_case_image(
            flip_row["image_path"], cases_dir / "flips", f"flip_{i}_{sid}_{flip_row['condition_id']}"
        )
        flip_out.append(
            {
                "rank": i,
                "source_id": sid,
                "condition_id": flip_row["condition_id"],
                "label": clean_row["label"],
                "dataset": clean_row["dataset"],
                "p_fake_clean": clean_row["p_fake"],
                "p_fake_transformed": flip_row["p_fake"],
                "shift": c["shift"],
                "copied_file_clean": clean_dest,
                "copied_file_transformed": flip_dest,
                "note": (
                    SOURCE_IMAGE_NOTE
                    + " Both copied files here are byte-identical (same original "
                    "image) since the transformed view was never persisted to "
                    "disk; only the condition_id label distinguishes which "
                    "p_fake corresponds to which scored view."
                ),
            }
        )

    return {
        "selection_method": (
            "Ranked by p_fake extremeness among non-clean, misclassified rows "
            "(false_negatives: lowest p_fake among fake sources scored below "
            "threshold; false_positives: highest p_fake among real sources "
            "scored at/above threshold; flips: largest |p_fake shift| among "
            "sources correct when clean but wrong under some transform). "
            "Deduplicated to one row per source_id for case diversity."
        ),
        "false_negatives": fn_out,
        "false_positives": fp_out,
        "flips": flip_out,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rows", type=Path, default=DEFAULT_ROWS)
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    ap.add_argument("--threshold", type=float, default=THRESHOLD)
    ap.add_argument("--cases-per-group", type=int, default=3)
    args = ap.parse_args()

    rows = load_rows(args.rows)
    notes: list[str] = []

    condition_ids = list(CONDITION_IDS)
    missing_conditions = set(condition_ids) - {r["condition_id"] for r in rows}
    if missing_conditions:
        notes.append(f"WARNING: conditions absent from data: {sorted(missing_conditions)}")
    extra_conditions = {r["condition_id"] for r in rows} - set(condition_ids)
    if extra_conditions:
        notes.append(f"WARNING: rows with condition_id not in official grid: {sorted(extra_conditions)}")

    rows_by_condition: dict[str, list[dict[str, Any]]] = {cid: [] for cid in condition_ids}
    for r in rows:
        if r["condition_id"] in rows_by_condition:
            rows_by_condition[r["condition_id"]].append(r)

    by_source = build_by_source(rows)

    n_sources = len(by_source)
    source_condition_counts = {sid: len(c) for sid, c in by_source.items()}
    incomplete_sources = [sid for sid, n in source_condition_counts.items() if n != len(condition_ids)]
    if incomplete_sources:
        notes.append(
            f"WARNING: {len(incomplete_sources)} source(s) do not have all "
            f"{len(condition_ids)} conditions present: {incomplete_sources[:10]}"
            + (" ..." if len(incomplete_sources) > 10 else "")
        )

    clean_metrics = group_metrics(rows_by_condition["clean"], args.threshold)
    clean_fake_recall = clean_metrics["fake_recall_at_0.5"]

    by_condition = {
        cid: summarize_condition(cid, rows_by_condition, by_source, clean_fake_recall, args.threshold)
        for cid in condition_ids
    }

    families: dict[str, list[str]] = {}
    for cid in condition_ids:
        families.setdefault(FAMILY_OF[cid], []).append(cid)

    by_family = {
        fam: summarize_family(fam, cids, rows_by_condition, by_source, clean_fake_recall, args.threshold)
        for fam, cids in families.items()
    }

    overall = group_metrics(rows, args.threshold)
    overall["clean_relative_delta_fake_recall"] = (
        (overall["fake_recall_at_0.5"] - clean_fake_recall)
        if (overall["fake_recall_at_0.5"] is not None and clean_fake_recall is not None)
        else None
    )
    pooled_counts = {
        "fake_to_real_flips": 0,
        "fake_to_real_total": 0,
        "real_to_fake_flips": 0,
        "real_to_fake_total": 0,
    }
    for cid in condition_ids:
        if cid == "clean":
            continue
        c = flip_counts(by_source, cid, args.threshold)
        for k in pooled_counts:
            pooled_counts[k] += c[k]
    overall["fake_to_real_flip_rate"] = rate_or_none(
        pooled_counts["fake_to_real_flips"], pooled_counts["fake_to_real_total"]
    )
    overall["real_to_fake_flip_rate"] = rate_or_none(
        pooled_counts["real_to_fake_flips"], pooled_counts["real_to_fake_total"]
    )
    overall["flip_counts"] = pooled_counts

    markdown_table = build_markdown_table(by_condition)

    run_ids = sorted({r["run_id"] for r in rows})
    method_ids = sorted({r["method_id"] for r in rows})
    if len(run_ids) > 1:
        notes.append(f"WARNING: multiple run_ids present in input: {run_ids}")
    if len(method_ids) > 1:
        notes.append(f"WARNING: multiple method_ids present in input: {method_ids}")

    cases_dir = args.out_dir / "cases"
    error_cases = build_error_cases(rows, by_source, cases_dir, args.threshold, args.cases_per_group)

    summary = {
        "preliminary": True,
        "caveat": CAVEAT,
        "threshold": args.threshold,
        "source_file": str(args.rows),
        "run_id": run_ids[0] if len(run_ids) == 1 else run_ids,
        "method_id": method_ids[0] if len(method_ids) == 1 else method_ids,
        "n_rows": len(rows),
        "n_sources": n_sources,
        "conditions": condition_ids,
        "families": families,
        "overall": overall,
        "by_condition": by_condition,
        "by_family": by_family,
        "markdown_table": markdown_table,
        "error_cases": error_cases,
        "notes": notes,
    }

    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    md_doc = (
        "# Robustness Evaluation Summary (PRELIMINARY)\n\n"
        f"> {CAVEAT}\n\n"
        f"Threshold: {args.threshold} (placeholder, unfitted) | "
        f"{summary['n_sources']} sources x {len(condition_ids)} conditions = {summary['n_rows']} rows\n\n"
        + markdown_table
    )
    (args.out_dir / "summary.md").write_text(md_doc)

    print(md_doc)
    print("\n--- notes ---")
    for n in notes:
        print(n)
    if not notes:
        print("(no data-quality warnings)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
