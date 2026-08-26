# CHANGELOG — product (newest first, append-only; corrections are new entries)

## 2026-08-27 — Phase 1 task 1.6 started under heavy→light→heavy routing
Why: Claude ACKed the Phase-1 split in A-019 and Mehul explicitly required lighter Luna models for mechanical work.
What: Claimed 1.6. Luna is producing a factual, read-only repo/license inventory; Codex retains all publication, licensing-policy, and final-diff decisions. Task 1.5 remains unclaimed until Codex writes its UI/behavior packet.

## 2026-08-27 — Product gate approved; placeholder-verdict presentation hardened
Why: Claude independently reproduced the data/model evidence and approved the gate, but found the unfitted 0.5 operating point recalls only 53% of smoke fakes despite AUROC 0.9923. Smoke cannot be used to tune it.
What: threshold and score are unchanged. While provenance is PLACEHOLDER, Gradio now leads with `BASELINE SIGNAL` + p_fake and shows the forced REAL/AI-GENERATED output only as an explicitly uncalibrated placeholder verdict. Normal verdict hierarchy returns automatically after a held-out-dev threshold artifact. Decision: A-018/B-012 + DECISIONS. Added branch tests; Phase-1 split pending.

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
