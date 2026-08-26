# Evaluation, Metrics, Ablations, and Error Analysis

> **Status: DECISION for protocol; implementation details marked OPEN must be fixed before measurements.**

## Evaluation principles

1. Every clean source image defines a family of transformed views.
2. All views inherit the source label.
3. Metrics are reported by class, transformation family, and severity.
4. One threshold chosen on development data is used across clean and transformed test conditions.
5. External and official-reference tests are not used to tune models, probes, thresholds, or calibration.
6. Confidence intervals resample source images, not transformed views as if independent.
7. Results must distinguish measured, estimated, and illustrative numbers.

## Exact official stress matrix

| ID | Family | Severity/operation |
|---|---|---|
| `clean` | None | Original canonical decode |
| `jpeg_q90` | JPEG | Quality 90 |
| `jpeg_q70` | JPEG | Quality 70 |
| `jpeg_q50` | JPEG | Quality 50 |
| `jpeg_q30` | JPEG | Quality 30 |
| `blur_s0.5` | Gaussian blur | Sigma 0.5 |
| `blur_s1.0` | Gaussian blur | Sigma 1.0 |
| `blur_s2.0` | Gaussian blur | Sigma 2.0 |
| `resize_0.5` | Downscale/upscale | Scale to 0.5x, then restore dimensions |
| `resize_0.25` | Downscale/upscale | Scale to 0.25x, then restore dimensions |
| `noise_s0.02` | Gaussian noise | Sigma 0.02 |
| `noise_s0.05` | Gaussian noise | Sigma 0.05 |
| `noise_s0.10` | Gaussian noise | Sigma 0.10 |
| `bright_-20` | Color jitter | Brightness -20% |
| `bright_+20` | Color jitter | Brightness +20% |
| `contrast_-20` | Color jitter | Contrast -20% |
| `contrast_+20` | Color jitter | Contrast +20% |
| `saturation_-20` | Color jitter | Saturation -20% |
| `saturation_+20` | Color jitter | Saturation +20% |
| `crop_0.8` | Center crop | Retain centered 80% crop, then model adaptation |

This expands the organizer's “brightness/contrast/sat. +/-20%” into six deterministic endpoints. Also report an optional composed/random color-jitter condition separately; do not replace the endpoint tests with it.

## Transform implementation manifest

Record for every run:

- library and version;
- RGB/value-range convention;
- JPEG encoder, chroma subsampling, and optimize/progressive flags;
- blur kernel size/truncation and boundary mode;
- downscale and upscale interpolation;
- Gaussian noise clipping and random seed;
- brightness/contrast/saturation operator definitions;
- crop geometry and post-crop handling;
- whether alpha was discarded or composited;
- image decode orientation handling.

Publish a small golden test set with expected transformed hashes or pixel summaries so others can verify the pipeline.

## Core confusion counts

Use `AI-generated` as the positive class:

- `TP`: fake predicted fake.
- `FN`: fake predicted real.
- `FP`: real predicted fake.
- `TN`: real predicted real.

For abstaining systems, publish both:

1. forced-binary metrics at the fixed class threshold;
2. selective metrics on accepted examples plus coverage/abstention.

Never silently count abstentions as correct or drop them without reporting coverage.

## Required metrics

### Balanced accuracy

```text
TPR = TP / (TP + FN)
TNR = TN / (TN + FP)
BalancedAccuracy = (TPR + TNR) / 2
```

Balanced accuracy is safer than plain accuracy when class counts differ.

### Fake recall

```text
FakeRecall = TP / (TP + FN)
```

This is the most important class-specific metric because post-processing often creates fake-to-real collapse.

### False-positive rate

```text
FPR = FP / (FP + TN)
```

High fake recall is not acceptable if authentic images are routinely labeled generated.

### Clean-to-transformed drop

For metric `M` and transformation `t`:

```text
Drop_M(t) = M(clean) - M(t)
```

Report signed points. A negative drop means the transformed score improved.

### Worst-transformation performance

```text
WorstFakeRecall = min_t FakeRecall(t)
WorstBalancedAcc = min_t BalancedAccuracy(t)
```

Report both the value and the transformation that caused it.

Calculate across exact severities, not only family averages.

### Prediction flip rate

For source `x` and transform `t`:

