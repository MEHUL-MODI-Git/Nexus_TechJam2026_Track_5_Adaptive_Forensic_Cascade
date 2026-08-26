# STATUS — global dashboard (both agents keep this current)

> 30-second orientation only. Detail lives in `workstreams/<ws>/STATE.md`. Messages in `coordination/CHANNEL.md`. Rules in `CLAUDE.md` / `AGENTS.md`.

## Snapshot
- **Phase:** ✅ PHASE 0 BUILT + MUTUALLY APPROVED-WITH-NOTES → **Phase-1 split awaiting Claude ACK (B-012).** Local build only; GitHub deferred.
- **Deadline:** Mon 1 Sept 12:00pm — submit ~9am · **Webinar: dropped by Mehul (27 Aug)**
- **Repo:** https://github.com/MEHUL-MODI-Git/TechJam_2026_Track_5 — **PRIVATE. ⚠️ MUST BE MADE PUBLIC BEFORE SUBMISSION** (brief deliverable).
- **Session note:** Mehul moved from the API session to the Claude Code session (~21:00). AGENT-A continuity = these files; the new session resumes via RESUME PROTOCOL.
- **Blockers:** none. Both Phase-0 gates independently rerun and approved-with-notes; Phase-1 claims wait on one split ACK.
- **Risks:** **LOTA PARKED by Mehul (revisit later)** — architecture impact assessed: cascade stays two-expert by promoting RIGID (training-free, no weights); disagreement + fusion features survive; Feasibility score arguably improves since judges can't reproduce a Baidu-gated dependency either. Verify RIGID repo + param count before committing. Original finding: **weights unobtainable without a Baidu account** (mirror search exhausted 22:45: no HF/Drive/Release mirror; repo is MIT so redistribution would be legal if obtained). **→ FOR MEHUL:** (A) can you get the two `.pth` files from `pan.baidu.com` (codes `imjw` / `a942`, already in the URLs)? Else (C) we substitute RIGID as the training-free second expert at Phase-1 entry. Detail + author-email option (B) in `handoffs/2026-08-26_lota-integration.md` addendum. **Nothing currently blocks — CF-384 is primary and green.**
- **Compute decision:** deferred to Phase 2 entry

## Workstreams
| Workstream | Owner | Status | Next (see its STATE.md) |
|---|---|---|---|
| core | Claude | ✅ PHASE-0 GATE APPROVED-WITH-NOTES | service notes in B-012 before named consumers |
| training | Claude | 🟢 cache + router + calibration ALL built | needs a real corpus to run against |
| eval | Codex | ⚪ ready (Phase 1) | harness + results-JSON implementation after Phase-0 gate |
| product | Codex | ✅ PHASE-0 GATE APPROVED-WITH-NOTES | placeholder-verdict mitigation done; await Phase-1 split |

## Task claims (claim BEFORE starting; release when done/parked)
| Task (id from 06-build-plan) | Owner | State |
|---|---|---|
| 0.2 canonical decode | Claude | ✅ done 22:10 (14 tests) |
| 0.3 transform grid (20 conds) | Claude | ✅ done 22:10 (144 tests) |
| 0.4 golden tests | Claude | ✅ done 22:10 (63 tests) |
| 0.5 CF-384 adapter | Claude | ✅ done 22:10 (+ service & CLI, parity tested) |
| 0.6 sanity check | Claude | ✅ BOTH halves PASS — MPS≡CPU 4.3e-05; clean-smoke AUROC **0.9923** |
| 1.x infer_dir.py (REQUIRED deliverable) | Claude | ✅ done early 22:30 (18 gate tests; policy ACKed by Codex, no rework) |
| 1.4 quality descriptors | Claude | ✅ done early 23:00 (29 tests) |
| 2.x self-probes (doc 03 step 4) | Claude | ✅ done early (17 tests) |
| 2.x feature-cache row v1 spec | Claude | ✅ FROZEN (Codex B-009 fixes applied) |
| 3.x calibration + threshold selection | Claude | ✅ done early (30 tests) |
| 2.x router: features + fusion ladder | Claude | ✅ done early (37 tests, learnability verified) |
| 1.3 full-grid baseline (single-expert) | Claude | ✅ DONE — 8,000 rows, 0 failures, 167s |
| 1.1 eval harness | **Claude [relay]** | ✅ DONE — Codex's protocol/metrics + Claude's results/report/runner (18 tests) |
| 1.5 Gradio stress panel | **Claude [relay]** | ✅ DONE — live 20-condition grid + SVG chart (21 tests) |
| 1.6 repo mechanics | **Claude [relay]** | ✅ DONE — inventory + repo created + pushed (private) |
| 1.6 repo mechanics/license inventory | Codex | 🟢 claimed; Luna inventory delegated, Codex reviews |
| 0.1 repo scaffold | Codex | ✅ done 00:45 (uv lock/offline sync/imports) |
| 0.7 smoke dataset | Codex | ✅ done 00:45 (200+200; validated; AUROC input) |
| 0.8 Gradio v0 | Codex | ✅ done 00:45 (live local server + parity tests) |

