# Error Analysis Note — DRAFT v1

> **Status:** Claude draft (Phase 5R); Codex reviews. **PRELIMINARY.** Every number here comes from
> the committed 8,000-row diagnostic grid (`results/grid-smoke-v1/`), which used an **unfitted 0.5
> threshold** and a smoke set whose real half is COCO and fake half is SID-Set. It is regenerated on
> the protected corpus before submission. Nothing here is a headline result.

## The one-line finding

**The detector does not become uncertain under transformation. It becomes confidently wrong — in
both directions, at the extremes of its output range.**

- Worst false negatives: AI images under noise σ=0.10 scored **p_fake = 0.0000**
- Worst false positives: real photographs under blur σ=2.0 scored **p_fake = 1.0000**

Not 0.4 and 0.6. Zero and one. A downstream system reading confidence as trust would act on both.

## Failure mode 1 — noise erases the evidence (false negatives)

| condition | fake recall | fake→real flip rate |
|---|---:|---:|
| clean | 53.0% | — |
| noise σ=0.05 | 9.0% | 83.0% |
| **noise σ=0.10** | **1.5%** | **97.2%** |

Of AI images the model correctly catches when clean, **97.2% flip to "real"** once mild Gaussian
noise is added. The generator fingerprint the detector relies on lives in the high-frequency band,
and additive noise occupies the same band. This is the single most exploitable weakness in the
system and we report it as such: adding imperceptible noise defeats this detector almost completely.

## Failure mode 2 — blur makes real photographs look generated (false positives)

At the operating point that yields **1.0% false positives on clean images**, blur at σ=2.0 yields
**64.0%**. Same model, same threshold — a 64× increase. At the naive 0.5 default the same condition
still gives 31.5%, so this is not an artifact of a badly chosen cut.

**These false positives are not random, and that is the interesting part.**

Of the nine real photographs most confidently misclassified as AI-generated under blur, **eight are
aircraft** — planes against open sky and tarmac. The ninth is a wave breaking on a beach. All ten
share one property: large smooth regions, simple backgrounds, little fine texture.

We tested that observation rather than resting on it. Measuring texture energy on the **clean**
originals:

| real photographs under blur σ=2.0 | median texture energy |
|---|---:|
| 20 most wrongly called "AI" | 442.9 |
| 20 least wrongly called "AI" | 1176.9 |

**The photographs the detector gets right have 2.66× more fine texture than the ones it gets wrong.**

### Why this happens

This connects to an independent measurement made elsewhere in the project. When we audited our
training corpus for a file-format confound, one image statistic survived every container change:
`noise_sigma`. Real photographs carry sensor noise; generated images are smooth. That is a genuine
physical difference and it is part of what any detector of this family learns.

Blur **removes sensor noise**. So blurring a real photograph moves it, along precisely the axis the
detector is sensitive to, into the region of feature space that generated images occupy. A
low-texture real photo — an aircraft against a clear sky — starts close to that boundary and needs
very little blur to cross it.

That is why the failure is asymmetric rather than a symmetric loss of accuracy, and it is why we
believe the fix is not a better detector but a router that measures the degradation and withholds
the verdict when the image has been pushed into that region.

## Trade-offs we accepted

1. **A single threshold across all 20 conditions**, never tuned per condition. Per-condition
   thresholds would improve every number in this note and would be leakage: at inference we do not
   know which transform was applied.
2. **Abstention costs coverage.** Refusing to answer on degraded images means answering fewer
   questions. For moderation triage we judge that correct; for a fully automated filter it would not
   be.
3. **We did not solve JPEG q30 or noise σ=0.10.** Fake recall is 11.5% and 1.5%. We report the
   conditions where the system fails next to those where it works.

## Compliance note for downstream use

**The strongest false-positive examples carry third-party trademarks** (FedEx and Polar Air Cargo
liveries are clearly legible). The brief forbids third-party trademarks in demo assets, so these
specific images must not appear in the demo video or public write-up. A trademark-free substitute —
the beach/wave false positive, or the F-22, which carries no commercial mark — should be used for
public material. The full set remains available in `results/robustness/cases/` for internal review.
