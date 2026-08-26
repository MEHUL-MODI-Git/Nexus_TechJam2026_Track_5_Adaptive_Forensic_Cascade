# eval — harness, metrics, ablations, error analysis
**Owner: Codex · Status: 🟢 PHASE 1 · task 1.1 in progress**

## ✅ Done 2026-08-26
- Nothing built. Full protocol pre-specified in `docs/05-evaluation-and-ablations.md` (metrics, stress matrix, table templates, ablation matrix, error taxonomy, statistical rules).
- Drafted cross-agent contracts/sequencing/freeze proposal in `handoffs/2026-08-26_codex-prebuild-plan.md`; sent for Claude peer review in MSG-005.
- `specs/phase0-eval.md` frozen v1 after A-010/B-008; no metric code starts before the Phase-0 gate.

## ▶ NEXT ACTION
1. Implement the frozen `specs/phase0-eval.md` contract against Claude's 8,000-row artifact.
2. Keep metric/protocol logic with Codex heavy; delegate only bounded mechanical scaffolding after an exact spec.
3. Verify source-level bootstrap, directional flip rates, single global threshold, and deterministic results JSON.

## Other open threads (do not lose)
- Bootstrap resamples SOURCE images, never transformed views as independent.
- Phase 4 owns the one sealed WildFake run + Robustness Summary + Error Analysis Note (required deliverables).
- Selective/abstention metrics needed once training ships the reliability head (coverage table, risk-coverage curve).

## Literal next command
```
cd "/Users/mehulmodi/MEHUL WORK/Hackathon/TechJam 2026" && sed -n '1,260p' specs/phase0-eval.md
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
