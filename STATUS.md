# STATUS — global dashboard (both agents keep this current)

> 30-second orientation only. Detail lives in `workstreams/<ws>/STATE.md`. Messages in `coordination/CHANNEL.md`. Rules in `CLAUDE.md` / `AGENTS.md`.

## Snapshot
- **Phase:** ✅ SPECS FROZEN (~21:15, DECISIONS entry, both agents on record) → **PHASE 0 BUILD RUNNING.** Mehul: "finish the mutual spec review, freeze the agreed specs, then immediately start Phase 0." Local build only; GitHub deferred.
- **Deadline:** Mon 1 Sept 12:00pm — submit ~9am · **Webinar:** Thu 28 Aug 5:00pm
- **Session note:** Mehul moved from the API session to the Claude Code session (~21:00). AGENT-A continuity = these files; the new session resumes via RESUME PROTOCOL.
- **Blockers:** none. Phase-0 product gate submitted for Claude review; core gate pending Claude packet.
- **Risks:** **LOTA PARKED by Mehul (revisit later)** — architecture impact assessed: cascade stays two-expert by promoting RIGID (training-free, no weights); disagreement + fusion features survive; Feasibility score arguably improves since judges can't reproduce a Baidu-gated dependency either. Verify RIGID repo + param count before committing. Original finding: **weights unobtainable without a Baidu account** (mirror search exhausted 22:45: no HF/Drive/Release mirror; repo is MIT so redistribution would be legal if obtained). **→ FOR MEHUL:** (A) can you get the two `.pth` files from `pan.baidu.com` (codes `imjw` / `a942`, already in the URLs)? Else (C) we substitute RIGID as the training-free second expert at Phase-1 entry. Detail + author-email option (B) in `handoffs/2026-08-26_lota-integration.md` addendum. **Nothing currently blocks — CF-384 is primary and green.**
- **Compute decision:** deferred to Phase 2 entry

## Workstreams
| Workstream | Owner | Status | Next (see its STATE.md) |
|---|---|---|---|
| core | Claude | 🟢 core built; 0.7 dependency delivered | Record 0.6 AUROC=0.9923 and post Phase-0 core gate |
| training | Claude | 🟢 router + calibration built (synthetic-tested) | needs real corpus → feature cache → fit |
| eval | Codex | ⚪ ready (Phase 1) | harness + results-JSON implementation after Phase-0 gate |
| product | Codex | 🟡 GATE SUBMITTED | Claude reviews `gates/phase-0-product.md` |

## Task claims (claim BEFORE starting; release when done/parked)
| Task (id from 06-build-plan) | Owner | State |
|---|---|---|
| 0.2 canonical decode | Claude | ✅ done 22:10 (14 tests) |
| 0.3 transform grid (20 conds) | Claude | ✅ done 22:10 (144 tests) |
| 0.4 golden tests | Claude | ✅ done 22:10 (63 tests) |
| 0.5 CF-384 adapter | Claude | ✅ done 22:10 (+ service & CLI, parity tested) |
| 0.6 sanity check | Claude | 🟡 half done — MPS-vs-CPU PASSES (1.5e-05); AUROC half needs 0.7 |
| 1.x infer_dir.py (REQUIRED deliverable) | Claude | ✅ done early 22:30 (18 gate tests; policy ACKed by Codex, no rework) |
| 1.4 quality descriptors | Claude | ✅ done early 23:00 (29 tests) |
| 2.x self-probes (doc 03 step 4) | Claude | ✅ done early (17 tests) |
| 2.x feature-cache row v1 spec | Claude | ✅ FROZEN (Codex B-009 fixes applied) |
| 3.x calibration + threshold selection | Claude | ✅ done early (30 tests) |
| 2.x router: features + fusion ladder | Claude | ✅ done early (37 tests, learnability verified) |
| 0.1 repo scaffold | Codex | ✅ done 00:45 (uv lock/offline sync/imports) |
| 0.7 smoke dataset | Codex | ✅ done 00:45 (200+200; validated; AUROC input) |
| 0.8 Gradio v0 | Codex | ✅ done 00:45 (live local server + parity tests) |

## Log (newest first)
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
