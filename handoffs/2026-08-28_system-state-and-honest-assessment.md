# Adaptive Forensic Cascade — system state, results, and honest assessment

**Date:** 2026-08-28, updated 2026-08-29 · **Author:** Claude (AGENT-A) · **Purpose:** shareable context dump —
what was built, what the numbers are, what succeeded, what failed, and where it falls short of
the original design.

> Every number here is measured on protected data and backed by a committed artifact. A
> regression test (`tests/test_published_numbers.py`) asserts these values still match their
> artifacts, so this document cannot silently drift from the results.

---

## 1. One-paragraph verdict

The system works and the core claim is unusually well defended: worst-case fake recall under
image degradation goes from **0.1227 to 0.8258**, and survives an adversarial control where the
baseline is handed a threshold fitted on the test set itself (**+0.4916**, CI95 [+0.475, +0.508]).
It generalised — dev predicted 0.8144, the untouched test gave 0.8258. On top of that sit two
capabilities that earned their place by measurement: an **abstention** policy (defer 20% →
accuracy 0.9090→0.9317) and an **audit mode** whose verdict-retention signal predicts a wrong
answer *better than the reliability head trained for the job* (AUROC 0.8696 vs 0.7206).
**But it delivers less than the architecture promised in one important way:** the designed
two-stage cascade with adaptive escalation to a heavier second expert does not exist. What
ships is a *one-stage* system that escalates to a **human**. **Five separate ideas were built or
specified, measured, and cut on evidence** — LOTA, PGC, our own self-probes, occlusion evidence
maps, and rung gating. The methodology is stronger than planned; the architecture is narrower.

## 2. What the system actually is

```
image
  │
  ├─ canonical decode (EXIF strip, RGB, provenance hashes)
  │
  ├─ CF-384 primary detector ──────────────► raw logit / p_fake      21,811,969 params (frozen)
  │
  ├─ quality descriptors (blur var-of-Laplacian, blockiness,
  │    noise sigma, photometric stats)
  │
  ├─ self-probes: re-score under JPEG q92 / crop 0.96 / resize 0.90
  │    → probe mean/std/range/max-delta/flip  (3 extra forward passes)
  │
  └─ ROUTER (MLP + worst-group loss)  ──────► corrected p_fake        1,827 params (ours)
         38 features, geometry excluded          │
         └─ reliability head (17 params) ───────► reliability → ABSTAIN if < 0.866080
                                                  │
                                          verdict + reliability + defer flag
                                                  │
  AUDIT MODE (optional, 20 extra passes) ─────────┤
    ├─ 20-condition stress grid → verdict retention → Forensic Robustness Certificate
    └─ degradation reporter (775 params) → "detected image history: JPEG compression (93%)"
```

- **Shipped total: 21,814,571 parameters** — **1.09%** of the 2B cap. Our own trainable weights are
  0.012% of the system. The contribution is the decision layer, not scale.
- **One decision path.** Gradio UI, `scripts/infer_dir.py` (required deliverable) and the eval
  harness all import the same `PredictionService`. There is no separate demo code path.
- **Single threshold across all 20 conditions**: `0.4667367651127279`, frozen in a validated,
  hashed artifact. The service refuses to start if config and artifact disagree.

### What is NOT in the system, despite being designed
- No second expert. No multi-expert fusion. No adaptive/selective compute.
- No generator-identity modelling (the corpus lacks generator labels).
- `disagreement.*` features exist in the vector but are always "absent" with a zero indicator,
  because there is only one expert.

---

## 3. Headline results — untouched internal test

**3,000 sources × 20 conditions = 60,000 rows, 0 decode failures.** Nothing was fitted on these
sources: not weights, not the threshold, not the feature set, not the rung choice. Architecture was
frozen first, then this cache was built stamped `role=evaluation`, then the evaluator ran.

| | worst-family recall | clean recall | clean FPR | overall acc |
|---|---|---|---|---|
| **Cascade (shipped)** | **0.8258** | 0.9613 | 0.0833 | 0.9090 |
| Primary @ 0.5 (published default) | 0.1227 | 0.7107 | 0.0027 | 0.7807 |

Worst family is `noise` for both; worst condition `noise_s0.10` (cascade 0.790, primary 0.007).

