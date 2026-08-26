# DECISIONS — joint decision log (newest first)

Entry format: `## <date> — <decision>` / **Proposed by / Approved by** / **Evidence** (file) / **Reverses if** (what observation would undo it).

---

## 2026-08-27 — GitHub repository created and pushed (PRIVATE until submission)
**Proposed by:** Mehul (instruction: "push into github, create project called TechJam_2026_Track_5"; visibility chosen by Mehul when asked). **Approved by:** binding — user directive.
**What:** `https://github.com/MEHUL-MODI-Git/TechJam_2026_Track_5` created **private** and pushed (14 commits, 114 files). Visibility decision: private now, **flip to public before the 1 Sept submission** — the brief's public-repo deliverable is judged at submission time, and public content is indexed by third parties within hours, so publishing an unfinished Results section is one-way. **ACTION REQUIRED BEFORE SUBMISSION: make the repository public.**
**Verified before publishing:** no organizer material (`Brief/`, `docs/evidence/`), no `.env`, no secrets, and no raw dataset images anywhere in the *history* — not merely the working tree, since history would retain them regardless of `.gitignore`.
**Auth note:** created via the GitHub REST API using Mehul's existing osxkeychain credential (`repo` scope). `gh` CLI was installed but its own auth rejected that token for lacking `read:org`; it was not needed.
**Reverses if:** Mehul wants a different owner/name — the remote is a one-line change and history is portable.

## 2026-08-27 — [relay] Claude assumes Codex's in-flight eval task (PROTOCOL §6)
**Proposed by:** Mehul (instruction: "codex limits are hit so you keep working"). **Approved by:** binding — user directive; PROTOCOL §6 relay condition ("Mehul announces a limit") is satisfied.
**What:** Claude claims Codex's in-flight **1.1 eval harness** and completes it. All relay changes are tagged `[relay]` in `workstreams/eval/CHANGELOG.md` and in commit messages; **Codex reviews them FIRST on return** and may revert or rework any of it — ownership of `src/eval/` does not transfer. Claude built strictly on top of Codex's existing `protocol.py`/`metrics.py` and reimplemented no metric. 1.5 (Gradio stress panel) and 1.6 (repo mechanics) remain Codex's and are relay candidates if the block persists.
**Evidence:** `workstreams/eval/CHANGELOG.md`, `results/grid-smoke-v1/diagnostic-results.json`, CHANNEL A-022.
**Reverses if:** Codex returns and prefers its own implementation — relay work is explicitly provisional.

## 2026-08-27 (~01:20) — Phase 0 exits; Phase-1 ownership split
**Proposed by:** Codex (B-012). **Approved by:** Claude (A-019).
**What:** Phase 0 is mutually complete with APPROVE-WITH-NOTES in both directions. In Phase 1, Codex owns 1.1 eval harness, 1.5 Gradio stress panel, and 1.6 repo mechanics/license inventory; Claude owns 1.3 single-expert full-grid baseline and remaining core notes, and drafts README prose for Codex review. Task 1.2 LOTA remains parked by Mehul; 1.7 webinar is joint. Claude's 1.3 artifact is intentionally a single-expert baseline, not a detector shootout.
**Evidence:** `coordination/gates/phase-0-core.md`, `coordination/gates/phase-0-product.md`, CHANNEL B-012/A-019/A-020.
**Reverses if:** a Phase-1 exit test fails and invokes the documented fallback ladder, or Mehul changes the split.

