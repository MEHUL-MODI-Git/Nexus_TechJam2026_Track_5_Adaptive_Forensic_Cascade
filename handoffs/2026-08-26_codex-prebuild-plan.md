# Codex pre-build plan — proposal for Claude review

**Date:** 2026-08-26  
**Status:** PROPOSAL — no implementation tasks have started  
**Scope:** Convert docs 00–08 and `06-build-plan.md` into a collision-safe execution sequence for the equal Claude/Codex partnership.

## 1. Strengths-based allocation

| Work | Executor | Reviewer / dependency |
|---|---|---|
| Core decode, expert preprocessing/adapters, training/cache/router | Claude | Codex reviews interfaces, tests, and phase-gate evidence |
| Eval metrics/harness, debugging, Gradio/plots/product mechanics | Codex | Claude reviews eval/product gate evidence |
| README/Devpost/video/error-analysis prose drafts | Claude | Codex verifies claims, integrates artifacts, owns publication mechanics |
| Cross-cutting architecture/data/protocol/threshold/scope decisions | Joint | Evidence decides; unresolved after one exchange → Mehul |
| Mechanical scaffolding/downloads/formatting/job monitoring | Light subagents | Owning heavy agent writes spec and verifies output |

Ownership prevents file collisions; it is not a judgment hierarchy. A task that fights its owner for more than one hour is offered to the peer in `CHANNEL.md`.

## 2. Locks required before build tasks

| Lock | Proposed owner | Required outcome before dependent code |
|---|---|---|
| Ownership + Phase-0 split | Joint | ACKed in MSG-004; Claude ACK/counter pending |
| `ExpertOutput` v1 logical contract | Joint | Doc-03 fields frozen; concrete Python/type/failure semantics agreed |
| Prediction record/API v1 | Claude proposes, Codex reviews | One record usable by CLI, Gradio, and eval; `P(fake)` polarity explicit |
| Eval-results JSON v1 | Codex proposes, Claude reviews | Run metadata, protocol version, per-condition metrics, bootstrap CIs, artifact links |
| Feature-cache row v1 | Claude proposes, Codex reviews | Source/group IDs, label, transform ID, expert/probe/quality/runtime values, missing flags, hashes/versions |
| Transform protocol v1 | Claude proposes, Codex reviews | Manifest fixes encoder/interpolation/range/crop/jitter/seed semantics; golden version and cache version tied together |
| Smoke manifest v1 | Codex | ~200 COCO train2017 real + ~200 licensed fake; fixed IDs, source/license, SHA-256/pHash; never COCO val2017 |
| Environment/repro lock | Joint | Python/uv dependencies, model cache paths, MPS→CPU fallback, seeds, config-version policy |
| Router data/fallback budget | Joint at Phase-2 entry | Reconcile build-plan 20–40k target vs doc-04 40–60k recommendation; define minimum viable size and extraction time cutoff |
| Threshold/reliability objectives | Joint before fitting | One dev-chosen class threshold across conditions; explicit reliability target and abstention fallback |
| Freeze manifest | Joint before Phase 4 | Commit/config/data manifests/checkpoints/transforms/seeds/calibration/thresholds fixed before single sealed run |

## 3. Contract proposals

### `ExpertOutput` v1

Keep the exact logical fields in doc 03:

- `expert_id: str`
- `raw_logit: float | null`
- `probability_after_expert_calibration: float | null`, always `P(fake)` in `[0,1]`
- `optional_embedding: array | null`
- `optional_patch_scores: array | null`
- `inference_ms: float`, non-negative
- `warnings: list[str]`

Proposed failure rule: an adapter initialization failure is fatal for that configured expert; a per-image recoverable failure emits null score fields plus a machine-readable warning and lets the cascade degrade according to doc 03. Checkpoint/preprocessing/license/parameter metadata belongs in the run manifest rather than being repeated in every output.

### Prediction record v1

Minimum cross-consumer record:

- schema/pipeline/config version; sample/source/image path or stable ID; content hash;
- optional ground-truth label (never required for inference);
- transform condition ID and source-view grouping ID;
- calibrated `p_fake`, forced-binary prediction at the single threshold, display decision (`REAL`/`AI-GENERATED`/`UNCERTAIN`), reliability;
- expert outputs, fusion weights, probe summary, rescue status, total/component runtimes, warnings;
- checkpoint and preprocessing versions in the containing run manifest.

The newer official screenshot's batch entrypoint emits a JSON list with at least `image_path` and numeric `pred`; additional diagnostics may be included only if the acceptance format permits them.

### Eval-results JSON v1

Top-level sections:

