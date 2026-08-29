# eval — harness, metrics, ablations, error analysis
**Owner: Codex · Status: 🔴 A-033/A-034 RE-REVIEW BLOCKED (B-030)**

## Current evidence
- Original Phase-2R eval repair remains accepted at `0a40ee8`.
- A-032/B-024 round-2 router repair is now accepted by Codex.
- Full current suite: **750 passed, 1 skipped, 9 warnings**; 59 focused repair tests pass.
- Local sealed dump independently verified complete: 174,380 rows, 8,719 unique sources,
  exactly 20 conditions/source, 0 failures/duplicates/label conflicts. **Do not rerun it.**
- Re-review packet: `handoffs/2026-08-29_claude-r1-r8-rereview.md` / B-030.

## Blocking repair set
1. Remove remaining train-vs-dev contradictions and fix the future freeze path without refitting.
2. Bind the sealed summary to its manifest/artifacts; enforce exact per-condition coverage/schema.
3. Replace the sealed reporter's remaining order-dependent AUROC implementation.
4. Tighten and disclose the measured `probe_flip` train/serve drift.

## NEXT ACTION
Wait for Claude's single ACK/counter + focused S1–S4 repair packet; re-review before release.

## Literal next command
```sh
cd "/Users/mehulmodi/MEHUL WORK/Hackathon/TechJam 2026" && tail -n 120 coordination/CHANNEL.md
```

## Hard constraints
- Never rerun the sealed reference set.
- One frozen threshold across conditions; no test/holdout/sealed retuning.
- No public number without data/method/code/config/artifact hashes and source-level uncertainty.
