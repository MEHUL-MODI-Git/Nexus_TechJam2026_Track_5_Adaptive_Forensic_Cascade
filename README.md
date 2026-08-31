# Adaptive Forensic Cascade

**Robust detection of AI-generated images under real-world transformations.**
TikTok TechJam 2026 — Track 5.

**▶ Demo video: https://youtu.be/KUedfboxC-Q**

> **Status (31 Aug 2026).** The **frozen cascade ships and is served on every
> path** — CLI, batch and UI all call one `PredictionService` with the frozen
> router, one threshold (0.4667367651) and abstention. It has been evaluated once
> on an untouched 3,000-source internal test (§7), confirmed on a second holdout,
> and scored once on the organizers' sealed reference subset after the freeze.
>
> **What is not finished is release, not engineering:** the demo video, the MIT
> licence approval, and the clean remote-history push are the owner's decisions,
> and a peer review gate remains open against the reproduction and provenance
> surfaces — not against the measured results, which were independently checked
> and not rejected. Every number here has a
> committed artifact behind it, and the ones that went against us are in §7 and
> §8 beside the ones that did not.

---

## 1. Overview

Detecting AI-generated images is close to solved on clean benchmark data. It is
not solved on the internet, where images arrive re-compressed, cropped,
filtered, and resized. This track exists because of that gap, and our work
targets it directly.

The central problem is not simply that accuracy drops after a transformation.
It is that a fixed detector **does not know when it has stopped being reliable**.
We measured this on our own smoke set: under a Gaussian blur of σ=2.0, our
primary detector's AUROC falls to 0.647 — near chance — while its false-positive
rate rises to 0.640. The model does not become uncertain. It becomes
*confidently wrong*, labelling genuine photographs as AI-generated.

The target architecture builds a system around frozen detectors rather than
fine-tuning another detector:

```text
image
  -> canonical decode (EXIF, RGB, no recompression)
  -> quality descriptors (blur / blockiness / noise / geometry)
  -> frozen expert detector(s)          <- downloaded, never fine-tuned
  -> mild self-probes on the primary    <- how fragile is this score, here?
  -> OUR reliability/fusion router       <- trained, frozen, and SERVED (§7)
       reliable  -> calibrated verdict
       uncertain -> behavioural rescue -> rescued verdict
  -> calibrated score + reliability readout
```

**The router and the reliability layer are our proposed contribution.** The expert
detectors are public, frozen checkpoints; we do not claim them. What we claim
today is their implementation and the evaluation protocol that makes every
performance claim checkable. The app serves the trained router, its frozen
threshold and the abstention decision (§7). It does **not** serve a rescue path:
that was built, measured and cut on evidence (§7).

## 2. What is built today

| Component | Status |
|---|---|
| Canonical decode (EXIF, RGB, provenance hashes) | ✅ built, tested |
| All 20 official transform conditions, deterministic + golden-tested | ✅ built, tested |
| Community Forensics 384 expert adapter | ✅ built, tested |
| Importable prediction service (one decision path for CLI/UI/batch) | ✅ built, tested |
| Quality descriptors | ✅ built, tested |
| Mild self-probes | ✅ built, tested |
| Calibration + threshold-selection code under a frozen objective | ✅ built, tested; **threshold fitted on the fitting split's train half** and frozen — the rung was selected on held-out dev, the threshold value was not (disclosed in §6) |
| Reliability head + abstention (defer to human) | ✅ fitted in a frozen second stage; policy pre-registered on dev, verified on the test |
| Adaptive rescue to a heavier second model | ❌ built and measured; **failed its gate**, reported as a negative result (§7) |
| Router (7-rung ladder: quality-only → static avg → prob mean → fixed weights → logistic → MLP → +worst-group) | ✅ implemented, repaired; fitted, frozen and shipped as `results/router-fitting-v2/router_reliability.pt` (1,827 params total, **of which** 17 are the second-stage reliability head, 18 KB) — the artifact `configs/predict.yaml` loads; `router.pt` is the earlier stage-1 checkpoint, kept for provenance |
| Full-grid baseline run (8,000 predictions) | ✅ complete |
| Evaluation harness | ✅ diagnostic and headline paths exercised; one-shot internal test + full ablation ladder |
| Second expert | ❌ **two** candidates integrated and both rejected on measured evidence (LOTA, PGC) — see §7 |
| Protected 15,000-source corpus, format-canonicalized, contamination-audited, split 12k fitting / 3k untouched test | ✅ built and verified |
| Router trained on that corpus | ✅ trained, frozen, evaluated once on the untouched 3k test, **and served on the live path** (§7) |

## 3. Setup

