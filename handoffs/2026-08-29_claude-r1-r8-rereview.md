# A-033/A-034 R1–R8 repair re-review — Codex verdict

**Reviewer:** Codex (AGENT-B) · **Date:** 2026-08-29 · **Boundary:**
`e299203..ea959ef` (repair commits after B-029)

## Verdict

**BLOCK remains for Phase-4 acceptance and release.** R1, R4's named retention/holdout
repairs, R5, R7 and the UI abstention wording are accepted. The full suite is stable and the
current preserved sealed dump is complete. R2, R3, R6 and R8 are only partially repaired.

## Independent verification

- Focused repair gate: **59 passed**; post-A-034 published-number/tie subset: **20 passed**.
- Full suite: **750 passed, 1 skipped, 9 warnings**.
- Repository Ruff: **29 findings** (reduced from 62, not clean).
- Both serving checkpoints and the degradation reporter are tracked; the shipped config names
  `router_reliability.pt`; a foreign threshold is rejected.
- Corrected retention values reproduce: internal **0.8696**, holdout **0.8636**, 2-condition
  internal **0.8690**, holdout **0.8374**.
- Preserved sealed dump still hashes to
  `db1d214802a4c58786613606261944befaf43ab47228985ffdea282b7bf6edbd` and independently has
  174,380 rows, 8,719 unique hashes, exactly 20 rows/hash, no source-set difference from the
  sealed manifest, no label/group conflicts and no multiplicity mismatches. **Do not rerun it.**

## Remaining blockers

### S1 — R2 wording and the future freeze path remain wrong

README §2 still says the threshold was “fitted on dev”; the constraint section twice says it was
“selected on dev”; and the ablation paragraph calls every rung threshold “dev-fitted.” The tracked
`results/router-fitting-v2/threshold-fitted.json` says the opposite: the rung thresholds were fitted
on train. README §6's deviation disclosure is correct, but it does not neutralise contradictory
claims elsewhere in the same public document.

`scripts/freeze_router.py` is deliberately left with the known train-vs-dev bug. Patching it for
future runs would not falsify the old artifact: that artifact already records its own fitting-code
revision. Keep the shipped threshold and sealed scores unchanged, but make any future freeze pass
held-out dev or fail closed. No refit and no sealed rerun are requested.

### S2 — R3's sealed-report boundary is not actually bound to the run

The v2 summary hashes the prediction dump, then separately hashes whichever checkpoint/config/
manifest files happen to exist when the summary is regenerated. Nothing proves those files produced
those rows. The dump has no method/checkpoint/config/code identity fields; the reporter does not
cross-check its SHA set, label/group metadata or `file_multiplicity` against `sealed_files.json`.
Its `code_revision` is the summary-regeneration HEAD (`e299203`), not the inference revision, and
that commit did not even contain the v2 reporter (it landed in `720d432`).

The claimed “every condition exactly once” check is also only set equality. A second row for the
same `(sha256, condition_id)` with a different `view_id` passes. Labels accept values outside
`{0,1}`. These are executable fail-closed gaps, not documentation preferences. The current dump is
valid by independent audit, so repair the validator/ledger from the preserved dump only; never
invoke the model.

The sealed reporter also retains its own order-dependent AUROC implementation. On the minimal tied
pair it returns 0 or 1 depending on row order instead of 0.5. The real dump has 31,231 `p_fake` rows
inside tied-score groups; shuffling moves the deduplicated AUROC by about 1.5e-7 (headline rounding
unchanged). Use the canonical tie-aware metric for the unweighted convention and a genuinely
tie-group-aware weighted implementation for per-file reporting.

### S3 — R6 is bounded loosely, not fully asserted or truthfully described

The new test is useful, but it does not assert the disclosed max score drift and allows up to 1,499
changed rows / 10 verdict changes. On the internal test I reproduce **550 changed rows, max
|delta p_fake| 0.298885, 2 verdict changes**; B-029's dev result remains 578 / 0.29525 / 3.
`handoffs/CHECKPOINT-NIMS.md` nevertheless says “train/serve parity ... 0 verdict disagreements.”
That result is cache/live parity under serving semantics, not training/serving feature parity.
Name the distinction and lock the measured score/verdict bounds; do not change the frozen model.

### S4 — R8's release truthfulness sweep is still incomplete

- README and Devpost label LOTA “MIT,” while the repository code is MIT but the external Baidu
  checkpoints have no stated licence. Public wording must distinguish code from weights.
- README says the shipped checkpoint has “1,827 params + a 17-param reliability head,” but the
  actual 1,827 already includes that 17-parameter head. The total 21,814,571 is correct.
- The new Devpost sealed section says the reference set was “never thresholded on,” then says the
  primary control's threshold was fitted on that same set. Scope the first statement to the shipped
  cascade.
- `workstreams/training/STATE.md` still says the sealed run “has not been touched,” despite A-034
  updating the adjacent review status.

## Accepted and not to be reopened without new evidence

- R1 clean-checkout artifact tracking.
- R4 corrections in the three named retention/holdout scripts and A-034 artifact regeneration.
- R5 checkpoint ↔ threshold-artifact rejection.
- R7 total/percentage arithmetic: **21,814,571, 1.09% of 2B**.
- Current sealed numerical results and completeness as facts about the preserved dump; the block is
  the reusable provenance/validation boundary, not a request to score it again.

## Required next packet

Batch S1–S4 into a stable commit and request one focused re-review. Mehul's separate decisions
(accepting the disclosed train-fitted threshold, MIT/public-history release, and video asset choice)
remain owner actions and are not self-cleared by either agent.
