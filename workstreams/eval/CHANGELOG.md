# eval — CHANGELOG (newest first)

## 2026-08-30 — A-035 focused re-review: S1/S3 accepted; S2 narrowly blocked
Why: Claude requested the Codex-first focused gate after repairing B-030 and supplied additional
clean-checkout evidence in A-036.
What: verified the threshold split, tied weighted AUROC, exact condition/manifest checks and exact
probe-drift regression; ran 78 focused tests and the full suite (769 passed, 1 skipped, 9 warnings).
An adversarial 40-row fixture proved the sealed reporter still accepts `file_multiplicity=1.9`
against manifest multiplicity 1 and uses 1.9 as the metric weight (effective total 40→58), and
accepts abstention string `"false"` (coverage 0.525→0.500). Phase-4 acceptance remains blocked until
metric-bearing fields are strictly schema-validated. The sealed model was not invoked. Packet:
`handoffs/2026-08-30_a035-a036-focused-rereview.md`; B-031.

## 2026-08-29 — Claude Phase 3/4 relay review: BLOCK
Why: Mehul requested Codex's required review-first audit of Claude's relay and later evaluation work.
What: full 733-test suite and 70 focused tests pass, and the local sealed dump is complete, but
release/Phase-4 acceptance is blocked. The freeze fitted its threshold on train while public
provenance says dev; sealed reporting bypasses the accepted fail-closed eval boundary and lacks
committed input/artifact hashes; three audit/holdout scripts compute tied AUROC incorrectly; serving
does not cross-check checkpoint threshold against the frozen artifact; and threshold-dependent
`probe_flip` changes semantics between training and serving. Full evidence and corrected AUROCs:
`handoffs/2026-08-29_claude-phase3-4-relay-review.md`. No Claude-owned implementation was changed.

## 2026-08-27 — Mehul invoked Claude relay; A-027 baseline controls ACKed
Why: Codex is near its usage limit and Mehul directed Claude to take over.
What: B-028 activates PROTOCOL §6 for Codex-owned eval/product work. Eval's container-leak audit is
clean. ACKed mandatory `quality_only`, but claims must compare against both CF-only and quality-only
plus the simple ladder under paired source bootstrap and existing clean constraints. Q95 is only
blockiness mitigation; the SID-Set provenance confound remains. Relay work is Codex-review-first.

## 2026-08-27 — Phase 2R eval peer gate accepted; router B-018 re-review BLOCKED

Why: A-025 independently re-reviewed the eval repair and returned APPROVE-WITH-NOTES with one
required E3c fix; the router repair then needed Codex’s separate peer gate before protected data
work could begin.
What: ACKed A-025’s eval verdict. Commit 0a40ee8 adds shared full threshold-artifact schema
validation, a sentinel and exact forged-artifact regression, and the fail-safe "unspecified"
provenance fallback. Evidence is 70 focused tests, full shared-tree **662 passed / 9 warnings**,
and Ruff clean. The eval half of Phase 2R.1 is accepted/closed.
The independent B-018 router re-review is BLOCKED on five fail-closed issues: exact 64-hex cache
keys; strict non-boolean integer labels and mapping-valued expert containers; controlled None
threshold provenance; complete v2 checkpoint required-field/schema/dimension/finite-value
validation and cross-checks; and removal or repair of the stale unchanged-score diagnostic
artifact. Full packet: handoffs/2026-08-27_router-repair-rereview.md.
Next: wait for the heavy-spec → lighter-implementation → heavy-verification router correction
and re-review it; do not launch protected compute while router/data gates remain blocked.

## 2026-08-27 — Phase 2R eval repair locally green; peer re-review requested
Why: A-024 accepted B-016's E1–E5 block, and long/protected compute cannot begin while incomplete
or unprovenanced data can emit reportable output.
What: Landed `ff943c7` using heavy spec → lighter implementation → heavy verification. Exact
method/source/canonical-condition coverage, canonical-grid authority, loader-only threshold bytes,
headline-free diagnostics, keyed paired bootstrap, dataset/method/code/transform/golden/freeze/
sealed provenance, and fail-closed failure denominators now have adversarial tests. Heavy review
caught and corrected the lighter pass's private-constructor test shortcut, calibration-bootstrap
schema mismatch, and 20x view-inflated dataset counts; these metric/protocol judgments were kept by
the heavy owner rather than re-delegated. Focused gate: 85 passed; Ruff clean; full shared-tree suite:
630 passed, 9 warnings; live 8,000-row diagnostic CLI check passed without rewriting artifacts.
Packet: `coordination/gates/phase-2r-eval.md`. Acceptance still waits on Claude re-review.

## 2026-08-27 — Phase 2R heavy repair spec frozen for lighter implementation
Why: Mehul required visible heavy-spec → lighter-implementation → heavy-verification routing, and
the jointly ACKed E1–E5 gate needed exact executable semantics before mechanical edits.
What: Added `specs/phase2r-eval-repair.md`, freezing exact method/source/canonical-condition
coverage, internal canonical-grid authority, a loader-only threshold capability, headline-free
diagnostic structure, keyed paired bootstrap, and the eval-run/freeze/failure-denominator manifest
boundary. The spec also fixes transform-vs-dataset hash identity, sealed authorization, all-zero
flip attribution, parameter validation, and atomic Markdown writes. No production code changed in
this milestone; the bounded implementation is routed to a lighter agent for heavy review.

## 2026-08-27 — Post-LOTA plan adopted; E1–E5 repair claimed
Why: Mehul requested a joint replan from the update pack, while B-016 still blocks scientific use of
the harness. Claude A-024 ACKed the block with no counter.
What: adopted the active overlay in A-023/A-024/B-020; claimed Phase-2R eval repair; froze E1–E5 plus
provenance/freeze/failure-denominator guards as the next executable acceptance set. Candidate adapters
remain Claude-owned; Codex will own their repaired-harness comparisons. The unprotected 24k pilot is
explicitly diagnostic-only and cannot select a submission model or produce a headline.

## 2026-08-27 — Claude eval repair independently re-reviewed; gate remains blocked
Why: Claude claimed fixes for the B-015 scientific-boundary findings in `2624b99`.
What: reran 567 tests and wrote five adversarial reproductions: sparse per-source coverage, caller-shrunk official grid, fabricated threshold object, nested diagnostic headline, and input-order-dependent paired deltas. Also verified mislabeled transform provenance and absent sealed/freeze guards. Full packet: `handoffs/2026-08-27_claude-repair-review.md`; B-016 requests ACK/counters. No eval production code changed.

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

## 2026-08-29 — A-033/A-034 repair re-review: BLOCK remains on S1–S4
Why: Claude requested the Codex-first gate after repairing B-029 and then amended the packet at
`ea959ef` with regenerated holdout artifacts and a deliverables sweep.
What: independently ran 59 focused tests, the full 750-test suite, Ruff and adversarial sealed/tie/
probe checks. Accepted R1, the named R4 fixes, R5 and R7. Kept release/Phase 4 blocked because public
train-vs-dev wording and the future freeze path remain wrong; the sealed ledger does not bind current
artifacts/manifest identity to prediction rows or enforce exact condition multiplicity and retains an
order-dependent AUROC; and the probe train/serve drift is not tightly asserted/disclosed. Current
sealed rows remain independently complete and numerically valid; never rerun them. Packet:
`handoffs/2026-08-29_claude-r1-r8-rereview.md`; B-030.

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
