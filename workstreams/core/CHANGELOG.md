# core — CHANGELOG (newest first)

## 2026-08-29 — CHEAPER AUDIT, A SELF-CAUGHT WRONG NUMBER, AND A CLAIMS SWEEP

**`scripts/audit_image.py`** — the whole system in one command for the demo and video:
verdict, what the RAW detector alone would have said, reliability, detected image history, and
the robustness certificate. On a real corpus image the raw detector misses at **0.0012**, the
router rescues it to **0.5739**, and the certificate then grades that rescue **11/20 VERY LOW**
rather than overselling it. 5 tests; the load-bearing one asserts auditing OBSERVES and never
moves the decision (p_fake, decision and certificate verdict identical audited vs not).

**CORRECTION — the audit costs 80 forward passes, not 20.** I wrote "20 extra forward passes"
into the certificate module, its UI text, the CLI, README §7 and the error note — five places,
asserted repeatedly, never measured. Each of the 20 conditions runs the FULL service (1 expert
+ 3 probes), so it is 20×4 = **80 passes, 2,988 ms against 136 ms — 21.9×**. Corrected
everywhere and now guarded by a STRUCTURAL test deriving the figure from the configs, because
a docstring nobody re-derives is exactly how it happened.

**The certificate does not need 20 conditions.** Free offline test on the internal-test cache:

| subset | AUROC | passes |
|---|---|---|
| all 20 | 0.8650 | 80 |
| `resize_0.25` + `crop_0.8` | **0.8664** | **8** |
| + 3 more | 0.8982 | 20 |

Two conditions match the full grid at a tenth of the cost; the geometric perturbations carry
the signal, the photometric ones do not. **The same lesson as the probe ablation, twice:
aggregating more signals dilutes.** Caveat: the subset was chosen greedily on the data it is
scored on, so anything above the unselected 0.8650 baseline is partly selection bias. Shipped
certificate still runs all 20 until the fresh holdout confirms it.

**Claims sweep.** After two wrong published numbers in one day, I swept every artifact against
`tests/test_published_numbers.py` and found four sets of claims with nothing asserting them:
the degradation reporter's figures (plus a guard that geometry stays EXCLUDED), the rung-gating
oracle ceiling (fails if an oracle ever clears 2 points), the two independently-implemented
FPR-matched controls (plus a cross-check they stay within 0.02), and the LOTA rejection
evidence. All bound now. `scripts/measure_ops.py` written for the last gap — README §9's
latency has no artifact — and it stamps `contended: true` and refuses to be quietly wrong if a
GPU job is live.

**Suite 728 passed.** Frozen decision path untouched throughout.

## 2026-08-28 (late) — AUDIT MODE: two new capabilities, two more ideas killed

**1. Forensic Robustness Certificate** (`f486599`). The 20-condition grid was built to
EVALUATE the system; run per-image it is the best confidence signal we have. Predicting a
wrong clean verdict on the internal test: reliability head **0.7206**, verdict retention
**0.8650**, combined **0.8863**. It works where the head fails — on the 157 sources the head
passes confidently but gets wrong, mean retention is **14.40/20** against **19.00/20** for
confident-and-correct; flagging `retention < 18` catches **72.6%** of those errors while
deferring 17.3%. The two fail differently: the head reads quality descriptors so it tracks
noise and is blind to blur; retention measures the verdict itself. Grade bands are the
MEASURED retention→accuracy relationship (20/20→99.1%, ≤14→60.6%), and a test asserts the UI
cannot quote an accuracy the data stopped supporting. Audit mode only: 20 extra forward
passes, stated on the certificate's face. `src/app/certificate.py`, 8 tests.

**2. Degradation reporter** (`f5b23c6`). 775 params, dev balanced accuracy **0.7332** against
0.143 chance (noise 0.99, resize 0.96, jpeg 0.78, crop 0.76, blur 0.65, clean 0.54, colour
0.47). Answers "why is it unsure" from descriptors already computed. **Geometry excluded on
purpose** — width/height would make crop and resize easy, but a real upload has no known
original size, so that accuracy would not survive deployment. **Class-weighted**: unweighted
it reported 0.00 recall on `clean` and I nearly published "clean is inseparable"; it was
outnumbered six to one by `colour`. Weighted, clean recall 0.54, and the confusion that
survives is real and physical (±20 brightness barely moves blur/blockiness/noise). It is an
explanation, never an input — a test asserts the router's feature builder does not mention it.

