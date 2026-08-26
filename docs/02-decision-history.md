# Decision History: How the Architecture Evolved

> **Status: DECISION RECORD**  
> Purpose: preserve the reasoning, reversals, and trade-offs from the “TechJam Track 5 Focus” conversation. This is important because the final architecture is simpler than several earlier proposals for deliberate reasons.

## Stage 0 - Establish the real problem

The initial framing was straightforward:

> Distinguish AI-generated images from authentic images after realistic transformations.

Reading the official pages changed the emphasis. Track 5 explicitly values robustness, generalisation, false positives, evaluation design, and error analysis. It also calls for a limited-compute, hackathon-scale proof of concept and says that robustness may be considered against a **subset** of the listed augmentations.

The first strategic consequence was:

> Clean accuracy is necessary but not the project. The project is the clean-to-transformed failure gap.

The second was:

> We are allowed to reuse public models. Our originality should come from how we make them reliable under the organizer's transformation regime and how we prove it.

## Stage 1 - Strong single detector plus robustness training

The first research pass identified Community Forensics as a compelling backbone because it exposes a compact detector to 4,803 generator models. The initial ladder was approximately:

```text
generic ResNet/ViT
    -> Community Forensics
    -> exact transformation augmentation
    -> SAFE-style crop/masking
    -> consistency loss
    -> multi-view inference
    -> DEAR-style pruning
```

### Why this was attractive

- A strong baseline could work almost immediately.
- Exact challenge transforms could be generated on the fly.
- Consistency between original and transformed images directly matches the label invariance.
- SAFE and DEAR offered concrete mechanisms beyond generic augmentation.

### Why it became insufficient

A single detector can fail systematically when its preferred evidence is destroyed. More transformations do not automatically create a new cue; they can simply teach the same model a broader but still brittle shortcut. AIGIBench also warns that ordinary augmentation has limited and sometimes trade-off-heavy effects.

This led to the multi-cue hypothesis:

> Different transformations damage different forensic evidence, so deliberately combine evidence families rather than multiple copies of the same classifier.

## Stage 2 - TRIDENT-style three-expert architecture

The next proposal used three branches:

```text
Community Forensics -> broad/generator-diverse evidence
LOTA               -> local low-level/bit-plane evidence
RIGID-style probe   -> behavioral response under perturbation
        -> reliability-aware router
        -> calibrated result + robustness confidence
```

This design also proposed:

- image-quality descriptors such as blur, JPEG blockiness, resolution, noise, luminance, contrast, and saturation;
- mild diagnostic probes such as JPEG 92, 0.90x resize, tiny crop, and sigma approximately 0.2 blur;
- per-expert stability measured from score variance under the probes;
- class-by-transformation Group-DRO;
- final-prediction consistency across transformations;
- a DEAR-inspired transformation-stable feature gate.

### The key conceptual advance

A static average fails when one evidence stream is destroyed. For example:

```text
Community AI score   0.79
LOTA AI score        0.21  <- low-level cue may be destroyed
Behavioral score     0.83
```

The broken expert should not receive equal weight. The router's question became:

> Which forensic evidence survived this input's processing history?

This was stronger than routing by content type or pretending to infer an exact transformation history.

### Why this design was too ambitious as the immediate plan

- Three always-on experts plus repeated probes inflate integration and inference costs.
- Group-DRO, consistency, feature gating, calibration, and a router all at once create an ablation nightmare.
- RIGID/RA-Det-style behavior and later WaRPAD overlap; using both can add complexity without evidence diversity.
- A beautiful diagram can make the team reluctant to remove a weak expert.

## Stage 3 - Deep-research correction: Community Forensics + WaRPAD

A deeper paper/repository review changed Expert B from LOTA to WaRPAD.

### Why LOTA was demoted at this stage

LOTA's paper provides impressive blur results but tests JPEG only at 100/95/90/85. The organizer goes to 30. Since LOTA explicitly relies on lower bit planes, its signal is plausibly at risk under severe compression.

WaRPAD, by contrast, directly evaluates:

- JPEG to quality 50;
- center crop to 50%;
- Gaussian noise to sigma 0.125.

The recommendation became:

```text
Expert A: Community Forensics 384
Expert B: WaRPAD
Our layer: self-probed reliability router + worst-group training + calibration
Optional Expert C: LOTA if complementary
```

### Other simplifications introduced

- Freeze both experts.
- Probe only Community; WaRPAD already performs behavioral operations internally.
- Train a tiny 10-20-feature MLP router.
- Replace a full Group-DRO framework with a smooth worst-group objective using log-sum-exp.
- Calibrate the final logit with temperature and bias.
- Use 40k-60k balanced source images rather than millions, because the experts are frozen.

### What remained a concern

WaRPAD is heavier per image. If it runs for every input, the demo may be slower and the system less practical than necessary.

## Stage 4 - LOTA returns as a distinct expert

The user highlighted LOTA's unusually strong Gaussian-blur robustness and asked whether JPEG 30 is already solved and whether success on only some transforms would be enough.

The resulting correction was philosophical as much as architectural:

> Stop demanding that every expert solve every transform.

