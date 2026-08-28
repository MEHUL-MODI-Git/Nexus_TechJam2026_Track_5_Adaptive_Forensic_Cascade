# TechJam Track 5 — Innovation Upgrade: Active Forensics

> **Status:** Current strategic recommendation  
> **Basis:** The measured system state in `2026-08-28_system-state-and-honest-assessment.md`.  
> **Goal:** Preserve the strong robustness result while strengthening the 20% **Innovation & Problem Insight** story without gambling the project on another large pretrained model.

## 1. Where we are now

The current shipped system is:

```text
image
  -> canonical decode
  -> Community Forensics CF-384
  -> quality descriptors
  -> three self-probes:
       JPEG q92
       crop 0.96
       resize 0.90
  -> 1,827-parameter MLP router with worst-group training
  -> 17-parameter reliability head
  -> probability + reliability + optional DEFER
```

The large detector is frozen. Our contribution is the decision layer and evaluation methodology.

Measured untouched internal-test results:

```text
Worst-family fake recall

Primary CF @ default threshold:   0.1227
Current robust system:           0.8258
```

Because the clean FPR differs, the fairer control gives the baseline a threshold fitted on the test set itself to match our clean FPR:

```text
Primary @ matched clean FPR:     0.3342
Current robust system:           0.8258
Advantage:                       +0.4916
CI95:                            about [+0.475, +0.508]
```

Development predicted `0.8144`; untouched test delivered `0.8258`, so the robustness gain generalized.

The problem is not performance. The problem is that the originally planned two-stage multi-expert cascade did not survive measurement.

LOTA and PGC were both tested and rejected. Therefore the shipped system is effectively one primary detector + self-probes + a robust decision layer + human deferral.

If we present this merely as “Community Forensics + quality features + an MLP,” the innovation story will be weaker than the technical result deserves.

---

## 2. The key discovery that should drive the next architecture

At matched FPR, the raw primary and the robust corrected policy are **complementary**:

| Family | Robust system | Raw primary @ matched FPR |
|---|---:|---:|
| Crop | 0.9620 | 0.9593 |
| Blur | 0.9471 | **0.9709** |
| Color | 0.9438 | **0.9647** |
| Resize | 0.9417 | **0.9763** |
| JPEG | **0.9047** | 0.8102 |
| Noise | **0.8258** | 0.3342 |

Interpretation:

```text
RAW PRIMARY POLICY
    better when original forensic evidence survives
    especially blur / color / resize

ROBUST CORRECTED POLICY
    much better when the detector collapses
    especially JPEG / noise
```

This means the most useful “second expert” may already exist inside the system:

> the **raw decision policy** and the **robust decision policy** are two complementary decision regimes.

Rather than chase another large model, route between them intelligently.

---

# 3. Recommended innovation: Active Forensics

Working name:

# **Active Forensics**
### Self-Probing Detection of AI-Generated Images Under Real-World Degradation

Core idea:

> Instead of passively making one prediction, the detector actively interrogates its own forensic evidence with small label-preserving transformations, observes how that evidence responds, chooses the most trustworthy decision policy, spends extra compute only when needed, and defers when the evidence remains unreliable.

This turns the existing self-probes from “extra features” into the central innovation.

---

# 4. Counterfactual forensic probing

The current system already creates:

```text
original
JPEG q92
crop 0.96
resize 0.90
```

and computes response features such as:

```text
probe mean
probe standard deviation
probe range
maximum score delta
prediction flip
quality descriptors
```

Reframe these as **counterfactual diagnostic interventions**:

```text
"What happens to my forensic prediction after a tiny re-encode?"
"What happens after a tiny crop?"
"What happens after a small rescale?"
```

The response pattern tells us whether the detector's current evidence is stable or fragile.

This is effectively the useful part of the earlier **DegradePrint** idea, but now integrated into the working system rather than built as a separate architecture.

---

# 5. Recommended architecture

```text
                                INPUT IMAGE
                                     |
                                     v
                              CF-384 BASE PASS
                                     |
                                     v
                         cheap quality descriptors
                                     |
                                     v
                           INITIAL STATE ESTIMATE
                                     |
                          enough evidence already?
                              /            \
                            YES             NO
                             |               |
                             |        choose next probe
                             |               |
                             |               v
                             |       run diagnostic probe
                             |               |
                             |               v
                             |      update response signature
                             |               |
                             |         enough evidence?
                             |            /       \
                             |          YES        NO
                             |           |          |
                             |           |       next probe
                             |           |
                             +-----------+
                                     |
                                     v
                         DUAL-POLICY ROUTER
                          /              \
                         /                \
                RAW CF POLICY      ROBUST MLP POLICY
                         \                /
                          \              /
                           +------------+
                                 |
                                 v
                         calibrated prediction
                                 +
                            reliability score
                                 |
                        +--------+--------+
                        |                 |
                     DECIDE             DEFER
```

