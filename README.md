# Adaptive Forensic Cascade

**Robust detection of AI-generated images under real-world transformations.**
TikTok TechJam 2026 — Track 5.

> **Status: work in progress (Phase 2 repair).** The current deployable path is
> the frozen CF-384 baseline plus the diagnostic stress UI. Headline evaluation,
> router deployment, licensing approval, and the clean remote-history push are
> still blocked on review. Sections marked *pending* stay empty rather than being
> filled with placeholder numbers; committed aggregate evidence lives in
> `results/`.

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
  -> OUR reliability/fusion router       <- implemented; real training not accepted yet
       reliable  -> calibrated verdict
       uncertain -> behavioural rescue -> rescued verdict
  -> calibrated score + reliability readout
```

**The router and the reliability layer are our proposed contribution.** The expert
detectors are public, frozen checkpoints; we do not claim them. What we claim
today is their implementation and the evaluation protocol that will make any
eventual performance claim checkable. The current app does not yet serve a
trained router, calibrated verdict, abstention decision, or rescue path.

## 2. What is built today

| Component | Status |
|---|---|
| Canonical decode (EXIF, RGB, provenance hashes) | ✅ built, tested |
| All 20 official transform conditions, deterministic + golden-tested | ✅ built, tested |
| Community Forensics 384 expert adapter | ✅ built, tested |
| Importable prediction service (one decision path for CLI/UI/batch) | ✅ built, tested |
| Quality descriptors | ✅ built, tested |
| Mild self-probes | ✅ built, tested |
| Calibration + threshold-selection code under a frozen objective | ✅ built, tested; no fitted artifact yet |
| Router (7-rung ladder: quality-only → static avg → prob mean → fixed weights → logistic → MLP → +worst-group) | ✅ implemented, repaired, 671 tests; peer re-review and a fitted checkpoint still pending |
| Full-grid baseline run (8,000 predictions) | ✅ complete |
| Evaluation harness | 🟡 diagnostic path works; headline path blocked on protocol repair |
| Second expert | ❌ evaluated and rejected on measured evidence (see Limitations) |
| Protected 15,000-source corpus, format-canonicalized, contamination-audited, split 12k fitting / 3k untouched test | ✅ built and verified |
| Router trained on that corpus | 🟡 feature extraction running |

## 3. Setup

Requirements: Python 3.12, [`uv`](https://docs.astral.sh/uv/), ~2 GB disk for
the model cache. Apple Silicon (MPS), CUDA, and CPU are all supported; the
device is selected automatically.

```bash
uv sync                      # create .venv and install pinned dependencies
.venv/bin/pytest -q          # run the test suite
```

The expert checkpoint downloads automatically from the Hugging Face Hub on
first use (~85 MB, MIT licensed).

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

**Run the demo UI**

```bash
.venv/bin/python -m src.app
```

## 5. Reproducing our results

Every public aggregate number must come from a committed artifact. To regenerate
the current diagnostic after acquiring the git-ignored smoke images:

```bash
# 1. Adapter sanity + backend consistency check
.venv/bin/python scripts/sanity_check.py --manifest data/manifests/smoke_v1.json

# 2. Full 20-condition grid  (400 sources x 20 conditions = 8,000 predictions)
.venv/bin/python scripts/run_grid.py \
    --manifest data/manifests/smoke_v1.json \
    --output results/grid-smoke-v1/prediction_rows.jsonl

# 3. Transform-protocol golden tests (fail if any transform changed)
.venv/bin/pytest tests/test_transforms_golden.py -q

# 4. Placeholder-threshold diagnostic (cannot emit a headline result)
.venv/bin/python scripts/run_eval.py \
    --rows results/grid-smoke-v1/prediction_rows.jsonl \
    --diagnostic
```

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
- **Threshold fitting happens only on held-out dev data.** Test and reference
  runners have no fitting path at all.
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

*Pending.* The headline path is blocked on exact-coverage, threshold-artifact,
diagnostic-schema, keyed-pairing, and provenance guards, and no threshold has
been fitted yet. Diagnostic observations from the full-grid run are recorded in
`results/grid-smoke-v1/diagnostic-results.md` and are explicitly **not**
headline results.

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
  published default threshold of 0.5, the primary detector recovers only 53% of
  AI-generated images on clean data despite an AUROC of 0.992 — the ranking is
  excellent, the cut is misplaced. Fixing this is what the calibration stage is
  for. We have deliberately *not* fitted a threshold on our smoke set to make
  the demo look better.
- **Noise and heavy blur remain hard.** Gaussian noise at σ=0.10 collapses fake
  recall. We report this rather than excluding the condition.
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

**1. Fix the corpus at the source, not with a re-encode.** Our reals and fakes differ in processing
pipeline, not only in being generated — real photographs carry sensor noise, our synthetic images
never did. Canonicalizing the container removed the JPEG/PNG artefact but not this, and
`noise_sigma` still separates the classes at AUROC 0.82 afterwards. The correct fix is a corpus where
both classes share a capture-and-processing history: generate the fakes *from* the same photographs
that supply the reals, then push both through one identical pipeline. That is a data-collection job,
not a modelling one, and it is the single highest-value thing we would do next.

**2. Attack the noise hole directly.** Fake recall falls to 1.5% at Gaussian noise sigma=0.10, with a
97% flip-to-real rate. This is the most exploitable weakness in the system and the one an adversary
would reach for first. Two concrete routes we did not have time to test: noise-aware augmentation
while fitting the router, and a denoise-then-detect preflight where the quality descriptors say the
image is noise-dominated.

**3. Find a second expert whose failures are genuinely different.** We rejected LOTA on evidence, and
the reason generalizes: it keys on high-frequency, least-significant-bit structure — the same band
our primary depends on and the same band compression destroys. A useful second expert must read
*different* evidence, most plausibly low-frequency or semantic inconsistency, which survives
recompression. Complementarity, measured as P(expert correct | primary wrong), is the selection
criterion; standalone accuracy is not.

**4. Evaluate against unseen generators.** SID-Set does not expose generator identity, so our
held-out split tests generalization to unseen *images*, not unseen *generators*. Every robustness
number we report carries that caveat. A generator-labelled corpus would let us hold out whole
families and measure what actually matters for deployment: performance against a model that did not
exist when we trained.

**5. Run the probe-cost gate we skipped.** Our own protocol said to decide whether the three
self-probes earn their place *before* committing to the long extraction, so we could drop them and
save three forward passes per image. A data crisis reordered the schedule and we launched with them
in. The scientific question is still answerable from the finished cache; the compute saving is gone.

**6. Calibration under shift.** We fit one threshold across all conditions, deliberately, because at
inference we do not know which transform was applied. A better system would estimate the degradation
first and select a calibration conditioned on it — which is the natural extension of the reliability
router we already built, and the obvious next architectural step.

## 9. Parameter inventory

The brief caps total model size at 2B parameters.

| Component | Parameters | Trained by us? |
|---|---:|---|
| Community Forensics 384 (ViT-S/16) | 21,811,969 | No — frozen |
| Reliability/fusion router (MLP implementation) | 1,987 one-expert / 2,548 planned two-expert | Not yet accepted/trained for release |
| **Current accepted model total** | **21,811,969** | — |

Comfortably within the limit. If the router clears its gate, its trainable
parameters would be roughly 0.01% of the system — the intended contribution is
the decision layer, not scale.

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
write it, and those reviews are preserved in `coordination/CHANNEL.md` — several
substantive bugs in this codebase were caught that way.