**Selection did not overfit:** dev 0.8144 → test 0.8258. It went *up*.

### The headline is not FPR-matched, so we matched it

The two arms sit ~30× apart in clean FPR, so the naive +0.70 overstates. We gave the baseline a
threshold **fitted on the test set itself** — leakage granted to it and denied to us:

| baseline arm | thr | worst-family | clean FPR | cascade advantage |
|---|---|---|---|---|
| Primary @ 0.5 | 0.5000 | 0.1227 | 0.0027 | +0.7034 |
| Primary @ dev-fitted thr | 0.1273 | 0.1827 | 0.0127 | +0.6433 |
| **Primary @ our clean FPR, test-fitted** | 0.0058 | 0.3342 | 0.0833 | **+0.4916 [+0.475, +0.508]** |

**+0.49 is the number we report.** A second implementation matching on *overall* FPR agrees
independently at +0.5045.

### Per-family — and where the baseline beats us

| family | cascade | primary @0.5 | primary @ matched FPR |
|---|---|---|---|
| crop | 0.9620 | 0.7600 | 0.9593 |
| blur | 0.9471 | 0.7264 | **0.9709** |
| color | 0.9438 | 0.7367 | **0.9647** |
| resize | 0.9417 | 0.7120 | **0.9763** |
| jpeg | **0.9047** | 0.3703 | 0.8102 |
| **noise** | **0.8258** | 0.1227 | 0.3342 |

**Read the third column.** At matched FPR the plain baseline *beats* the cascade on blur, colour
and resize and ties on crop. **Our entire advantage is `noise` and `jpeg`** — the families where the
primary collapses. We raise the floor, not the ceiling. On clean images we gain nothing:
0.9613 vs a matched 0.9620.

### Stability
Of sources decided *correctly* when clean, how often does a transform flip the verdict?
Cascade **5.30%** of fake views / 5.35% of real. Primary **26.64%** of fake / 0.43% of real
(its apparent stability on reals is an artefact of calling almost everything real).

---

## 4. Abstention — the Phase-3 feature that DID work

Reliability head predicts *whether its own decision is correct* at the frozen operating point.
Fitted in a strict second stage after threshold freeze, with every classifier parameter frozen —
the script asserts `max |Δ p_fake| = 0.0`, so adding self-assessment moved no verdict.

Policy pre-registered **on dev before the test was consulted**: smallest abstention rate whose
accuracy-on-kept beats full coverage by ≥2 points. Selected 20% coverage, frozen as a reliability
**value** (0.866080), never a percentile (a percentile would re-tune itself on each new batch).

| internal test | coverage | accuracy | worst-family |
|---|---|---|---|
| decide everything | 1.000 | 0.9090 | 0.8258 |
| **defer least-reliable 20%** | 0.799 | **0.9317** | **0.9136** |

Deferred images score **0.8191** vs 0.9317 kept — it declines on images it would have got wrong.
Dev predicted +2.22 accuracy points; test delivered **+2.27**, at coverage 0.799 vs 0.80 frozen.

**A near-miss worth recording:** the first fit reported dev AUROC **0.3659** — worse than random,
selective-risk curve running backwards — and looked like a clean negative result. It was
*underfitting*: 40 steps reaching loss 0.384 when a constant predictor at the 0.91 base rate scores
0.303. At 3,000 steps it converges (train AUROC 0.6883, dev 0.6842). The script now always reports
train AUROC and the constant-predictor loss so "no signal" can never again be confused with "not
converged."

### Abstention's blind spot (published as a limitation)
Abstain rate tracks **noise** almost perfectly and is nearly blind to **blur**:

| condition | fake recall | FPR | abstain rate |
|---|---|---|---|
| clean | 0.9613 | 0.0833 | 7.2% |
| noise σ=0.05 | 0.8087 | 0.1787 | 85.9% |
| noise σ=0.10 | 0.7900 | 0.2967 | 98.6% |
| jpeg q30 | 0.8447 | 0.1187 | 68.0% |
| **blur σ=2.0** | 0.9533 | **0.1260** | **0.03%** |

Blur makes an image look *cleaner*, so the head reads high quality and stays confident.
Consequently **every one of our worst individual errors carries reliability 0.91–0.99 and would NOT
be deferred.** Abstention removes the uncertain middle, not the confidently-wrong tail. A deployment
treating "did not abstain" as "safe to automate" would be wrong in exactly the cases that matter.

