# TechJam Track 5 — LOTA Weights Update & Current Plan

> **Status:** CURRENT UPDATE  
> This supersedes only the earlier assumption that LOTA weights were inaccessible. All prior Track 5 research, architecture, training, evaluation, and risk documents remain valid.

## Important update

We now have the **LOTA pretrained weights**.

Therefore:
- LOTA is no longer blocked by Baidu Netdisk.
- Do not restart the project.
- Do not discard previous work.
- Treat only the earlier statement “LOTA weights are inaccessible” as outdated.
- LOTA returns to the main experimental path, but it still has to earn its final slot through results.

## Immediate priority

Before changing architecture, integrate and verify LOTA correctly.

Check:
- checkpoint loads without mismatch;
- repo/model variant matches the checkpoint;
- official preprocessing is reproduced;
- input size, RGB/value range, normalization, and patch/crop logic are correct;
- class ordering maps correctly to `P(AI-generated)`;
- sigmoid/softmax is applied exactly once;
- deterministic inference works;
- real/fake sanity samples give sensible outputs;
- latency and memory are measured.

Do not assume success just because the checkpoint loads.

## Run LOTA on the exact TechJam stress harness

Evaluate:

```text
Clean

JPEG: 90, 70, 50, 30
Gaussian Blur: sigma 0.5, 1.0, 2.0
Resize: 0.5x and 0.25x, then upscale
Gaussian Noise: sigma 0.02, 0.05, 0.10
Color: brightness/contrast/saturation +/-20%
Center Crop: 80%
```

LOTA’s paper did not test JPEG down to 70/50/30, so our own benchmark is essential.

## Compare LOTA directly with the current primary

At minimum compare:

```text
Community Forensics
vs
LOTA
```

Measure:
- clean balanced accuracy;
- fake recall;
- false-positive rate;
- JPEG30 fake recall;
- blur2 fake recall;
- resize0.25 fake recall;
- noise0.10 fake recall;
- crop0.8 fake recall;
- worst-transform fake recall;
- fake-to-real flip rate;
- latency.

Most importantly calculate:

```text
P(LOTA correct | Community wrong)
P(Community correct | LOTA wrong)
P(both wrong)
error correlation
```

Break these down by transformation family and severity.

LOTA stays only if it meaningfully corrects failures made by the primary.

## Current main architecture

```text
                         INPUT IMAGE
                              |
                 +------------+------------+
                 |                         |
                 v                         v
         PRIMARY EXPERT                   LOTA
      Community Forensics         local / low-bit evidence
      or GAPL if proven better
                 |                         |
                 +------------+------------+
                              |
                      RELIABILITY / FUSION
                           ROUTER
                              |
                  +-----------+-----------+
                  |                       |
               reliable                uncertain
                  |                       |
                  v                       v
               result                   WaRPAD
                                    behavioral rescue
                                          |
                                          v
                                     final fusion
                                          |
                                          v
                              REAL / AI / UNCERTAIN
                                      +
                                  reliability
```

Do **not** hard-code LOTA as “the blur expert.” Strong blur results are a hypothesis about where it may help, not a production rule.

## Status of GAPL and PGC

### GAPL
GAPL remains a **primary-detector challenger** to Community Forensics.

Do not delay LOTA evaluation to integrate GAPL.

Replace Community only if GAPL clearly improves:
- worst-transform fake recall;
- fake-to-real flip rate;
- FPR;
- overall robustness;
- while staying practical in latency/setup.

### PGC
PGC was promoted mainly because LOTA had become inaccessible.

Now PGC becomes an **optional challenger**, not a required replacement.

Do not automatically build:

```text
Community + LOTA + PGC + WaRPAD
```

Every extra expert must earn its slot.

## DegradePrint remains alive

DegradePrint stays as the **parallel high-upside innovation experiment**, not the guaranteed main architecture.

Hypothesis:

> Real and AI-generated images may exhibit different response signatures when the same frozen detector is subjected to small controlled transformations.

Using the selected primary backbone, generate mild views:

```text
original
mild JPEG
mild blur
mild resize
mild crop
```

Extract:

```text
base logit
probe logits
delta logits
score variance
max score change
prediction flips
cosine embedding drift
L2 embedding drift
```

First test it with simple logistic regression:

```text
primary score only
vs
primary score + DegradePrint response features
```

If it does not materially improve held-out robustness, kill it.

If it helps, feed those features into the main reliability router.

## Potential best final hybrid

Only if experiments support every component:

```text
                    PRIMARY BACKBONE
                   Community / GAPL
                          |
              +-----------+-----------+
              |                       |
              v                       v
         primary score          DegradePrint
                              response signature
              |                       |
              +-----------+-----------+
                          |
                         LOTA
                 local forensic evidence
                          |
                          v
                 RELIABILITY ROUTER
                          |
               +----------+----------+
               |                     |
            reliable              uncertain
               |                     |
               v                     v
            result                 WaRPAD
                                      |
                                      v
                                 final result
```

Do not commit to this hybrid before ablations.

## Mandatory baselines before a fancy router

Evaluate:

```text
Community alone
LOTA alone
probability mean
logit mean
fixed weighted average
logistic regression stacking
```

Only then compare against the learned router.

If the MLP router does not beat logistic stacking meaningfully, use the simpler model.

## Training strategy

Keep large experts frozen first.

Train only:

```text
fusion/router
reliability head
rescue fusion
calibration
```

Track class × transformation groups:

```text
real-clean / fake-clean
real-JPEG / fake-JPEG
real-blur / fake-blur
real-resize / fake-resize
real-noise / fake-noise
real-color / fake-color
real-crop / fake-crop
```

Use:

```text
BCE
+
smooth worst-group emphasis
```

Prediction consistency remains optional.

## Main success criteria

Do **not** define success as solving every transform perfectly.

The objective is:

> Materially reduce transformation-induced fake-to-real failures compared with the strongest single detector while keeping false positives acceptable.

Recommended headline metric:

```text
Worst-Transformation Fake Recall
at a controlled real-image FPR
```

Also report:
- balanced accuracy;
- fake recall;
- FPR;
- fake-to-real flip rate;
- clean-to-transformed drop;
- worst balanced accuracy;
- calibration;
- latency;
- rescue invocation rate.

JPEG30 can remain the hardest limitation and the project can still be strong.

## LOTA kill criteria

Even with the weights available, remove LOTA if:
- it rarely corrects primary failures;
- its errors are highly correlated with the primary;
- it harms worst-transform fake recall;
- severe JPEG creates harmful confident errors the router cannot suppress;
- it materially increases FPR;
- preprocessing/inference is unreliable;
- gains disappear on held-out generators/sources.

Useful internal decision rule: LOTA should either
- correct a meaningful share of primary failures, roughly 15%+ overall or especially strongly in an important transformation family; or
- provide a clear robustness gain of roughly 2+ points.

These are internal gates, not organizer requirements.

## Current priority order

```text
1. Keep existing primary + TechJam evaluation harness working
2. Integrate and validate LOTA
3. Run LOTA on the exact stress grid
4. Measure Community–LOTA complementarity
5. Build simple fusion baselines
6. Build reliability router
7. Add calibration
8. Add selective WaRPAD rescue
9. Test DegradePrint cheaply
10. Test GAPL / PGC only if they can improve measured weaknesses
```

## Guiding principle

> **Architecture follows evidence, not attachment to a paper or an earlier diagram.**

The fact that LOTA weights are now available is good news, but it does not automatically make LOTA part of the final submission. Measure first, then decide.
