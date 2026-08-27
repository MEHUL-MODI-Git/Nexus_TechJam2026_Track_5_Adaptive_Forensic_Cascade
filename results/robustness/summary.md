# Robustness Evaluation Summary (PRELIMINARY)

> PRELIMINARY. Computed with an unfitted PLACEHOLDER decision threshold (0.5, not calibrated) on the grid-smoke-v1 smoke set, whose real half is COCO images and fake half is SID-Set full-synthetic images. This is not a headline or final result -- it is a robustness triage artifact for internal use pending real threshold calibration and the sealed Phase 4 evaluation.

Threshold: 0.5 (placeholder, unfitted) | 400 sources x 20 conditions = 8000 rows

| Condition | Family | N | AUROC | Fake recall @0.5 | FPR @0.5 | Balanced acc | Delta vs clean | Fake to real flip | Real to fake flip |
|---|---|---|---|---|---|---|---|---|---|
| noise_s0.10 | noise | 400 | 0.817 | 1.5% | 0.5% | 50.5% | -51.5pp | 97.2% | 0.5% |
| noise_s0.05 | noise | 400 | 0.913 | 9.0% | 0.5% | 54.2% | -44.0pp | 83.0% | 0.5% |
| jpeg_q30 | jpeg | 400 | 0.937 | 11.5% | 0.0% | 55.8% | -41.5pp | 78.3% | 0.0% |
| jpeg_q50 | jpeg | 400 | 0.959 | 29.0% | 0.0% | 64.5% | -24.0pp | 45.3% | 0.0% |
| resize_0.25 | resize | 400 | 0.923 | 34.0% | 2.0% | 66.0% | -19.0pp | 38.7% | 2.0% |
| jpeg_q70 | jpeg | 400 | 0.965 | 38.0% | 0.0% | 69.0% | -15.0pp | 28.3% | 0.0% |
| noise_s0.02 | noise | 400 | 0.976 | 39.0% | 0.5% | 69.2% | -14.0pp | 27.4% | 0.5% |
| bright_+20 | color | 400 | 0.987 | 40.5% | 0.0% | 70.2% | -12.5pp | 25.5% | 0.0% |
| saturation_-20 | color | 400 | 0.990 | 44.5% | 0.0% | 72.2% | -8.5pp | 16.0% | 0.0% |
| contrast_+20 | color | 400 | 0.989 | 47.0% | 0.0% | 73.5% | -6.0pp | 17.0% | 0.0% |
| resize_0.5 | resize | 400 | 0.945 | 47.5% | 2.5% | 72.5% | -5.5pp | 12.3% | 2.5% |
| blur_s2.0 | blur | 400 | 0.647 | 48.5% | 31.5% | 58.5% | -4.5pp | 15.1% | 31.5% |
| blur_s0.5 | blur | 400 | 0.984 | 51.0% | 0.5% | 75.2% | -2.0pp | 3.8% | 0.5% |
| blur_s1.0 | blur | 400 | 0.941 | 51.5% | 2.5% | 74.5% | -1.5pp | 4.7% | 2.5% |
| jpeg_q90 | jpeg | 400 | 0.988 | 52.5% | 0.0% | 76.2% | -0.5pp | 1.9% | 0.0% |
| clean | clean | 400 | 0.992 | 53.0% | 0.0% | 76.5% | +0.0pp | n/a | n/a |
| saturation_+20 | color | 400 | 0.993 | 54.0% | 0.0% | 77.0% | +1.0pp | 4.7% | 0.0% |
| bright_-20 | color | 400 | 0.992 | 57.0% | 0.0% | 78.5% | +4.0pp | 6.6% | 0.0% |
| contrast_-20 | color | 400 | 0.992 | 58.0% | 0.0% | 79.0% | +5.0pp | 5.7% | 0.0% |
| crop_0.8 | crop | 400 | 0.990 | 62.0% | 0.0% | 81.0% | +9.0pp | 8.5% | 0.0% |
