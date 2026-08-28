# TechJam Track 5 — Innovation Add-On Plan: Forensic Evidence Survival Audit

> **Status:** Current strategic recommendation  
> **Goal:** Keep the validated degradation-aware detection system intact, but add one bounded, high-upside innovation experiment that improves the Innovation & Problem Insight story without risking the working classifier.

## 1. Current strategic position

The current core system is already real and defensible:

```text
Base detector (Community Forensics)
        +
cheap degradation / quality descriptors
        +
small learned correction head
        +
worst-group training
        +
reliability / deferral
```

The base detector collapses under hard transformations, especially noise, while the learned correction layer dramatically improves worst-case fake recall.

Even an oracle threshold fitted on the test set cannot reproduce the full gain, so the improvement is not just threshold tuning.

The failed extras so far were:

```text
LOTA rescue          -> rejected
PGC rescue           -> rejected
self-probe features  -> approximately zero contribution
```

Those failures reveal an important insight:

> Heavy JPEG and noise destroy the fine-grained/high-frequency forensic evidence that many detectors rely on. Adding more passive forensic sensors that depend on the same evidence may not rescue the hard cases.

That should become part of the innovation narrative.

## 2. Why speed alone should not be the innovation headline

If removing the three self-probes preserves performance on a fresh holdout, the system may become roughly 6× faster.

That is excellent for feasibility.

But:

> **“We made it faster” is not enough to carry the Innovation & Problem Insight score by itself.**

The working classifier remains the core technical contribution, but we should explore one additional capability that is orthogonal to raw accuracy and speed.

## 3. Recommended experiment: Forensic Evidence Survival Audit

The strongest bounded experiment is:

# **Forensic Evidence Survival Audit**

Question:

> **Where is the detector's forensic evidence coming from, how concentrated or distributed is it, and does that evidence survive realistic redistribution?**

This is not another detector.

It is an optional forensic analysis layer.

Conceptual architecture:

```text
                         IMAGE
                           |
                           v
                  CURRENT DETECTOR
                           |
                     AI probability
                           |
          +----------------+----------------+
          |                                 |
          v                                 v
 DEGRADATION-AWARE                  EVIDENCE AUDIT
    CORRECTION                              |
          |                          patch evidence map
          |                                 |
          |                          evidence coverage
          |                                 |
          |                          evidence survival
          |                          under degradation
          |                                 |
          +----------------+----------------+
                           |
                           v
                    FORENSIC REPORT
```

The normal classifier remains unchanged.

The audit is optional.

## 4. Core idea

Most AI-image detectors return:

```text
AI-generated: 87%
```

That does not tell us:

- what regions caused the prediction;
- whether evidence is spread across the image or concentrated in one tiny patch;
- whether the evidence survives JPEG;
- whether noise destroys the signal;
- whether the detector relies on a fragile cue.

The audit should answer those questions.

Example:

```text
Verdict: AI-generated
Probability: 87%
Reliability: MEDIUM

Current degradation:
heavy compression / moderate noise

Evidence coverage:
71%

Evidence concentration:
distributed

Evidence survival:
JPEG: HIGH
Resize: HIGH
Blur: MEDIUM
Noise: LOW

Recommendation:
DECIDE / DEFER
```

## 5. Patch-level evidence map

A simple implementation does not require retraining the base detector.

Divide the image into a coarse grid, for example:

```text
4 x 4
```

For each patch:

1. perturb, mask, blur, or replace the patch;
2. re-run the detector;
3. measure how much the AI score changes.

Conceptually:

```text
importance_i = score(original) - score(image with patch i perturbed)
```

This creates a patch evidence map:

```text
patch 1  -> importance
patch 2  -> importance
...
patch 16 -> importance
```

Visualize it as a heatmap.

The heatmap alone is not the innovation. The Track-5-specific extension is to measure **evidence survival under redistribution**.

## 6. Evidence Coverage Score

We want to know whether the decision depends on:

```text
one tiny fragile region
```

or:

```text
evidence distributed across much of the image
```

Possible metrics:

```text
fraction of patches needed to explain X% of importance
entropy of patch-importance distribution
Gini / concentration score
top-k evidence fraction
effective number of contributing patches
```

Example:

```text
Image A
top 1 patch = 82% of evidence
-> highly concentrated / fragile

Image B
top 8 patches = 80% of evidence
-> distributed evidence
```

Possible report:

```text
Evidence Coverage: LOW
or
Evidence Coverage: HIGH
```

## 7. Evidence Survival under degradation

Take the original evidence map:

```text
E_original
```

Then apply selected real-world transformations:

```text
JPEG
noise
resize
blur
```

and recompute:

```text
E_JPEG
E_noise
E_resize
E_blur
```

Calculate how much the evidence survives.

Possible measures:

```text
map correlation
cosine similarity
rank correlation
fraction of top evidence patches preserved
relative total importance retained
coverage change
```

This creates a:

# **Forensic Survival Profile**

Example:

