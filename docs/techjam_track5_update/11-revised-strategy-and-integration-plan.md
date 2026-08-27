# Revised Track 5 Strategy After the LOTA Blocker

> **Status:** CURRENT RECOMMENDATION  
> **Purpose:** This file tells the existing planning/build agent how to integrate the new discoveries into the already-developed Track 5 project without throwing away previous work.

## 1. Executive decision

The LOTA checkpoint access failure should **not** trigger a project reset.

The best current strategy is:

### Main / safe system — Adaptive Forensic Cascade

```text
strong primary detector
    +
accessible complementary forensic expert
    ->
small reliability / fusion layer
    ->
selective behavioral rescue
    ->
calibrated AI / REAL / UNCERTAIN output
```

Current candidates:

```text
Primary:
Community Forensics OR GAPL

Complementary local expert:
PGC

Behavioral rescue:
WaRPAD

Optional experimental specialist:
self-trained LOTA, only if reproduction is quick and useful
```

### Parallel innovation experiment — DegradePrint

```text
one frozen primary detector
    +
mild diagnostic views
    +
stable-evidence features
    +
transformation-response signature
    ->
small fusion/reliability head
```

Do not immediately replace the main cascade with DegradePrint.

Use the cascade as the guaranteed competition path. Test DegradePrint cheaply in parallel.

## 2. Which option is preferred now?

If forced to choose one path today:

> **Choose the revised Adaptive Forensic Cascade.**

Why:

- highest probability of measurable gains in seven days;
- multiple fallbacks;
- accessible pretrained components;
- easy to ablate;
- easier to debug;
- strong engineering story;
- allows simplification when a component fails.

DegradePrint has a higher novelty ceiling but greater experimental risk.

## 3. Strategy ranking

### 1. Revised Adaptive Forensic Cascade — safest strong option

Approximate strategic rating: **9/10**.

### 2. Hybrid Cascade + DegradePrint — potentially the best final architecture

This is the ideal destination **if experiments support it**.

### 3. Pure DegradePrint — higher novelty, higher uncertainty

Approximate strategic rating: **7/10**.

### 4. Single public detector + augmentation

Safe but weak innovation.

### 5. Reproduce LOTA and preserve the exact old architecture

Lowest priority. Do not let inaccessible weights dictate the project.

## 4. Why the cascade is safer

The cascade has graceful project-level degradation.

If the router fails:

```text
primary + calibrated stacking
```

still works.

If PGC fails:

```text
primary + WaRPAD
```

still works.

If WaRPAD is too slow:

```text
primary + PGC
```

still works.

If GAPL is difficult to integrate:

```text
Community Forensics
```

still works.

This makes it extremely suitable for a seven-day hackathon.

## 5. Why DegradePrint still deserves effort

Its hypothesis is cleaner and more obviously ours:

> The way a detector's logits and embeddings move under small controlled transformations may itself distinguish authentic and AI-generated images.

The first test is cheap:

```text
base score only
vs
base score + response features
```

using logistic regression.

If there is no gain, kill it.

If there is a real gain, integrate it into the main router.

This gives us high upside without jeopardizing the safe path.

## 6. Potential final hybrid

If all useful components earn their place, the final architecture could be:

```text
                                INPUT
                                  |
                                  v
                         PRIMARY BACKBONE
                      Community OR GAPL
                                  |
                 +----------------+----------------+
                 |                                 |
                 v                                 v
          primary global score            DegradePrint probes
                                                   |
                                          response signature
                                                   |
                 +----------------+----------------+
                                  |
                                  v
                                PGC
                         local peak evidence
                                  |
                 +----------------+----------------+
                                  |
                           RELIABILITY ROUTER
                                  |
                       +----------+----------+
                       |                     |
                    reliable              uncertain
                       |                     |
                       v                     v
                    result                WaRPAD
                                             |
                                             v
                                        final fusion
                                             |
                                             v
                              REAL / AI / UNCERTAIN
                                     + reliability
```

Do **not** build every branch automatically. Every branch must be justified by ablation.

