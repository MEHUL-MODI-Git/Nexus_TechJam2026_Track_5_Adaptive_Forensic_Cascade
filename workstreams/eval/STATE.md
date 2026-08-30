# eval — harness, metrics, ablations, error analysis
**Owner: Codex · Status: 🔴 PHASE-4 EXIT BLOCKED (B-032)**

## Current evidence
- Original Phase-2R eval repair remains accepted at `0a40ee8`; B-024 router repair is accepted.
- A-035 S1 threshold-split and S3 probe-drift repairs are accepted.
- S2's tied weighted AUROC and core sealed manifest/completeness checks are correct.
- Full suite: **769 passed, 1 skipped, 9 warnings**; focused gate: **78 passed**.
- Phase-4 audit focused suite: **102 passed**.
- The preserved dump remains complete: 174,380 rows / 8,719 sources / 20 conditions each.
  **Do not rerun it.**
- The real internal cache independently checks complete: 60,000 rows / 3,000 sources / 20 each.
- Current packet: `handoffs/2026-08-30_phase4-exit-review.md` / B-032.

## Remaining eval blockers
1. B-031 sealed strict schemas: fractional multiplicity and string abstention still move metrics.
2. The Phase-4 build-plan command/config does not exist; no canonical frozen reproducer covers the
   protected public tables.
3. The internal-test reporter accepts incomplete/mismatched caches and emits non-finite headlines;
   a 39-row/2-source/19-condition fixture returned rc=0.
4. Ablation generator/artifact says dev-fitted while it fits thresholds on train and does not index
   the complete ladder/±probe/±rescue evidence.

## NEXT ACTION
Wait for Claude's ACK/counter and batched B-032 repair; focused re-review before Phase-4 exit.

## Literal next command
```sh
cd "/Users/mehulmodi/MEHUL WORK/Hackathon/TechJam 2026" && tail -n 100 coordination/CHANNEL.md
```

## Hard constraints
- Never rerun the sealed reference set.
- One frozen threshold across conditions; no test/holdout/sealed retuning.
- No public number from malformed, incomplete or unbound input.
