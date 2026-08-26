# eval — harness, metrics, ablations, error analysis
**Owner: Codex · Status: ⚪ SPEC FROZEN · implementation starts Phase 1**

## ✅ Done 2026-08-26
- Nothing built. Full protocol pre-specified in `docs/05-evaluation-and-ablations.md` (metrics, stress matrix, table templates, ablation matrix, error taxonomy, statistical rules).
- Drafted cross-agent contracts/sequencing/freeze proposal in `handoffs/2026-08-26_codex-prebuild-plan.md`; sent for Claude peer review in MSG-005.
- `specs/phase0-eval.md` frozen v1 after A-010/B-008; no metric code starts before the Phase-0 gate.

## ▶ NEXT ACTION
1. Support Phase-0 interface review only; do not implement task 1.1 while product/core exit work is active.
2. At Phase-0 gate, verify Claude's prediction rows/transform IDs and prepare the Phase-1 harness claim.
3. Implement `specs/phase0-eval.md` immediately after gate approval.

## Other open threads (do not lose)
- Bootstrap resamples SOURCE images, never transformed views as independent.
- Phase 4 owns the one sealed WildFake run + Robustness Summary + Error Analysis Note (required deliverables).
- Selective/abstention metrics needed once training ships the reliability head (coverage table, risk-coverage curve).

## Literal next command
```
cd "/Users/mehulmodi/MEHUL WORK/Hackathon/TechJam 2026" && tail -n 120 coordination/CHANNEL.md
```

## Hard constraints
- One threshold across all conditions; abstentions never silently counted correct — report coverage.
- Sealed WildFake subset: exactly one evaluation run, Phase 4, after freeze.
- Every reported number must be reproducible via `scripts/run_eval.py --config configs/frozen.yaml`.

## Read next
| Task | Read |
|---|---|
| Metrics + templates | `docs/05-evaluation-and-ablations.md` |
| What feeds the harness | ExpertOutput contract in `docs/03-recommended-architecture.md`; cache schema in `docs/04-training-and-data.md` |
| Acceptance gates | doc 05 "Acceptance gates" + `06-build-plan.md` exit tests |
| Current pre-build proposal | `handoffs/2026-08-26_codex-prebuild-plan.md` |
