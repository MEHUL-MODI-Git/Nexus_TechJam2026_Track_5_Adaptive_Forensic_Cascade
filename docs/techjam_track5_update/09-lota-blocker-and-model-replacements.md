# Track 5 Update: LOTA Blocker, Replacement Models, and Immediate Consequences

> **Status:** IMPORTANT UPDATE TO THE PREVIOUS TRACK 5 PLAN  
> **Purpose:** This file records the new information discovered after the original Adaptive Forensic Cascade plan was already underway. Read it alongside the earlier Track 5 documentation. Do **not** discard the previous plan; this is a delta/update document.

## 1. What changed

The previous implementation plan expected **LOTA** to be the cheap local/low-level forensic expert in the common path:

```text
Primary general detector
    +
LOTA local forensic specialist
    -> small reliability/fusion router
        -> if uncertain, invoke WaRPAD
```

The implementation blocker is that the **pretrained LOTA checkpoint is distributed through Baidu Netdisk**, and access currently requires a Chinese-number/Baidu-account workflow that is not realistically available to the team.

Therefore:

> **The LOTA pretrained checkpoint cannot be treated as a dependable hackathon dependency.**

This is a dependency/reproducibility problem, not evidence that the LOTA research idea is bad.

## 2. What not to do

Do not spend hackathon time trying to bypass Baidu verification. Do not depend on an unverified third-party checkpoint mirror merely because a `.pth` file appears online. Do not block the entire architecture on one inaccessible research artifact.

The blocker exposes a useful architecture lesson:

> A hackathon system should not depend critically on research artifacts whose official weights are hard to retrieve or reproduce.

This matters directly to TechJam's Technical Execution and Feasibility/Practicality criteria.

## 3. LOTA is still technically usable

The LOTA method itself remains relevant. The public implementation includes training logic, so one possible parallel path is:

```text
Official LOTA code
    +
compatible GenImage training subset
    ->
our own LOTA-like checkpoint
```

However, this is now a **bounded stretch experiment**, not a critical dependency.

Why:

- exact reproduction may consume time;
- we may not match the authors' reported results within the hackathon window;
- the original reason to choose LOTA was that it was supposed to be a ready-to-use lightweight expert;
- once retraining is required, its implementation economics change.

Recommended rule:

> Give LOTA reproduction a strict time budget. Keep it only if it trains quickly and shows useful complementarity on our own stress matrix.

## 4. Why LOTA was attractive

LOTA offered a genuinely different evidence family:

```text
Community / broad detector
    -> global learned generator evidence

LOTA
    -> low-bit-plane / local-noise / high-gradient-patch evidence
```

Its paper reported unusually strong Gaussian-blur robustness, including sigma values matching or exceeding Track 5's `sigma = 2` maximum.

However, its JPEG robustness evidence was much milder than TechJam's grid. The paper tested roughly:

```text
JPEG 100 / 95 / 90 / 85
```

while TechJam includes:

```text
JPEG 90 / 70 / 50 / 30
```

So LOTA was never proven to be a severe-JPEG specialist.

The correct philosophy remains:

> A specialist does not need to solve every corruption. It only needs to repair enough mistakes made by the primary detector to earn its slot.

## 5. Accessible replacement candidate: PGC

A new replacement candidate identified after the LOTA blocker is **PGC — Peak-Guided Calibration** (ICML 2026).

### Core idea

PGC targets the possibility that global representations suppress highly localized synthetic artifacts. It identifies discriminative local peak features and uses them to calibrate a broader decision.

Conceptually this occupies the role we wanted from LOTA:

```text
broad/global evidence
        +
localized forensic evidence
```

but via a different mechanism.

### Why PGC is attractive

The latest research pass identified:

- accessible public implementation/checkpoints through normal public model hosting;
- corruption robustness experiments across many perturbation types;
- Gaussian blur testing up to approximately sigma 2;
- brightness / contrast / saturation perturbations;
- noise and other degradations;
- modern-generator evaluation.

This is better aligned with the TechJam stress suite than relying on LOTA's blur result alone.

### Trade-off