## 7. What is reused versus ours in the hybrid

### Reused

- Community Forensics or GAPL weights;
- PGC weights;
- WaRPAD implementation/backbone.

### Built by us

- exact Track 5 transformation engine;
- unified expert adapters;
- DegradePrint diagnostic views;
- transformation-response features;
- reliability/fusion router;
- smooth worst-group training;
- calibration;
- abstention policy;
- selective WaRPAD trigger;
- complementarity analysis;
- fake-to-real flip analysis;
- reproducible stress benchmark;
- demo visualizations.

This is enough original system work for a strong hackathon story.

## 8. Updated implementation sequence

### Phase 0 — preserve the working baseline

Keep all existing working infrastructure:

- Community Forensics baseline;
- exact Track 5 transform harness;
- metrics/evaluation;
- Gradio/UI scaffold;
- any existing adapter interfaces;
- LOTA code already written, but mark weights as unavailable.

Exit criterion:

```text
image
 -> primary detector
 -> result
 -> stress test
```

still works.

### Phase 1 — primary shootout

Benchmark:

```text
Community Forensics
GAPL
```

using one fixed evaluation subset and the same preprocessing/evaluation protocol.

Compare:

- clean balanced accuracy;
- fake recall;
- FPR;
- JPEG30;
- blur2;
- resize0.25;
- noise0.10;
- crop0.8;
- worst-transform fake recall;
- fake-to-real flips;
- latency.

Choose the winner as production primary.

If GAPL setup consumes too much time, keep Community.

### Phase 2 — complementary-expert replacement

Benchmark PGC.

Measure:

```text
P(PGC correct | primary wrong)
```

by transformation family and class.

If complementarity is weak, drop PGC.

### Phase 3 — simple fusion baselines

Before a neural router, implement:

```text
probability mean
logit mean
fixed validation-optimized weights
regularized logistic regression stacker
```

The router must beat these to justify itself.

### Phase 4 — reliability router

Candidate features:

```text
primary logit
PGC logit
entropy/confidence
absolute disagreement
quality descriptors
mild primary self-probe stability
```

Outputs:

```text
fusion weights
reliability
rescue probability
```

Use the smallest model that works.

### Phase 5 — cheap DegradePrint hypothesis test

Using the selected primary backbone, generate:

```text
original
mild JPEG
mild blur
mild resize
mild crop
```

Extract:

```text
base/probe logits
delta logits
score variance
max score delta
embedding cosine drift
embedding L2 drift
quality descriptors
```

Train regularized logistic regression.

Compare:

```text
primary score only
vs
primary + DegradePrint response features
```

Kill the idea if there is no meaningful robustness gain.

### Phase 6 — behavioral rescue

Integrate WaRPAD only after the common path is stable.

Trigger using validated low reliability / disagreement / instability.

Measure:

```text
rescue invocation rate
rescue correction rate
rescue harm rate
common-path latency
rescued latency
```

If most inputs invoke WaRPAD, the adaptive-compute story has failed.

### Phase 7 — robust training

Track class x transformation groups:

```text
real-clean / fake-clean
real-JPEG / fake-JPEG
real-blur / fake-blur
real-resize / fake-resize
real-noise / fake-noise
real-color / fake-color
real-crop / fake-crop
```

Start with:

```text
BCE + smooth worst-group penalty
```

Prediction consistency remains optional and must earn itself.

### Phase 8 — calibration and abstention

Separate:

```text
class probability
```

from:

```text
reliability
```

Possible final decisions:

```text
AI-GENERATED
REAL
UNCERTAIN
```

This is especially useful under severe JPEG or other out-of-reliable-region inputs.

## 9. Updated success definition

Do **not** define success as solving every corruption perfectly.

A strong result could be:

```text
baseline worst fake recall 58%
final system               68%
```

or:

```text
baseline fake->real flip 22%
final system             10%
```

while clean FPR remains acceptable.

JPEG30 can remain the hardest known limitation if the system still materially improves it or correctly lowers reliability.

## 10. Recommended headline metric

Lead with:

> **Worst-Transformation Fake Recall at a controlled real-image FPR**

Also report:

- fake-to-real flip rate;
- worst balanced accuracy;
- clean-to-transform drop;
- selective risk / coverage;
- clean FPR.

## 11. What not to do

Do not:

- continue hunting Baidu mirrors;
- trust unofficial checkpoints;
- redesign everything around reproducing LOTA;
- hard-code “blur expert” / “JPEG expert” rules;
- run every heavy model on every image before measuring need;
- fine-tune all backbones simultaneously;
- merge DegradePrint before its cheap test proves signal;
- keep PGC just because it is a newer paper;
- delete the working baseline.

## 12. New LOTA status

LOTA is now:

```text
OPTIONAL EXPERIMENT
```

not:

```text
REQUIRED EXPERT
```

If reproduction works quickly, benchmark it and keep it only if it adds unique corrections.

## 13. Decision gates

### Primary

Choose GAPL over Community only if local measurements show a clear advantage and integration remains practical.

### PGC

Keep only if it materially repairs primary failures or improves the headline robustness metric.

### DegradePrint

Keep only if response features add measurable held-out signal beyond the primary score.

### Router

Use logistic stacking if the MLP does not meaningfully beat it.

### WaRPAD

Keep only if selective rescue improves robustness at an acceptable rescue rate and latency.

### LOTA reproduction

Kill if it becomes a time sink.

## 14. Judge explanation if the hybrid succeeds

> Strong AI-image detectors often fail after redistribution because the forensic evidence they rely on changes under compression, blur, resizing, and cropping. Our system combines strong global detection with localized forensic evidence, explicitly measures how the image's representation responds to controlled transformations, estimates whether the available evidence remains trustworthy, and invokes a heavier behavioral detector only when necessary. We optimize the small fusion layer against the worst class-transformation failures rather than average clean accuracy.

This is stronger than saying:

> We ensembled several open-source detectors.

## 15. If DegradePrint fails

Do not hide it. The project can still finish as:

```text
Community/GAPL
+
PGC
+
reliability router
+
selective WaRPAD
```

That remains a strong hackathon architecture.

## 16. If PGC also fails

Simplify to:

```text
primary detector
+
DegradePrint response signature
+
WaRPAD rescue
```

or:

```text
primary detector
+
self-probed reliability
+
WaRPAD rescue
```

Always collapse gracefully to the strongest measured simpler system.

## 17. Recommended effort allocation

Approximate:

```text
80% effort -> guaranteed cascade path
20% effort -> DegradePrint hypothesis test
```

AI-assisted coding makes this parallel experiment practical, but it must never jeopardize the working baseline.

## 18. Official TechJam alignment

Track 5 asks for a prototype that distinguishes AI-generated from authentic images and remains robust under realistic transformations including JPEG, blur, resize, noise, color changes, and crop. It allows public/properly licensed models and data, requires models below 2B parameters, assumes limited compute, and emphasizes technical approach, evaluation, generalisation, false positives, robustness summaries, and error analysis.

It does **not** require:

- training from scratch;
- solving every listed transformation perfectly;
- using LOTA;
- using a particular model family;
- achieving a minimum JPEG30 score;
- always returning a forced binary answer.

Therefore the evidence-driven revised strategy is fully aligned with the competition.

## 19. Instruction to the existing planning/build agent

Use this as the operational handoff:

> **Do not restart the project. Treat the LOTA checkpoint issue as a model-slot dependency failure, not an architectural failure. Preserve the existing baseline and evaluation harness. Continue with Community Forensics while benchmarking GAPL as primary challenger and PGC as accessible complementary expert. Keep WaRPAD as selective behavioral rescue. In parallel, implement the smallest possible DegradePrint experiment using the same frozen primary backbone: cache original/probe logits and embedding drifts, train a logistic classifier on response features, and kill the idea if it does not materially improve held-out worst-transform fake recall or fake-to-real flips. If it does improve them, integrate the response signature into the existing reliability router. Every new component must earn its slot through ablation.**
