# eval — harness, metrics, ablations, error analysis
**Owner: Codex · Status: 🔴 PHASE-4 ACCEPTANCE NARROWLY BLOCKED (B-031)**

## Current evidence
- Original Phase-2R eval repair remains accepted at `0a40ee8`; B-024 router repair is accepted.
- A-035 S1 threshold-split and S3 probe-drift repairs are accepted.
- S2's tied weighted AUROC and core sealed manifest/completeness checks are correct.
- Full suite: **769 passed, 1 skipped, 9 warnings**; focused gate: **78 passed**.
- The preserved dump remains complete: 174,380 rows / 8,719 sources / 20 conditions each.
  **Do not rerun it.**
- Current packet: `handoffs/2026-08-30_a035-a036-focused-rereview.md` / B-031.

## Remaining eval blocker
The sealed reporter accepts fractional `file_multiplicity` while using it as a metric weight, and
accepts string `"false"` as an abstention boolean. Both malformed values silently move public
metrics. Require strict field schemas plus adversarial regressions, using the preserved dump only.

## NEXT ACTION
Wait for Claude's single ACK/counter and narrow summary-only repair; focused re-review before gate.

## Literal next command
```sh
cd "/Users/mehulmodi/MEHUL WORK/Hackathon/TechJam 2026" && tail -n 100 coordination/CHANNEL.md
```

## Hard constraints
- Never rerun the sealed reference set.
- One frozen threshold across conditions; no test/holdout/sealed retuning.
- No public number from malformed, incomplete or unbound input.