```text
Original evidence coverage: 0.78

After JPEG:
0.74

After resize:
0.76

After blur:
0.66

After noise:
0.31
```

Interpretation:

> The detector's forensic evidence remains stable under JPEG and resizing but largely disappears after noise.

This directly matches the Track 5 problem.

## 8. Most important validation experiment

Do **not** build a polished UI first.

First ask whether the audit contains useful signal.

On **development data only**, compare:

```text
correct predictions
vs
wrong predictions
```

for:

```text
evidence coverage
evidence concentration
evidence survival
```

Especially inspect:

```text
high-confidence correct
high-confidence wrong
low-confidence correct
low-confidence wrong
```

An excellent result would be something like:

```text
Correct predictions:
mean evidence survival = 0.78

Incorrect predictions:
mean evidence survival = 0.39
```

or:

```text
confidently wrong predictions
show significantly more concentrated / fragile evidence
```

That would be valuable because the current reliability head has a known weakness:

> Some of the system's worst mistakes can still be confidently wrong.

If evidence survival catches some of those cases, it becomes a genuinely useful new capability.

## 9. Kill criteria

This experiment must stay bounded.

Keep it only if at least one is true on development data:

```text
1. Evidence survival clearly separates correct vs incorrect predictions.

2. Evidence concentration identifies a subset of confidently wrong cases.

3. Evidence coverage/survival adds useful signal beyond the existing reliability score.

4. The visualization reveals a stable, interpretable failure pattern useful for the demo and error analysis.
```

Kill it quickly if:

```text
correct and incorrect predictions look the same;
the maps are unstable/noisy;
the metric is dominated by trivial image content;
it requires major retraining;
it consumes too much time;
it adds no explanation beyond the existing reliability head.
```

Do not force it into the classifier just because it looks interesting.

## 10. Optional per-image robustness certificate

A second, lower-risk feature can reuse the existing transformation engine.

Instead of only:

```text
AI = 87%
```

offer an optional:

# **Forensic Robustness Certificate**

Example:

```text
FORENSIC ROBUSTNESS CERTIFICATE

Verdict:
AI-generated

Stable under:
✓ JPEG 90
✓ JPEG 70
✓ blur 0.5
✓ resize 0.5
✓ crop 0.8

Unstable under:
⚠ JPEG 30
⚠ noise 0.10

Verdict retention:
16 / 20 stress conditions

Worst-case AI probability:
58%

Forensic reliability:
MEDIUM
```

The idea:

> We do not only return a prediction. We audit whether that prediction survives the same redistribution conditions it may encounter in the real world.

This should be an optional audit button rather than part of normal inference.

## 11. Normal mode vs Audit mode

### Normal mode

```text
Image
  -> base detector
  -> degradation-aware correction
  -> reliability
  -> REAL / AI / DEFER
```

Goal:

```text
fast
deployable
simple
```

### Audit mode

Triggered only for deeper forensic analysis:

```text
Image
  -> evidence map
  -> evidence coverage
  -> evidence survival profile
  -> robustness certificate
  -> forensic report
```

This keeps the normal product fast while giving the demo a richer innovation layer.

## 12. Recommended final product structure

Possible positioning:

# **ForensicAdapter + Forensic Audit**

```text
                         IMAGE
                           |
                           v
                  BASE AI DETECTOR
                           |
                           v
              DEGRADATION-AWARE ADAPTER
                           |
                  robust AI probability
                           |
                           v
                    RELIABILITY HEAD
                           |
                    REAL / AI / DEFER


                   OPTIONAL AUDIT MODE
                           |
          +----------------+----------------+
          |                |                |
          v                v                v

     degradation       evidence map      robustness
       profile           + coverage       certificate

          +----------------+----------------+
                           |
                           v
                    FORENSIC REPORT
```

## 13. What is actually ours

### Reused

```text
Community Forensics CF-384
```

### Ours

```text
degradation / quality measurement pipeline
small learned correction head
worst-group training objective
reliability / deferral head
evaluation protocol
quality shortcut controls
duplicate handling
error analysis
optional evidence-survival audit
optional robustness certificate
```

The message:

> The base detector supplies forensic evidence. Our system determines how much that evidence can be trusted after redistribution and adapts the decision accordingly.

## 14. Innovation story

Do **not** present the story as:

```text
we tried lots of models and most failed
```

Present the progression:

```text
1. Strong detector performs well on clean images.

2. Real-world transformations cause severe fake-to-real collapse.

3. We first tried adding more forensic evidence.

4. LOTA failed.
5. PGC failed.
6. Self-probing added almost no classification value.

7. We analyzed why.

8. Hard cases, especially JPEG and noise,
   destroy the fine-grained evidence those approaches rely on.

9. Key insight:
   don't ask another detector for the same destroyed evidence.

10. Instead, directly measure degradation
    and adapt the detector's decision boundary.

11. Then audit whether the remaining evidence is
    spatially distributed and survives redistribution.
```

This is a strong **problem-insight** narrative.

## 15. Suggested judge-facing claim

