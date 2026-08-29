# eval — harness, metrics, ablations, error analysis
**Owner: Codex · Status: 🔴 CLAUDE PHASE-3/4 RELAY REVIEW BLOCKED (B-029)**

## Current evidence
- Original Phase-2R eval repair remains accepted at `0a40ee8`.
- A-032/B-024 round-2 router repair is now accepted by Codex.
- Full current suite: **733 passed, 1 skipped, 9 warnings**; 70 high-risk focused tests pass.
- Local sealed dump independently verified complete: 174,380 rows, 8,719 unique sources,
  exactly 20 conditions/source, 0 failures/duplicates/label conflicts. **Do not rerun it.**
- Full blocking review: `handoffs/2026-08-29_claude-phase3-4-relay-review.md` / B-029.

## Blocking repair set
1. Correct train-vs-dev threshold provenance/deviation; Mehul decides whether it is acceptable.
2. Harden sealed summary from the preserved dump with full hashes, coverage and failure ledger.
3. Replace ad-hoc tied AUROC with canonical tie-aware math; regenerate affected artifacts/docs.
4. Cross-check checkpoint threshold against frozen artifact.
5. Resolve threshold-dependent `probe_flip` train/serve semantics and test it.

## NEXT ACTION
Wait for Claude's single ACK/counter + batched R1–R8 repair packet; then re-review before release.

## Literal next command
```sh
cd "/Users/mehulmodi/MEHUL WORK/Hackathon/TechJam 2026" && tail -n 120 coordination/CHANNEL.md
```

## Hard constraints
- Never rerun the sealed reference set.
- One frozen threshold across conditions; no test/holdout/sealed retuning.
- No public number without data/method/code/config/artifact hashes and source-level uncertainty.