---

## 4b. Audit mode — added 2026-08-29

**The evaluation harness turned out to be the best confidence signal.** Running the
20-condition grid on one image and counting how many conditions preserve the verdict predicts
a wrong verdict better than the reliability head we trained for it:

| signal | AUROC predicting a wrong clean verdict |
|---|---|
| reliability head | 0.7206 |
| **verdict retention** | **0.8696** |
| combined | 0.8863 |

It fixes the blind spot §4 documents. Of the **157** sources the head passes confidently but
gets wrong, mean retention is **14.40/20** vs **19.00/20** for confident-and-correct; flagging
`retention < 18` catches **72.6%** of them while deferring 17.3%. The two fail differently —
the head reads quality descriptors so it tracks noise and is blind to blur; retention measures
the verdict itself. Grades are the measured relationship, not chosen labels:

| retention | grade | clean verdict correct | share |
|---|---|---|---|
| 20/20 | HIGH | 99.1% | 61.4% |
| 18–19 | MEDIUM | 94.9% | 20.9% |
| 15–17 | LOW | 84.9% | 10.4% |
| ≤14 | VERY LOW | 60.6% | 7.4% |

Costs 20 forward passes, so it is explicitly audit mode, not the default path.
Artifact: `results/robustness/retention-signal.json`.

**Degradation reporter** (775 params): names the transformation family from the eight cached
quality descriptors — dev balanced accuracy **0.7332** vs 0.143 chance. Geometry excluded on
purpose (a real upload has no known original size) and class-weighted (unweighted it reported
0.00 recall on `clean`, which was imbalance, not inseparability). It is an explanation and
structurally cannot reach the verdict.

## 5. What FAILED — and why the failures are informative

### 5.1 The second expert failed twice, for the same structural reason

| candidate | licence | params | outcome |
|---|---|---|---|
| **LOTA** (ICCV 2025) | MIT | 23.5M | Reads the **least-significant-bit plane** of a random 32×32 patch. Non-deterministic (0.31 score swing on one image). AUROC 1.000 → **0.592** on JPEG q95 re-encode, fake recall → **0.000**. Rejected. |
| **PGC** (Apache-2.0) | Apache-2.0 | 306.7M | Loads with 0 missing/unexpected keys, **fully deterministic** (spread 0.0). But P(correct \| cascade wrong) = **0.5426**, correction−harm = **−2451**. Rejected. |

PGC was given a fair hearing before being cut. Beyond wholesale replacement we tried
confident-override at four tail widths, logit-space blending at three weights, and family-gated
rescue. **The best variant nets +1 across 12,000 dev rows** — indistinguishable from zero. There is
no operating point where it helps.

**The reason generalises, and it is the sharpest finding in the project.** A rescue only ever sees
images the reliability head deferred, and that pool is dominated by `noise` (6,578) and `jpeg`
(3,950). LOTA reads the LSB plane; PGC reads a YCbCr quantization residual. Both live in the
high-frequency band — exactly what noise and heavy JPEG destroy.

> **You cannot rescue noise-destroyed evidence with a detector that reads evidence from the noise band.**

PGC is genuinely *better* than our cascade where degradation is photometric (colour 0.9532 vs
0.9159; blur 0.9762 vs 0.9286) — but those families are a sliver of the deferred pool, so the wins
are swamped. Artifact: `results/pgc/rescue.json`.

### 5.1b Our own self-probes buy nothing (2026-08-29)

The shipped system re-scores every image under three mild perturbations — **3 of its 4 forward
passes, ~110 ms of its 128 ms**. An 8-arm × 3-seed dev ablation found **no probe budget
distinguishable from any other, including using none at all**; every difference sits inside the
seed spread (sd 0.0036–0.0123). The pre-registered rule selected **zero probes**. The robustness
gain comes from the quality descriptors and the worst-group objective, not from self-probing.
Independently confirms the earlier 24k pilot. Artifact: `results/probe-ablation/dev-results.json`.

### 5.1c Occlusion evidence maps are void (2026-08-29)