> **Our system does not attempt to recover forensic traces that redistribution has already destroyed. Instead, it estimates the degradation state of the incoming image, adapts the detector's decision boundary to that state, and optionally audits where the remaining forensic evidence comes from and whether it survives realistic redistribution.**

## 16. Suggested innovation statement

Avoid overclaiming.

Do not say:

```text
"We invented explainable AI-image detection."
"We invented robustness auditing."
"We invented quality-aware correction."
```

Say:

> **Our Track-5-specific contribution is a lightweight degradation-aware forensic adapter paired with an optional evidence-survival audit. The adapter corrects a frozen detector using direct measurements of degradation, while the audit tests whether the detector's spatial forensic evidence remains distributed and stable under realistic redistribution.**

## 17. Why this is stronger than another detector

Another detector adds:

```text
more latency
more memory
more integration risk
more licensing/reproducibility risk
high chance of correlated failure
weak originality if it becomes an ensemble
```

The project has already shown this with LOTA and PGC.

The proposed audit adds a new **type of capability**:

```text
prediction
+
trust / evidence analysis
```

rather than:

```text
prediction
+
another prediction
```

That is more useful for innovation and presentation.

## 18. Other ideas considered

| Addition | Innovation potential | Risk | Recommendation |
|---|---:|---:|---|
| Evidence Survival Audit | High | Medium-low | **Best bounded experiment** |
| Per-image robustness certificate | Medium-high | Low | **Good demo addition** |
| Degradation type/severity prediction | Medium | Low | Useful but less distinctive |
| Quality-aware calibration | Low-medium | Low | Already close to current system |
| Generator attribution | High | High | Wrong timing / needs labels |
| Partial-AI localization | High | High | Expands scope too much |
| VLM explanation | Medium | Medium | Risk of hallucinated explanations |
| New frequency detector | Medium | High | Crowded + repeats failed strategy |
| Another expert model | Low | High | Do not prioritize |

## 19. Recommended immediate actions

```text
1. Finish fresh-holdout validation of the probe-free system.

2. Run the quality-descriptor ablation on train/dev
   to determine what actually drives the robustness gain.

3. Wait for / inspect the sealed organizer benchmark.

4. In parallel, give the Evidence Survival Audit
   a bounded development-only experiment.

5. If evidence coverage/survival shows useful signal,
   build it as optional Audit Mode.

6. If it does not show useful signal,
   kill it immediately.

7. Then freeze engineering and focus on
   video, Devpost, diagrams, pitch and error cases.
```

## 20. Quality-descriptor ablation remains worth doing

The current 38-dimensional vector contains dead weight.

Probe features appear to add approximately zero.

Disagreement features are structurally absent because only one expert remains.

Therefore identify what actually drives the correction.

Test on train/dev:

```text
Primary only

Primary + noise_sigma
Primary + blockiness
Primary + blur
Primary + luminance
Primary + saturation
Primary + clipping
...

Primary + top 2
Primary + top 3

Primary + all quality descriptors
```

Also consider leave-one-feature-out.

A valuable possible result:

```text
Primary only                    -> weak
+ noise estimate                -> large gain
+ noise + blockiness            -> most of gain
+ all quality descriptors       -> small extra gain
+ worst-group objective         -> strongest tail robustness
```

If only 1–3 descriptors carry most of the effect, the story becomes sharper:

> **A tiny amount of explicit degradation information repairs most of the failure of a 21.8M-parameter detector.**

Do not assume this until measured.

## 21. Do not contaminate the new holdout

The newly acquired fresh 3,000-source holdout must remain fresh.

Use:

```text
train/dev
```

for:

```text
quality-feature selection
audit design
audit metric selection
hyperparameters
```

Then freeze.

Only after freezing should the fresh holdout be used for one-shot validation.

Do not repeatedly inspect holdout outcomes and redesign from them.

The project's methodological rigor is one of its strongest advantages.

## 22. Final recommendation

Yes, removing useless probes and gaining a large speedup is worthwhile.

No, speed should **not** be the entire innovation pitch.

The best additional bet is:

# **Forensic Evidence Survival / Robustness Audit**

because it:

```text
adds a different capability instead of another detector;
directly addresses false confidence;
matches the Track 5 transformation problem;
can reuse existing infrastructure;
does not risk the working classifier;
is visually compelling in a demo;
has a clear kill condition;
can be built as optional audit mode;
strengthens Innovation & Problem Insight.
```

The desired final product is:

```text
fast degradation-aware robust detector
        +
reliability / deferral
        +
optional forensic evidence survival audit
```

not:

```text
a growing ensemble of more models
```

## 23. Binding principle

> **Do not add complexity simply to look innovative. Add one capability that changes what the product can tell the user.**

The current classifier already answers:

```text
"Is this image likely AI-generated?"
```

The audit should add:

```text
"Where is that forensic evidence?"
"How concentrated is it?"
"Will it survive redistribution?"
"Should we trust this decision?"
```

That is the most promising innovation direction without putting the validated core system at risk.