Requirements: Python 3.12, [`uv`](https://docs.astral.sh/uv/), ~2 GB disk for
the model cache. Apple Silicon (MPS), CUDA, and CPU are all supported; the
device is selected automatically.

```bash
uv sync                      # create .venv and install pinned dependencies
.venv/bin/pytest -q          # run the test suite
```

The expert checkpoint downloads automatically from the Hugging Face Hub on
first use (87 MB, MIT licensed).

**This was verified, not assumed.** `scripts/verify_clean_checkout.py` clones this
repository into a scratch directory that shares nothing with the development tree
and, from inside that clone, runs the suite, scores an image and runs the batch
interface. At `578efa7`: **756 passed, 14 skipped, 0 failed**;
the checkpoint downloaded into the clone's own empty cache; `predict.py` and
`infer_dir.py` both returned 0, the latter scoring 6 images with 0 failures.
The 14 skips are tests that need the git-ignored feature caches and the
sealed dump, and they say so. Artifact: `results/clean-checkout/verification.json`.

*(The skipped tests are why this check exists: a suite that skips what a clean
checkout cannot run will pass in a clean checkout whether or not the system works.)*

## 4. Usage

**Score one image**

```bash
.venv/bin/python scripts/predict.py path/to/image.jpg
.venv/bin/python scripts/predict.py path/to/image.jpg --transform jpeg_q30 --json
```

**Score a directory** (the batch interface required by the brief)

```bash
.venv/bin/python scripts/infer_dir.py INPUT_DIR --output predictions.json
```

Emits a JSON array of `{"image_path": ..., "pred": ...}`, where `pred` is a
probability in `[0,1]` and higher means more likely AI-generated. One row is
emitted per recognised image, ordered deterministically. A file that cannot be
decoded receives `"pred": null` with an `"error"` field — never an invented
score — so the output can always be zipped back to the input list. Use
`--errors strict` to fail loudly instead.

Add `--detailed` for a full report per image. The brief's addendum binds
`image_path` and `pred` to be present for every image and permits reliability
fields as **extra keys**, so `--detailed` adds them alongside — a harness reading
only the two required keys is unaffected:

```bash
.venv/bin/python scripts/infer_dir.py INPUT_DIR --output predictions.json --detailed
```

Each row then also carries the verdict, the **raw detector score and the router's
correction to it**, the self-assessed reliability, whether the system defers to a
human, any detected damage, and image metadata. It prints a digest to stderr:

```
image                                       verdict    score      raw  reliab.
bird_jpeg_q30.png                      AI-GENERATED   0.9458   0.0191    0.788  <- corrected
board_clean.png                        AI-GENERATED   0.9625   0.7070    0.956
board_jpeg_q70.png                     AI-GENERATED   0.9062   0.0993    0.927  <- corrected

3 scored | 3 AI-generated | 2 rescued by the router | 1 deferred to a human
```

**Full forensic report for one image** (audit mode)

```bash
.venv/bin/python scripts/audit_image.py path/to/image.jpg
.venv/bin/python scripts/audit_image.py path/to/image.jpg --json
.venv/bin/python scripts/audit_image.py path/to/image.jpg --no-audit   # fast path
```

Prints the verdict, **what the raw detector alone would have said**, the
self-assessed reliability, the detected image history, and the robustness
certificate. Example on a corpus image the raw detector misses:

```
VERDICT           ◆ AI-GENERATED
score             0.5739  ███████████·········  (threshold 0.4667)
raw detector      0.0012  ····················  (+0.5727 after correction)
                                                 <- the router changed this verdict
reliability       0.875   ██████████████████··
IMAGE HISTORY     no strong degradation detected (50% confidence)

verdict retention 11 / 20   ███████████·········
grade             VERY LOW — correct for 60.6% of held-out sources
worst case        0.072 at jpeg_q30
```

The raw detector would have called this real at 0.0012; the router rescues it —
and the certificate then declines to oversell that rescue. Audit mode costs 80
forward passes (~3.0 s); `--no-audit` and `infer_dir.py` stay on the fast path.

**Run the demo UI**

```bash
.venv/bin/python -m src.app
```

## 5. Reproducing our results

Every public number must come from a committed artifact, and one command checks
all of them:

```bash
.venv/bin/python scripts/run_eval.py --config configs/frozen.yaml
```

This is the Phase-4 exit test from the build plan. `configs/frozen.yaml`
records, for each of the **11 published tables**, the artifact and its SHA-256,
the inputs it was computed from and theirs, and the command that regenerates it.
The check verifies **both** — an artifact that still matches while its inputs
moved is worse than a mismatch, because it looks like agreement. On this
repository it reports:

```
11 verified, 0 verified with absent inputs, 0 drifted, 0 missing
```

Entries are labelled `input-bound` (artifact and inputs both hashed) or
`artifact-only` — the latter for the ops measurement and the clean-checkout
proof, which describe *this machine* and have no tracked input to bind to.

Add `--regenerate` to re-run each regenerable command and report any artifact
whose hash moves. Drift is reported as a finding, not smoothed over.

**The sealed reference entry is `summary_only` and the verifier refuses any
sealed entry that is not.** The organizers' subset is scored exactly once and
already was; a reproduction tool that *could* re-run inference on it would be a
defect, not a convenience.

```bash
# Transform-protocol golden tests (fail if any transform changed)
.venv/bin/pytest tests/test_transforms_golden.py -q

# Prove a fresh clone runs: clones, runs the suite, scores images
.venv/bin/python scripts/verify_clean_checkout.py
```

<details>
<summary>Rebuilding a protected table from raw data (needs the git-ignored caches)</summary>

The commands are recorded per table in `configs/frozen.yaml`. For example the
headline internal-test result:

```bash
.venv/bin/python scripts/evaluate_internal_test.py \
    --cache data/feature_cache/internal-test-v2 \
    --checkpoint results/router-fitting-v2/router_reliability.pt \
    --threshold-artifact results/router-fitting-v2/threshold-artifact.v1.json
```

The feature caches are git-ignored (hundreds of MB) and rebuilt with
`scripts/build_feature_cache.py`. The early 400-source smoke grid
(`results/grid-smoke-v1/`) is retained for history only — it used a placeholder
threshold and a since-disowned corpus comparison, and **no published number
comes from it**.
</details>

The smoke dataset can be rebuilt with `scripts/download_smoke_sources.py` and
`scripts/prepare_smoke_dataset.py`; use each command's `--help` for paths. Its
selection seed and source revisions are recorded. Raw images are absent from the
clean local history and must also be removed from the private remote's old
history before publication.

### Reproducibility guarantees

- **Deterministic transforms.** Every condition is a pure function of
  `(image, condition_id)`. Noise seeds derive from the image's own SHA-256, so
  a rerun on another machine reproduces the same pixels.
- **Golden tests.** 60 checked-in hashes fail the build if any transform's
  output changes, and a version tripwire fails if behaviour changes without a
  `PIPELINE_VERSION` bump.
- **Backend consistency.** MPS and CPU agree to |Δlogit| < 5e-5 on this
  checkpoint (verified, not assumed).
- **Shared serving path.** The single-image CLI, directory batch script, and UI
  import the same prediction service; a parity test asserts identical scores.
  Grid extraction currently invokes the expert/transform interfaces directly
  and is reconciled through the prediction-row contract.

## 6. Evaluation protocol

Protocol decisions were frozen *before* results were produced, to keep the
evaluation honest:

- **One threshold across all conditions.** Never tuned per transform — that
  would be leakage dressed up as robustness.
- **Where each thing was fitted, stated exactly.** Weights and the decision
  threshold were fitted on the **fitting-TRAIN split**; the *rung* (which model in
  the ladder) was selected on **held-out dev**; the internal test, the second
  holdout and the sealed reference set were never used for any fitting. Test and
  reference runners have no fitting path at all.

  **This is a deviation from our own frozen protocol, found by peer review and
  recorded rather than quietly fixed.** our evaluation protocol required threshold
  fitting on held-out dev only; `scripts/freeze_router.py` passed the *train*
  split to `select_threshold`, so `threshold-artifact.v1.json` records
  `n_dev_sources: 8998` — the training split — while these docs said dev.
  Measured impact is small: refitting on the true 3,000-source dev split gives
  0.4636303604 against the frozen 0.4667367651 (dev worst-family 0.81565 vs
  0.81444). **We did not change the threshold**, because the sealed reference set
  may be scored only once and has already been scored at the frozen value.
  Full record: `docs/threshold-deviation.md`.
- **Objective:** maximise the bootstrap-mean worst *transformation-family* fake
  recall over the six families, subject to clean false-positive rate and
  balanced accuracy staying within one point of baseline. The worst individual
  condition is *reported* at that threshold, never selected on.
- **Bootstrap unit is the source image,** label-stratified, with all 20
  transformed views travelling together — transformed views are not independent
  observations.
- **The organizer's reference subset is sealed.** It is excluded from every
  fitting step by a hash denylist that aborts the job on a single hit.

## 7. Results

**One-shot evaluation on the untouched internal test: 3,000 sources x 20
conditions = 60,000 rows, 0 decode failures.** Nothing was fitted on these
sources — not the weights, not the threshold, not the feature set, not the rung
choice. The architecture was frozen first (`results/router-fitting-v2/freeze.json`,
stamped `NOT_A_HEADLINE_RESULT`), then this cache was built with
`role=evaluation`, then the evaluator ran on it. The model and threshold were
never refit: the evaluator was re-run once, solely to add the FPR-matched control
below, which strengthens the baseline and can only shrink our reported gain.

Model: 1,827-parameter MLP with worst-group loss over 38 features, one expert
(CF-384), single threshold 0.4667367651127279 across all 20 conditions.

### Headline

| | worst-family fake recall | clean recall | clean FPR | overall acc |
|---|---|---|---|---|
| **Cascade (frozen)** | **0.8258** | 0.9613 | 0.0833 | 0.9090 |
| Primary @ 0.5 (published default) | 0.1227 | 0.7107 | 0.0027 | 0.7807 |

Worst family is `noise` for both; worst single condition is `noise_s0.10`
(cascade 0.790, primary 0.007). Paired source bootstrap, 2,000 resamples:
**+0.7034, CI95 [+0.6872, +0.7205]**.

**Selection did not overfit the dev split**: worst-family recall is **0.8258 on
the untouched test against 0.8144 on dev** — the number the architecture was
chosen by. It went up, not down.

### The headline comparison is not FPR-matched, so we matched it

The cascade runs at clean FPR 0.0833 and the primary at 0.5 runs at 0.0027 —
about 30x apart. A recall gain measured across that gap is partly just a looser
cut, so quoting +0.70 alone would overclaim. We therefore re-ran the comparison
with the **baseline strengthened, which biases every number below against us**:

| baseline arm | thr | worst-family recall | clean FPR | cascade advantage (paired) |
|---|---|---|---|---|
| Primary @ 0.5 (published default) | 0.5000 | 0.1227 | 0.0027 | +0.7034 [+0.687, +0.720] |
| Primary @ its fitted threshold (train half) | 0.1273 | 0.1827 | 0.0127 | +0.6433 [+0.627, +0.661] |
| **Primary @ our clean FPR, threshold fitted on this test set** | 0.0058 | 0.3342 | 0.0833 | **+0.4916 [+0.475, +0.508]** |

The last row hands the primary **a threshold fitted on the internal test itself**
to reproduce our exact operating point — leakage we grant the baseline and deny
ourselves. It closes about a third of the distance, and the cascade still leads
by **+0.49 worst-family recall**. We report +0.49 as the defensible number. As a
cross-check, matching on *overall* rather than clean FPR gives an independent
+0.5045 [+0.487, +0.520] (`results/internal-test/fpr-matched-baseline.json`).

**The same control kills any clean-image claim, and we make none.** At matched
FPR the primary's clean fake recall is **0.9620** against our **0.9613** — a hair
behind. The cascade buys robustness under degradation and **nothing at all on
clean images**. That is exactly what a router over degradation-aware features
should do, and we would have reported it either way.

### Robustness under transformation

Per-family fake recall at the single frozen threshold:

| family | cascade | primary @0.5 | primary @0.0058 (FPR-matched) |
|---|---|---|---|
| crop | 0.9620 | 0.7600 | 0.9593 |
| blur | 0.9471 | 0.7264 | **0.9709** |
| color | 0.9438 | 0.7367 | **0.9647** |
| resize | 0.9417 | 0.7120 | **0.9763** |
| jpeg | **0.9047** | 0.3703 | 0.8102 |
| **noise** | **0.8258** | 0.1227 | 0.3342 |

**Read the third column, not the second.** Once the primary is given our clean
FPR, it *beats* the cascade on blur, colour and resize and ties it on crop. The
cascade's entire advantage is `noise` (+0.49) and `jpeg` (+0.09) — the two
families where the primary collapses. Because our metric is the *minimum* over
families, raising that floor is what moves it; but we are not claiming
across-the-board superiority, and this table is why. A reader who cares only
about blur should use the primary with a tuned threshold, not our cascade.

**On clean images the cascade buys nothing, and we do not claim otherwise.** At
matched FPR the primary's clean recall is 0.9620 against our 0.9613. This is
worth stating twice, because it also means none of our reported gain can come
from the JPEG/PNG format shortcut in §8 — that confound lives in clean-image
separability, which is exactly where we show no advantage.

Stability, measured as: of sources decided *correctly* when clean, how often does
a transform flip the verdict? Cascade **5.30%** of fake views and 5.35% of real
views. Primary **26.64%** of fake views and 0.43% of real views. The primary's
apparent stability on reals is an artefact of it calling almost everything real.

### The constraint that did not hold, stated rather than hidden

The threshold was fitted under a clean-FPR cap of 0.0756, measuring 0.0736 —
both computed on the fitting split's **train** half, which is where the threshold
value came from (§6). On held-out dev the same frozen threshold measures 0.0760.
**On the untouched test the cascade's clean FPR is 0.0833 — above that cap.** A 300-source pre-flight had flagged this before the full run, and we
recorded the decision in advance: if the full test confirmed it, it ships as a
stated limitation and **the threshold does not get re-tuned to hide it**. The
full test confirmed it, and the threshold is unchanged. The practical meaning is
that at our operating point roughly 1 in 12 clean real photographs is called
AI-generated, and that rises to 1 in 3.4 under heavy noise (`noise_s0.10`, FPR
0.297). Anyone deploying this should pick a threshold against their own
tolerance rather than inheriting ours.

Two independent operating-point matchings were computed and agree: matching the
primary on **clean** FPR (threshold 0.0058) gives worst-family 0.3342 and a
cascade advantage of **+0.4916** [+0.475, +0.508]
(`results/internal-test/results.json`), while matching on **overall** FPR
(threshold 0.0070) gives 0.3213 and **+0.5045** [+0.487, +0.520]
(`results/internal-test/fpr-matched-baseline.json`). Different criteria, different
thresholds, same conclusion.

### Full ablation ladder, scored on the untouched test

Every rung was refit with the freeze's seed and split — reproducing its dev
number exactly — then scored **once** on the internal test at its own fitted
threshold (fitted on the train half, like the shipped one; §6). Rung selection
had already happened on held-out dev; this is disclosure, not a second bite.

| rung | params | threshold | dev worst-family | **test worst-family** | clean FPR | overall acc |
|---|---:|---:|---:|---:|---:|---:|
| quality_only | 17 | 0.49680 | 0.5076 | 0.5402 | **0.4393** | 0.6542 |
| static_average | 0 | 0.12725 | 0.1849 | 0.1827 | 0.0127 | 0.8351 |
| probability_mean | 0 | 0.12725 | 0.1849 | 0.1827 | 0.0127 | 0.8351 |
| fixed_weights | 0 | 0.12725 | 0.1849 | 0.1827 | 0.0127 | 0.8351 |
| logistic | 117 | 0.46491 | 0.6860 | 0.6902 | 0.0713 | 0.8943 |
| mlp | 1,827 | 0.42994 | 0.7587 | 0.7664 | 0.0500 | **0.9213** |
| **mlp+wg (selected)** | 1,827 | 0.46674 | 0.8144 | **0.8258** | 0.0833 | 0.9090 |

All **seven** implemented rungs are here. Three of them — `static_average`,
`probability_mean` and `fixed_weights` — return **numerically identical** results,
to every decimal. That is not a copy-paste error: with a single expert, a
logit-space mean, a probability-space mean and a weighted sum over one weight are
the same monotone function of one score, so any threshold-based metric must agree.
We report them rather than omitting them, because a table that calls itself the
full ladder and silently runs five of seven rungs is asking to be trusted on
exactly the point it is hiding. (Codex caught that omission; B-032.)

The dev ordering survives on unseen data, so the selection was not a lucky draw.
Two things in this table cut against us and we are pointing at them rather than
leaving them to be found:

1. **The quality-descriptors-only baseline is not a real detector.** It reaches
   0.5402 worst-family recall only by calling **43.9% of clean real photographs
   AI-generated**. This is the control we added after discovering the JPEG/PNG
   format shortcut (§8), and it does its job: plain image statistics cannot
   substitute for the detector at any usable operating point.
2. **The worst-group objective costs average accuracy, and we chose it anyway.**
   Plain `mlp` has *higher* overall accuracy (0.9213 vs 0.9090) and a *lower*
   clean FPR (0.0500 vs 0.0833) than the rung we shipped. `mlp+wg` buys +0.059
   worst-family recall with 1.2 points of accuracy and 3.3 points of clean FPR.
   Notably, `mlp` would **not** have breached the clean-FPR cap that `mlp+wg`
   breaches on unseen data. We are not switching to it: the selection rule was
   pre-registered on worst-case robustness, which is the brief's concern, and
   re-picking the rung after seeing the test is precisely the leakage this whole
   protocol exists to prevent. It is recorded here so a reader can disagree with
   the objective rather than be misled about its cost.

Artifact: `results/internal-test/ablation.json`.

### Abstention: the system declines to decide on 20% of images

The router carries a reliability head trained to predict *whether its own
decision is correct* at the frozen operating point. It is fitted in a strict
second stage, after the threshold is frozen, with every classifier parameter
frozen — the fitting script asserts that `p_fake` is bit-identical before and
after (`max |Δ| = 0.0`), so adding self-assessment moved no verdict.

The abstention policy was chosen **on dev, before the test was consulted**, by a
pre-registered rule: the smallest abstention rate whose accuracy-on-kept beats
full coverage by ≥2 points. That selected 20% coverage, frozen as a reliability
value (0.866080) rather than a percentile, so it cannot silently re-tune itself
on new data.

| | coverage | accuracy | worst-family recall |
|---|---|---|---|
| decide on everything | 1.000 | 0.9090 | 0.8258 |
| **defer the least reliable 20%** | 0.799 | **0.9317** | **0.9136** |

Dev predicted +2.22 accuracy points; the untouched test delivered **+2.27**, at
coverage 0.799 against the 0.80 it was frozen at. Deferred images score 0.8191
against 0.9317 for kept ones — the system is declining on the images it would
have got wrong, which is the only thing that makes abstention more than theatre.

**Where it fails, stated up front:** the abstain rate tracks *noise* almost
perfectly (7.2% clean → 98.6% at σ=0.10) but is nearly blind to blur — 0.03% at
blur σ=2.0, where the false-positive rate is 0.1260. Blur makes an image look
*cleaner*, so the head reads high quality and stays confident. Every one of our
worst individual errors carries reliability 0.91–0.99 and would not be deferred.
Abstention removes the uncertain middle, not the confidently wrong tail. See
`deliverables/error-analysis-note.md`.

### The organizers' reference benchmark — one run, after freeze

Scored **once**, after the architecture was frozen, on the sealed subset: **8,719 unique
images** (5,000 COCO val2017 + 3,719 unique DALL-E after deduplication) × 20 conditions =
**174,380 rows, 0 failures**. Scored through `PredictionService` itself, so what was measured
is exactly what ships. Nothing was fitted and the threshold was not touched.

| | deduplicated | per-file |
|---|---|---|
| clean AUROC | **0.9964** | 0.9964 |
| all-conditions AUROC | **0.9821** | 0.9813 |
| clean fake recall | 0.9680 | 0.9653 |
| clean FPR | **0.0158** | 0.0158 |
| **worst-family fake recall** | **0.8787** (`resize`) | 0.8686 |

Bootstrap over **unique images** (never files, per the duplication note below): 0.8787,
CI95 [0.8703, 0.8874].

**Two things went better here than on our own held-out test.** Worst-family recall is 0.8787
against 0.8258 internally, and clean FPR is 0.0158 — comfortably inside the 0.0756 cap our
internal test *breached* at 0.0833. That constraint failure did not reproduce.

**Two things did not, and both are reported.**

*Our advantage over a properly-tuned baseline is +0.09 here, not +0.43.* Against the primary at
its published default the gap is +0.4283 — but that baseline runs at clean FPR 0.0002 against
our 0.0158. Applying the same control we apply to ourselves elsewhere (§7 above), giving the
primary our operating point with its threshold fitted **on this very set, in its favour**, it
reaches 0.7844. So the defensible gain is **+0.0944**, against +0.4916 on our own corpus, and on
clean images the matched primary slightly beats us (0.9769 vs 0.9680).

That is not a contradiction of our headline; it is the same finding from another angle. **Our
correction helps most where the base detector is weakest.** On this distribution the primary is
already strong, so there is less left to correct.

*Abstention does not transfer to this distribution.* The frozen policy defers 26% of images, and
the deferred set is as accurate as the kept set — 0.9407 against 0.9412. On our internal test the
identical policy bought +2.27 accuracy points; here it buys 0.0001. The reliability head was
fitted on SID-Set and does not generalise to COCO + DALL-E. Deferring a quarter of the images for
no measurable gain is a real cost and we state it as one.

Artifact: `results/sealed/reference-results.json`. It carries a provenance ledger
that is explicit about its own limits: the prediction dump's SHA-256 and the
threshold artifact are bound to these rows, and every image's label, group and
file multiplicity is cross-checked against the sealed manifest row by row (the
summary refuses to run on any disagreement). The checkpoint and config hashes are
**not** bound — the dump predates that ledger and carries no model identity
fields, so those hash whatever exists when the summary is regenerated. We say so
in the artifact rather than letting their presence imply more.

### Audit mode: the evaluation harness became the best confidence signal

We built the 20-condition transform grid to *evaluate* the system. Running it on
a single image at inference time turns out to predict whether that image's
verdict is correct better than the reliability head we trained for the job.

Measured on the untouched internal test (3,000 sources), predicting a **wrong**
clean verdict:

| signal | AUROC |
|---|---|
| reliability head (trained for this) | 0.7206 |
| **verdict retention across 20 conditions** | **0.8696** |
| both combined | 0.8863 |

And it lands on the exact weakness §8 documents. Of the 157 sources the
reliability head passes with high confidence but gets **wrong**, mean retention
is **14.40/20** against **19.00/20** for the confident-and-correct ones. Flagging
`retention < 18` among high-confidence images catches **72.6%** of those
blind-spot errors while deferring only 17.3% of them. The two signals fail
differently: the reliability head reads quality descriptors, so it tracks noise
and is nearly blind to blur; retention measures the verdict itself.

The demo exposes this as a **Forensic Robustness Certificate**, whose grades are
the measured relationship rather than labels we chose:

| verdict retention | grade | clean verdict was correct for | share of sources |
|---|---|---|---|
| 20/20 | HIGH | 99.1% | 61.4% |
| 18–19 | MEDIUM | 94.9% | 20.9% |
| 15–17 | LOW | 84.9% | 10.4% |
| ≤14 | VERY LOW | 60.6% | 7.4% |

**Confirmed on a second untouched set.** Because the internal test's own results generated
this idea, we acquired a **fresh 3,000-source holdout** (shards never previously consumed,
canonicalized identically, verified disjoint from everything we fit on) and re-measured with
every threshold fixed beforehand. Retention AUROC **0.8636** there against 0.8696 internally —
and the reliability head *degraded* to 0.6478, so retention's margin widened from +0.149 to
**+0.216**. The grade-band accuracies the UI quotes hold to within a third of a point on three
of four bands (HIGH 0.9924 vs 0.9910; MEDIUM 0.9461 vs 0.9490; LOW 0.8517 vs 0.8490), and
VERY LOW came in *better* than promised (0.6473 vs 0.6060). Artifact:
`results/holdout/validation.json`.

We also tested, and **rejected**, a cheaper version: on the internal test a 2-condition subset
matched the full grid at a tenth of the cost, but the subset had been chosen greedily on the
data it was scored on. Frozen in advance and re-measured on the holdout it scored **0.8374
against 0.8636** — selection bias, not a finding. It is not shipped.

This is **audit mode**, and its cost is real: each of the 20 conditions runs the full
service (1 expert + 3 probes), so an audit is **80 CF-384 forward passes — ~3.0 s
against 136 ms** for a normal prediction, 21.9×. The default decision path never runs
it, and the certificate states the cost on its face. Dropping the self-probes (§8, they
buy nothing measurable) would cut this to 20 passes.

### The system can say *why* it is unsure

A 775-parameter classifier reads the eight quality descriptors already computed
for every image and names the transformation family they look like — *"detected
image history: JPEG compression (93%)"* — flagging when that family is one where
our detector is measurably weakest. Balanced accuracy **0.7332** against 0.143
chance on dev (noise 0.99, resize 0.96, jpeg 0.78, crop 0.76, blur 0.65,
clean 0.54, colour 0.47).

Two choices that cost accuracy on purpose. **Geometry is excluded**: width and
height would make crop and resize easy, but a real upload has no known original
size, so that accuracy would not survive deployment. And the fit is
**class-weighted**: unweighted it reported 0.00 recall on `clean` and we nearly
published "clean is inseparable" — it was simply outnumbered six to one by
`colour`. Weighted, clean recall is 0.54. The confusion that *survives* is real —
a ±20 brightness shift barely moves blur, blockiness or noise — and the reporter
emits that caveat itself rather than presenting a coin flip as an explanation.

It is an explanation and never an input: the router cannot see it, and a test
asserts the feature builder does not so much as mention it.

### The second expert failed, and we report it as a result

The architecture was designed to escalate hard images to a heavier second
detector. **Two candidates were integrated and both were rejected on measurement,
so no second expert ships.**

| candidate | licence | outcome |
|---|---|---|
| LOTA (ICCV 2025) | **code MIT; weights unlicensed** (published only through a login-walled Baidu drive with no stated licence) | Reads the least-significant-bit plane; non-deterministic (one image's score moved 0.31 across runs) and AUROC falls 1.000 → **0.592** on JPEG re-encoding |
| PGC (Apache-2.0, 306.7M) | Apache-2.0 | Loads cleanly and is deterministic, but P(PGC correct \| cascade wrong) = **0.5426** on the test — a coin flip — and correction-minus-harm is **−2451** |

PGC was given a fair hearing before being cut: beyond wholesale replacement we
tried confident-override at four tail widths, logit-space blending at three
weights, and family-gated rescue. The best variant nets **+1 across 12,000 dev
rows**. There is no operating point where it helps.

**Why both failed is the same reason, and it is worth stating.** The rescue only
ever sees images the reliability head deferred, and that pool is dominated by
`noise` and `jpeg`. LOTA reads the LSB plane; PGC reads a YCbCr quantization
residual. Both live in the high-frequency band — exactly what noise and heavy
JPEG destroy. **You cannot rescue noise-destroyed evidence with a detector that
reads evidence from the noise band.** PGC is genuinely better than our cascade
where degradation is photometric (colour 0.9532 vs 0.9159), but those families
are a sliver of the deferred pool.

So the escalation that ships is to a **human**, not to a second model — and the
numbers above support it rather than merely asserting it. Evidence:
`results/pgc/rescue.json`.

Full artifacts: `results/internal-test/results.json`,
`results/internal-test/fpr-matched-baseline.json`,
`results/internal-test/abstention.json` and `results/pgc/rescue.json`.

## 8. Limitations and honest reflection

- **Our training corpus had a shortcut that would have invalidated everything,
  and we found it ourselves.** Both classes were drawn from one dataset
  specifically to avoid learning dataset artefacts. That was not enough: within
  SID-Set, every real image is stored as JPEG and every synthetic image as PNG,
  so **file format alone predicted the label for 100.00% of 15,000 sources**.
  Every file carried a `.jpg` extension regardless of its actual bytes, which is
  why it went unnoticed. Our own quality descriptors read it directly —
  `blockiness` alone separates the classes at AUROC 0.89, and 53.7% of reals
  show JPEG blocking against 2.7% of fakes. We re-encoded every source to a
  single container before extraction. Full disclosure of what that does and does
  not fix: it removes the blocking artefact (`blockiness` AUROC 0.90 -> 0.64) but
  a residual remains, because `noise_sigma` (0.82) is unaffected by container and
  reflects a genuine difference between photographs and generated images. We
  therefore also added a mandatory **quality-descriptors-only baseline** to every
  ablation, so no result of ours can be read without knowing what plain image
  statistics achieve on the same data.

- **Single expert, and the second one was rejected on evidence.** LOTA (ICCV
  2025) was our intended second expert. We obtained the weights, integrated them
  against the authors' own code, and measured rather than assumed. It is MIT
  licensed, loads cleanly (ResNet-50, 23.5M parameters), and its published
  results are excellent — AUROC 0.9996-0.9999 across all eight generators it was
  evaluated on. It is not suitable here, for reasons we can state precisely.
  Its input is the **least-significant-bit plane** of a randomly chosen 32x32
  patch, which makes it (a) **non-deterministic** — the same image scored three
  times varies by up to 0.31 — and (b) dependent on exactly the information
  lossy compression destroys. Every image in its published evaluation is a
  lossless PNG. On identical pixels re-encoded as JPEG q95 its AUROC falls from
  1.000 to **0.592 and its fake recall to 0.000** — it calls every AI image real.
  We also note that its apparent perfection on our corpus was the format shortcut
  above, not detection. A detector that works only on uncompressed images cannot
  help on a platform where every upload is recompressed, and that is a finding
  worth reporting rather than a dependency worth shipping.
- **The default operating point is poor and we did not hide it.** At the
  published default threshold of 0.5, the primary detector recovers only 71% of
  AI-generated images on clean internal-test data and 12% under the worst
  transformation family — the ranking is excellent, the cut is misplaced. Fixing
  this is what the calibration stage is for.
- **We buy robustness with false positives, and the constraint we set ourselves
  did not hold on unseen data.** The threshold was fitted under a clean
  false-positive cap of 0.0756 — measured on the train half it was fitted on, and
  0.0760 on held-out dev; on the untouched test the cascade measured
  **0.0833**, above it. We had pre-registered what to do if this happened and did
  it: report it, do not re-tune. About 1 in 12 clean real photographs is called
  AI-generated, rising to 1 in 3.4 under σ=0.10 noise. A deployment should choose
  its own threshold rather than inherit ours.
- **Part of our headline gain is operating point, and we measured how much.**
  Against the primary at its published 0.5 default the cascade gains +0.70 worst
  family recall, but those two points sit ~30x apart in clean FPR. Handing the
  baseline a threshold fitted on the test set itself to reproduce our operating
  point — leakage we deny ourselves — cuts the gain to **+0.49**. That is the
  number we report.
- **The cascade does nothing for clean images, and we say so.** At matched FPR
  the primary's clean fake recall is 0.9620 against our 0.9613. Every gain we
  claim is a gain under degradation; there is no clean-image claim in this work.
- **Our own self-probes do not earn their cost.** The shipped system re-scores
  every image under three mild perturbations — 3 of its 4 forward passes and
  ~110 ms of its 128 ms. An 8-arm × 3-seed ablation on dev found **no probe
  budget distinguishable from any other, including using no probes at all**;
  every difference sits inside the seed spread. The robustness gain comes from
  the quality descriptors and the worst-group objective, not from self-probing.
  We report this rather than quietly keeping a component that looks clever.
- **Patch-level evidence attribution does not work on this detector.** We tried
  to build an evidence heatmap by occluding image patches and measuring the score
  change. A guard written before the experiment compared two occlusion operators
  (mean-fill vs blur) and found their maps correlate at only **0.261** — so the
  method measures the artefacts its own masks create, not where the evidence is.
  This detector reads high-frequency traces and masks manufacture high-frequency
  content. The audit is reported void rather than shipped as a convincing
  picture of nothing.
- **Noise remains hard even after the cascade.** Gaussian noise at σ=0.10 is the
  worst condition for both arms (cascade fake recall 0.790 at FPR 0.297). We
  report it rather than excluding the condition.
- **Smoke-set scale and composition.** The early AUROC 0.992 figure comes from
  400 source images whose real half is COCO and whose fake half is SID-Set. Two
  different sources means part of that separation may be dataset provenance
  rather than AI-generation. It is a diagnostic, not a benchmark claim, and the
  protected evaluation replaces it.

- **The organizers' reference subset contains substantial duplication.** Of the
  8,843 supplied AI images, only **3,719 are unique**; 5,124 files are
  byte-identical copies, some repeated five times. Scored per file, 1,808 images
  are weighted up to 5x and confidence intervals come out far too narrow. We
  deduplicate before scoring and report both conventions so our numbers can be
  reconciled with any computed the other way.
- **No production hardening.** This is a prototype: no adversarial robustness
  guarantees, no throughput tuning, no deployment path.

## 8b. What we would do with more time

Ranked by what our own measurements say matters most, not by what sounds impressive.

**1. Ship the probe-free variant — already validated, deliberately not taken.** The three
self-probes are 3 of the system's 4 forward passes and ~86% of its latency, and §8 shows they
buy nothing measurable. On the fresh untouched holdout a probe-free router is *better on every
metric*: worst-family **0.8373 vs 0.8289**, clean FPR **0.0720 vs 0.0753**, accuracy **0.9139 vs
0.9124** — at **one forward pass instead of four**, which would take the normal path from 128.6 ms
to ~19 ms.

We did not adopt it, and the reason is worth stating because it is not a technical one: the
sealed reference benchmark was scored on the *with-probes* system, and that set may be run
exactly once. Switching now would leave our only official number describing a system we do not
ship. A 4× speedup does not outrank that. It is the first thing to do the moment a second
evaluation opportunity exists. Artifact: `results/holdout/validation.json`.

**2. Fix the corpus at the source, not with a re-encode.** Our reals and fakes differ in processing
pipeline, not only in being generated — real photographs carry sensor noise, our synthetic images
never did. Canonicalizing the container removed the JPEG/PNG artefact but not this, and
`noise_sigma` still separates the classes at AUROC 0.82 afterwards. The correct fix is a corpus where
both classes share a capture-and-processing history: generate the fakes *from* the same photographs
that supply the reals, then push both through one identical pipeline. That is a data-collection job,
not a modelling one, and it is the single highest-value thing we would do next.

**3. Attack the noise hole directly.** Fake recall falls to 1.5% at Gaussian noise sigma=0.10, with a
97% flip-to-real rate. This is the most exploitable weakness in the system and the one an adversary
would reach for first. Two concrete routes we did not have time to test: noise-aware augmentation
while fitting the router, and a denoise-then-detect preflight where the quality descriptors say the
image is noise-dominated.

**4. Find a second expert whose failures are genuinely different.** We rejected LOTA on evidence, and
the reason generalizes: it keys on high-frequency, least-significant-bit structure — the same band
our primary depends on and the same band compression destroys. A useful second expert must read
*different* evidence, most plausibly low-frequency or semantic inconsistency, which survives
recompression. Complementarity, measured as P(expert correct | primary wrong), is the selection
criterion; standalone accuracy is not.

**5. Evaluate against unseen generators.** SID-Set does not expose generator identity, so our
held-out split tests generalization to unseen *images*, not unseen *generators*. Every robustness
number we report carries that caveat. A generator-labelled corpus would let us hold out whole
families and measure what actually matters for deployment: performance against a model that did not
exist when we trained.

**6. Calibration under shift.** We fit one threshold across all conditions, deliberately, because at
inference we do not know which transform was applied. A better system would estimate the degradation
first and select a calibration conditioned on it — which is the natural extension of the reliability
router we already built, and the obvious next architectural step.

**Closed since this list was written.** One item here was *"run the probe-cost gate we skipped"* —
our protocol said to decide whether the three self-probes earn their place before committing to the
long extraction, and a data crisis reordered the schedule so we launched with them in. We have since
answered it from the finished cache: 8 probe budgets × 3 seeds, no budget distinguishable from any
other including using none at all (§8), confirmed on the fresh holdout. The compute saving was lost
for this run; the finding stands and is item 1 above.

## 9. Parameter inventory and operating cost

The brief caps total model size at 2B parameters. Measured, not estimated:

| Component | Parameters | Trained by us? |
|---|---:|---|
| Community Forensics 384 (ViT-S/16) | 21,811,969 | No — frozen |
| Reliability/fusion router (MLP + worst-group loss) | 1,827 | **Yes** — the contribution |
| ├─ of which the reliability/abstention head | 17 | Yes — fitted in a frozen second stage |
| Degradation reporter (loaded by the UI and audit CLI) | 775 | **Yes** |
| **Shipped total** | **21,814,571** | — |

**1.09% of the 2B cap** (21,814,571 / 2,000,000,000 = 0.0109), and our own trainable
parameters — the 1,827-parameter router plus the 775-parameter degradation reporter — are
**0.012%** of the shipped system. The contribution is the decision layer, not scale.

*(Corrected 2026-08-29 after Codex review R7: this previously read "0.0000109 of the cap"
and "0.001%", which mistook the dimensionless fraction 0.0109 for a percentage and was wrong
by three orders of magnitude. The degradation reporter's 775 parameters were also omitted
while the UI loads and calls it.)*

Parked, not shipped, but measured and kept in the repo as evidence: PGC
(306,704,641 params). Had it been adopted the total would still have been
~328.5M — well inside the cap. It failed on complementarity, not on size (§7).

### Latency and memory

Apple M4 Pro, 24 GB, PyTorch MPS, 50 clean 1024×1024 images after warm-up, measured on an
**otherwise idle machine** (the generator stamps `contended: true` and warns if a long-running
GPU job is live, because latency measured against a busy GPU is not a number worth publishing):

| path | p50 | p95 | forward passes |
|---|---:|---:|---:|
| CF-384 alone (baseline) | 19.5 ms | 20.6 ms | 1 |
| **Full cascade (shipped)** | **134.6 ms** | **150.9 ms** | 4 |
| Audit mode (20-condition certificate) | ~3.0 s | — | 80 |
| PGC alone (parked candidate) | 54.3 ms | 55.3 ms | 1 |

Peak RSS **727 MB** for the shipped path. These are one measured run; repeating
it moves the figures a few percent, so the artifact is the source of truth and the tests assert
the values with tolerance rather than to the decimal.

The cascade costs **6.9× the baseline**, and we are not going to pretend that is
free. Almost all of it is the three probe forward passes that produce the router's stability
features — the router head itself is 1,827 parameters and its arithmetic is negligible. At
~7.5 images/second on a laptop this is comfortable for interactive use and for this project's
batch sizes, but it is a real cost to weigh against the robustness it buys (§7).

**And §8 shows those probes buy nothing measurable.** Dropping them would take the normal path
to ~19 ms and an audit from 80 forward passes to 20. We have not shipped that change because it
alters the frozen architecture and the sealed benchmark measured the with-probes system (§8b).

Artifact: `results/ops/ops-evidence.json`.

## 10. Licenses

| Asset | License |
|---|---|
| Community Forensics 384 (code + weights) | MIT |
| SID-Set (synthetic images) | CC BY 4.0 |
| COCO train2017 (real images) | COCO Terms of Use |
| This repository | MIT draft in `LICENSE`; owner approval pending before publication |

Dataset licenses and redistribution terms are inventoried in
`data/manifests/LICENSES.md`. The clean local history contains no raw
third-party images; the private remote still holds the pre-cleanup history and
must not be made public yet.

## 11. Contributions

Solo entry (Mehul Modi), built with two AI coding agents working as peers under
a written protocol: one owning the detection pipeline, experts, and training
components; the other owning evaluation, the demo application, and repository
mechanics. Every cross-cutting contract was reviewed by the agent that did not
write it. **The review record is the commit history:** each repair commit names
the finding it answers, the reproduction that demonstrated it, and what the fix
changed — including the cases where a published number was wrong. Several
substantive bugs were caught that way, among them an evaluator that returned
success while writing `NaN`, an AUROC that depended on row order, a parameter
statement wrong by three orders of magnitude, and a documented exit test that had
never been runnable.