**3. Evidence Survival Audit — VOID** (`a751229`). Killed by a guard written before the
experiment ran: two occlusion operators (mean-fill, blur) produce maps correlating at only
**0.261**, so patch attribution measures the artefacts its own masks create. Predicted from
first principles — this detector reads high-frequency traces, which is why LOTA and PGC died,
and masks manufacture high-frequency content. Five minutes spent instead of hours on a
heatmap over noise.

**4. Self-caught discipline breach** (`209f51d` → the retention artifact commit). The
retention numbers went into README §7 from a shell one-liner with **no committed artifact**,
which is exactly the rule `tests/test_published_numbers.py` exists to enforce.
`scripts/diagnostics/retention_signal.py` now produces
`results/robustness/retention-signal.json`, reproducing every published figure, with four new
assertions — including one that fails if retention ever stops beating the reliability head.

**Suite 718 passed, 1 honest skip.** The frozen decision path is untouched by all of this:
the certificate and the reporter are additive surfaces, and checkpoint Nims still ships.

## 2026-08-28 — SERVING THE FROZEN CASCADE: the router is wired into the decision path

**The defect this closes.** `router.pt` was loaded by `evaluate_internal_test.py` and by nothing
else. `PredictionService` still fused by naive mean at the PLACEHOLDER 0.5 threshold, so the Gradio
demo, `scripts/infer_dir.py` (a REQUIRED deliverable) and every ad-hoc prediction served the raw
primary — the arm measured at **0.1227** worst-family recall — while README §7 reported the cascade
at **0.8258**. A judge running our demo could not reproduce our headline; the two artifacts
contradicted each other.

**Parity is now structural.** The feature-bearing half of `build_row` became
`feature_cache.extract_feature_blocks`, called by BOTH the offline cache builder and the live
service. The router scores production images through the same function that produced every row it
was fitted on, so the two cannot drift the way two copies silently do. An optional `precomputed`
map lets the service hand over the expert output it already computed rather than pay a second
forward pass.

**New `src/router/head.py`** — loads a frozen checkpoint through the trainer's fail-closed loader and
scores one image. It has no path that fits, tunes or calibrates anything.

| verification | result |
|---|---|
| 60,000 cache rows: head vs evaluator batch path | max abs delta **7.7e-07**, **0 verdict disagreements** |
| closest cached score to the threshold | **2.1e-05** — 27x the largest numerical difference |
| 25 images end-to-end FROM PIXELS vs evaluated scores | max abs delta **1.2e-07**, **0 disagreements** |
| `infer_dir.py` output | routed **0.2376**, not the raw **0.0014** |

**Fail-closed against the realistic regression, which is config drift.** `fusion: router` with no
head raises; a threshold that is not the checkpoint's frozen one raises rather than quietly deciding
at a boundary the router was never fitted against. The live threshold is read from the **validated
artifact**, never from `configs/predict.yaml` — a YAML file carries no provenance and is trivially
edited, the artifact is schema-checked and hashed.

**Cost, measured rather than hidden.** p50 **18.8 ms → 130.3 ms**, p95 20.1 → 138.9. The head itself
is 1,827 parameters; the added 110 ms is three probe forward passes. This is the quantitative case
for Phase 3 adaptive escalation: pay that cost only on images that need it.

**Three tests changed because behaviour intentionally changed** — frozen provenance replaces
PLACEHOLDER, and the UI shows a real verdict instead of demoting it. The placeholder-demotion branch
keeps its own test. Added: both fail-closed guards, a test that the router is not a no-op, and a
permanent live-vs-evaluated parity test. **Suite 693 passed.** Commit `be655dc`.

**Model economy:** implemented heavy-direct. The work is train/serve parity and threshold
provenance — delegating would have required transferring exactly the judgment that makes it correct.


