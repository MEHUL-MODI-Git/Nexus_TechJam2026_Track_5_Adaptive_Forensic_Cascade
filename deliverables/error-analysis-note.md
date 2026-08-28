# Error Analysis Note

> **Status:** regenerated on the **protected, untouched internal test** (3,000 sources ×
> 20 conditions = 60,000 rows) at the **frozen** decision threshold 0.4667367651127279.
> This supersedes the earlier draft, which was computed on an 8,000-row smoke grid at an
> unfitted 0.5 threshold with COCO reals against SID-Set fakes — a comparison we disowned
> in README §8. Every number below is reproducible from
> `results/robustness/error-taxonomy.json` via `scripts/error_taxonomy.py`.

At the shipped operating point the cascade misses **8.0% of AI images** (2,390 false
negatives) and misclassifies **10.2% of real photographs** (3,068 false positives).

## The one-line finding

**The detector does not become uncertain under degradation. It becomes confidently wrong —
in both directions, at the extremes of its output range.**

- Worst false negatives: AI images scored **p_fake = 0.0001**
- Worst false positives: real photographs scored **p_fake = 0.9996**

Not 0.45 and 0.55. A downstream system reading the score as confidence would act on both.

## Failure mode 1 — noise erases the evidence, and pushes reals the other way

Noise is simultaneously our worst false-negative **and** worst false-positive condition:

| condition | fake recall | FPR |
|---|---:|---:|
| clean | 0.9613 | 0.0833 |
| noise σ=0.02 | 0.8787 | 0.1153 |
| noise σ=0.05 | 0.8087 | 0.1787 |
| **noise σ=0.10** | **0.7900** | **0.2967** |

The generator fingerprint lives in the high-frequency band and additive noise occupies the
same band. At σ=0.10 nearly one real photograph in three is called AI-generated. This is
the single most exploitable weakness in the system, and adding imperceptible noise is the
cheapest attack against it.

**Representative case — `fully_synthetic/190e2b3d3a1e504c.jpg`** (skateboarders on a
graffitied stairwell): a photorealistic generation whose content is *already* high-texture
— graffiti, weathered concrete, blown-out backlighting. Under `contrast_+20` it scores
**0.0001**. Content that looks like noise hides the fingerprint just as added noise does,
which is why our worst false negatives are gritty documentary-style scenes rather than the
smooth, over-rendered images people expect a detector to miss.

## Failure mode 2 — blur makes real photographs look generated

At clean the false-positive rate is 0.0833; under blur σ=2.0 it is **0.1260**, and the
errors are not random.

**Representative case — `real/ebaabab805ab2c4f.jpg`** (a row of fire trucks against open
sky and tarmac): under `blur_s2.0` it scores **0.9994**. The image is dominated by large
smooth regions — sky, asphalt — with saturated manufactured objects in front of them. Blur
removes the sensor noise that marks it as a photograph, and what remains looks like a
render. Our earlier smoke-set analysis found the same pattern in aircraft photographs
(eight of nine worst false positives were planes against sky and tarmac); the protected
corpus reproduces it with a different subject, so it is a property of the *content class*,
not of one dataset.

A second family of false positives is heavily processed real photography.
**`real/95efd34d1ad0803b.jpg`** — a trade-show snapshot with saturated artificial lighting
and an added white border — scores **0.9996** under `contrast_-20`. Images that have already
been through a processing pipeline have had the same evidence stripped from them.

## Failure mode 3 — photometric shifts are not free

Brightness and contrast are usually treated as benign, and for real images they are. For
synthetic ones they are not: `bright_+20` drops fake recall to 0.8967 and `contrast_+20` to
0.9173, against 0.9613 clean. Both are one-click operations in any photo app.

## What abstention catches, and what it does not

The system declines to decide on the 20% of images it judges least reliable. That set is
strongly enriched for errors:

- **41.8%** of all false negatives fall in it
- **38.6%** of all false positives fall in it
- but only **18.1%** of *correct* decisions do

So abstention is roughly 2.2× enriched for mistakes, and accuracy on the images the system
does decide rises from 0.9090 to 0.9317.

**The honest limitation is where it fails.** Abstention rate tracks degradation almost
perfectly for noise — 7.2% clean, 85.9% at σ=0.05, 98.6% at σ=0.10 — because the
reliability head reads quality descriptors, and noise is exactly what those measure. It is
nearly blind to blur: at blur σ=2.0 it abstains on **0.03%** of images while the
false-positive rate there is 0.1260. Blur makes an image look *cleaner*, so the head reads
high quality and stays confident.

This is why **every one of the worst errors listed above carries reliability between 0.91
and 0.99 and would not be deferred.** Abstention removes the moderately uncertain middle,
not the confidently wrong tail. A deployment that treats "did not abstain" as "safe to
automate" would be wrong in precisely the cases that matter most.

## Trade-offs we accepted, stated plainly

1. **We buy robustness with false positives.** The cascade lifts worst-family fake recall
   from 0.1227 to 0.8258, but its clean FPR is 0.0833 against the primary's 0.0027. Against
   a primary handed our own operating point the honest gain is **+0.49**, not +0.70
   (README §7).
2. **The gain is not uniform.** At matched FPR the primary *beats* the cascade on blur,
   colour and resize. The entire advantage is `noise` and `jpeg`. We raise the floor, not
   the ceiling.
3. **Nothing is gained on clean images** (0.9613 vs a matched primary's 0.9620).
4. **The clean-FPR constraint we set ourselves did not hold** on unseen data: 0.0833 against
   the 0.0756 cap. We reported it rather than re-tuning the threshold.
5. **Abstention costs coverage.** One image in five is deferred to a human. That is a real
   operational cost and it is the price of the accuracy gain above.

## What we fixed after writing this — and what remains

**The confidently-wrong tail now has a detector, and it is not the reliability head.**

The limitation above says abstention removes the uncertain middle but not the
confidently wrong tail. We went looking for a second signal that fails *differently*,
and found one already sitting in the project: the 20-condition stress grid we built to
evaluate the system. Run on a single image, **verdict retention** — how many of the 20
conditions preserve the clean verdict — predicts a wrong verdict better than the
reliability head trained for that purpose:

| signal | AUROC predicting a wrong clean verdict |
|---|---|
| reliability head | 0.7206 |
| **verdict retention** | **0.8650** |
| both combined | 0.8863 |

It works precisely where the reliability head fails. Of the **157** sources the head
passes with high confidence but gets wrong, mean retention is **14.40 / 20** against
**19.00 / 20** for the confident-and-correct ones. Flagging `retention < 18` among
high-confidence images catches **72.6%** of those blind-spot errors while deferring only
17.3% of them.

The reason the two are complementary is the reason the blind spot existed: the
reliability head reads quality descriptors, so it tracks noise and is nearly blind to
blur. Retention measures the verdict itself and inherits no such bias. Artifact:
`results/robustness/retention-signal.json`.

This ships as **audit mode** — it costs 20 forward passes, so it is an explicit deeper
check rather than part of the default path.

**What still is not fixed.**

- Retention reduces the confidently-wrong tail; it does not eliminate it. At
  `retention ≥ 18` the clean verdict is still wrong for about 5% of sources.
- The reliability head's blur blindness is unchanged. `blur_varlap` is in its feature
  vector and is evidently not being used in a way that separates "blurred real
  photograph" from "clean high-quality photograph". Retention routes around that
  weakness rather than repairing it.
- Both signals were measured on the internal test, whose per-family results informed
  this analysis. A fresh untouched holdout has been acquired to confirm the
  retention→accuracy relationship before it is treated as a headline claim.