```text
FlipRate(t) = mean[decision(x) != decision(t(x))]
```

Also report directional flips:

```text
FakeToRealFlip(t) = P(pred_clean=fake and pred_t=real | y=fake)
RealToFakeFlip(t) = P(pred_clean=real and pred_t=fake | y=real)
```

The first is especially aligned with DEAR's prediction-asymmetry finding.

## Strongly recommended secondary metrics

- AUROC.
- Average precision.
- Expected calibration error with documented bins.
- Brier score.
- Negative log likelihood.
- Selective risk versus coverage.
- Area under the risk-coverage curve.
- Rescue invocation rate.
- Rescue correction rate.
- Rescue harm rate: common path correct, rescued result wrong.
- Common-path and rescued p50/p95 latency.

## Headline result table template

Populate with measured values only.

| Method | Clean BAcc | Worst BAcc | Worst fake recall | JPEG30 fake recall | Blur2 fake recall | Resize0.25 fake recall | Noise0.10 fake recall | Crop0.8 fake recall | FPR clean | Max fake-to-real flip |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Primary only |  |  |  |  |  |  |  |  |  |  |
| LOTA only |  |  |  |  |  |  |  |  |  |  |
| Static average |  |  |  |  |  |  |  |  |  |  |
| Learned linear stacker |  |  |  |  |  |  |  |  |  |  |
| Router, no probes |  |  |  |  |  |  |  |  |  |  |
| Router + probes |  |  |  |  |  |  |  |  |  |  |
| Router + worst-group |  |  |  |  |  |  |  |  |  |  |
| Full cascade + rescue |  |  |  |  |  |  |  |  |  |  |

## Full transformation table template

| Method | Metric | Clean | J90 | J70 | J50 | J30 | B0.5 | B1 | B2 | R0.5 | R0.25 | N0.02 | N0.05 | N0.10 | Color worst | Crop0.8 | Worst |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Primary | Fake recall | | | | | | | | | | | | | | | | |
| LOTA | Fake recall | | | | | | | | | | | | | | | | |
| Full cascade | Fake recall | | | | | | | | | | | | | | | | |
| Primary | Balanced acc. | | | | | | | | | | | | | | | | |
| Full cascade | Balanced acc. | | | | | | | | | | | | | | | | |

## Detector shootout

Before building the final router, run a bounded shootout:

| Candidate | Clean | JPEG30 | Blur2 | Resize0.25 | Noise0.10 | Crop0.8 | Worst fake recall | FPR | p95 latency | Setup status |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Community Forensics 384 | | | | | | | | | | |
| OmniAID recommended weights | | | | | | | | | | |
| LOTA | | | | | | | | | | |
| WaRPAD | | | | | | | | | | |
| RIGID | | | | | | | | | | |
| SAFE, if integrated | | | | | | | | | | |
| AIDE, if integrated | | | | | | | | | | |

Use one frozen evaluation subset and one protocol. Avoid cherry-picking each model's preferred preprocessing unless that preprocessing is intrinsic to the official model.

## Complementarity analysis

For experts `A` and `B`, measure:

```text
Correction(B|A) = P(B correct | A wrong)
JointFailure(A,B) = P(A wrong and B wrong)
ErrorCorrelation = corr(1[A wrong], 1[B wrong])
```

Break these down by:

- real versus fake;
- transformation family;
- severity;
- generator/source;
- quality bin.

Also compute oracle ensemble performance: count a sample correct if any expert is correct. This is not deployable performance; it is the upper-bound evidence that a router has something useful to learn.

## Mandatory ablations

### A. Strongest single detector

Purpose: establish the true baseline.

Variants:

- Community Forensics;
- OmniAID;
- selected primary.

### B. Simple fusion baselines

- probability mean;
- logit mean;
- fixed validation-optimized weights;
- regularized logistic regression stacker.

These prevent us from crediting a complex router for gains available from ordinary calibration.

### C. Router feature ablations

1. expert logits only;
2. logits + confidence/entropy;
3. plus disagreement;
4. plus quality descriptors;
5. plus self-probe stability;
6. full feature set.

### D. Robustness-training ablations

- mean BCE only;
- exact transformation sampling;
- BCE + smooth worst-group term;
- BCE + consistency;
- BCE + worst-group + consistency.

