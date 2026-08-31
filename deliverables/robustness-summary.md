# Robustness Evaluation Summary

**TikTok TechJam 2026 — Track 5 · Adaptive Forensic Cascade**  
Official deliverable #4: performance on clean images versus transformed images.

> Generated from committed artifacts by `scripts/build_robustness_summary.py`. Every
> figure below is reproducible with `scripts/run_eval.py --config configs/frozen.yaml`.
> Generated 2026-08-31.

---

## 1. What was measured, and on what

| | |
|---|---|
| Evaluation set | **3,000 images** held back from all fitting |
| Conditions | **20** — the organizers' grid, 1 clean + 19 transformed |
| Scored predictions | **60,000** |
| Decision threshold | **one value, frozen before this set was scored**, never tuned per condition |
| Baseline | the same frozen detector alone, no correction layer |

Nothing was fitted, selected or re-thresholded on this data. It was scored once.

## 2. Headline: clean versus transformed

Detection rate on AI-generated images — the number that collapses under transformation.

| | Baseline detector | **Our cascade** |
|---|---:|---:|
| Clean images | 71.1% | **96.1%** |
| Worst transformation family | 12.3% | **82.6%** |
| All 20 conditions | 56.7% | **92.0%** |
| False alarms on clean real photos | 0.3% | 8.3% |
| Overall accuracy | 78.1% | **90.9%** |

**The baseline does not degrade gracefully — it fails.** On its worst family it detects
12.3% of AI images. Ours holds at 82.6%.

## 3. Every transformation family

| Family | Baseline | Our cascade | Gain | Our detection rate |
|---|---:|---:|---:|---|
| Clean (no transformation) | 71.1% | **96.1%** | +25.1 pt | `█████████████████████·` |
| JPEG compression | 37.0% | **90.5%** | +53.4 pt | `████████████████████··` |
| Gaussian blur | 72.6% | **94.7%** | +22.1 pt | `█████████████████████·` |
| Downscale | 71.2% | **94.2%** | +23.0 pt | `█████████████████████·` |
| Gaussian noise ⬅ worst | 12.3% | **82.6%** | +70.3 pt | `██████████████████····` |
| Colour adjustment | 73.7% | **94.4%** | +20.7 pt | `█████████████████████·` |
| Crop | 76.0% | **96.2%** | +20.2 pt | `█████████████████████·` |

## 4. Every individual condition

| Condition | Setting | Baseline | **Ours** |
|---|---|---:|---:|
| Clean | original | 71.1% | **96.1%** |
| JPEG compression | quality 90 | 65.6% | **95.5%** |
| JPEG compression | quality 70 | 43.1% | **92.0%** |
| JPEG compression | quality 50 | 29.9% | **89.9%** |
| JPEG compression | quality 30 | 9.6% | **84.5%** |
| Gaussian blur | sigma 0.5 | 71.4% | **95.0%** |
| Gaussian blur | sigma 1.0 | 73.7% | **93.8%** |
| Gaussian blur | sigma 2.0 | 72.9% | **95.3%** |
| Downscale | 50% scale | 74.3% | **94.7%** |
| Downscale | 25% scale | 68.1% | **93.6%** |
| Gaussian noise | sigma 0.02 | 30.5% | **87.9%** |
| Gaussian noise | sigma 0.05 | 5.6% | **80.9%** |
| Gaussian noise | sigma 0.10 | 0.7% | **79.0%** |
| Colour adjustment | brightness -20 | 82.7% | **97.6%** |
| Colour adjustment | brightness +20 | 66.1% | **89.7%** |
| Colour adjustment | contrast -20 | 82.2% | **95.5%** |
| Colour adjustment | contrast +20 | 71.0% | **91.7%** |
| Colour adjustment | saturation -20 | 68.0% | **95.1%** |
| Colour adjustment | saturation +20 | 72.1% | **96.7%** |
| Crop | 80% centre crop | 76.0% | **96.2%** |

The two hardest conditions are the ones that destroy high-frequency detail:
noise at sigma 0.10 takes the baseline to **0.7%**
and JPEG quality 30 to **9.6%**. Ours holds at
79.0% and 84.5%.

## 5. The comparison made fair

A detector raises its detection rate simply by accusing more images, and the baseline is
far more conservative than ours — it flags 0.3% of clean real photos
against our 8.3%. Part of the raw gap is that difference in operating
point, not in skill, so we removed our advantage:

| Baseline arm | Threshold | Worst-family detection | Our lead |
|---|---:|---:|---:|
| Published default | 0.5000 | 12.3% | +70.3 pt |
| **Given our false-alarm rate, tuned on this test set in its own favour** | 0.0058 | **33.4%** | **+49.2 pt** |

**+49.2 points**, CI95 [+47.5, +50.8], paired bootstrap over image
sources. That is the number we report — the smaller, defensible one.

## 6. Does it hold on data we have never touched?

| Set | What it is | Worst-family detection | Clean false alarms |
|---|---|---:|---:|
| Internal test | 3,000 held-back images | 82.6% | 8.3% |
| Second holdout | 3,000 images acquired later, thresholds fixed first | 82.9% | 7.5% |
| **Organizers' reference set** | 8,719 unique images, sealed from day one, scored once | **87.9%** | **1.6%** |

The organizers' set was never trained on, never tuned against, and scored exactly once after
the architecture was frozen: 174,380 predictions, 0 failures. Results there are **better** than on our own
held-back data.

## 7. Cost

| | |
|---|---:|
| Parameters shipped | 21,814,571 (1.09% of the 2B limit) |
| Of which trained by us | 2,602 |
| Latency, baseline | 19 ms per image |
| Latency, full cascade | 135 ms per image (6.9x) |
| Peak memory | 727 MB |

Measured on an Apple M4 Pro laptop. The robustness is bought with compute, and we state the
price rather than implying it is free.

## 8. Honest limits

- **We raise more false alarms.** 8.3% of clean real photographs are
  flagged, against 7.6% we set ourselves as a cap. We reported the breach rather than
  re-tuning to hide it.
- **We raise the floor, not the ceiling.** At a matched false-alarm rate the baseline is
  competitive on blur, colour and crop. Our advantage concentrates on noise and compression —
  the conditions where the baseline collapses.
- **Single-source training corpus.** Fitting used one dataset family, so generalisation to
  other generators is evidenced by the organizers' set rather than by our own training data.

Representative failures, with images and scores: `deliverables/error-analysis-note.md`.
