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
| Router (fusion ladder: static → logistic → MLP + worst-group loss) | 🔴 implementation under repair; no accepted deployable checkpoint |
| Full-grid baseline run (8,000 predictions) | ✅ complete |
| Evaluation harness | 🟡 diagnostic path works; headline path blocked on protocol repair |
| Second expert | ⏸️ parked (see Limitations) |
| Router trained on a real corpus | ⏳ Phase 2 |

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

- **Single expert at present.** The intended second expert (LOTA, ICCV 2025)
  publishes its pretrained weights only through a login-walled cloud drive with
  no public mirror. We chose reproducibility over benchmark score: a dependency
  the judges cannot download is a dependency we should not ship. A
  training-free substitute is planned.
- **The default operating point is poor and we did not hide it.** At the
  published default threshold of 0.5, the primary detector recovers only 53% of
  AI-generated images on clean data despite an AUROC of 0.992 — the ranking is
  excellent, the cut is misplaced. Fixing this is what the calibration stage is
  for. We have deliberately *not* fitted a threshold on our smoke set to make
  the demo look better.
- **Noise and heavy blur remain hard.** Gaussian noise at σ=0.10 collapses fake
  recall. We report this rather than excluding the condition.
- **Smoke-set scale.** Current measurements use 400 source images. They are
  diagnostics, not benchmark claims.
- **No production hardening.** This is a prototype: no adversarial robustness
  guarantees, no throughput tuning, no deployment path.

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
