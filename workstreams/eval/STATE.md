# eval — harness, metrics, ablations, error analysis
**Owner: Codex · Status: 🔴 REPAIR RE-REVIEW BLOCKED · task 1.1 requires fixes**

## ✅ Verified 2026-08-27
- Full suite after Claude's repair: 567 passed, 9 warnings.
- Direct method separation and CLI rejection of partial-grid + real-threshold mode are repaired.
- Detailed adversarial evidence: `handoffs/2026-08-27_claude-repair-review.md`; B-016 sent.

## 🔴 Blocking findings
1. Sparse method×source×condition coverage can still emit `eval-results.v1`.
2. Caller-supplied `official_conditions` can redefine the canonical grid to seven conditions.
3. A directly fabricated, invalid `FrozenThreshold` can still mint a headline.
4. Diagnostic method records contain literal `headline` blocks.
5. Paired deltas are input-order dependent instead of key-aligned.
6. Transform hash is mislabeled, run manifest is optional, and sealed/freeze/failure-denominator provenance is absent.

## ▶ NEXT ACTION
1. Await Claude's evidence-based ACK/counters on B-016; do not accept more relay edits without CHANNEL agreement.
2. Freeze E1–E5 as executable acceptance tests before implementation.
3. Correct exact coverage, canonical grid authority, threshold validation, diagnostic schema, keyed paired bootstrap, and provenance/freeze guards.
4. Rerun adversarial cases + full suite and post a new eval gate packet for Claude.

## Literal next command
```
cd "/Users/mehulmodi/MEHUL WORK/Hackathon/TechJam 2026" && tail -120 coordination/CHANNEL.md
```

## Hard constraints
- One frozen threshold across all conditions; incomplete/partial is diagnostic-only.
- Sealed WildFake subset: exactly one evaluation run, Phase 4, after production freeze.
- Every public number needs method/data/code/config/artifact hashes and source-level uncertainty.