## Log (newest first)
- **2026-08-27 — PUSHED TO GITHUB.** `MEHUL-MODI-Git/TechJam_2026_Track_5`, **private** (Mehul's call: flip to public before submission — public content is indexed within hours and the Results section is still empty). 14 commits, 114 files. History audited for organizer material/secrets/raw images before pushing, not just the working tree. Webinar dropped per Mehul. **⚠️ Standing action: make the repo public before 1 Sept.**
- **2026-08-27 — 1.6 inventory + Phase-2 feature cache built.** `LICENSES.md` now covers checkpoints, datasets, dependencies and demo assets with the parameter table (**two dependency licences corrected** — torch and numpy declare more complex expressions than I had written from memory; the file records the command to re-derive them). `Brief/` and `docs/evidence/` git-ignored — redistributing the organizers' PDF in a public repo is Mehul's call, and ignoring is the reversible default. **`src/router/feature_cache.py` + 30 tests**: canonical cache key with refuse-to-append, fail-closed denylist (no denylist ⇒ refuses to build), abort-not-skip on a sealed hit. **Suite 541 green.**
- **2026-08-27 — [relay] task 1.5 DONE (the demo money-shot).** Stress panel runs all 20 conditions live (~0.7 s) and plots score-vs-condition as dependency-free inline SVG, with verdict flips marked by colour + caret + text listing. Palette validated (CVD ΔE 23.8 light / 25.7 dark). Codex's existing app code and CSS untouched — panel added alongside, CSS appended as a revertible block. **Measured: a correctly-detected AI image loses its verdict under 15 of 20 conditions; a real photo flips to "AI-generated" under 5.** Suite **511 green**.
- **2026-08-27 — [relay] PROTOCOL §6 INVOKED.** Mehul: Codex hit usage limits. Claude claimed **1.1 eval harness** and completed it on top of Codex's `protocol.py`/`metrics.py` (reimplemented nothing): added bootstrap, results assembly, markdown reporting, runner, 18 tests. **First full evaluation artifact produced** over 8,000 rows: `results/grid-smoke-v1/diagnostic-results.{json,md}`. Reproduces the independent 1.3 diagnostic exactly (cross-validation). New findings: **real→fake flip 0.315 at blur_s2.0**, **fake→real flip 0.515 at noise_s0.10**, jpeg_q30 loses 0.415 recall at zero FPR cost. The diagnostic/headline boundary is now structural — a placeholder threshold physically cannot emit a headline block. **Suite 490 green.** All relay work tagged for Codex's review-first on return.
- **2026-08-27 — PHASE 1 STARTED. Task 1.3 DONE.** `scripts/run_grid.py` (+15 tests) produced **8,000 prediction rows** (400 sources × 20 conditions, 0 failures, 167s ≈ 21ms/row) for Codex's harness. **First real robustness picture** (`results/grid-smoke-v1/DIAGNOSTIC_SUMMARY.md`): worst families are **noise** (recall 0.165@0.5; σ=0.10 collapses to 0.015) and **blur** (pooled AUROC 0.8576). **`blur_s2.0` is the standout: AUROC 0.6470 with FPR 0.640 — heavy blur pushes REAL images toward 'fake', i.e. systematic bias, not graceful degradation.** Colour/crop nearly free (~0.99). This gives the router a demonstrated job: the failure modes are predictable from `noise_sigma`/`blur_varlap`, which we already compute. Also landed the full B-013 calibration hardening batch. **Suite 438 green. All work committed ([claude] ×3).**
- **2026-08-27 ~01:20** — Mutual Phase-0 gate review complete: Claude approved product; Codex approved core, both with non-blocking notes. Placeholder-threshold UI now leads with baseline signal/score and demotes the unfitted binary verdict; threshold remains 0.5 and unfitted. Phase-1 split proposed in B-012.
- **2026-08-27** — **PHASE 0 CORE COMPLETE (0.2–0.6 all green).** Codex's 0.7 landed (200 real + 200 fake); I re-ran 0.6 independently on MPS and reproduced its CPU result exactly: **clean-smoke AUROC 0.9923**. Gate verdict on its product packet: **APPROVE-WITH-NOTES** (re-derived every data claim myself, incl. re-hashing 40 images from disk — 0 mismatches). Core gate packet posted. **FINDING: the default 0.5 threshold is badly miscalibrated — fake recall only 0.530 (we miss 47% of AI images) despite AUROC 0.99; ~0.016 gives 0.850 recall / 0.920 BAcc.** Independently confirms the previously-UNVERIFIED third-party claim. No threshold frozen from smoke data — Phase 2 fits it on a dev split.
- **2026-08-27** — **Router built** (`src/router/{features,model}.py`, 37 tests): full doc-04 fusion ladder (static avg → logistic → MLP → worst-group loss), 1,987-param MLP, availability masking, missing-indicator discipline. **Learnability verified on synthetic data: routed 0.90+ vs static-average <0.65.** Everything is now in place to fit the router the moment a real feature cache exists. **Combined suite: 387 green.**
- **2026-08-27 ~00:45** — Codex Phase-0 product gate submitted: 0.1/0.7/0.8 done; 350 tests; smoke AUROC 0.9923; live Gradio server verified.
- **2026-08-27** — **Codex is active and fast**: 0.1 scaffold locked (uv + full deps + `.gitignore`), 0.8 Gradio v0 wired to my `PredictionService`, smoke tooling built, and it returned a strong APPROVE-WITH-FIXES review of my feature-cache spec (B-009) — including catching a duplicate-SHA rule that would have rejected the entire cache. All 6 fixes applied; spec FROZEN. **Claude built `src/router/calibration.py`** (frozen threshold objective + temperature/bias + ECE, 30 tests) — fully independent of Codex/data/LOTA. Pillow deprecation cleanup: warnings 344→47, goldens unchanged. **Combined suite: 349 green.**
- **2026-08-26 (late)** — **Record correction + gap closed:** the spec-freeze entry claimed "feature-cache row v1" was frozen; it had never been written, only referenced. Now specified in `specs/phase2-feature-cache.md` (DRAFT v1, Codex reviewing) — row schema, cache key/invalidation, failure & missing-value rules, sealed-subset denylist abort, throughput budget (30k sources ≈ 9.3h at measured 14ms/img, inside the agreed ≤12h). Codex restarted; `git init` done (no commits yet, no `.gitignore`).
- **2026-08-26 (late)** — **Self-probes built** (doc 03 step 4): 3 mild probes + stability features, own namespace and version key, missing-value discipline (all-probes-fail ⇒ `None`, not zeros). 17 tests, **306 total green**. Probe instability is discriminative on CF-384 (texture swings ~50x more than photo). LOTA parked by Mehul after architecture-impact review.
- **2026-08-26 ~23:00** — Task **1.4 quality descriptors** built (blur var-of-Laplacian, JPEG blockiness, robust noise sigma, photometric + geometry stats; 29 tests, **289 total green**). Measured and documented a real blockiness limitation on 8px-periodic content — it is a router feature, not a standalone compression detector. Codex's **B-008 ACKed the infer_dir policy exactly as built** (no rework) and froze the eval/product specs.
- **2026-08-26 ~22:30** — `scripts/infer_dir.py` (REQUIRED official deliverable) built early with 18 gate-smoke tests; both contested corrupt-file behaviors implemented as flags so Codex's ACK only flips a default. **260 tests green.**
- **2026-08-26 ~22:10** — **Phase 0 core built: 0.2/0.3/0.4/0.5 done, 0.6 half.** 242 tests green. First measurements: MPS≡CPU (worst |Δlogit| 1.5e-05) so MPS is trusted; CF-384 21.81M params; ~14 ms/image (~70 img/s) — above the Phase-2 GPU-escalation threshold. Two protocol deltas found by tests (blur kernel clamp <7px; DecodedImage immutable-not-hashable) → A-011.
- **2026-08-26 ~21:20** — Codex accepted A-010 counter, froze eval/product v1, and claimed 0.1/0.7/0.8 (B-008).
- **2026-08-26 ~21:15** — **SPEC FREEZE.** All 10 Codex review notes resolved in `specs/phase0-core.md` v2 (+3 non-blocking adopted); threshold clarifications answered (6 families, clean excluded, severities pooled, label-stratified source bootstrap); eval spec APPROVE-WITH-ONE-FIX, product spec APPROVE. A-010 posted. Claude claimed 0.2–0.6; build started.
- **2026-08-26 evening** — Coordination framework installed (CLAUDE.md, AGENTS.md, coordination/, workstreams/, handoffs/, teaching/). MSG-001 posted to Codex. Plan (`06-build-plan.md`) approved by Mehul earlier today.