LOTA can be useful even if its weight collapses under JPEG 30. A reliability system exists precisely to exploit an expert where it helps and suppress it where it does not.

The proposed evidence families became:

```text
Community Forensics -> broad learned/generator-general evidence
WaRPAD             -> behavioral/cropping-robustness evidence
LOTA               -> local low-level/bit-plane evidence
```

Crucially, LOTA was **not** hard-coded as “the blur expert.” The router should discover its useful region empirically.

### Reframed success condition

Old, overly rigid target:

> Beat every current detector on every transformation and solve JPEG 30.

New target:

> Materially reduce transformation-induced degradation and fake-to-real flips relative to the strongest individual detector, while retaining clean performance and acceptable false positives.

This accepts an honest outcome such as:

- large gains on blur, resize, crop, and noise;
- a smaller but real gain on JPEG 30;
- low reliability/abstention on unresolved severe compression.

That is still a strong submission because the official brief does not impose a per-transform pass mark or require perfection on the full list.

## Stage 5 - Final hackathon correction: Adaptive Forensic Cascade

The final conversation turn explicitly rejected designing for a perfect universal model. The architecture was simplified to maximize the probability of measurable results in seven days:

```text
                        INPUT
                          |
          +---------------+---------------+
          |                               |
          v                               v
  Community/OmniAID                      LOTA
   primary expert                cheap forensic specialist
          |                               |
          +---------------+---------------+
                          |
               quality/reliability features
                          |
                    SMALL ROUTER
                    /          \
             reliable          uncertain
                |                  |
          final result           WaRPAD
                                   |
                              final fusion
                                   |
                        prediction + reliability
```

### Why this is now preferred

- The common path uses two relatively compact experts.
- The heavier behavioral method is paid for only when useful.
- The small router is feasible to train quickly.
- Each component has an operational purpose.
- Model slots remain replaceable.
- The UI can explain why an image was escalated.
- Failure on JPEG 30 becomes a calibrated limitation rather than an overconfident false “real.”

## What changed, in one table

| Earlier belief | Revised belief | Reason |
|---|---|---|
| One strong detector plus augmentation may be enough | Heterogeneous cues are more promising | A transformation can destroy a whole evidence family |
| Run three experts for every image | Use a two-expert common path and selective rescue | Better latency and integration economics |
| LOTA should be excluded because JPEG evidence is mild | Test it as a specialist and let reliability suppress it | An expert need not solve every transform to add value |
| WaRPAD should be Expert B always-on | WaRPAD should start as rescue | It is behaviorally compelling but computationally heavier |
| Every planned loss should be in the first system | Router + BCE/worst-group first; consistency is an ablation | Fewer moving parts and clearer causality |
| Full Group-DRO is necessary | Smooth worst-group emphasis may be enough | Easier, safer implementation |
| DEAR-like feature pruning should be core | Treat feature gating as a stretch | Porting across architectures is non-trivial |
| The architecture is tied to Community/LOTA/WaRPAD | Slots are fixed; models are replaceable | Experiments must outrank narrative attachment |
| Project success means solving all corruptions | Success means measurable, honest robustness improvement | Official brief seeks a convincing prototype, not universal solution |

## Why JPEG 30 must remain an explicit limitation

Severe JPEG compression destroys and replaces high-frequency evidence. Many forensic detectors are built precisely on subtle artifacts in that frequency range. The challenge is not simply “denoise then classify”: JPEG introduces structured block/quantization artifacts and can make a generated image resemble the real side of a learned boundary.

Recent 2025-2026 work still exists specifically because compression, rescaling, lossy transmission, and unseen generators remain failure modes. Therefore:

- JPEG 30 is not a trivial solved condition.
- We should seek a material gain, not promise near perfection.
- We should report fake recall and fake-to-real flip rate, not hide behind accuracy.
- Reliability must drop when the system leaves its validated region.
- The demo should show abstention or manual-review escalation for uncertain cases.

## Frozen concept, replaceable implementation

The part that should remain stable is:

```text
strong broad detector
    + cheap orthogonal evidence
    -> per-sample reliability
       -> direct result when reliable
       -> expensive second opinion when uncertain
    -> calibration / optional abstention
```

The following are empirical choices:

- Community Forensics versus OmniAID as primary.
- LOTA versus another local expert.
- WaRPAD versus RIGID as behavioral rescue.
- exact probe set;
- router architecture;
- rescue threshold;
- abstention coverage;
- optional consistency or feature-gating loss.

## Decision principles retained from the conversation

1. **Architecture follows evidence, not loyalty to a paper.**
2. **A specialist can be valuable without being universal.**
3. **Worst-group fake recall matters more than a flattering average.**
4. **Prediction stability is a feature, not proof of correctness.**
5. **Reliability is distinct from class probability.**
6. **Frozen experts are the safe starting point.**
7. **Every extra component must earn itself through ablation.**
8. **An honest known limitation is stronger than an unsupported universal claim.**
9. **The innovation is the validated system design and training/evaluation protocol, not the downloaded checkpoints.**
10. **A working demonstration by 24-36 hours outranks an elegant but unfinished architecture.**

