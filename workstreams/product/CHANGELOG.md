# product — CHANGELOG (newest first)

## 2026-08-29 — [relay] deliverable truthfulness sweep: the R8 pass had missed the `deliverables/` tree

Why: R8 repaired README, Devpost and the UI for public contradictions, but the sweep did not cover
every file under `deliverables/`, and four defects of the same class survived there.

What (no product code touched; prose deliverables are Claude's per the strengths allocation, and
this lands review-first for Codex):
- **Devpost omitted the sealed reference benchmark entirely** — our only measurement on the
  organizers' own data, and the strongest evidence we have for deliverable #1. Added, with both
  results that did *not* transfer stated beside it: the FPR-matched advantage is +0.09 there rather
  than +0.49, and abstention buys 0.0001 on that distribution against +2.27 points internally.
- **Devpost latency was a run behind its artifact** — "~6.8x, 127.9 ms vs 18.8 ms" against
  `results/ops/ops-evidence.json`'s 6.92x, 134.6 ms vs 19.5 ms. This is the drift R4 caught in the
  README; the Devpost copy was not corrected with it.
- **Devpost's parameter enumeration still omitted the 775-parameter reporter** while quoting the
  R7-corrected total, i.e. half of R7.
- **The video script's header still said v2** after commit `06165f5` rewrote it to v3.
- The submission checklist claimed the sealed run had **NOT** been fired and that Codex was offline
  with the B-024 re-review pending. Both were stale by a day: the run happened once on 29 Aug, and
  B-029 delivered an approval of B-024 plus a BLOCK on the wider packet. Corrected, and the three
  decisions that are Mehul's alone are now listed in one place with a recommendation each.

## 2026-08-29 — Claude relay/release review: BLOCK
Why: Mehul requested the return-owner review required by PROTOCOL §6.
What: a clean checkout cannot start the claimed shipped cascade because configured
`router_reliability.pt` is ignored/untracked; the degradation reporter checkpoint is likewise absent.
Public docs also contain a 1000× parameter-cap arithmetic error, omit the 775-parameter reporter,
contradict themselves on whether the router/abstention ship, and overstate peer-gate completion.
Repository-wide Ruff has 62 findings. Full packet:
`handoffs/2026-08-29_claude-phase3-4-relay-review.md`. No product implementation was changed.

## 2026-08-27 — Mehul handed Codex work to Claude under PROTOCOL §6
Why: Codex is near its usage limit and Mehul explicitly directed Claude to take over.
What: B-028 grants temporary `[relay]` execution for Codex-owned eval/product work. Existing release,
licence, sealed-data and public-history constraints remain unchanged; relay edits are review-first
for Codex on return. LOTA weights remain ignored/uncommitted and final use remains licence-gated.

## 2026-08-27 — Narrow checkpoint ignore guard recorded
Why: Mehul supplied two local LOTA `.pth` checkpoints for a bounded, pending
preflight; large checkpoint files must not enter Git accidentally.
What: The heavy owner made the small direct `.gitignore` amendment for `*.pth`,
`*.pt`, and `*.ckpt`. The files remain unchanged and untracked. The coordination
packet was drafted by the lighter agent; no license, README, architecture, or
cache-admission claim was added.

## 2026-08-27 — Stress panel accepted; product plan updated after LOTA
Why: Claude A-024 independently reproduced the 39-test/Ruff gate and Mehul requested joint post-LOTA
replanning.
What: closed task 1.5 as accepted. Kept release blocked on remote history, owner approvals, CF pin and
scientific gates. Product will expose only components that pass the new correction/candidate gates;
PGC/GAPL/DegradePrint remain absent from public claims. The historical plan and update pack stay
unchanged; the operational overlay lives in `coordination/PLAN-UPDATE-2026-08-27.md`.

## 2026-08-27 — README and license inventory brought back to current truth
Why: the release review proved the public-facing docs described a trained/deployable router, a shared eval serving path, a pinned CF download, accepted MIT licensing, and a clean remote that do not exist yet.
What: recast the architecture as the target and the current baseline as CF-384 + diagnostic stress UI; documented blocked eval/router paths and the correct tracked diagnostic; added the diagnostic reproduction command; corrected parameter/training/redistribution claims; disclosed the unpinned CF constructor, NPR's absent license, the underfilled router corpus, pending MIT owner approval, and the still-dirty private remote. No license choice, remote mutation, or code claim was made on Mehul's behalf.

## 2026-08-27 — Stress-panel scientific and accessibility repair complete
Why: the relay review reproduced invalid `NaN`/decision records being plotted, a 19-failure grid being called stable, and 2.35:1 chart-label contrast on the app's forced dark surface.
What: every plotted record now requires a finite `[0,1]` score, binary decision consistent with its threshold, and threshold/provenance equality with clean; invalid transformed records become explicit error gaps and an invalid clean reference aborts safely at the UI boundary. Incomplete grids now use a distinct `incomplete` state and never claim stability. The palette now follows the actual dark surface with ≥4.5:1 text/status contrast. Added adversarial coverage; focused app suite is 39 passed and Ruff is clean. Task 1.5 awaits Claude's peer re-review.

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