No new large pretrained model is required.

---

# 6. Innovation component A — Dual-policy routing

Train a tiny gate that selects between:

```text
Policy A: raw / calibrated Community Forensics decision
Policy B: existing worst-group-trained robust MLP decision
```

The gate asks:

> **Which decision policy should be trusted for this image?**

Inputs can include:

```text
raw CF logit
robust MLP logit
absolute disagreement
quality features
probe-response features
reliability estimate
```

Do **not** hard-code:

```text
if JPEG -> robust
if blur -> raw
```

Those family results motivated the idea, but the deployed gate should learn from evidence because real inputs may have unknown or chained transformations.

If this works, we can preserve the raw detector's strengths on blur/color/resize while retaining the robust system's huge JPEG/noise gains.

---

# 7. Innovation component B — Adaptive probing

Current latency:

```text
CF-384 alone:
p50 ~18.8 ms
p95 ~20.0 ms

Current 3-probe system:
p50 ~127.9 ms
p95 ~145.3 ms
```

The current pipeline is around **6.8× slower**, mostly because all three extra CF passes always run.

Turn this weakness into the feasibility innovation.

Instead of:

```text
always run JPEG + crop + resize probes
```

do:

```text
base pass
   |
   v
sufficient confidence?
  / \
yes  no
 |    |
stop  run probe 1
        |
        v
     sufficient?
      / \
    yes  no
     |    |
    stop  probe 2
            |
           ...
```

Possible behavior:

```text
easy image       -> 1 total CF pass
medium image     -> 2 passes
hard image       -> 3-4 passes
```

The project then becomes an **adaptive-compute forensic detector** rather than fixed expensive test-time augmentation.

---

# 8. Innovation component C — Optional next-probe selection

If time permits, let the system choose the most informative next action:

```text
STOP
RUN_JPEG_PROBE
RUN_CROP_PROBE
RUN_RESIZE_PROBE
```

State can include:

```text
base score
entropy
quality features
observed probe responses
policy disagreement
current reliability
```

Conceptually:

```text
choose action with highest expected information gain
```

Do **not** build RL unless absolutely necessary.

A small supervised classifier or even a validated fixed best probe order is enough for the hackathon.

If a fixed order performs almost as well, use the simpler version.

---

# 9. Why the failed LOTA/PGC experiments strengthen the innovation story

Do not hide them.

They produced an important structural finding.

The deferred/error-heavy pool is dominated by:

```text
noise
JPEG
```

These transformations damage high-frequency forensic traces.

LOTA relies heavily on low-bit / noise-like information.

PGC uses local/quantization-residual-style high-frequency evidence.

Therefore:

> **The hardest cases destroyed the same frequency evidence the rescue experts needed.**

A strong judge-facing insight is:

> **You cannot reliably rescue noise-destroyed evidence with another detector that reads evidence from the noise band.**

This explains why “add more forensic experts” failed and motivates the pivot to active self-diagnosis.

Experiment progression:

```text
1. Strong primary detector
2. Robustness correction works
3. Try independent rescue experts
4. LOTA fails
5. PGC fails
6. Analyze failure population
7. Discover shared high-frequency dependency
8. Stop adding passive sensors
9. Actively interrogate the primary sensor instead
```

That is a strong **Innovation & Problem Insight** narrative.

---

# 10. Reliability and abstention remain valuable

Measured:

| Policy | Coverage | Accuracy | Worst-family |
|---|---:|---:|---:|
| Decide everything | 1.000 | 0.9090 | 0.8258 |
| Defer least-reliable ~20% | 0.799 | **0.9317** | **0.9136** |

So the final system should preserve:

```text
AI-GENERATED
REAL
UNCERTAIN / DEFER
```

rather than force a binary decision.

But reliability must be described carefully.

Current blind spot:

```text
noise sigma 0.10 -> abstain ~98.6%
JPEG q30         -> abstain ~68%
blur sigma 2.0   -> abstain ~0.03%
```

Some confidently wrong cases still receive very high reliability.

Therefore do **not** claim:

> “If the system does not abstain, the answer is safe.”

Correct claim:

> Reliability improves selective decision quality substantially, but confidently wrong tails remain and are explicitly documented.

---

# 11. Exact experiments to run next

## Experiment 1 — Verify dual-policy complementarity on DEV

The family complementarity above came from the internal test.

Before building a gate, confirm on development data that:

```text
raw policy wins some regions
robust policy wins other regions
```

If this does not reproduce on dev, do not train a gate based on test observations.

---

## Experiment 2 — Dual-policy gate

Train a tiny classifier:

```text
input:
raw score
robust score
disagreement
quality
probe response
reliability

output:
RAW
or
ROBUST
```

Compare against:

```text
raw only
robust only
static blend
logistic blend
```

Keep the gate only if it improves a genuinely held-out result.

---

## Experiment 3 — Probe-budget ablation

Evaluate:

```text
0 probes
1 probe
2 probes
3 probes
```

For each report:

```text
worst-family fake recall
balanced accuracy
clean FPR
fake-to-real flip rate
p50/p95 latency
```

Goal:

> Find the minimum evidence budget that captures most of the robustness gain.

---

## Experiment 4 — Individual probe value

Measure:

```text
JPEG only
crop only
resize only

JPEG + crop
JPEG + resize
crop + resize
```

This tells us which probe should normally come first.

---

## Experiment 5 — Adaptive stopping

Train a lightweight:

```text
STOP / CONTINUE
```

decision after each evidence step.

A simple objective can trade off:

```text
classification risk
+
lambda * number_of forward passes
```

No complex reinforcement learning is required.

---

## Experiment 6 — Optional next-probe selector

Only if enough time remains:

```text
STOP / JPEG / CROP / RESIZE
```

If the fixed best order is nearly as strong, ship the fixed order.

Complexity itself is not innovation.

---

# 12. Methodological warning — protect the project's strongest advantage

The current evaluation methodology is unusually rigorous:

- architecture frozen before untouched test;
- frozen threshold;
- protected test set;
- FPR-matched adversarial baseline control;
- negative results published;
- contamination discovered and corrected;
- published numbers bound to committed artifacts.

Do **not** ruin this by training the new gate on internal-test outcomes and then reporting that same test as untouched.

The test-family results have already been inspected.

Therefore:

```text
design/train -> train/dev only
final claim  -> genuinely untouched evaluation
```

If an experiment is run on the existing internal test after this point, label it:

```text
POST-HOC EXPLORATORY
```

Possible new held-out validation can come from a new untouched split or another permitted benchmark.

Methodological credibility is more valuable than squeezing out another couple of points.

---

# 13. Known limitations that should stay in the submission

## No proven unseen-generator generalization

Current corpus is single-source SID-Set and lacks generator identity.

Do not claim unseen-generator generalization unless separately measured.

## Dataset-format shortcut was discovered

Originally:

```text
real -> JPEG
fake -> PNG
```

File extensions hid the actual byte format.

The team detected the issue, normalized encoding, and added a mandatory quality-only control.

This is a strength of the methodology and should be explained.

## Reference set contains many duplicates

The supplied DALL-E set contains substantial exact duplication.

Evaluation should deduplicate and bootstrap over unique images rather than pretending duplicates are independent samples.

Again, this is a research-quality insight, not something to hide.

---

# 14. Suggested final UI

For every image show:

```text
CLASS
AI / REAL

CLASS SCORE
calibrated model output

RELIABILITY
trustworthiness estimate

PROBES USED
none / JPEG / resize / crop

SELECTED POLICY
raw forensic policy
or
robust degradation policy

FINAL ACTION
DECIDE
or
DEFER
```

Easy case:

```text
AI-GENERATED
Score: 0.94
Reliability: HIGH

Probes used: none
Selected policy: raw forensic policy
```

Hard case:

```text
UNCERTAIN — leans AI
Score: 0.63
Reliability: LOW

Probes used:
JPEG
resize
crop

Selected policy:
robust degradation policy

Action:
DEFER FOR REVIEW
```

This makes the architecture visible in the demo.

---

# 15. How to frame the innovation

Do **not** claim:

```text
"We invented uncertainty."
"We invented routing."
"We invented robust AI-image detection."
```

The more defensible claim is:

> **Our contribution is an active forensic decision architecture built around counterfactual self-probing. Instead of treating image transformations only as training augmentation or evaluation corruption, we use controlled transformations as diagnostic actions at inference time. Their response pattern determines which decision policy is trusted, whether more forensic evidence should be acquired, and whether the system should abstain.**

---

# 16. Suggested one-sentence claim

