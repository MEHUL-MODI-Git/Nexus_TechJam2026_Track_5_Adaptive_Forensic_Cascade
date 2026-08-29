# Submission checklist — deadline Mon 1 Sept 12:00, target 09:00

Derived verbatim from the brief's own "Deliverable acceptance checklist"
(`docs/00-official-brief.md` §5.5). **Owner column says who can actually close it** — several
items only Mehul can.

| # | Requirement | State | Owner | Evidence / what remains |
|---|---|---|---|---|
| 1 | Devpost covers approach, tools, models/APIs, libraries, data | ✅ **complete, all numbers protected** | Claude → Codex review | `deliverables/devpost-draft.md` — no `[PENDING]` left; withdrawn smoke figures removed |
| 2 | Public repo URL works without special access | 🔴 **BLOCKED** | **Mehul** | Remote `main` still holds pre-cleanup history with raw images. Needs explicit MIT approval + verified clean-history force-push. **Do not publish before this.** |
| 3 | README includes limitations | ✅ | — | README §8 |
| 3b | README includes what would be improved with more time | ✅ | — | README §8b |
| 4 | README includes team contributions | ✅ | — | README §11 (solo + two agents) |
| 5 | End-to-end demo on **public** YouTube | 🔴 not recorded | **Mehul** | Script v2 ready and fully numbered: `deliverables/video-script.md` (carries a numbers-to-artifact table) |
| 6 | Devpost links the video | 🔴 | **Mehul** | After #5 |
| 7 | Video cleared for trademarks/copyright | 🟡 **needs Mehul's call** | Mehul | FedEx / Polar Air liveries in `fp_1`,`fp_2` must NOT appear. The best protected FP case shows a legible **public-agency** fire livery — Mehul decides or substitutes; both flagged in the script |
| 8 | Clean-vs-transformed robustness summary | ✅ **on protected data** | Claude | README §7 — per-family, per-condition, FPR-matched baselines, full ablation ladder |
| 9 | Error analysis with representative FPs and FNs | ✅ **regenerated on protected data** | Claude | `deliverables/error-analysis-note.md` — named files, images actually inspected |
| 10 | Parameter statement showing <2B compliance | ✅ | — | README §9 — **21,814,571** shipped total (1.09% of the 2B cap), 0.012% trainable, plus measured latency/memory |
| 11 | WildFake non-training safeguard documented | ✅ | — | 13,843-entry denylist; audit: 0 exact hits, 2 perceptual both verified unrelated; guard is fail-closed and aborted a real run |

## Technical work still open

| Item | State | Blocker |
|---|---|---|
| Feature extraction (12,000 sources) | ✅ | 240,000 rows |
| Train the 7-rung ladder | ✅ | `results/router-fitting-v2/training.json` |
| **Does the cascade beat `quality_only`?** | ✅ **YES** | dev +0.307 worst-family, CI95 [0.283, 0.331] — excludes zero |
| Fit calibration + freeze one threshold | ✅ | `mlp+wg` @ **0.4667367651127279**; re-run reproduces byte-identically |
| Untouched internal-test evaluation (3,000 sources) | ✅ **DONE 17:30** | worst-family **0.8258** vs dev 0.8144 (no overfit); **+0.49** over an FPR-matched primary. README §7 |
| Sealed WildFake reference run (**once only**) | 🔴 **NOT RUN — needs Mehul** | Architecture is now frozen, so the precondition is met. Requires explicit authorization + dedupe to 3,719 unique (A-029). **Not fired without it.** |
| Codex re-review of B-024 repair | ⏳ | Codex offline |
| Codex review of ~19 `[relay]` entries + A-031 breach | ⏳ | Codex offline |

## Hard rules that survive any schedule pressure

- The sealed reference subset is used **exactly once**, after the architecture is frozen, and never
  for fitting, threshold selection, or model choice.
- No public number without a committed artifact behind it.
- No claim of cascade benefit unless it beats **both** CF-only and quality-only under paired
  source bootstrap (Codex's B-028 control 2).
- Repo stays private until Mehul approves the licence and the clean-history push.
