# eval — harness, metrics, ablations, error analysis
**Owner: Codex · Status: 🔴 PHASE-4 EXIT BLOCKED (B-033)**

## Current evidence
- Original Phase-2R eval repair remains accepted at `0a40ee8`; B-024 router repair is accepted.
- A-035 S1 threshold-split and S3 probe-drift repairs are accepted.
- S2's tied weighted AUROC and core sealed manifest/completeness checks are correct.
- Full suite: **769 passed, 1 skipped, 9 warnings**; focused gate: **78 passed**.
- Phase-4 audit focused suite: **102 passed**.
- The preserved dump remains complete: 174,380 rows / 8,719 sources / 20 conditions each.
  **Do not rerun it.**
- The real internal cache independently checks complete: 60,000 rows / 3,000 sources / 20 each.
- A-037 repair review at `99d03fb`: **74 focused passed; full 787 passed / 1 skipped /
  9 warnings**. Exact pin and seven-rung ablation are accepted.
- Current packet: `handoffs/2026-08-31_a037-focused-rereview.md` / B-033.

## Remaining eval blockers
1. Internal reporter trusts row `family`; changing only 4,500 fake noise rows to `family=blur`
   returns rc=0 and moves worst-family 0.8258 → 0.8864. Split/expert binding is also loose.
2. Sealed reporter accepts a two-source real-only manifest, returns rc=0 and writes bare NaN.
3. Frozen index names two nonexistent generator scripts and omits published PGC rescue evidence.

## NEXT ACTION
Wait for Claude's ACK/counter and batched B-033 repair; focused re-review before Phase-4 exit.

## Literal next command
```sh
cd "/Users/mehulmodi/MEHUL WORK/Hackathon/TechJam 2026" && tail -n 100 coordination/CHANNEL.md
```

## Hard constraints
- Never rerun the sealed reference set.
- One frozen threshold across conditions; no test/holdout/sealed retuning.
- No public number from malformed, incomplete or unbound input.
