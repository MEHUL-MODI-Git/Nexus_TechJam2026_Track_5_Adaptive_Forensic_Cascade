"""Generate `deliverables/robustness-summary.md` — official deliverable #4.

The brief asks for "a compact table or visual summary comparing performance on clean
images versus transformed images". This writes that document straight from the
committed artifacts, so the deliverable cannot drift from the results it describes.

    .venv/bin/python scripts/build_robustness_summary.py
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAMILY_ORDER = ["clean", "jpeg", "blur", "resize", "noise", "color", "crop"]
PRETTY = {"clean": "Clean (no transformation)", "jpeg": "JPEG compression", "blur": "Gaussian blur",
          "resize": "Downscale", "noise": "Gaussian noise", "color": "Colour adjustment",
          "crop": "Crop"}
COND_LABEL = {
    "clean": "original", "jpeg_q90": "quality 90", "jpeg_q70": "quality 70",
    "jpeg_q50": "quality 50", "jpeg_q30": "quality 30", "blur_s0.5": "sigma 0.5",
    "blur_s1.0": "sigma 1.0", "blur_s2.0": "sigma 2.0", "resize_0.5": "50% scale",
    "resize_0.25": "25% scale", "noise_s0.02": "sigma 0.02", "noise_s0.05": "sigma 0.05",
    "noise_s0.10": "sigma 0.10", "bright_-20": "brightness -20", "bright_+20": "brightness +20",
    "contrast_-20": "contrast -20", "contrast_+20": "contrast +20",
    "saturation_-20": "saturation -20", "saturation_+20": "saturation +20",
    "crop_0.8": "80% centre crop",
}


def pct(x):
    return f"{x * 100:.1f}%"


def bar(x, width=22):
    """A plain-text bar so the table reads as a visual summary too."""
    filled = round(x * width)
    return "█" * filled + "·" * (width - filled)


def main() -> int:
    it = json.loads((ROOT / "results/internal-test/results.json").read_text())
    sealed = json.loads((ROOT / "results/sealed/reference-results.json").read_text())
    hold = json.loads((ROOT / "results/holdout/validation.json").read_text())
    ops = json.loads((ROOT / "results/ops/ops-evidence.json").read_text())
    router, primary = it["router"], it["primary_at_0.5"]
    matched = it["primary_at_matched_clean_fpr"]
    boot = it["paired_bootstrap_router_vs_primary_matched"]
    dedup = sealed["conventions"]["deduplicated"]
    from src.pipeline.transforms import CONDITION_IDS, FAMILY_OF

    lines: list[str] = []
    A = lines.append
    A("# Robustness Evaluation Summary")
    A("")
    A("**TikTok TechJam 2026 — Track 5 · Adaptive Forensic Cascade**  ")
    A("Official deliverable #4: performance on clean images versus transformed images.")
    A("")
    A("> Generated from committed artifacts by `scripts/build_robustness_summary.py`. Every")
    A("> figure below is reproducible with `scripts/run_eval.py --config configs/frozen.yaml`.")
    A(f"> Generated {datetime.now(UTC).strftime('%Y-%m-%d')}.")
    A("")
    A("---")
    A("")
    A("## 1. What was measured, and on what")
    A("")
    A("| | |")
    A("|---|---|")
    A(f"| Evaluation set | **{it['n_sources']:,} images** held back from all fitting |")
    A(f"| Conditions | **{len(CONDITION_IDS)}** — the organizers' grid, 1 clean + 19 transformed |")
    A(f"| Scored predictions | **{it['n_rows']:,}** |")
    A("| Decision threshold | **one value, frozen before this set was scored**, never tuned per condition |")
    A("| Baseline | the same frozen detector alone, no correction layer |")
    A("")
    A("Nothing was fitted, selected or re-thresholded on this data. It was scored once.")
    A("")
    A("## 2. Headline: clean versus transformed")
    A("")
    A("Detection rate on AI-generated images — the number that collapses under transformation.")
    A("")
    A("| | Baseline detector | **Our cascade** |")
    A("|---|---:|---:|")
    A(f"| Clean images | {pct(primary['clean_fake_recall'])} | **{pct(router['clean_fake_recall'])}** |")
    A(f"| Worst transformation family | {pct(primary['worst_family_fake_recall'])} "
      f"| **{pct(router['worst_family_fake_recall'])}** |")
    A(f"| All 20 conditions | {pct(primary['overall_fake_recall'])} "
      f"| **{pct(router['overall_fake_recall'])}** |")
    A(f"| False alarms on clean real photos | {pct(primary['clean_fpr'])} | {pct(router['clean_fpr'])} |")
    A(f"| Overall accuracy | {pct(primary['overall_accuracy'])} | **{pct(router['overall_accuracy'])}** |")
    A("")
    A("**The baseline does not degrade gracefully — it fails.** On its worst family it detects")
    A(f"{pct(primary['worst_family_fake_recall'])} of AI images. Ours holds at "
      f"{pct(router['worst_family_fake_recall'])}.")
    A("")
    A("## 3. Every transformation family")
    A("")
    A("| Family | Baseline | Our cascade | Gain | Our detection rate |")
    A("|---|---:|---:|---:|---|")
    for fam in FAMILY_ORDER:
        if fam == "clean":
            b, o = primary["clean_fake_recall"], router["clean_fake_recall"]
        else:
            b = primary["family_fake_recall"].get(fam)
            o = router["family_fake_recall"].get(fam)
            if b is None or o is None:
                continue
        mark = " ⬅ worst" if fam == router["worst_family"] else ""
        A(f"| {PRETTY[fam]}{mark} | {pct(b)} | **{pct(o)}** | +{(o - b) * 100:.1f} pt | `{bar(o)}` |")
    A("")
    A("## 4. Every individual condition")
    A("")
    A("| Condition | Setting | Baseline | **Ours** |")
    A("|---|---|---:|---:|")
    for cid in CONDITION_IDS:
        b = primary["per_condition"][cid]["fake_recall"]
        o = router["per_condition"][cid]["fake_recall"]
        fam = PRETTY[FAMILY_OF[cid]].split(" (")[0]
        A(f"| {fam} | {COND_LABEL.get(cid, cid)} | {pct(b)} | **{pct(o)}** |")
    A("")
    A("The two hardest conditions are the ones that destroy high-frequency detail:")
    A(f"noise at sigma 0.10 takes the baseline to **{pct(primary['per_condition']['noise_s0.10']['fake_recall'])}**")
    A(f"and JPEG quality 30 to **{pct(primary['per_condition']['jpeg_q30']['fake_recall'])}**. Ours holds at")
    A(f"{pct(router['per_condition']['noise_s0.10']['fake_recall'])} and "
      f"{pct(router['per_condition']['jpeg_q30']['fake_recall'])}.")
    A("")
    A("## 5. The comparison made fair")
    A("")
    A("A detector raises its detection rate simply by accusing more images, and the baseline is")
    A(f"far more conservative than ours — it flags {pct(primary['clean_fpr'])} of clean real photos")
    A(f"against our {pct(router['clean_fpr'])}. Part of the raw gap is that difference in operating")
    A("point, not in skill, so we removed our advantage:")
    A("")
    A("| Baseline arm | Threshold | Worst-family detection | Our lead |")
    A("|---|---:|---:|---:|")
    A(f"| Published default | 0.5000 | {pct(primary['worst_family_fake_recall'])} "
      f"| +{(router['worst_family_fake_recall'] - primary['worst_family_fake_recall']) * 100:.1f} pt |")
    A(f"| **Given our false-alarm rate, tuned on this test set in its own favour** "
      f"| {matched['threshold']:.4f} | **{pct(matched['worst_family_fake_recall'])}** "
      f"| **+{boot['mean_delta'] * 100:.1f} pt** |")
    A("")
    A(f"**+{boot['mean_delta'] * 100:.1f} points**, CI95 "
      f"[+{boot['ci95_low'] * 100:.1f}, +{boot['ci95_high'] * 100:.1f}], paired bootstrap over image")
    A("sources. That is the number we report — the smaller, defensible one.")
    A("")
    A("## 6. Does it hold on data we have never touched?")
    A("")
    A("| Set | What it is | Worst-family detection | Clean false alarms |")
    A("|---|---|---:|---:|")
    A(f"| Internal test | {it['n_sources']:,} held-back images | {pct(router['worst_family_fake_recall'])} "
      f"| {pct(router['clean_fpr'])} |")
    A(f"| Second holdout | {hold['n_sources']:,} images acquired later, thresholds fixed first "
      f"| {pct(hold['shipped_model']['worst_family_fake_recall'])} "
      f"| {pct(hold['shipped_model']['clean_fpr'])} |")
    A(f"| **Organizers' reference set** | {dedup['clean']['n_images']:,} unique images, "
      f"sealed from day one, scored once | **{pct(dedup['worst_family_fake_recall'])}** "
      f"| **{pct(dedup['clean']['fpr'])}** |")
    A("")
    A("The organizers' set was never trained on, never tuned against, and scored exactly once after")
    A(f"the architecture was frozen: {sealed['n_rows']:,} predictions, "
      f"{sealed['provenance']['n_failed_rows']} failures. Results there are **better** than on our own")
    A("held-back data.")
    A("")
    A("## 7. Cost")
    A("")
    A("| | |")
    A("|---|---:|")
    A(f"| Parameters shipped | {ops['parameters']['shipped_total']:,} "
      f"({ops['parameters']['percent_of_limit']:.2f}% of the 2B limit) |")
    A(f"| Of which trained by us | {ops['parameters']['router_head'] + ops['parameters']['degradation_reporter']:,} |")
    A(f"| Latency, baseline | {ops['latency_ms']['baseline_cf_only']['p50']:.0f} ms per image |")
    A(f"| Latency, full cascade | {ops['latency_ms']['cascade_shipped']['p50']:.0f} ms per image "
      f"({ops['latency_ms']['cascade_over_baseline']:.1f}x) |")
    A(f"| Peak memory | {ops['peak_rss_mb']:.0f} MB |")
    A("")
    A("Measured on an Apple M4 Pro laptop. The robustness is bought with compute, and we state the")
    A("price rather than implying it is free.")
    A("")
    A("## 8. Honest limits")
    A("")
    A(f"- **We raise more false alarms.** {pct(router['clean_fpr'])} of clean real photographs are")
    A("  flagged, against 7.6% we set ourselves as a cap. We reported the breach rather than")
    A("  re-tuning to hide it.")
    A("- **We raise the floor, not the ceiling.** At a matched false-alarm rate the baseline is")
    A("  competitive on blur, colour and crop. Our advantage concentrates on noise and compression —")
    A("  the conditions where the baseline collapses.")
    A("- **Single-source training corpus.** Fitting used one dataset family, so generalisation to")
    A("  other generators is evidenced by the organizers' set rather than by our own training data.")
    A("")
    A("Representative failures, with images and scores: `deliverables/error-analysis-note.md`.")
    A("")

    out = ROOT / "deliverables" / "robustness-summary.md"
    out.write_text("\n".join(lines))
    print(f"wrote {out} ({len(lines)} lines)")
    return 0


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(ROOT))
    raise SystemExit(main())
