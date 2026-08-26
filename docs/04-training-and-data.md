# Training and Dataset Strategy

> **Status: PROPOSAL until datasets, licenses, and compute are confirmed.**  
> Goal: train the smallest component that can learn when each pretrained evidence stream is trustworthy.

## What stays frozen first

Freeze:

- Community Forensics or the selected OmniAID primary;
- LOTA if retained;
- WaRPAD's self-supervised backbone and method parameters;
- RIGID if used as backup.

Train:

- expert-specific score calibration if required;
- reliability/fusion router;
- rescue-stage fusion;
- final temperature and bias;
- optional abstention threshold.

Why freeze the experts:

- it preserves broad generator knowledge learned from much larger corpora;
- it avoids catastrophic overfitting to a small hackathon subset;
- it keeps compute and training time low;
- it makes ablations interpretable;
- it cleanly separates reused models from our contribution.

Only after the frozen system plateaus should we test unfreezing a classifier head or final block. That trial must be reversible and compared against the frozen baseline on source-held-out data.

## Dataset roles

| Source | Role | Use in training? | Main caveat |
|---|---|---:|---|
| **GenImage** | Primary router training and source-held-out development | Yes, subset | Older generator set; preserve paired/semantic structure |
| **SID-Set** | Social-media-oriented diversity | Yes, controlled subset | Contains real, fully synthetic, and tampered; use correct labels |
| **Community Forensics Small** | Optional router diversity | Maybe | Roughly 278 GB; expert may already be trained on related data |
| **CIFAKE** | Smoke test / weak baseline | Minimal or no | 32x32 CIFAR-10 real vs SD1.4 fake creates outdated resolution/content shortcuts |
| **T2I-CoReBench images** | Modern-generator fake-recall external test | No initially | Mostly/generated-only; unmatched reals create semantic shortcuts |
| **AIGIBench** | External robustness/generalization test | No | Preserve benchmark integrity |
| **RRDataset** | Real social transmission/re-digitization test | No | Download/time may be substantial |
| **Chameleon** | Hard fake generalization test | No | Use only if license/access fits |
| **Organizer WildFake subset** | Official demonstration/reference | **Never** | 4,998 COCO real + 8,843 DALL-E Advanced fake; forbidden for training |

## Recommended size

Because only a small router is trained, start with **40,000-60,000 source images**, balanced real/fake and diversified by generator/content source.

Example initial allocation:

```text
20k-30k real
20k-30k fully generated
```

This is a planning range, not an official requirement. Increase only if feature extraction and storage are already stable.

## Label policy

For Track 5's image-level binary task:

```text
real/authentic          -> 0
fully AI-generated      -> 1
partially tampered      -> exclude from initial binary training
unknown/mixed license   -> exclude
```

SID-Set's tampered class is valuable future work, but mixing it into “fully generated” changes the task and may distort the detector.

## Split policy

Never randomly split near-duplicate images or generations from the same source across train/dev/test.

Use grouped splits by as many of these as metadata allows:

- generator family/model;
- real-image source dataset;
- prompt or source-image lineage;
- semantic class;
- image hash/perceptual cluster;
- transformation seed/derived family.

Recommended:

```text
train sources/generators      -> router fitting
held-out dev sources          -> early stopping, thresholds, calibration
held-out internal test        -> final ablations
external datasets             -> modern/generalization claims
official WildFake reference   -> sealed demonstration only
```

The clean original and all transformed versions of one source image must remain in the same split.

## Contamination controls

For every dataset:

1. compute SHA-256 of original bytes;
2. decode canonically and compute a perceptual hash;
3. store source, split, class, generator, prompt/source lineage when available;
4. detect exact cross-split duplicates;
5. detect near duplicates at a documented perceptual-hash threshold;
6. create a hash denylist from the official WildFake reference subset;
7. reject train examples matching or near-matching that denylist;
8. version the manifest, not merely directory contents.

Any human review of the official reference set should occur after architecture/threshold decisions are frozen.

## Transform generation

Generate transformations on the fly for router training or in a deterministic feature-cache job. Do not store hundreds of thousands of redundant copies unless caching is necessary.

### Official single-transform families

```text
clean
JPEG: 90, 70, 50, 30
Gaussian blur sigma: 0.5, 1.0, 2.0
resize/down-up: 0.5, 0.25
Gaussian noise sigma: 0.02, 0.05, 0.10
color: brightness/contrast/saturation +/-20%
center crop: 80%
```

### Sampling strategy

Use a balanced or curriculum sampler so clean and severe cases are not drowned out by easy/mild variants. One simple policy:

- 20% clean;
- 80% one transformed view, with transformation families sampled uniformly;
- within a family, severities sampled uniformly at first;
- after an initial epoch/evaluation, increase sampling for the worst class-family groups.

Do not train only on every image's worst transform chosen using the test set. Hard-corruption mining must use training/dev outcomes only.

### Chained transforms

Real reposts often chain resize, JPEG, and color changes. Create a **secondary unofficial stress suite** for two-step chains, but keep it separate from official single-transform reporting so the submission does not misrepresent the organizer grid.

Examples:

```text
resize 0.5 -> JPEG 50
crop 0.8 -> JPEG 30
blur 1.0 -> JPEG 50
color jitter -> resize 0.25
```

## Cached feature table

Frozen experts allow fast experimentation by caching one row per source-view pair:

```text
sample_id
source_id
split
label
dataset
generator/source group
transform_family
severity
primary logit/probability/entropy
LOTA logit/probability/patch stats
probe stability features
quality descriptors
optional WaRPAD score
runtime fields
```

The cache must include checkpoint hashes and preprocessing versions. Never reuse features after changing decode/preprocessing without a cache-version bump.

## Base classification loss

Use binary cross-entropy on the router's final logit:

```text
L_bce = BCEWithLogits(z_final, y)
```

Class balance should be enforced by sampling or explicit weights. Do not let the larger official fake count or any source imbalance determine the operating prior accidentally.

## Class-by-transformation groups

Track at least:

```text
real + clean       fake + clean
real + JPEG        fake + JPEG
real + blur        fake + blur
real + resize      fake + resize
real + noise       fake + noise
real + color       fake + color
real + crop        fake + crop
```

Initially group by family to keep batches populated. Add severity-level subgroups later if data supports stable estimates, especially `fake + JPEG30` and `fake + resize0.25`.

## Smooth worst-group objective

Let `L_g` be mean loss for group `g` in the accumulation window. Use:

```text
L_worst = tau * log(sum_g exp(L_g / tau))
L_total = L_bce + lambda_w * L_worst
```

`tau` controls how closely the smooth term approximates a maximum. Normalize or use `logmeanexp` so the scale does not grow arbitrarily with group count.

Purpose:

> Prevent strong real accuracy and easy clean cases from hiding a collapse in generated images under one severe transform.

Use moving estimates or sufficiently stratified batches; a “worst group” computed from one or two examples is noise.

## Prediction consistency - optional ablation

For clean source `x` and label-preserving transform `T(x)`, compare final predictions:

```text
L_cons = JS(p(x), p(T(x)))
```

or use a Huber penalty between calibrated logits.

Then:

```text
L = L_bce + lambda_w*L_worst + lambda_c*L_cons
```

Keep `lambda_c` small. Do **not** force expert internal representations to be equal: JPEG truly changes low-level evidence, and erasing that response could destroy useful cues. Consistency is an ablation, not a core dependency.

## Reliability targets

Possible supervised target:

```text
q = 1 if final/common-path prediction is correct at the operating threshold
q = 0 otherwise
```

Train a reliability head with BCE or Brier loss. More useful variants predict:

- common path correctness;
- whether WaRPAD will correct the common path;
- expected absolute error;
- out-of-reliable-region flag.

Start with correctness/recovery targets. Complex uncertainty decomposition is unnecessary in week one.

## Rescue training policy

Avoid running WaRPAD for the full training corpus until the common path is stable.

1. Train/evaluate primary + LOTA.
2. Identify uncertain/disagreement/error-enriched examples using training/dev only.
3. Run WaRPAD on all dev examples and a stratified training subset containing both easy and hard cases.
4. Train the rescue predictor/fusion on these scores.
5. Validate that the rescue trigger generalizes instead of simply memorizing transform labels.

The rescue model needs negative examples too; otherwise it will learn to invoke WaRPAD for everything.

## Calibration procedure

1. Freeze expert/router weights.
2. Fit per-expert calibration only if raw score scales differ badly.
3. Fit final `T` and `b` on held-out dev data across clean and transformed groups.
4. Choose one operating threshold under the stated objective.
5. Freeze thresholds before internal/external/official test evaluation.
6. Report ECE and Brier score by clean/transformed and class where feasible.

## Fine-tuning gate

Fine-tuning the primary becomes eligible only if:

- adapters and preprocessing are verified;
- the router has plateaued;
- a specific feature gap is identified;
- there is enough held-out generator diversity to catch regression;
- the team can rerun the entire matrix.

Try in this order:

1. classifier head only;
2. low-rank adapter if officially supported;
3. final backbone block;
4. never full fine-tuning during the critical path unless evidence is overwhelming.

Reject fine-tuning if it improves in-domain transformed results but hurts source-held-out or modern-generator tests.

## DEAR-inspired feature gating - stretch

If primary embeddings are accessible, estimate for each feature channel `j`:

```text
R_j = class_separability_j / (transformation_variation_j + epsilon)
```

High `R_j` separates real/fake and remains stable. Low `R_j` varies under transformations without reliable class separation.

Possible interventions:

- prune low-`R_j` channels;
- learn a regularized per-channel gate;
- use stability features only in the router.

This is inspired by DEAR's diagnosis but is not DEAR itself. It must be named accurately and abandoned if it does not beat the simpler score-level router quickly.

## Data strategy by day

### Day 1

- small, balanced smoke subset;
- enough clean and exact transforms to verify adapters and metrics;
- no large downloads before end-to-end inference works.

### Day 2-3

- 40k-60k router corpus from GenImage plus filtered SID-Set;
- grouped train/dev split;
- feature cache for both common experts and probes.

### Day 4-5

- rescue features on stratified hard/easy subset;
- external modern fake set such as T2I-CoReBench;
- AIGIBench/RRDataset only if downloads and licenses are practical.

### Day 6-7

- frozen final internal test;
- sealed organizer reference evaluation;
- error exemplars and reproducibility package.

## Dataset claims to avoid

- Do not call CIFAKE representative of 2026 generators.
- Do not train with generated-only modern data paired against unrelated real content and then call gains forensic.
- Do not report the organizer reference set as hidden final score.
- Do not claim no leakage without hash/source-lineage checks.
- Do not call transformed copies independent samples in confidence intervals; bootstrap by source image.
- Do not tune on an external benchmark and still call it an untouched external test.