## 2026-08-27 (~01:10) — Placeholder thresholds cannot lead the demo verdict
**Proposed by:** Claude (A-018, after independently measuring the placeholder operating point). **Approved by:** Codex (B-012).
**What:** The Phase-0 threshold remains `0.5` with provenance `PLACEHOLDER-uncalibrated-phase0`; no smoke-set fitting is permitted. While provenance starts with `PLACEHOLDER`, Gradio leads with `BASELINE SIGNAL` and the p_fake score, and demotes the service's forced binary output to `Placeholder verdict: REAL/AI-GENERATED — operating point not calibrated`. Once a held-out-dev threshold artifact replaces placeholder provenance, the normal binary verdict becomes primary automatically. This changes presentation only, not scores, thresholding, pipeline behavior, or evaluation.
**Evidence:** `coordination/gates/phase-0-core.md` diagnostic: clean smoke AUROC 0.9923 but threshold-0.5 fake recall 0.530/BAcc 0.765; A-018/B-012.
**Reverses if:** a validated held-out-dev threshold artifact is installed (automatic UI branch), or the product contract is replaced jointly.

## 2026-08-26 (~21:15) — SPEC FREEZE: Phase-0 core / eval / product contracts frozen
**Proposed by:** both agents (Claude `specs/phase0-core.md`; Codex `specs/phase0-eval.md` + `specs/phase0-product.md`). **Approved by:** Codex (B-006 items 1-6, B-007) + Claude (A-006, A-010) — both on record. Build authorized by Mehul ("finish the mutual spec review, freeze the agreed specs, then immediately start Phase 0").
**What:** Frozen for Phase 0 — (a) `ExpertOutput` v1 success-only + typed `ExpertInferenceError`/`ExpertInitError`; (b) `prediction.v1` record emitted by an importable `PredictionService` that Gradio/CLI/infer_dir/eval all import (no subprocess, no duplicate decision logic); (c) `prediction-row.v1` and `eval-results.v1` (Codex-owned); (d) transform protocol v1 — 20 conditions, exact parameters, `configs/transforms.yaml` as the single numeric source, `src/pipeline/version.py` as the single version source; (e) golden scheme [**correction 2026-08-26 late: this clause also named "feature-cache row v1", which had NOT in fact been written — only referenced. Corrected by `specs/phase2-feature-cache.md` (DRAFT v1, pending Codex review). The golden scheme half was real and remains frozen.**]; (f) smoke manifest v1 (Codex-owned); (g) threshold objective — select on bootstrap-mean worst transformation-FAMILY fake recall over 6 families (clean excluded, entering only via the FPR +1pt / BAcc -1pt constraints; severities pooled within family; label-stratified source bootstrap), report worst exact condition at the frozen threshold; (h) corpus target 30k sources / 12k minimum / ≤12h projected cache time. All 10 Codex "required before freeze" notes resolved in core spec v2; 3 non-blocking notes adopted.
**RESOLVED 2026-08-26 ~21:20 (B-008), freeze now complete with nothing open:** (i) `infer_dir.py` corrupt-file policy — Codex ACKed Claude's counter: default one row per recognized file, failed decode → `pred: null` + `error`, exit 0 with stderr summary, `--errors {null,skip,strict}`, gate smoke uses `strict`. Built exactly so (`scripts/infer_dir.py`, 18 gate tests). (ii) Codex replaced the stale exact-condition selection text in `specs/phase0-eval.md` §2 with the frozen six-family bootstrap-mean objective, and added optional structured `expert_failures` to `prediction-row.v1` (matching `prediction.v1`). `specs/phase0-eval.md` and `specs/phase0-product.md` are marked FROZEN v1. **Mutual spec review complete.**
**Evidence:** `specs/phase0-core.md` v2 (FROZEN header), `specs/phase0-eval.md`, `specs/phase0-product.md`, `handoffs/2026-08-26_core-spec-review.md`, CHANNEL A-006/B-006/B-007/A-010.
**Reverses if:** the 28-Aug webinar contradicts a transform parameter or the deliverable spec (then: CHANNEL + new DECISIONS entry + `PIPELINE_VERSION`/golden/cache bump before any retained headline measurement).

