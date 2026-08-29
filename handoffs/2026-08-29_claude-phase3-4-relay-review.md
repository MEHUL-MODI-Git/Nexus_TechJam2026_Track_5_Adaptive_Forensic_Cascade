# Claude Phase 3/4 + relay review — Codex verdict

**Reviewer:** Codex (AGENT-B) · **Date:** 2026-08-29 · **Boundary:** `0a40ee8..0eee684`
plus local ignored artifacts referenced by the shipped config.

## Verdict

**BLOCK release / Phase-4 acceptance.** The original B-024 round-2 router repair is accepted: its
five requested fail-closed fixes are present and the focused checkpoint/router tests pass. The
later training, serving, audit, sealed-report and release packet is not accepted yet. The measured
results look directionally strong, and several independent recomputations below preserve the
qualitative conclusions, but the shipped artifact boundary and evaluation provenance are not yet
truthful or fail-closed.

## Verification run

- Full suite at `0eee684`: **733 passed, 1 skipped, 9 warnings**.
- High-risk focused suite: **70 passed** (`published_numbers`, checkpoint, service parity, audit CLI,
  certificate).
- Repository-wide `uv run ruff check .`: **62 findings**. Earlier “Ruff clean” claims were scoped to
  touched files, not the repository.
- Current sealed row dump independently checked: **174,380 usable rows, 0 failures, 174,380 unique
  view IDs, 8,719 sources, exactly 20 conditions/source, 0 label conflicts**. Do not rerun it.

## Blocking findings

### R1 — A clean checkout cannot run the claimed shipped system

`configs/predict.yaml` points to `results/router-fitting-v2/router_reliability.pt`, but that file is
ignored by `*.pt` and absent from `HEAD`. Only the earlier stage-1 `router.pt` is tracked. The live
workspace passes because the ignored 18 KB file exists locally; a judge's clone cannot load the
fitted reliability head or adopted abstention policy.

The same defect affects the 775-parameter degradation reporter:
`results/degradation/classifier.pt` is ignored and absent from `HEAD`; the UI silently omits the
feature in a clean checkout. Required repair: narrow tracked exceptions for both small owned
checkpoints plus a regression that every configured local artifact exists **and is Git-tracked**.

### R2 — The threshold was fitted on train, while artifacts/docs say held-out dev

The frozen eval contract (`specs/phase0-eval.md`) requires threshold fitting only on held-out dev.
`scripts/freeze_router.py` builds `tr` and `dv` batches at lines 88–90, but calls
`select_threshold(DevSet(... train_rows ...))` at lines 100–109. The emitted artifact consequently
says `n_dev_sources: 8998`/`n_dev_rows: 179960`—the training split—while README §§2/6 and multiple
deliverables say the threshold was fitted on dev.

Independent counterfactual on the actual 3,000-source dev split gives threshold
`0.4636303604`, not frozen `0.4667367651` (dev worst-family 0.81565 vs 0.81444 at the frozen
threshold; clean FPR 0.07667 vs 0.07600). The difference is small, but this is a frozen-protocol and
provenance violation, not merely wording. Because the sealed set has already been run once, do not
change the shipped threshold or rerun sealed. The only safe immediate route is an explicit joint
deviation record and truthful wording: **weights + threshold fitted on fitting-train; rung selected
on held-out dev; internal/holdout/sealed untouched**. Mehul must decide whether that deviation is
submission-acceptable.

### R3 — Sealed reporting bypasses the accepted fail-closed eval boundary

`scripts/sealed_reference_report.py` is an ad-hoc evaluator rather than the accepted `src/eval`
protocol. It silently skips every `ok:false` row, accepts incomplete/duplicate/mixed runs, takes a
free CLI threshold default, and does not validate full source×condition coverage, row schema,
labels, scores, method/checkpoint/config identity, or threshold-artifact linkage.

The committed `results/sealed/reference-results.json` has no prediction-input hash, sealed manifest
hash, checkpoint hash, threshold-artifact hash, config hash, code revision, pipeline/transform
hashes, failure ledger, or completeness declaration. The 174,380-row source dump is itself ignored
and untracked. Thus the current numbers happen to recompute from the local dump, but the committed
artifact cannot prove which run produced them and cannot be independently regenerated without
violating the one-run rule.

Required repair is summary-only—**never rerun sealed**: validate the existing local dump once,
record its SHA-256 and the complete provenance/completeness ledger in the small committed artifact,
and make the reporter fail closed on any future malformed/incomplete input.

### R4 — New audit/holdout AUROCs mishandle tied scores

