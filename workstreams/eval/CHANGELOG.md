# eval — CHANGELOG (newest first)

## 2026-08-27 — Codex critical relay review: task 1.1 blocked pending correction
Why: Mehul asked Codex to critically review Claude's provisional relay implementation before accepting ownership back.
What: independently verified the single-method smoke math and full suite, then reproduced method pooling, arbitrary-string headline provenance, partial-grid headline output, incomplete frozen schema/provenance, and missing paired uncertainty. Full 30-finding packet: `handoffs/2026-08-27_claude-relay-critical-review.md`; B-015 requests Claude's evidence-based ACK/counters. No eval production code changed in the review.

## 2026-08-27 — [relay] task 1.1 completed by Claude while Codex is limit-blocked
**PROTOCOL §6 relay invoked:** Mehul announced Codex hit its usage limits. Claude claimed the in-flight eval task. **All changes below are `[relay]` and Codex reviews them first on return.**

Codex had already built (untouched by me): `src/eval/protocol.py` (row validation, threshold-artifact loading) and `src/eval/metrics.py` (confusion counts, AUROC, AP, Brier, NLL, ECE, condition metrics, paired flips, signed drops, worst-condition). 12 tests. I built ON these and reimplemented nothing.

Added by Claude `[relay]`:
- `src/eval/results.py` — label-stratified **source-level bootstrap** (all views of a source travel together; resampling rows independently would shrink intervals by ~sqrt(20) and be confidently wrong), per-condition and per-family aggregation, signed drops, directional-flip attribution, and the `eval-results.v1` / `diagnostic-results.v1` assembly.
- **The B-014/A-021 boundary is now STRUCTURAL, not conventional:** `eval-results.v1` refuses to run against a `PLACEHOLDER` provenance, and `diagnostic-results.v1` refuses to run against anything else. A diagnostic document carries no `headline` block at all and repeats the provenance verbatim in a `NOT_A_HEADLINE_RESULT` field, so even a stray screenshot is self-incriminating. Neither path can produce the other's output.
- `src/eval/report.py` — markdown tables rendered strictly FROM the results JSON, never recomputed (two code paths producing "the same" number is how a report ends up disagreeing with its own artifact).
- `scripts/run_eval.py` — one command: rows → validated results JSON → markdown.
- `tests/test_eval_results.py` — **18 tests**, weighted toward the boundary (placeholder cannot make a headline; real artifact cannot make a diagnostic) and the objective semantics (clean excluded from worst-family; worst exact condition reported not selected on; selective/rescue explicitly null, never zero).

**First full evaluation artifact:** `results/grid-smoke-v1/diagnostic-results.{json,md}` over 8,000 rows, 1000 bootstrap replicates. It reproduces my independent diagnostic exactly (noise family recall 0.1650, blur AUROC 0.8576), which cross-validates Codex's metric code against my separate computation.

**New numbers the harness surfaced that I had not computed:**
- **max real→fake flip = 0.3150 at `blur_s2.0`** — 31.5% of real photos correctly called REAL when clean are flipped to "AI-generated" by heavy blur. This quantifies the systematic bias found in 1.3.
- **max fake→real flip = 0.5150 at `noise_s0.10`** — over half of correctly-detected fakes disappear under noise.
- `jpeg_q30` loses 0.4150 fake recall vs clean with **zero** FPR increase — JPEG degrades detection without inducing false alarms, unlike blur.

# CHANGELOG — eval (newest first, append-only; corrections are new entries)

## 2026-08-27 — Phase 1 task 1.1 started
Why: Phase 0 passed both independent gates and Claude ACKed the Phase-1 split in A-019; task 1.3 then produced the required 8,000-row grid input in A-020.
What: Claimed 1.1. Codex heavy retains metric/protocol logic and final verification; Luna received a bounded factual input audit before implementation. No smoke-derived threshold will be fitted or reported as headline.

## 2026-08-26 — Eval protocol contract frozen v1
Why: Mutual heavy-model review completed in A-010/B-008 before build.
What: `specs/phase0-eval.md` frozen with six-family bootstrap-mean threshold selection, source-level bootstrap, structured expert-failure records, `prediction-row.v1`, and `eval-results.v1`. Implementation remains Phase 1 after the Phase-0 gate.

## 2026-08-26 — Pre-build planning packet drafted; implementation intentionally deferred
Why: Mehul authorized planning with Claude before starting the build, overriding STATE.md's implementation next action for this session.
What: Audited Phase 0–5 dependencies, contracts, protocol/version locks, threshold/freeze semantics, and fallbacks. Proposal saved at `handoffs/2026-08-26_codex-prebuild-plan.md` and sent to Claude in MSG-005. No eval code or task claim started.

## 2026-08-26 — Workstream initialized
Why: Mehul requested session-continuity + dual-agent framework (26 Aug).
What: STATE.md created with Phase-0/next actions from 06-build-plan.md. No code exists yet.
