# CHANGELOG — product (newest first, append-only; corrections are new entries)

## 2026-08-27 — Phase-0 product gate submitted (0.1/0.7/0.8)
Why: all frozen Phase-0 product deliverables and the real adapter smoke dependency are implemented and independently reproducible.
What: initialized uv/git scaffold and lock; built deterministic acquisition + manifest validation for 200 COCO-train2017 real and 200 SID-Set fully-synthetic images; built Gradio v0 over the shared `PredictionService`. Heavy review corrected canonical-pHash drift, Gradio callback arity, invalid-score rendering, dataset API field names, sampling bias, and network retry behavior. Evidence: `coordination/gates/phase-0-product.md`; combined suite 350 passed; clean-smoke AUROC 0.9923. Gate awaits Claude review.

## 2026-08-26 — Product spec frozen; Phase-0 tasks claimed
Why: Claude resolved the core review and approved Codex specs in A-010; Codex accepted the final batch-error policy in B-008; Mehul authorized immediate Phase-0 build.
What: `specs/phase0-product.md` frozen v1. Claimed tasks 0.1 (local scaffold), 0.7 (licensed smoke manifest/data), and 0.8 (Gradio v0). Public GitHub remains deferred by Mehul; local git only.

## 2026-08-26 — Pre-build planning packet drafted; implementation intentionally deferred
Why: Mehul authorized planning with Claude before starting the build, overriding STATE.md's scaffold next action for this session.
What: Audited Phase 0–5 dependencies/deliverables and found newer 26-Aug official screenshot requirements absent from docs 00/PDF. Proposal saved at `handoffs/2026-08-26_codex-prebuild-plan.md` and sent to Claude in MSG-004/005. No repo scaffold, external GitHub action, or build task started.

## 2026-08-26 — Workstream initialized
Why: Mehul requested session-continuity + dual-agent framework (26 Aug).
What: STATE.md created with Phase-0/next actions from 06-build-plan.md. No code exists yet.