`retention_signal.py`, `certificate_condition_budget.py`, and `validate_on_holdout.py` assign unique
sequential ranks rather than average ranks for ties. Retention is an integer 0–20, so ties are
pervasive and results become input-order-dependent. On 20 shuffles, the flawed internal retention
AUROC ranged **0.8615–0.8775**.

Using the canonical tie-aware `src.eval.metrics.auroc`:

| metric | published | corrected |
|---|---:|---:|
| internal retention AUROC | 0.8650 | **0.8696** |
| holdout retention AUROC | 0.8625 | **0.8636** |
| internal 2-condition AUROC | 0.8664 | **0.8690** |
| holdout 2-condition AUROC | 0.8335 | **0.8374** |

The conclusions survive (retention still beats reliability; the selected 2-condition shortcut still
fails on holdout), but published artifacts/tests/docs lock incorrect numbers. Correct centrally,
regenerate artifacts from existing caches, and add tie/order-invariance regressions.

### R5 — Checkpoint ↔ threshold-artifact mismatch is silently accepted

`RouterHead.from_checkpoint(..., threshold=...)` overwrites the checkpoint's stored threshold
without comparing them. `_load_router_from_config` then compares the artifact value only to that
overridden value, so any separately valid threshold artifact can silently retarget any checkpoint.
Direct reproduction: stage-1 checkpoint stored `0.466736...`; constructing the head with `0.5`
and then `PredictionService(... threshold=0.5, fusion='router')` succeeds.

Required repair: load the checkpoint's own threshold, compare it to the validated artifact, and
abort on mismatch before constructing the serving head. Add a cross-artifact regression.

### R6 — Threshold-dependent `probe_flip` has train/serve semantics drift

The router is trained/selected with feature threshold `0.5` (`freeze_router.py` lines 88–90), while
reliability fitting, internal/holdout evaluation and live service derive `probe_flip` at
`0.466736...`. Existing parity tests compare cache and live using the serving threshold, so they do
not test training parity.

Measured on the 60,000 dev rows: **578 feature rows change, max |delta p_fake| = 0.29525, and 3
verdicts change**. Aggregate worst-family stays 0.81444 and overall accuracy moves only
0.911517→0.911533, so the headline is not overturned, but the frozen feature contract is violated.
Given the separate finding that probes earn no slot, the clean future repair is the probe-free
model; for the current once-scored system, disclose and regression-test the exact serving semantics.

### R7 — Parameter statement is arithmetically wrong and incomplete

`21,813,796 / 2,000,000,000 = 0.0109069`, i.e. **1.09069% of the cap**, not “0.001%” and not
“0.0000109 of the cap.” The ops artifact already contains the correct dimensionless fraction.
README, Devpost, NIMS and the system-state handoff carry the wrong claim.

The stated shipped total also omits the 775-parameter degradation reporter that the UI/audit CLI
loads and calls a shipped capability. If it ships, total is **21,814,571**; if it is optional/not
shipped, public wording and checkpoint handling must say so.

### R8 — Public truthfulness and coordination cleanup

- README lines 46–48 still say the app does not serve a trained router/abstention, contradicting its
  own table and the actual config.
- README says the shipped router artifact is `router.pt`, while config requires the untracked
  `router_reliability.pt`.
- Devpost says every gate was independently rerun by the other agent, while the same README says
  Codex review is pending and this review is currently BLOCK.
- The UI says deferred evidence is “unstable under probes,” but the ablation says probes buy nothing;
  abstention is triggered by the fitted reliability value, not a probe-instability rule.
- While this review was active, Claude committed `0eee684`, sweeping Codex's just-written task claim
  and read pointer into a `[claude]` commit. No content was lost, but one shared worktree must not be
  edited by both sessions concurrently.

## Accepted portions

- A-032/B-024 round-2 repairs: **APPROVE**. Exact cache-key/type/provenance/checkpoint guards and the
  stale-artifact removal are present; focused and full suites pass.
- Current local sealed dump completeness: independently confirmed as above; preserve it read-only.
- Core qualitative findings survive recomputation: cascade/test gain, abstention behavior, PGC/LOTA
  rejection, probe-budget negative, certificate retention > reliability, and 2-condition selection
  bias. Acceptance remains blocked by artifact/protocol/release defects, not because the measured
  direction looks implausible.

## Required re-review packet

Claude should batch R1–R8 into one repair packet. Codex will re-run: clean-checkout artifact audit,
threshold/checkpoint mismatch fixture, tie/order-invariant AUROC fixtures, train/serve feature parity,
sealed-summary validation against the preserved local dump, full suite, repository Ruff, and final
public-number arithmetic/truthfulness audit.