PGC is heavier than LOTA. That is acceptable only if the measured complementarity justifies it.

Do not keep PGC because it is newer. Measure:

```text
P(PGC correct | primary wrong)
```

plus error correlation, worst-transform fake recall, FPR, fake-to-real flips, latency, and memory.

## 6. New primary challenger: GAPL

Another newly prioritized model is **GAPL — Generator-Aware Prototype Learning** (CVPR 2026).

GAPL is not merely a LOTA replacement. It is more interesting as a **primary-detector challenger**.

Why it matters:

- accessible inference checkpoint;
- robustness experiments under JPEG and Gaussian blur;
- potentially better resilience than some frequency-heavy approaches;
- modern 2026 method.

The primary decision is therefore no longer:

```text
Community Forensics by default forever
```

but:

```text
Community Forensics
vs
GAPL
```

using the same local TechJam evaluation harness.

The final primary should be chosen using our own measured:

- clean balanced accuracy;
- fake recall;
- FPR;
- JPEG30 fake recall;
- blur2 fake recall;
- resize0.25 fake recall;
- noise0.10 fake recall;
- crop0.8 fake recall;
- worst-transform fake recall;
- fake-to-real flip rate;
- latency;
- setup reliability.

## 7. Community Forensics remains important

Do not discard Community Forensics simply because newer candidates exist.

It remains attractive because it is:

- compact;
- publicly accessible;
- already integrated or partly integrated;
- trained on extraordinary generator diversity;
- suitable for repeated inference / mild self-probes;
- a strong reproducible baseline.

The correct status is:

```text
Primary slot:
Community OR GAPL
chosen empirically
```

## 8. WaRPAD remains useful

The LOTA blocker does not invalidate WaRPAD.

WaRPAD remains attractive because it supplies behaviorally different evidence and can be used as a selective rescue method rather than always-on.

Current role:

```text
common path confident
    -> return

common path uncertain
    -> invoke WaRPAD
    -> fuse again
```

If WaRPAD proves too slow or difficult to integrate, RIGID remains a reasonable behavioral backup.

## 9. Revised safe cascade

If we preserve the existing Adaptive Forensic Cascade concept, the current safer implementation is:

```text
                         INPUT IMAGE
                              |
                              v
                       PRIMARY DETECTOR
                    Community OR GAPL
                              |
               +--------------+--------------+
               |                             |
               v                             v
         primary evidence                   PGC
                                    local / peak evidence
               |                             |
               +--------------+--------------+
                              |
                       RELIABILITY ROUTER
                              |
                 +------------+------------+
                 |                         |
             confident                  uncertain
                 |                         |
                 v                         v
              result                    WaRPAD
                                           |
                                           v
                                      final fusion
                                           |
                                           v
                               REAL / AI / UNCERTAIN
                                      + reliability
```

This is the **safe revised cascade** after the LOTA checkpoint issue.

## 10. Updated architecture principle

The project should no longer be described as:

```text
Community + LOTA + WaRPAD
```

The fixed concept should be:

```text
STRONG PRIMARY DETECTOR
    +
COMPLEMENTARY FORENSIC EVIDENCE
    ->
RELIABILITY / FUSION
    ->
OPTIONAL BEHAVIORAL RESCUE
```

The model names are replaceable.

That makes the project resilient to inaccessible checkpoints, dependency failures, newer models, and unexpected local benchmark results.

## 11. Immediate actions

1. Keep the current Community Forensics baseline operational.
2. Stop blocking on LOTA weights.
3. Give LOTA reproduction only a bounded parallel attempt.
4. Benchmark GAPL as primary challenger.
5. Benchmark PGC as complementary local expert.
6. Preserve WaRPAD as selective rescue.
7. Use the existing exact TechJam stress harness for every comparison.
8. Keep all large experts frozen initially.
9. Train only small routing/fusion/calibration layers unless evidence justifies more.
10. Keep every new component only if it earns itself in ablations.

## 12. Binding principle

> **Results outrank narrative.**

Do not retain a model because its paper is impressive or because an older architecture diagram included it. The blocker should be treated as an opportunity to make the system more reproducible and less fragile.
