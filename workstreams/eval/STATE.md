# eval — harness, metrics, ablations, error analysis
**Owner: Codex · Status: 🔴 PHASE 2R EVAL REPAIR CLAIMED · E1–E5 jointly ACKed**

## ✅ Current evidence
- Full suite: 601 passed, 9 warnings (2026-08-27).
- Claude A-024 ACKed B-016 with no counter; Codex owns the repair.
- Post-LOTA plan adopted in A-023/A-024/B-020:
  `coordination/PLAN-UPDATE-2026-08-27.md`.
- The 24k DegradePrint/quality run is unprotected diagnostic evidence only; it cannot select a
  submission model, mint a headline, or serve as a trained fallback.

## 🔴 Blocking acceptance cases
1. Require exact method×source×canonical-condition coverage.
2. Make the canonical 20-condition grid non-overridable for headline evaluation.
3. Accept only a validated, loaded frozen threshold artifact.
4. Forbid every literal `headline` field in diagnostic documents.
5. Align paired bootstrap by `(source_id, condition_id)`, never input position.
6. Require correct transform/run/method/code/golden/sealed/freeze provenance and fail closed on
   denominator shrinkage or incomplete failure ledgers.

## ▶ NEXT ACTION
1. Add E1–E5 adversarial regression tests before production edits.
2. Repair `src/eval/` within the frozen protocol; rerun adversarial cases + full suite.
3. Post a new eval gate packet for Claude review.
4. After the gate, own candidate comparisons and paired deltas; Claude owns candidate adapters.

## Literal next command
```
cd "/Users/mehulmodi/MEHUL WORK/Hackathon/TechJam 2026" && \
  .venv/bin/python -m pytest tests/test_eval_protocol.py tests/test_eval_results.py -q
```

## Hard constraints
- One frozen threshold per method across every condition; incomplete/partial is diagnostic-only.
- Sealed WildFake subset: one run after production freeze; never fitting or component selection.
- Every public number needs method/data/code/config/artifact hashes and source-level uncertainty.
