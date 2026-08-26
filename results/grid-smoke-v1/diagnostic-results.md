# Diagnostic report (NOT a result)

> **⚠️ DIAGNOSTIC ONLY — these numbers may not be reported as results.**
> Threshold provenance: `PLACEHOLDER-uncalibrated-phase0` — not fitted on held-out dev.
> The operating point below is an unfitted reference point, not our chosen threshold.

- **Threshold:** 0.5000 (`PLACEHOLDER-uncalibrated-phase0`, fitted on held-out dev: False)
- **Sources:** 400 · **Views:** 8000 · **Conditions:** 20
- **Methods:** commfor_384
- **Bootstrap:** 300 replicates, unit = source_id, stratified by label

## Summary

| quantity | value |
|---|---|
| clean balanced accuracy | 0.7650 |
| clean fake recall | 0.5300 |
| clean AUROC | 0.9923 |
| **worst family** (fake recall) | **noise** = 0.1650 |
| worst exact condition (reported) | noise_s0.10 = 0.0150 |
| max real→fake flip | 0.3150 (blur_s2.0) |
| max fake→real flip | 0.5150 (noise_s0.10) |

Selective/abstention metrics: **not emitted** — no validated reliability estimator exists yet (absence is explicit, not zero).

### By transform family (severities pooled)

| family | conditions | fake recall | 95% CI | FPR | BAcc | AUROC |
|---|---:|---:|---|---:|---:|---:|
| jpeg | 4 | 0.3275 | [0.2812, 0.3770] | 0.0000 | 0.6638 | 0.9595 |
| blur | 3 | 0.5033 | [0.4432, 0.5750] | 0.1150 | 0.6942 | 0.8576 |
| resize | 2 | 0.4075 | [0.3537, 0.4700] | 0.0225 | 0.6925 | 0.9348 |
| noise | 3 | 0.1650 | [0.1317, 0.1967] | 0.0050 | 0.5800 | 0.8989 |
| color | 6 | 0.5017 | [0.4483, 0.5623] | 0.0000 | 0.7508 | 0.9902 |
| crop | 1 | 0.6200 | [0.5600, 0.6850] | 0.0000 | 0.8100 | 0.9899 |

*The worst family is the selection objective. `clean` is excluded from it by design and enters only through the constraints.*

### By condition

| condition | family | fake recall | FPR | BAcc | AUROC | Δrecall vs clean | real→fake | fake→real |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| blur_s0.5 | blur | 0.5100 | 0.0050 | 0.7525 | 0.9845 | 0.0200 | 0.0050 | 0.0200 |
| blur_s1.0 | blur | 0.5150 | 0.0250 | 0.7450 | 0.9406 | 0.0150 | 0.0250 | 0.0250 |
| blur_s2.0 | blur | 0.4850 | 0.3150 | 0.5850 | 0.6470 | 0.0450 | 0.3150 | 0.0800 |
| bright_+20 | color | 0.4050 | 0.0000 | 0.7025 | 0.9869 | 0.1250 | 0.0000 | 0.1350 |
| bright_-20 | color | 0.5700 | 0.0000 | 0.7850 | 0.9924 | -0.0400 | 0.0000 | 0.0350 |
| clean | clean | 0.5300 | 0.0000 | 0.7650 | 0.9923 | 0.0000 | — | — |
| contrast_+20 | color | 0.4700 | 0.0000 | 0.7350 | 0.9885 | 0.0600 | 0.0000 | 0.0900 |
| contrast_-20 | color | 0.5800 | 0.0000 | 0.7900 | 0.9923 | -0.0500 | 0.0000 | 0.0300 |
| crop_0.8 | crop | 0.6200 | 0.0000 | 0.8100 | 0.9899 | -0.0900 | 0.0000 | 0.0450 |
| jpeg_q30 | jpeg | 0.1150 | 0.0000 | 0.5575 | 0.9373 | 0.4150 | 0.0000 | 0.4150 |
| jpeg_q50 | jpeg | 0.2900 | 0.0000 | 0.6450 | 0.9586 | 0.2400 | 0.0000 | 0.2400 |
| jpeg_q70 | jpeg | 0.3800 | 0.0000 | 0.6900 | 0.9651 | 0.1500 | 0.0000 | 0.1500 |
| jpeg_q90 | jpeg | 0.5250 | 0.0000 | 0.7625 | 0.9876 | 0.0050 | 0.0000 | 0.0100 |
| noise_s0.02 | noise | 0.3900 | 0.0050 | 0.6925 | 0.9758 | 0.1400 | 0.0050 | 0.1450 |
| noise_s0.05 | noise | 0.0900 | 0.0050 | 0.5425 | 0.9133 | 0.4400 | 0.0050 | 0.4400 |
| noise_s0.10 | noise | 0.0150 | 0.0050 | 0.5050 | 0.8174 | 0.5150 | 0.0050 | 0.5150 |
| resize_0.25 | resize | 0.3400 | 0.0200 | 0.6600 | 0.9229 | 0.1900 | 0.0200 | 0.2050 |
| resize_0.5 | resize | 0.4750 | 0.0250 | 0.7250 | 0.9449 | 0.0550 | 0.0250 | 0.0650 |
| saturation_+20 | color | 0.5400 | 0.0000 | 0.7700 | 0.9929 | -0.0100 | 0.0000 | 0.0250 |
| saturation_-20 | color | 0.4450 | 0.0000 | 0.7225 | 0.9901 | 0.0850 | 0.0000 | 0.0850 |

### Raw counts (auditable)

| condition | TP | FN | FP | TN |
|---|---:|---:|---:|---:|
| blur_s0.5 | 102 | 98 | 1 | 199 |
| blur_s1.0 | 103 | 97 | 5 | 195 |
| blur_s2.0 | 97 | 103 | 63 | 137 |
| bright_+20 | 81 | 119 | 0 | 200 |
| bright_-20 | 114 | 86 | 0 | 200 |
| clean | 106 | 94 | 0 | 200 |
| contrast_+20 | 94 | 106 | 0 | 200 |
| contrast_-20 | 116 | 84 | 0 | 200 |
| crop_0.8 | 124 | 76 | 0 | 200 |
| jpeg_q30 | 23 | 177 | 0 | 200 |
| jpeg_q50 | 58 | 142 | 0 | 200 |
| jpeg_q70 | 76 | 124 | 0 | 200 |
| jpeg_q90 | 105 | 95 | 0 | 200 |
| noise_s0.02 | 78 | 122 | 1 | 199 |
| noise_s0.05 | 18 | 182 | 1 | 199 |
| noise_s0.10 | 3 | 197 | 1 | 199 |
| resize_0.25 | 68 | 132 | 4 | 196 |
| resize_0.5 | 95 | 105 | 5 | 195 |
| saturation_+20 | 108 | 92 | 0 | 200 |
| saturation_-20 | 89 | 111 | 0 | 200 |
