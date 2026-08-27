# Alternative Track 5 Solution: DegradePrint — Transformation-Response Forensics

> **Status:** NEW ALTERNATIVE SOLUTION / HIGH-UPSIDE EXPERIMENT  
> **Relationship to previous plan:** DegradePrint is **not merely a renamed component of the Adaptive Forensic Cascade**. It is a separate architecture/hypothesis that can be built and benchmarked using the same data, transformation harness, metrics, UI, and frozen primary detector.

Recommended framing:

- Adaptive Forensic Cascade = **Solution A / safe primary path**.
- DegradePrint = **Solution B / higher-novelty experimental path**.
- If DegradePrint provides complementary signal but is weaker alone, merge its response signature into the cascade router.

## 1. Motivation

The previous solution asks:

> Can multiple heterogeneous detectors compensate for each other's failures under real-world transformations?

DegradePrint asks:

> Can AI-generated images be detected partly from **how a strong detector's evidence changes under small controlled transformations**?

Instead of requiring several independent pretrained experts, DegradePrint can operate around **one strong frozen backbone**.

This reduces external checkpoint dependency and increases the amount of the final system that is clearly ours.

## 2. Core hypothesis

Suppose a frozen detector gives two images the same original AI score:

```text
Image A original = 0.91
Image B original = 0.91
```

Now create mild diagnostic views.

Image A:

```text
original   0.91
JPEG90     0.89
blur0.5    0.87
resize     0.88
small crop 0.90
```

Image B:

```text
original   0.91
JPEG90     0.62
blur0.5    0.48
resize     0.59
small crop 0.83
```

The initial confidence is identical, but the **trajectory of the forensic evidence under transformation** differs strongly.

DegradePrint treats this trajectory itself as useful evidence.

## 3. Why this is plausible

Existing research already supports the broader idea that perturbation response contains forensic information:

- RIGID: representation stability under small perturbations;
- WaRPAD: perturbation/crop robustness behavior;
- RA-Det: robustness asymmetry;
- DACOM: distortion-aware detector confidence / reliable-region estimation.

DegradePrint therefore does **not** claim to invent perturbation-based forensics in general.

The narrower proposed contribution is:

> Build an explicit **multi-transformation response signature** aligned with the real-world redistribution families in TechJam, and combine it with stable evidence that survives those transformations.

## 4. Main architecture

```text
                               INPUT IMAGE x
                                      |
                                      v

                         DIAGNOSTIC VIEW GENERATOR
                                      |
             +------------+-----------+-----------+------------+
             |            |           |           |            |
             v            v           v           v            v
          original     mild JPEG    mild blur   mild resize  mild crop
             |            |           |           |            |
             +------------+-----------+-----------+------------+
                                      |
                                      v

                             SAME FROZEN BACKBONE
                         Community OR GAPL winner
                                      |
                            embeddings + logits
                                      |
                +---------------------+---------------------+
                |                                           |
                v                                           v

        STABLE-EVIDENCE BRANCH                   RESPONSE-SIGNATURE BRANCH
                |                                           |
      asks "what survives?"                       asks "how did it change?"
                |                                           |
      robust pooled embeddings                         delta logits
      or stable projected feature                   cosine embedding drift
                                                     L2 feature distance
                                                     score variance
                                                     max score delta
                                                     flip indicators
                                                     quality descriptors
                |                                           |
                +---------------------+---------------------+
                                      |
                                      v
                               OUR FUSION HEAD
                                      |
                          +-----------+-----------+
                          |                       |
                          v                       v
                   fake probability           reliability
                          |                       |
                          +-----------+-----------+
                                      |
                                      v
                             REAL / AI / UNCERTAIN
```

## 5. Stable-evidence branch

For diagnostic transforms `T_i`, the frozen backbone produces:

```text
h_i = f(T_i(x))
```

The stable branch attempts to capture evidence that remains useful across mild changes.

Start simple:

```text
mean pooled embedding
or
small learned projection + pooling
```

Do not immediately build a transformer/attention network around these views.

The question is simply:

> Which evidence survives redistribution-like perturbations?

## 6. Response-signature branch

The response branch intentionally models changes.

Candidate features:

```text
base logit
probe logits
per-probe delta logits
mean delta
score std / variance
max absolute delta
score range
number of threshold flips

cosine(base_embedding, probe_embedding)
1 - cosine similarity
L2 embedding drift
normalized embedding drift
relative drift across probe families

image width/height
blur proxy
JPEG/blockiness proxy
contrast
luminance
noise proxy
```

Conceptually:

```text
response_signature(x)
=
[
  delta_JPEG,
  delta_blur,
  delta_resize,
  delta_crop,
  embedding_drift_JPEG,
  embedding_drift_blur,
  ...
]
```

Important:

> The response branch is **not** supposed to be invariant. The movement itself is the signal.

## 7. Critical training insight: outer corruption + inner probes

A naive version would learn response behavior only from clean source images. That is insufficient because an actual TikTok input may already be severely processed.

### Outer corruption

First sample a received-view corruption:

```text
x_b = C(x)
```

where `C` comes from the official Track 5 families:

```text
clean
JPEG 90/70/50/30
blur 0.5/1/2
resize 0.5/0.25
noise 0.02/0.05/0.10
color +/-20%
crop 0.8
```

This represents the image as received by the platform.

### Inner probes

Then apply small diagnostic probes to that already-corrupted image:

```text
P1(x_b)
P2(x_b)
P3(x_b)
```

Example:

```text
source
  |
  v
outer corruption: JPEG30
  |
  v
received image
  |
  +-> tiny JPEG probe
  +-> mild blur probe
  +-> mild resize probe
  +-> tiny crop probe
```

This avoids learning only pristine-image response signatures.

## 8. Suggested diagnostic probes