### E. Calibration ablations

- raw score;
- temperature only;
- temperature + bias;
- reliability head plus abstention.

### F. Rescue ablations

- no WaRPAD;
- WaRPAD always on;
- WaRPAD on heuristic disagreement;
- WaRPAD on learned rescue gate;
- RIGID substitute if applicable.

### G. Optional third-expert ablation

- primary only;
- primary + LOTA;
- primary + WaRPAD;
- primary + LOTA + selective WaRPAD.

This demonstrates whether LOTA earns its slot rather than merely decorating the architecture.

## Illustrative result pattern - not data

The conversation used tables like the following to define what “good enough” could mean:

| Method | Clean | JPEG30 | Blur2 | Resize0.25 | Noise0.10 | Crop0.8 |
|---|---:|---:|---:|---:|---:|---:|
| Existing primary | 94 | 60 | 68 | 70 | 75 | 81 |
| LOTA | 96 | 52 | **96** | 72 | 80 | 85 |
| Static average | 95 | 61 | 88 | 75 | 81 | 86 |
| **Illustrative cascade** | **95** | **69** | **94** | **84** | **88** | **91** |

These are **ILLUSTRATIVE ONLY**. Their purpose is to show that JPEG 30 may remain unsolved while the overall project is compelling. Delete or replace this table before any public submission if there is any risk of confusion with real results.

## Statistical reporting

- Use 1,000+ source-level bootstrap replicates where runtime permits.
- Report 95% confidence intervals for headline deltas.
- For paired model comparisons, bootstrap the per-source metric difference.
- If training the router with multiple seeds, report mean and range/standard deviation for at least three seeds where feasible.
- Treat transformations of the same source as correlated.
- Do not claim a one-point gain is meaningful when uncertainty is larger.

## Calibration and selective evaluation

Reliability claims require more than a colored badge.

Report:

| Coverage | Selective error | Fake recall on accepted | FPR on accepted | Abstained fake share | Abstained real share |
|---:|---:|---:|---:|---:|---:|
| 100% | | | | | |
| 95% | | | | | |
| 90% | | | | | |
| 80% | | | | | |

A useful reliability estimator should make error fall as low-reliability cases are removed. Check this for clean and transformed subsets separately.

## Error-analysis taxonomy

For each model and transformation, sample representative cases from:

### False negatives - fake predicted real

- severe JPEG destruction;
- extreme resizing/low native resolution;
- photorealistic modern generators;
- low-texture or smooth content;
- images whose camera-like noise fools local experts;
- semantic/content domains absent from training;
- expert agreement on the wrong answer;
- stable-but-wrong self-probes.

### False positives - real predicted fake

- denoised or heavily edited photography;
- CGI/digital art not generated by modern AI;
- scanned/re-digitized images;
- screenshots, memes, or text-heavy images;
- unusually smooth backgrounds;
- strong sensor/compression artifacts;
- synthetic-looking subject matter;
- old/low-resolution images.

### Router errors

- trusted the wrong expert;
- ignored a useful LOTA correction;
- invoked rescue unnecessarily;
- rescue overturned a correct common result;
- predicted high reliability for a wrong answer;
- abstained on an easy case.

For each case show original/transformed pair, scores, weights, probe stability, quality features, rescue status, and final output. Do not present attention maps as causal explanations.

## Demo case-selection ethics

- Predefine case-selection rules or include both successes and failures.
- Do not cherry-pick only examples where the router behaves perfectly.
- Include at least one severe limitation, likely JPEG 30 or a modern-generator miss.
- Use assets with permission and avoid third-party marks in the public video.

## Acceptance gates

The final system should beat the strongest single detector on at least one of these primary outcomes without a material regression on the others:

- worst-transformation fake recall;
- maximum fake-to-real flip rate;
- worst balanced accuracy;
- selective risk at fixed coverage.

It must also keep clean balanced accuracy and FPR within predeclared tolerances. Suggested initial tolerances, subject to team decision:

- clean balanced-accuracy regression no worse than 1 percentage point;
- clean FPR increase no worse than 1 percentage point;
- headline robustness gain at least 2 points or clearly outside uncertainty.

These are internal kill thresholds, not organizer requirements.