> **Active Forensics turns AI-image detection from a passive one-shot classifier into an active diagnostic process that probes the current image, measures how forensic evidence responds to benign transformations, selects the most reliable decision policy, and spends additional computation only when needed.**

---

# 17. Suggested 30-second judge explanation

> Modern AI-image detectors often work well on clean images but silently fail after compression, noise, resizing, or reposting. We first built a transformation-aware robustness layer that dramatically raised worst-case fake recall. But our experiments showed something more interesting: the raw detector remained stronger on some degradations, while the robust policy dominated on JPEG and noise. We then tested two independent forensic rescue models and rejected both because the hardest transformations destroyed the same high-frequency evidence those models relied on. That led us to Active Forensics. Instead of adding more passive detectors, our system actively probes an image with small counterfactual transformations, measures how its own forensic evidence responds, chooses the most trustworthy decision policy, spends additional compute only when needed, and defers when the evidence remains unreliable.

---

# 18. Why this maps well to the TechJam rubric

## Technical Execution — 35%

Strong evidence already exists:

```text
exact transformation harness
frozen primary
robust MLP
protected evaluation
reliability head
unified prediction service
tests
artifact-bound results
```

Adaptive probing and dual-policy routing extend this rather than replacing it.

## Innovation & Problem Insight — 20%

Strongest story:

```text
discover transformation failure
-> build robust correction
-> attempt multi-expert rescue
-> measure LOTA failure
-> measure PGC failure
-> diagnose shared high-frequency weakness
-> discover raw/robust policy complementarity
-> convert transformations into active diagnostics
```

## Impact & Relevance — 20%

Real systems care about:

```text
false accusations
silent fake-to-real failure
degraded reposts
compute cost
uncertain inputs
```

The proposed architecture addresses all five.

## Feasibility & Practicality — 15%

Instead of stacking huge detectors:

```text
one 21.8M primary
+
tiny learned heads
+
extra forward passes only when useful
```

## Presentation — 10%

The demo naturally shows:

```text
base result
probe sequence
forensic response
selected policy
reliability
final decision
```

---

# 19. Recommended priority

If time is limited:

```text
1. Preserve the current frozen result.
2. Verify raw-vs-robust complementarity on DEV.
3. Build the tiny dual-policy gate.
4. Run 0/1/2/3-probe ablations.
5. Implement simple adaptive stopping.
6. Update UI to expose active probing.
7. Preserve reliability / deferral.
8. Add next-probe selection only if the simpler system works.
```

Do **not** prioritize:

```text
another large pretrained detector
reintroducing LOTA
reintroducing PGC
large-scale backbone fine-tuning
complex reinforcement learning
```

unless the active-probing approach fails and enough time remains.

---

# 20. Kill criteria

## Dual-policy gate

Keep only if it improves genuinely held-out results over:

```text
raw primary
robust MLP
simple static fusion
```

Kill it if it only memorizes transformation labels or fails to reproduce on dev.

## Adaptive probing

Keep only if it preserves most of the robustness while materially reducing average probe count / latency.

A result like:

```text
3-probe system:
worst recall ~0.826
always 3 probes

adaptive system:
worst recall ~0.81-0.82
average ~1.2-1.8 probes
```

would be a compelling feasibility trade-off.

## Next-probe selector

Kill if a fixed best order performs similarly.

---

# 21. Final strategic recommendation

Do **not** pivot away from the working system.

The existing robustness result is too strong and too well defended.

Evolve it:

```text
CURRENT SYSTEM
      |
      v
reinterpret self-probes as
ACTIVE FORENSIC DIAGNOSTICS
      |
      +
DUAL-POLICY ROUTING
      |
      +
ADAPTIVE PROBE STOPPING
      |
      +
existing reliability / deferral
```

That changes the project from:

> “A robust correction layer on top of Community Forensics”

into:

> **“An active forensic detector that interrogates its own evidence and adapts both its decision policy and compute to the degradation state of the current image.”**

That is the strongest current combination of:

```text
measured results
innovation
feasibility
technical depth
judge narrative
```

without gambling the project on another unproven model.

---

# 22. Binding principle

> **Do not add architecture for appearance. Use measured failures to decide what the system should become.**

The evidence currently says:

```text
more passive high-frequency experts -> failed
self-probed robustness              -> worked
raw and robust policies             -> complementary
reliability / deferral              -> useful
fixed full probing                  -> expensive
```

Therefore the natural next architecture is:

# **Active self-probing + policy routing + adaptive compute + calibrated deferral**