## 2026-08-26 (~21:00) — Local build authorized; GitHub deferred
**Proposed by:** Mehul (instruction: "is github needed right, build locally right now?" — confirmed GitHub is only a submission-time deliverable). **Approved by:** binding — user directive.
**What:** Build proceeds locally now (local `git init`, no remote). Public GitHub repo creation/push is a later external action once Mehul provides owner/name/credentials (proposed name: `techjam-track5-forensic-cascade`). Push well before submission. Build tasks may be claimed once spec freeze is recorded (B-006 responses pending from Claude).
**Evidence:** this entry; STATUS.md snapshot.
**Reverses if:** Mehul changes it.

## 2026-08-26 — Updated brief requirements adopted (infer_dir script + README items)
**Proposed by:** Codex (MSG-004, from `docs/evidence/2026-08-26_track5-deliverables.png`). **Approved by:** Claude (verified screenshot visually; MSG-005).
**What:** Newer §5.5 brief page is binding: (a) REQUIRED directory-inference script emitting JSON `{image_path, pred}` per image — `scripts/infer_dir.py`, built Phase 1, gate-tested thereafter; (b) README must add overview/setup/reproduce sections; (c) well-commented code in both agents' DoD. Docs 00–08 preserved; addendum at `docs/00a-brief-addendum-2026-08-26.md`.
**Evidence:** the screenshot; `docs/00a-brief-addendum-2026-08-26.md`; `specs/phase0-core.md` §6b.
**Reverses if:** organizers publish contradicting requirements (webinar 28 Aug).

## 2026-08-26 — Strengths-based task routing
**Proposed by:** Mehul (instruction, 26 Aug: "use your strengths… if codex is good at something use it for that, if claude is good at something use it for that"). **Approved by:** binding — user directive.
**What:** Tasks route to the better-suited agent regardless of workstream ownership (reassign via CHANNEL). Claude: paper-to-code fidelity, ML judgment, long agentic jobs, all prose deliverables (Codex reviews). Codex: well-specified implementation, debugging, UI/Gradio, fast iteration. Stuck >1h → offer the task over.
**Evidence:** `CLAUDE.md` (Strengths-based allocation rule), `AGENTS.md`, MSG-003.
**Reverses if:** Mehul changes it, or measured outcomes show a mapping is wrong (then update the map via a new entry).

## 2026-08-26 — Claude and Codex operate as equals
**Proposed by:** Mehul (instruction, 26 Aug: "you and codex will work as equals"). **Approved by:** binding — user directive.
**What:** Identical authority and rules for both agents; mutual review in both directions; either may challenge/veto anything via CHANNEL; evidence breaks ties, never seniority; unresolved disagreements escalate to Mehul. Ownership = execution responsibility only.
**Evidence:** `CLAUDE.md` (Peer equality rule), `AGENTS.md`, `PROTOCOL.md` §4, MSG-002.
**Reverses if:** Mehul changes it.

## 2026-08-26 — Dual-agent coordination framework adopted
**Proposed by:** Mehul (instruction, 26 Aug: continuity system + Claude⇄Codex channel + joint checkpoints + model economy). **Approved by:** Claude (set up); Codex ACK pending (MSG-001).
**What:** 4 workstreams (core/training = Claude; eval/product = Codex); CHANNEL.md messaging; phase-exit gate reviews; heavy-spec→cheap-execute→heavy-verify model economy.
**Evidence:** `CLAUDE.md`, `AGENTS.md`, `coordination/PROTOCOL.md`.
**Reverses if:** Mehul changes the setup, or gate reviews prove too slow for the 5.5-day schedule (then downgrade to FYI-only reviews for non-critical gates).

## 2026-08-26 — Execution plan (Phases 0–5) adopted
**Proposed by:** Claude (from docs 00–08). **Approved by:** Mehul (plan review, 26 Aug).
**What:** `06-build-plan.md` — always-submittable phases, Gradio-first demo, fallback ladder, compute decision deferred to Phase 2 entry.
**Evidence:** `06-build-plan.md`.
**Reverses if:** webinar (28 Aug) answers change the transform protocol materially, or a phase exit-test failure triggers the fallback ladder.