Patch-occlusion attribution was killed by a guard written *before* the experiment: two occlusion
operators (mean-fill, blur) produce maps correlating at only **0.261**, so the method measures
the artefacts its own masks create. Predicted from first principles — this detector reads
high-frequency traces, and masks manufacture high-frequency content.
Artifact: `results/evidence-audit/validation.json`.

### 5.1d Rung gating is dead on its ceiling (2026-08-29)

`mlp` beats `mlp+wg` on accuracy and clean FPR, so gating between them looked promising. An
**oracle** that always picks the correct rung — unbeatable by any learnable gate — adds
**+0.0047** worst-family recall. The rungs agree on 96.9% of rows. Killed in eight minutes
without building anything. Artifact: `results/probe-ablation/rung-complementarity.json`.

### 5.2 A constraint we set ourselves did not hold
Threshold was selected under a clean-FPR cap of **0.0756**; on unseen data it measured **0.0833**.
A 300-source pre-flight had flagged it, and the pre-registered response was honoured: **report it,
do not re-tune.** The threshold is unchanged.

### 5.3 A rung we did not ship looks better on average

Full ablation, every rung refit with the freeze seed/split (each reproduces its dev number exactly)
then scored once on the untouched test at its own dev-fitted threshold:

| rung | params | thr | dev worst | **test worst** | clean FPR | overall acc |
|---|---|---|---|---|---|---|
| quality_only | 17 | 0.49680 | 0.5076 | 0.5402 | **0.4393** | 0.6542 |
| static_average | 0 | 0.12725 | 0.1849 | 0.1827 | 0.0127 | 0.8351 |
| logistic | 117 | 0.46491 | 0.6860 | 0.6902 | 0.0713 | 0.8943 |
| mlp | 1,827 | 0.42994 | 0.7587 | 0.7664 | 0.0500 | **0.9213** |
| **mlp+wg (shipped)** | 1,827 | 0.46674 | 0.8144 | **0.8258** | 0.0833 | 0.9090 |

Two disclosures this forces:
1. **`quality_only` is not a real detector** — it reaches 0.5402 worst-family only by calling
   **43.9% of clean real photographs AI-generated**. This is the control added after the format
   confound, and it does its job.
2. **Plain `mlp` has higher overall accuracy (0.9213 vs 0.9090) and lower clean FPR (0.0500 vs
   0.0833)** than the shipped rung, and would *not* have breached the clean-FPR cap. We did **not**
   switch: the rule was pre-registered on worst-case robustness, and re-picking after seeing the test
   is the exact leakage the protocol exists to prevent. Published so a reader can disagree with the
   objective rather than be misled about its price.

### 5.4 The training corpus had a shortcut that would have invalidated everything
Both classes were drawn from one dataset to avoid dataset artefacts. Not enough: inside SID-Set,
**every real is JPEG and every fake is PNG**, so file format predicted the label for **100.00% of
15,000 sources** — and every file carried a `.jpg` extension regardless of its bytes, which is why it
went unseen. `blockiness` alone separated the classes at AUROC 0.89. Fix: re-encode every source to
one container (blockiness AUROC 0.90 → 0.64), plus a **mandatory quality-only baseline in every
comparison**. Residual remains: `noise_sigma` (0.82) is container-independent and reflects a genuine
photo-vs-generated difference.

### 5.5 The reference benchmark is 42% duplicates
Of 8,843 supplied DALL-E images only **3,719 are unique**; 5,124 files are byte-identical copies,
some repeated 5×. COCO val2017 is clean (5,000/5,000). Scored per file, 1,808 images are weighted up
to 5× and CIs come out far too narrow. We deduplicate before scoring, bootstrap over **unique images
never files**, and report both conventions.

---

## 6. Operating cost

| path | p50 | p95 |
|---|---|---|
| CF-384 alone (baseline) | 18.8 ms | 20.0 ms |
| **Full cascade (shipped)** | **127.9 ms** | **145.3 ms** |
| PGC alone (parked) | 54.3 ms | 55.3 ms |

Peak RSS ≈ 1.24 GB. **~6.8× the baseline**, almost all of it the three probe forward passes; the
1,827-parameter head's own arithmetic is negligible. This is precisely what adaptive escalation was
meant to amortise — it failed its gate, so the shipped system pays the cost on every image.

---

## 7. Expectation vs delivery — the honest ledger

