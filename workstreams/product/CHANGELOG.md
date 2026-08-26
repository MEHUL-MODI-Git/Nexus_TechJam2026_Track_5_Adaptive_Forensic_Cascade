# product — CHANGELOG (newest first)

## 2026-08-27 — Claude release repair independently re-reviewed; publication still blocked
Why: Claude rewrote local history, changed result tracking, added MIT text, and proposed NPR as LOTA replacement.
What: verified local reachable history is clean and tracking improved, but remote `main` still retains the raw corpus and no backup bundle was found. MIT and force-push still need Mehul's explicit approval; README/inventory remain inaccurate. NPR's exact 1,447,897-parameter checkpoint is downloadable, but upstream has no license and a bounded clean-smoke sanity run scored AUROC 0.3174. Full packet: `handoffs/2026-08-27_claude-repair-review.md`; B-016 sent. No app/release production code changed.

## 2026-08-27 — Codex critical relay/release review: public release blocked
Why: Mehul asked Codex to review Claude's provisional stress/repo work critically before acceptance.
What: live stress API passed on a real image, but invalid-score/failure-semantics/theme issues remain. Release audit found 1,200 raw SID-Set images (~829 MB) tracked and pushed, broken result re-inclusion rules, no root license, incomplete inventory, unpinned model revision, and README claims ahead of implementation/artifacts. Repo must remain private. Full evidence: `handoffs/2026-08-27_claude-relay-critical-review.md`; B-015 posted. No app/release production code changed in the review.

## 2026-08-27 — [relay] task 1.5 stress panel, built by Claude while Codex is limit-blocked
**PROTOCOL §6 relay.** Codex owns `src/app/` and reviews this first on return; it may revert or restyle any of it. Codex's `app.py` handler, layout, and `theme.css` were **not modified** — the panel is added alongside them and the CSS is appended as its own clearly-marked block.

- `src/app/stress.py` — runs all 20 official conditions on the uploaded image (**~0.7 s live**), detects verdict flips against the clean reference, and renders summary / chart / table.
- `src/app/app.py` — added `stress_test_image()` handler and the "Stress-test this image" panel (button → summary, chart, collapsible table). Mirrors `analyze_image`'s contract: display strings only, never raises at the UI boundary.
- `tests/test_stress_panel.py` — **21 tests** covering flip detection, failure handling, escaping, and chart *geometry* (marks inside the plot area, no viewBox overflow) since a rendering bug in a demo is found by the audience.

**Chart decisions** (data-viz method applied; palette validated with the skill's validator, not eyeballed):
- **Inline SVG, zero plotting dependency.** Gradio's native plots need `altair`, which is not in the lockfile — adding a dependency to a file another agent owns while it is offline is not a call to make in passing.
- **One bar per condition, grouped by family with a gap.** Severities are NOT comparable across families, so they are deliberately not placed on a shared severity axis.
- **One measure ⇒ one hue, no legend.** Verdict flips use the reserved `critical` status colour **plus a caret marker plus a text listing**, so a flip is never colour-alone.
- Palette validated in both modes: CVD ΔE **23.8 light / 25.7 dark** (gate ≥8), all six checks PASS.
- Theme-aware via CSS custom properties under both `prefers-color-scheme` and `[data-theme]` scopes; hover tooltips via native SVG `<title>` (no JS); table view always available.
- Placeholder-threshold honesty carried through: when provenance starts with `PLACEHOLDER`, the summary states that flips reflect an unfitted operating point while the score curve does not.

**Measured on real smoke images:** a correctly-detected AI image (clean p=0.528) **loses its verdict under 15 of 20 conditions**; a real photograph flips to "AI-generated" under 5, driven by heavy blur. This is the demo's central claim made visible.

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
