# eval — harness, metrics, ablations, error analysis
**Owner: Codex · Status: 🟡 PHASE 2R REPAIR GREEN LOCALLY · PEER RE-REVIEW REQUIRED**

## ✅ Current evidence
- Commit `ff943c7`: E1–E5 + provenance/freeze/failure-denominator repair.
- Focused eval/run-grid gate: 85 passed; Ruff clean. Full shared-tree suite: 630 passed, 9 warnings.
- Real 8,000-row diagnostic CLI: 400 sources, no literal `headline`, diagnostic-only warning intact.
- Claude A-024 ACKed B-016 with no counter; Codex owns the repair.
- Post-LOTA plan adopted in A-023/A-024/B-020:
  `coordination/PLAN-UPDATE-2026-08-27.md`.
- Heavy spec → lighter implementation → heavy verification completed. Gate packet:
  `coordination/gates/phase-2r-eval.md`.
- The 24k DegradePrint/quality run is unprotected diagnostic evidence only; it cannot select a
  submission model, mint a headline, or serve as a trained fallback.

## 🟡 Gate status
- E1–E5 and provenance/freeze/denominator adversarial cases pass locally.
- Eval remains blocked from Phase-2R exit until Claude independently approves the packet.
- Training B-018 and protected data roles remain separate blockers; no long cache may launch.

## ▶ NEXT ACTION
1. Claude independently re-reviews `coordination/gates/phase-2r-eval.md` and `ff943c7`.
2. Codex answers evidence-based findings; do not launch protected compute meanwhile.
3. After both 2R.1 gates pass, review the protected mini-pilot/candidate comparisons.

## Literal next command
```
  cd "/Users/mehulmodi/MEHUL WORK/Hackathon/TechJam 2026" && \
  .venv/bin/python -m pytest tests/test_eval_protocol.py tests/test_eval_results.py tests/test_run_grid.py -q
```

## Hard constraints
- One frozen threshold per method across every condition; incomplete/partial is diagnostic-only.
- Sealed WildFake subset: one run after production freeze; never fitting or component selection.
- Every public number needs method/data/code/config/artifact hashes and source-level uncertainty.
