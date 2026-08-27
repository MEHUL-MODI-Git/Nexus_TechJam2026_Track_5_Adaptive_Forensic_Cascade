# Active Plan Update — Post-LOTA Strategy

> **Status:** JOINTLY ADOPTED by Claude `A-023`/`A-024` and Codex `B-020` on 2026-08-27
>
> **Authority:** Mutable execution overlay for the remainder of the build. It changes model slots,
> task order, and kill decisions without rewriting historical ground truth in docs `00`–`08` or
> `06-build-plan.md`. Hard constraints and frozen evaluation rules remain binding.
>
> **Target:** submission-ready by 1 Sept 09:00; hard deadline 12:00.

## Decision in one paragraph

Do not reset the project. Community Forensics remains the production primary. The common path now
tests a **quality-conditioned correction head** over the primary logit; multi-expert fusion activates
only if a second always-on expert earns admission. PGC is the first licensed heavy candidate, but it
is evaluated only as a bounded challenger/selective rescue unless measured throughput makes it
affordable. GAPL is blocked from code integration until its repository licence is clear. LOTA
reproduction is removed from the schedule. The current logit-response DegradePrint branch is parked
after a negative unprotected diagnostic; embedding drift is deferred. No long cache run or public
release occurs before the existing eval/router gates pass.

## Evidence boundary

The 24,000-row pilot produced this diagnostic over three source-held-out seeds at a train-fitted 5%
clean-FPR target:

| arm | dev worst-family fake recall, mean |
|---|---:|
| primary logit | 0.211 |
| primary + quality | 0.604 |
| primary + quality + logit response | 0.612 |
| primary + logit response | 0.254 |

This is useful for prioritization only. The cache is `UNPROTECTED_SMOKE_ONLY`, uses obsolete
`feature-cache-row.v1`, has no untouched test or generator-held-out split, and the comparison lacks
paired source-bootstrap uncertainty. It cannot support a submission result, final component kill,
or the claim that quality lowered clean FPR. Reproduce with
`scripts/diagnostics/degradeprint_probe.py 0`, then seeds `1` and `2`.

## Mandatory model-economy execution rule

Mehul's 2026-08-27 instruction is binding for every implementation task:

1. The heavy owner writes the exact spec, acceptance tests, interfaces, safety boundaries and file
   ownership first.
2. A lighter model performs mechanical coding, test scaffolding, adapter wiring from a frozen spec,
   formatting, batch-job launch/monitoring, and other routine repository work.
3. The heavy owner reviews the diff, runs adversarial and full verification, and alone makes metric,
   architecture, threshold, licensing, data-split, kill-gate and release decisions.
4. Work is implemented directly by the heavy model only when it is too small to delegate safely or
   delegation would require transferring the same judgment-heavy context; the owner records that
   reason in the workstream CHANGELOG.

Pattern: **heavy spec → light implementation → heavy verification**. A lighter model never lands
unreviewed eval logic, router semantics, preprocessing behavior, contamination controls or public
claims.

## Phase 2R — Repair and freeze inputs

### 2R.1 Clear existing gates first

Run in parallel:

- **Codex / eval:** freeze E1–E5 as executable tests, then repair exact
  method×source×condition coverage, canonical-grid authority, loaded-threshold validation,
  diagnostic schema, keyed paired bootstrap, and complete freeze/provenance/failure-denominator
  guards.
- **Claude / training:** repair all B-018 consumed-field, source-label/split/cache-key, checkpoint
  load/parity/provenance, BCE-with-logits, baseline-ladder, kill-gate, and reliability-ordering issues.
- **Product:** task 1.5 is accepted. Release remains blocked; keep the remote private.

Exit: both adversarial gate packets pass, the full suite is green, and neither diagnostic nor
incomplete data can emit a headline.

### 2R.2 Repair data roles before fitting

- Acquire exactly **15,000 sources, 7,500/class**.
- Create a protected **12,000-source fitting manifest** (train/dev) and a separate untouched,
  balanced **3,000-source internal-test manifest**.
- Enforce exact SHA and perceptual near-duplicate separation across all roles; maintain consistent
  label per source; document that SID-Set lacks generator identity and therefore does not prove
  unseen-generator generalization.
- Validate the sealed WildFake SHA+pHash denylist before any fitting extraction. A hit aborts.

### 2R.3 Protected mini-pilot and one feature freeze

Use `specs/degradeprint-pilot.md` on a small protected source-disjoint subset before the long job.
The mini-pilot decides two things:

1. Does quality-conditioned correction pass the protected gain/clean-cost gate?
2. Do JPEG92/crop96/resize90 probe responses improve error prediction or selective risk beyond
   quality alone?

If (2) fails, remove probes before the long cache and save their three extra forwards per view. Add
no embeddings, blur probe, or heavy expert. ACK `feature-cache-row.v2`/spec v3: `probe_flip` is
derived only after threshold freeze and is never cached.

### 2R.4 Protected fitting cache

After the feature set and B-018 repair are jointly accepted, remeasure throughput on at least 200
sources and launch one protected fitting cache. Preserve full official family/severity coverage and
the <=12 h wall-clock cap; shrink source count only through a new joint decision if the measured
projection exceeds the cap.

Exit: atomic manifest, re-derivable key, exact expected row coverage, zero sealed hits, all fitting
rows from the fitting manifest, and no internal-test rows exposed to training.

## Phase 3R — Correction model and bounded candidates

Run in parallel after 2R.1:

### Common-path ladder — Claude owns training, Codex reviews metrics

1. raw primary;
2. calibrated primary;
3. regularized quality-conditioned logistic correction;
4. smallest justified MLP correction;
5. optional smooth worst-group objective.

Keep the simplest method whose paired source-bootstrap improvement is meaningful while clean
balanced accuracy regresses <=1 point and clean FPR rises <=1 point. Freeze class calibration and
the single cross-condition threshold before fitting reliability from source-disjoint/out-of-fold
predictions.

### Candidate preflight — split ownership

- **Claude:** licence/preprocessing fidelity and `src/experts/` adapters.
- **Codex:** repaired-harness comparison, paired deltas, latency presentation, and product impact.

Apply `specs/post-lota-model-preflight.md`:

- PGC first: Apache-2.0 code/weights, but ~1.25 GB checkpoint plus DINOv2-Large; 4 h adapter/preflight
  cap before parking.
- GAPL: HF model card says MIT, but official GitHub has no licence. No code copying or adapter
  dependency until resolved; then a 3 h cap.
- Smoke-grid results are diagnostic triage, not adoption evidence. CF remains primary unless a
  protected, paired comparison later shows a clear constrained win.

No heavy candidate enters the 15k training cache. A candidate may proceed to the rescue experiment
only if it has legal provenance, finite/parity-checked scores, measured memory/latency/parameters,
and material `P(candidate correct | common path wrong)`.

Exit: protected correction-head gate result and a documented keep/park decision for every candidate.

## Phase 4R — Optional rescue, freeze, final evaluation

1. Give the best admissible rescue candidate a **6 h total cap** on a stratified hard/easy fitting
   subset plus dev. Report invocation, correction, harm, common/rescued p50/p95 latency, and
   parameter total. Cut it if the robustness/selective-risk gain is <2 points, uncertainty includes
   no gain, or invocation is not selective.
2. Jointly freeze architecture, checkpoints, calibration, class threshold, reliability/abstention
   policy, configs, code commit and manifests.
3. Evaluate once on the untouched internal-test manifest with the repaired exact-coverage harness.
4. Only after freeze, run the sealed WildFake reference subset exactly once. It never changes the
   system.
5. Produce the robustness summary, error-analysis note, latency/memory/parameter evidence and final
   ablation table. Clearly label the preliminary DegradePrint diagnostic and SID-Set grouping limit.

## Phase 5R — Ship

- Claude drafts README narrative, Devpost text, video script and error-analysis prose; Codex reviews,
  integrates, and owns UI/repo mechanics.
- Restore public result claims only after eval and training peer gates.
- Pin all adopted checkpoint revisions and update `LICENSES.md`.
- Do not force-push or make the repository public until Mehul explicitly approves MIT licensing and
  the verified clean-history force-push. Re-audit the remote afterward.
- Run `infer_dir.py`, Gradio, frozen evaluation reproduction, licence, parameter and deliverable
  checklists before the 09:00 target.

## Honest fallback ladder

| failure | submission fallback |
|---|---|
| protected cache/correction fails | CF-384 + honestly fitted calibration/threshold if available + accepted stress UI + diagnostic robustness table |
| probes add no protected reliability signal | quality-only correction; omit probes from common path |
| correction fails its gate | calibrated CF-384 baseline |
| PGC/GAPL fails legal/runtime/complementarity gate | omit it; no heavy rescue |
| rescue fails | common path only; report negative rescue ablation |
| release approvals remain missing | escalate to Mehul; never publish dirty history or assert an unapproved licence |

The unprotected 24k pilot is never a submitted-model fallback.