Do **not** run the full TechJam grid at inference time.

Start with mild, cheap probes such as:

```text
original
JPEG quality ~90-92
Gaussian blur sigma ~0.3-0.5
resize to ~0.9 then restore
center crop retaining ~95-98%
```

Probe selection should be ablated. The goal is diagnostic signal, not brute-force test-time augmentation.

## 9. Frozen backbone choice

Use one strong accessible primary detector:

```text
Community Forensics 384
or
GAPL
```

Benchmark both.

Select based on:

- baseline fake recall;
- severe corruption robustness;
- availability of useful embeddings;
- inference cost;
- implementation reliability.

DegradePrint should not depend on one specific backbone.

## 10. What is reused versus ours

### Reused

- Community Forensics or GAPL weights;
- official preprocessing.

### Ours

- diagnostic view generator;
- logit/embedding extraction;
- stable-evidence pooling/projection;
- transformation-response signature;
- response classifier/head;
- fusion head;
- reliability head;
- outer-corruption training protocol;
- exact Track 5 stress evaluation;
- response-profile visualization;
- calibration and abstention logic.

This creates a cleaner ownership story than a pure ensemble.

## 11. First experiment should be tiny

Do not start with neural heads.

First test whether the idea has signal.

Procedure:

1. Freeze the primary detector.
2. Generate diagnostic views.
3. Cache base/probe logits, embedding drift, and quality features.
4. Train regularized logistic regression.
5. Compare:

```text
PRIMARY SCORE ONLY
vs
PRIMARY + DEGRADEPRINT RESPONSE FEATURES
```

If response features do not improve held-out robustness, kill DegradePrint immediately.

## 12. Kill criterion

Keep DegradePrint only if it produces at least one meaningful held-out gain, such as:

- ~2+ points improvement in worst-transform fake recall; or
- clear reduction in fake-to-real flip rate; or
- meaningful calibration/selective-risk improvement;

without unacceptable clean FPR or clean balanced-accuracy regression.

If the simple classifier cannot show signal, do not invest in complex heads.

## 13. If the hypothesis works

Upgrade carefully:

```text
stable pooled embedding
    +
response-feature MLP
    ->
small fusion network
```

Possible loss:

```text
L_total = L_BCE + lambda_w * L_worst + lambda_s * L_stable
```

Where:

- `L_BCE` is the main class loss;
- `L_worst` emphasizes the worst class x transform groups;
- `L_stable` acts only on the stable-evidence branch.

Do **not** force the response branch to become invariant.

## 14. Optional WaRPAD rescue

DegradePrint can stand alone, but low-reliability cases can optionally invoke WaRPAD:

```text
                              IMAGE
                                |
                                v
                           DEGRADEPRINT
              +----------------+----------------+
              |                                 |
       stable evidence                 response signature
              |                                 |
              +----------------+----------------+
                               |
                          fusion/reliability
                               |
                    +----------+----------+
                    |                     |
                 reliable              uncertain
                    |                     |
                    v                     v
                 result                 WaRPAD
                                           |
                                           v
                                      final fusion
```

This preserves adaptive compute.

## 15. Why DegradePrint fits TechJam well

Track 5 emphasizes robustness under compression, blur, resizing, noise, color changes, and crop.

DegradePrint makes those transformations part of the **inference/training representation**, rather than treating them only as evaluation nuisances.

It therefore has a strong problem-insight story:

> Model both the forensic evidence that survives redistribution and the way forensic evidence responds to redistribution.

## 16. Demo concept

Example UI:

```text
AI-GENERATED
91%

Reliability: HIGH

DEGRADATION RESPONSE PROFILE
Original        0.91
Mild JPEG       0.89
Mild blur       0.87
Mild resize     0.88
Mild crop       0.90

Stable evidence: high
Response signature: AI-like
```

Difficult case:

```text
UNCERTAIN
AI leaning: 0.61
Reliability: LOW

Primary forensic evidence becomes unstable
under mild encoding / resize probes.
```

Then expose a separate button:

```text
Run Full TechJam Stress Test
```

and compare baseline vs final system across the official grid.

## 17. Rubric fit

### Technical Execution — 35%

- deterministic transform engine;
- frozen strong backbone;
- multi-view extraction;
- cached features;
- small trainable heads;
- calibration;
- ablations;
- end-to-end demo.

### Innovation & Problem Insight — 20%

- explicit transformation-response fingerprint;
- stable evidence + response evidence separation.

### Impact & Relevance — 20%

- reliability and abstention rather than unsafe overconfidence.

### Feasibility & Practicality — 15%

- one main detector;
- small heads;
- limited training cost;
- fewer checkpoint dependencies.

### Presentation — 10%

- response profile is visual and easy to explain.

## 18. Risks

The biggest risk is scientific:

> The response features may not add enough information beyond the primary score.

Other risks:

- response features may mostly encode severity rather than authenticity;
- probe overhead may hurt latency;
- stable branch may wash out discriminative information;
- source/dataset shortcuts may enter the response model;
- stable-but-wrong predictions remain possible.

These risks are why the cheap logistic-regression test comes first.

## 19. Relationship to the current cascade

DegradePrint starts as **Solution B**, not as part of the cascade.

If it works, its response signature can be fed into the cascade router:

```text
primary score
PGC score
expert disagreement
quality features
DegradePrint response signature
        |
        v
 reliability router
        |
   +----+----+
   |         |
return     WaRPAD
```

This hybrid may ultimately be stronger than either solution independently.

## 20. Bottom line

DegradePrint is a **high-upside, Track-5-specific research experiment with a cheap first validation step**.

It is not currently the safest default architecture.

The safest default remains the revised Adaptive Forensic Cascade.

If DegradePrint response features produce real held-out robustness gains, they may become the central innovation of the final submission.