## 2026-08-27 — Phase 1 task 1.3: full-grid baseline (8,000 rows) + B-013 hardening
- `scripts/run_grid.py` + `tests/test_run_grid.py` (**15 tests**): 20-condition grid over the smoke manifest → `prediction-row.v1` JSONL for Codex's harness. Decodes each source once then transforms 20×; `content_sha256` is the VIEW hash (per B-009 [F3]) so conditions are distinguishable while `source_id` stays shared for the bootstrap unit; `decision`/`reliability` emitted null so the harness recomputes at the frozen threshold; resumable; expert failures emit a typed `prediction-failure.v1` row rather than a fabricated score.
- **Run:** 400 sources × 20 conditions = **8,000 rows, 0 decode failures, 0 expert failures, 167 s (~21 ms/row)**. Artifacts in `results/grid-smoke-v1/`.
- **Findings** (`DIAGNOSTIC_SUMMARY.md`, diagnostic only — headline table is Codex's): worst families **noise** (pooled recall 0.165@0.5, σ=0.10 → 0.015) and **blur** (pooled AUROC 0.8576). **`blur_s2.0`: AUROC 0.6470 AND FPR 0.640** — heavy blur biases REAL images toward "fake"; the model is confidently wrong rather than uncertain. Colour/crop nearly free (~0.99 AUROC). A single global threshold provably cannot serve noise and blur simultaneously — a finding to report, not hide.
- **B-013 calibration batch landed in full:** strict pre-artifact validation (score range, unknown/mismatched condition-family ids, inconsistent source labels, clean needing both classes, hard refusal to let the six-family objective become five), candidate validation, recorded deterministic tie-break (order-independence tested), atomic validated artifact save/load, helper guards, numerically stable sigmoid.
- **B-012 service fixes:** `ExpertInitError` now actually caught (survivors continue, zero survivors fatal, registry injectable for tests); expert warnings aggregated into `PredictionRecord.warnings`; threshold/fusion fail closed.
- Last Pillow `mode=` deprecation removed; goldens unchanged (no version bump). **Suite: 438 green**, warnings 47 → 5.


## 2026-08-27 — Calibration/threshold module + Pillow deprecation cleanup
- `src/router/calibration.py` + `tests/test_calibration.py` (**30 tests**) — see `workstreams/training/STATE.md`; logged here because it lands in `src/router/` (core-adjacent, Claude-owned).
- **Deprecation cleanup:** removed the deprecated `mode="RGB"` argument from every `Image.fromarray` call in my modules/tests (removed in Pillow 13, Oct 2026). **Golden tests still pass unchanged**, which is the proof the output is byte-identical — no `PIPELINE_VERSION` bump needed. Suite warnings fell 344 → 47 (the remainder are product-side gradio/`getdata` notices in Codex's lane).
**Combined suite (both agents): 349 tests green.**

## 2026-08-26 (late) — Mild self-probes (doc 03 step 4) — the router's reliability signal
- `src/pipeline/probes.py` + `configs/probes.yaml` + `PROBE_VERSION` in `version.py` — 3 probes exactly as doc 03 specifies: `probe_jpeg_q92`, `probe_crop_0.96` (95–98% band), `probe_resize_0.90`. Features: `probe_mean/std/range/max_delta/flip` + `n_probes_ok`, schema `probe-features.v1`.
- **Namespace separation enforced by test:** probe ids are `probe_`-prefixed and asserted disjoint from the 20 official condition ids, so a diagnostic can never leak into the stress-matrix table (eval spec requires unofficial suites live in their own namespace). `PROBE_VERSION` is separate from `PIPELINE_VERSION` so changing a probe invalidates router features without implying the official grid moved.
- **Probe pixel ops reuse the official transform primitives** (`_jpeg`/`_crop`/`_resize`) rather than reimplementing them — probe JPEG encoding cannot drift from official JPEG encoding.
- **Missing-value discipline (doc 03 step 5):** a failed probe is recorded as a typed failure and shrinks `n_probes_ok`; it never contributes an invented score. If ALL probes fail, the summary features are `None` — and `probe_flip` is `None` (unknown), explicitly not `False`. Tested both ways.
- `tests/test_probes.py` — **17 tests**; feature math asserted exactly against a scripted stub expert (population stdev, range, max-delta, flip-at-threshold), plus real-adapter integration and a 6px-image case.
- **First measurement:** probe instability is genuinely discriminative — on CF-384, `texture.png` swings ~50x more than `photo.png` (probe_range 0.031 vs 0.0006). That spread is exactly the signal the Phase-2 router is meant to learn from.
- **NOT wired into `prediction.v1`:** that schema is frozen with Codex and probes would triple per-image latency. Phase-2 feature-cache calls `compute_probe_features` directly; proposing an optional `probes` field to Codex when the router lands.
**Suite total: 306 tests green.**

## 2026-08-26 ~23:00 — Task 1.4 quality descriptors (early, unblocked)
- `src/pipeline/quality.py` — `QualityDescriptors` (`quality-descriptors.v1`): `blur_varlap` (variance of Laplacian on [0,1] luma), `blockiness` (8x8 grid-energy ratio), `noise_sigma` (Immerkaer-style median-absolute estimate, edge-robust), plus luminance mean/std, saturation mean, clipped-low/high fractions, and geometry (w/h, megapixels, aspect, portrait). numpy-only, deterministic, own strided `valid` convolution (no scipy dependency).
- `tests/test_quality.py` — **29 tests** pinning the DIRECTION of each descriptor under the official conditions (that is what the Phase-2 router depends on), not content-dependent exact values.
- **Measured limitation, documented not hidden:** blockiness is inflated by content that is itself 8px-periodic and grid-aligned (fences, blinds, halftone, UI screenshots) regardless of compression — our own `photo.png` fixture scores ~22 uncompressed, and its value FALLS at q90 because JPEG smooths the aliasing. Verified the metric is correct on non-aliasing content (`gradient` 1.00→2.42, `texture` 0.97→1.26 as quality drops q100→q30). Conclusion recorded in the docstring: router feature, never a standalone compression detector. Good raw material for the Phase-4 error-analysis note.
- Also pinned: a linear ramp sits at the var-of-Laplacian floor (~1e-7) by construction, so blur cannot lower it — pinned as a test so a future reader does not mistake it for a broken estimator.
**Suite total: 289 tests green.**

## 2026-08-26 ~22:30 — `scripts/infer_dir.py` built early (Phase-1 item, unblocked)
Built ahead of schedule because it is the REQUIRED official deliverable and the likely judge entry point; the contested corrupt-file default (A-010 item 3) is implemented as `--errors {null,skip,strict}`, so Codex's pending ACK only flips a default rather than requiring a rewrite.
- `scripts/infer_dir.py` — thin wrapper over `PredictionService`; recursive discovery, case-insensitive extension match, ordering by normalized relative POSIX path, atomic write via temp+rename, per-file error isolation, progress to stderr, JSON array of `{image_path, pred}` to stdout file.
- `tests/test_infer_dir.py` — **18 tests**, the full product-spec §5 standing gate checklist: both-class valid images, nested-path + ordering determinism, corrupt-file behavior in all three modes, required-keys/range validation, relative-POSIX-path assertion, batch≡direct-service parity, byte-identical rerun, empty dir, 4px thumbnail, atomic-write residue check.
- Verified on a mixed directory: nested `.PNG` found, `.txt` ignored, corrupt `.jpg` → `{"pred": null, "error": "decode_failed"}` with exit 0; `--errors strict` exits nonzero.
**Suite total: 260 tests green.**

## 2026-08-26 ~21:15–22:10 — Phase 0 tasks 0.2–0.6 built and green (242 tests)
**Spec:** `specs/phase0-core.md` v2 (FROZEN). **Tests:** `.venv/bin/python -m pytest tests/ -q` → **242 passed**.

Files added (all `[claude]`, core-owned):
- `src/pipeline/version.py` — single version source (`PIPELINE_VERSION=0.1.0`, `GOLDEN_VERSION=0.1.0`). No other module defines a version literal.
- `configs/transforms.yaml` — sole authoritative numeric source for all 20 conditions + encoder/kernel manifest.
- `src/pipeline/decode.py` (**0.2**) — `DecodedImage` (frozen) with `raw_*` pre-EXIF dims, canonical post-EXIF dims, `bit_depth`, machine-readable warnings; typed `DecodeError`; `LOAD_TRUNCATED_IMAGES=False`. 14 tests.
- `src/pipeline/transforms.py` (**0.3**) — all 20 conditions, config-driven, deterministic; `FAMILY_OF` exposes the 6 transform families the eval threshold objective needs. 144 tests.
- `tests/golden/` + `scripts/{make_golden_sources,regen_golden}.py` (**0.4**) — 3 self-made sources (no third-party content), 60 golden records with shape+mode inside each record; version-drift tripwire test. 63 tests.
- `src/experts/base.py` — `ExpertOutput` (success-only, finite-value guards in `__post_init__`), `ExpertInferenceError`/`ExpertInitError`, embedding-never-serialized rule. 11 tests.
- `src/experts/commfor.py` (**0.5**) — CF-384 adapter. Loads `model.safetensors` directly (bypasses the `device:"cuda"` config trap), `timm` backbone `pretrained=False` + `strict=True` load, sigmoid applied exactly once, `logit_on_device()` for the backend check.
- `src/pipeline/service.py` + `configs/predict.yaml` — `PredictionService` (**the single decision path**), `prediction.v1` record matching product spec §2.
- `scripts/predict.py` — thin CLI, zero decision logic. `scripts/sanity_check.py` (**0.6**).

**Measured (first real numbers):**
- **MPS-vs-CPU consistency PASSES** — worst |Δlogit| = **1.48e-05** across 3 images (tolerance 1e-2). MPS is trustworthy for this checkpoint; no CPU fallback needed.
- Checkpoint `OwensLab/commfor-model-384@6076002bf0d9dd37537f965ee2f06f826c333b61`, **21.81M params** (matches the card), loads in ~1s.
- Throughput ~**14 ms/image** on MPS after warmup (~70 img/s) — comfortably above the 10 img/s feature-cache escalation threshold in `06-build-plan.md`. Provisional input to the Phase-2 compute decision.
- CLI↔service parity asserted (`tests/test_service_parity.py`).

**Two protocol deltas found during build** (both recorded in CHANNEL A-011, no measured numbers affected, goldens unchanged, `PIPELINE_VERSION` NOT bumped):
1. **Blur kernel clamp.** torchvision `gaussian_blur` reflect-padding requires pad < min(H,W), so σ=2.0 (k=13) CRASHED on images under 7px. Kernel is now clamped to `min(k, 2*min(H,W)-1)` with σ unchanged; `k<=1` is the identity. Engages only below `ceil(3σ)+1` px, so no normal image is touched — but it stops a thumbnail in judge data from killing a batch run. Rule recorded in `configs/transforms.yaml`. Found by the note-N7 tiny-image property test.
2. **`DecodedImage` immutability, not hashability.** Spec §1 DoD said "hashable/immutable"; a frozen dataclass holding a `list[str]` is immutable but not hashable. Test asserts `FrozenInstanceError` on mutation. Contract fields unchanged.

**0.6 is partially complete:** the MPS-vs-CPU half passes now; the ≥20-real/≥20-fake clean-smoke AUROC half needs Codex's task 0.7 smoke manifest (`data/manifests/smoke_v1.json`) — `scripts/sanity_check.py` already reads that path and skips cleanly with a message until it exists.

**Scaffold boundary respected:** created only `src/pipeline/`, `src/experts/`, `configs/`, `tests/`, `scripts/` + my own files. No `pyproject.toml`, `uv.lock`, `.gitignore`, pytest config, or `git init` — those remain Codex's task 0.1. A local `.venv` was created to run the tests (derived artifact; `uv sync` will manage it once 0.1 lands).

## 2026-08-26 (evening) — Pre-build planning: spec v2 + integration research landed
Why: Mehul authorized planning before build ("start working on the plans"); spec-before-build agreed with Codex.
What: `specs/phase0-core.md` v2 — transform protocol v1 (exact params), ExpertOutput dataclass, CF-384 adapter section filled from verified research, §6b infer_dir (new official requirement, `docs/00a`). Handoffs: commfor-integration (green — exact preprocessing/output confirmed), lota-integration (RISK: Baidu-only weights, hardcoded cuda, inverted polarity). CHANNEL: A-006 review of Codex pre-build packet (ACK failure-semantics/ownership/screenshot, counters on threshold objective + corpus budget), A-007 research FYI. Fixed my CLAUDE.md line-41 mangle (Codex catch).

## 2026-08-26 — Workstream initialized
Why: Mehul requested session-continuity + dual-agent framework (26 Aug).
What: STATE.md created with Phase-0/next actions from 06-build-plan.md. No code exists yet.
