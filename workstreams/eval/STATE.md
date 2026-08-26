# eval — harness, metrics, ablations, error analysis
**Owner: Codex · Status: 🔴 RELAY REVIEW BLOCKED · task 1.1 requires fixes**

## ✅ Verified 2026-08-27
- Full suite: 558 passed, 9 warnings.
- Single-method smoke diagnostic math independently matches the rows: real→fake 0.315 at blur_s2.0; fake→real 0.515 at noise_s0.10.
- Claude relay added results assembly, report renderer, CLI, and tests; review packet is `handoffs/2026-08-27_claude-relay-critical-review.md`.

## 🔴 Blocking findings
1. Results pool multiple method IDs; no per-method results or paired deltas.
2. Any non-placeholder string can create a headline; `FrozenThreshold` is not structurally required.
3. Partial grids can emit headline results; six-family/completeness checks are absent.
4. `eval-results.v1` omits most frozen provenance/artifact/freeze fields and never reads the run manifest.
5. CIs cover fake recall only; sealed Phase-4 and failure-denominator guards are absent.

## ▶ NEXT ACTION
1. Await Claude ACK/counters on B-015 while specifying the minimal corrected result shape.
2. Implement method-aware assembly and artifact-object-only headline entry point.
3. Enforce exact expected coverage/provenance/freeze guards; add paired bootstrap deltas and regression reproductions.
4. Post a new eval gate packet for Claude to rerun.

## Literal next command
```
cd "/Users/mehulmodi/MEHUL WORK/Hackathon/TechJam 2026" && tail -120 coordination/CHANNEL.md
```

## Hard constraints
- One frozen threshold across all conditions; incomplete/partial is diagnostic-only.
- Sealed WildFake subset: exactly one evaluation run, Phase 4, after production freeze.
- Every public number needs method/data/code/config/artifact hashes and source-level uncertainty.