| | planned | delivered |
|---|---|---|
| Primary detector + adapter | ✅ | ✅ CF-384, MPS≡CPU verified |
| 20-condition transform grid, golden-tested | ✅ | ✅ |
| Quality descriptors + self-probes | ✅ | ✅ |
| Trained router / fusion ladder | ✅ | ✅ 7-rung ladder, frozen selection |
| Calibration + single frozen threshold | ✅ | ✅ |
| Abstention / reliability | ✅ | ✅ **works, generalised** |
| **Second expert (LOTA/WaRPAD)** | ✅ | ❌ **two candidates, both rejected on evidence** |
| **Selective rescue / adaptive compute** | ✅ | ❌ **built, measured, failed its gate** |
| **Complementarity analysis** | ✅ | ⚠️ done, but the answer was "no complementarity" |
| Gradio demo + stress panel | ✅ | ✅ primary→corrected, reliability, DEFERRED banner, certificate, degradation |
| Audit mode / robustness certificate | not planned | ✅ **exceeded scope** — retention beats the trained reliability head |
| Degradation explanation | not planned | ✅ **exceeded scope** — 0.7332 balanced accuracy |
| Required deliverables (robustness, error analysis) | ✅ | ✅ both regenerated on protected data |

**Below expectation:** the architecture. It is a one-stage system named after a two-stage one, the
gains are concentrated in two of six families, nothing is gained on clean images, and we pay full
latency on every image with no adaptive path.

**At expectation:** the core robustness result, and it is solid.

**Above expectation:** the methodology — pre-registered rules, an FPR-matched control invented
against ourselves, a genuine one-shot test, contamination proven by set intersection, negative
results published rather than dropped, and a regression test binding every published number to its
artifact.

**Scope limit to state plainly:** the corpus is single-source (SID-Set) with no generator identity,
so **we cannot claim unseen-generator generalisation.** That was never in scope, but it bounds what
the result means.

---

## 8. Open / pending

- **The sealed reference run is IN FLIGHT** (~20,000 of 174,380 rows at time of writing). The
  threshold was frozen on SID-Set; COCO val2017 reals + DALL-E 3 fakes are a different distribution
  and the frozen operating point may sit badly there. **If it comes back weak, that is the result
  and it gets reported — no re-tuning.** So "it works" is currently established on our own held-out
  data; the organizers' benchmark is still an open question.
- **Codex (AGENT-B) has not reviewed** the B-024 repair or ~25 `[relay]` entries. Everything built
  on 28 Aug is self-reviewed; the rulebook wants peer review at gates and it has not happened.
- **Owner-only actions:** make repo public, approve MIT, verified clean-history force-push (remote
  `main` still holds raw-image history), record the demo video, link it on Devpost.
- **Trademark call:** the strongest protected false-positive case shows fire apparatus with
  "HILLSBORO FIRE & RESCUE" legible. Lower risk than the already-banned FedEx/Polar Air liveries, but
  it is Mehul's call.
- **Discrepancy on record:** `CLAUDE.md` says the sealed set is "COCO val2017 4,998"; the directory
  holds **5,000**. Recorded, not silently resolved.

---

## 9. Where the evidence lives

| artifact | contents |
|---|---|
| `results/internal-test/results.json` | the one-shot headline + FPR-matched control |
| `results/internal-test/fpr-matched-baseline.json` | independent second implementation of the control |
| `results/internal-test/abstention.json` | frozen abstention policy measured on the test |
| `results/internal-test/ablation.json` | full rung ladder on the untouched test |
| `results/pgc/rescue.json` | the negative rescue result |
| `results/robustness/error-taxonomy.json` | FP/FN taxonomy with named representative files |
| `results/router-fitting-v2/freeze.json` | dev selection, stamped `NOT_A_HEADLINE_RESULT` |
| `results/router-fitting-v2/router_reliability.pt` | the shipped 17 KB checkpoint |
| `results/sealed/` | the sealed reference run (in flight) |
| `deliverables/` | error-analysis note, Devpost draft, video script, submission checklist |
| `tests/test_published_numbers.py` | binds every published number to its artifact |

**Suite: 699 passing.** Repo: `MEHUL-MODI-Git/TechJam_2026_Track_5` (**private** — must not be made
public until the history and licence gates clear).