1. `schema_version` and run/config/git provenance.
2. Dataset manifest hash, split, source count, class counts, and sealed/reference flag.
3. Transform manifest/golden/cache versions and fixed threshold.
4. Method/checkpoint/parameter/runtime metadata.
5. Per-condition confusion counts and metrics.
6. Headline aggregates: clean/worst BAcc and fake recall, FPR, drops, directional flips, AUROC/AP.
7. Source-bootstrap confidence intervals and paired deltas.
8. Selective/rescue/calibration tables when applicable.
9. Paths/hashes for prediction rows and generated Markdown/plot artifacts.

Bootstrap units are source images, never transformed views.

## 4. Execution sequence

### Planning checkpoint P0 (now)

1. Reconcile newer screenshot deliverables and repair malformed shared-rulebook line.
2. ACK/counter this plan and assign owners for the four contracts.
3. Record only agreed cross-cutting items in `DECISIONS.md`.
4. Do not claim build tasks until Mehul gives build authorization.

### Phase 0 — first signal

1. Codex claims/scaffolds 0.1 locally; public GitHub creation is a separate external action requiring the target repo identity/credentials.
2. After scaffold, Claude claims 0.2–0.6 while Codex claims 0.7 and 0.8.
3. App starts against the agreed prediction interface; a stub is allowed until the CF adapter lands.
4. Codex verifies provenance/counts/licenses for smoke data; light subagent may perform downloads only from a written spec.
5. Both agents produce gate packets; each independently runs the other's exit evidence.

### Phase 1 — baseline and demo

1. Codex implements eval-results v1, metrics tests, source bootstrap, JSON/Markdown generation.
2. Claude supplies deterministic transforms plus CF/LOTA outputs; Codex runs the frozen full-grid shootout.
3. Pre-webinar results are labeled provisional. Webinar answers trigger manifest/golden/cache version changes before any headline result is retained.
4. Primary selection uses worst-family fake recall, FPR, directional flips, calibration, and latency; near tie keeps CF-384.
5. Codex implements stress UI and license/repo checklist; phase gate freezes the baseline protocol.

### Phase 2 — trained fusion

1. Denylist and grouped source manifest exist before any fitting/caching job.
2. Throughput benchmark chooses local vs GPU and activates a pre-agreed corpus/time fallback.
3. Claude produces versioned cache/router/calibration artifacts; Codex validates schema and acceptance metrics.
4. Proposed class-threshold objective: maximize dev worst-exact-condition fake recall subject to clean FPR no more than primary +1 point and clean BAcc no worse than primary -1 point. Claude should counter if statistically unsuitable.
5. Keep the simplest ladder rung that meets gates; Codex adds evidence/reliability UI only for the retained variant.

### Phase 3 — rescue only after router acceptance

1. Start WaRPAD only after Phase-2 common path passes or an explicit joint exception.
2. Enforce six-hour integration cap and bounded rescue-rate target; RIGID substitution requires rerun/decision record.
3. Codex computes conditional correction, joint failure, error correlation, oracle ceiling, rescue correction/harm/rate, and matched latency.
4. Retain rescue only if it meets doc-08 benefit/latency criteria; otherwise publish a negative ablation.

### Phase 4 — freeze and one sealed run

1. Freeze production variant, manifests, transforms, seeds, checkpoints, router/calibration, thresholds, and code revision.
2. Ensure internal ablation predictions/caches already exist or can be reproduced without using sealed outcomes for selection.
3. Run required internal/full metrics, reproducibility, error exemplars, and ops evidence.
4. Run WildFake reference exactly once after freeze; never adjust anything from its outcome.
5. Claude drafts prose artifacts; Codex verifies every claim against measured JSON and integrates tables/plots.

### Phase 5 — ship

1. Batch inference script satisfies newer `image_path`/`pred` JSON requirement.
2. README includes overview, setup, reproduction, limitations/future work, solo contribution, licenses, parameter statement.
3. Gradio polish remains stretch; reproducibility, video, Devpost, public repo, and submission buffer outrank it.

## 5. Gate evidence invariant

Each gate packet must include exact commands, exit codes/test output, metric artifact paths/hashes, hard-constraint checklist, known gaps, fallback state, and proposed next split. The reviewing peer runs the exit test rather than trusting prose.

## 6. Open decisions for Claude/Mehul

- Treat the 26-Aug screenshot additions as binding? Codex proposes yes.
- Confirm concrete `ExpertOutput` null/failure rules and prediction-record owner.
- Confirm threshold objective or propose a better predeclared objective.
- Set Phase-2 target/minimum corpus and hard extraction cutoff after throughput measurement.
- Decide public GitHub repository name/owner before the external create/push step.

