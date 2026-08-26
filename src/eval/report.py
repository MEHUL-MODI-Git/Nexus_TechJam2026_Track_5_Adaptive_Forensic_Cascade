"""Markdown reporting from a results document.

[relay] Claude, while Codex is limit-blocked (PROTOCOL §6).

Hard rule from the eval spec: **tables consume the results JSON; they never
recompute a metric.** Two code paths producing "the same" number is how a
report ends up disagreeing with the artifact it claims to summarize, and the
disagreement is always discovered by a reader, not by us.
"""

from __future__ import annotations

from typing import Any

from .results import DIAGNOSTIC_SCHEMA


def _fmt(value: Any, places: int = 4) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.{places}f}"
    return str(value)


def render_markdown(document: dict[str, Any]) -> str:
    """Render the full report. Every number is read from `document`."""
    diagnostic = document["schema_version"] == DIAGNOSTIC_SCHEMA
    protocol = document["protocol"]
    dataset = document["dataset"]
    lines: list[str] = []

    title = "Diagnostic report (NOT a result)" if diagnostic else "Evaluation results"
    lines += [f"# {title}", ""]

    if diagnostic:
        lines += [
            "> **⚠️ DIAGNOSTIC ONLY — these numbers may not be reported as results.**",
            f"> Threshold provenance: `{protocol['threshold_provenance']}` — "
            "not fitted on held-out dev.",
            "> The operating point below is an unfitted reference point, not our "
            "chosen threshold.",
            "",
        ]

    lines += [
        f"- **Threshold:** {_fmt(protocol['threshold'])} "
        f"(`{protocol['threshold_provenance']}`, "
        f"fitted on held-out dev: {protocol['threshold_fitted_on_held_out_dev']})",
        f"- **Sources:** {dataset['source_count']} · **Views:** {dataset['view_count']} "
        f"· **Conditions:** {dataset['condition_count']}",
        f"- **Methods:** {', '.join(document.get('method_ids', []))}",
        f"- **Bootstrap:** {protocol['bootstrap']['n_replicates']} replicates, "
        f"unit = {protocol['bootstrap']['unit']}, "
        f"stratified by {protocol['bootstrap']['stratified_by']}",
        "",
    ]

    for method in document.get("methods", []):
        lines += _render_method(method, len(document.get("methods", [])) > 1)

    if document.get("paired_deltas"):
        lines += ["## Paired method deltas", "",
                  "*Computed on identical bootstrap resamples, so the intervals are "
                  "comparable.*", "",
                  "| metric | A | B | delta (B-A) | 95% CI |", "|---|---|---|---:|---|"]
        for d in document["paired_deltas"]:
            lines.append(f"| {d['metric']} | {d['method_a']} | {d['method_b']} | "
                         f"{_fmt(d['delta_mean'])} | [{_fmt(d['ci95_low'])}, "
                         f"{_fmt(d['ci95_high'])}] |")
        lines.append("")

    if document.get("warnings"):
        lines += ["## Warnings", ""] + [f"- {w}" for w in document["warnings"]] + [""]
    return "\n".join(lines)


def _render_method(method: dict[str, Any], multi: bool) -> list[str]:
    """One method's tables. Methods are NEVER pooled (Codex R1)."""
    lines: list[str] = []
    summary = method["headline"]
    if multi:
        lines += [f"## Method: `{method['method_id']}`", ""]
    if summary:
        lines += ["#### Summary" if multi else "## Summary", "",
                  "| quantity | value |", "|---|---|",
                  f"| clean balanced accuracy | {_fmt(summary['clean']['balanced_accuracy'])} |",
                  f"| clean fake recall | {_fmt(summary['clean']['fake_recall'])} |",
                  f"| clean AUROC | {_fmt(summary['clean']['auroc'])} |",
                  f"| **worst family** (fake recall) | **{summary['worst_family']['family']}** "
                  f"= {_fmt(summary['worst_family']['fake_recall'])} |",
                  f"| worst exact condition (reported) | "
                  f"{summary['worst_exact_condition']['condition_id']} "
                  f"= {_fmt(summary['worst_exact_condition']['fake_recall'])} |",
                  f"| max real→fake flip | "
                  f"{_fmt(summary['max_directional_flip']['real_to_fake_flip'])} "
                  f"({summary['max_directional_flip']['real_to_fake_condition']}) |",
                  f"| max fake→real flip | "
                  f"{_fmt(summary['max_directional_flip']['fake_to_real_flip'])} "
                  f"({summary['max_directional_flip']['fake_to_real_condition']}) |",
                  ""]
        if summary.get("selective") is None:
            lines += ["Selective/abstention metrics: **not emitted** — no validated "
                      "reliability estimator exists yet (absence is explicit, not zero).", ""]

    if method.get("families"):
        lines += ["### By transform family (severities pooled)", "",
                  "| family | conditions | fake recall | 95% CI | FPR | BAcc | AUROC |",
                  "|---|---:|---:|---|---:|---:|---:|"]
        for fam in method["families"]:
            m, ci = fam["metrics"], fam["ci95"]["fake_recall"]
            lines.append(
                f"| {fam['family']} | {fam['n_conditions']} | {_fmt(m['fake_recall'])} | "
                f"[{_fmt(ci['ci95_low'])}, {_fmt(ci['ci95_high'])}] | "
                f"{_fmt(m['false_positive_rate'])} | {_fmt(m['balanced_accuracy'])} | "
                f"{_fmt(m['auroc'])} |"
            )
        lines.append("")
        lines += ["*The worst family is the selection objective. `clean` is excluded "
                  "from it by design and enters only through the constraints.*", ""]

    lines += ["### By condition", "",
              "| condition | family | fake recall | FPR | BAcc | AUROC | Δrecall vs clean "
              "| real→fake | fake→real |",
              "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for entry in method["conditions"]:
        m = entry["metrics"]
        flips = entry.get("flips") or {}
        lines.append(
            f"| {entry['condition_id']} | {entry['family']} | {_fmt(m['fake_recall'])} | "
            f"{_fmt(m['false_positive_rate'])} | {_fmt(m['balanced_accuracy'])} | "
            f"{_fmt(m['auroc'])} | {_fmt(entry['drops']['fake_recall'])} | "
            f"{_fmt(flips.get('real_to_fake_flip'))} | {_fmt(flips.get('fake_to_real_flip'))} |"
        )
    lines.append("")

    lines += ["### Raw counts (auditable)", "",
              "| condition | TP | FN | FP | TN |", "|---|---:|---:|---:|---:|"]
    for entry in method["conditions"]:
        c = entry["counts"]
        lines.append(f"| {entry['condition_id']} | {c['tp']} | {c['fn']} | {c['fp']} | {c['tn']} |")
    lines.append("")

    return lines
