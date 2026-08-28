# Submission checklist — deadline Mon 1 Sept 12:00, target 09:00

Derived verbatim from the brief's own "Deliverable acceptance checklist"
(`docs/00-official-brief.md` §5.5). **Owner column says who can actually close it** — several
items only Mehul can.

| # | Requirement | State | Owner | Evidence / what remains |
|---|---|---|---|---|
| 1 | Devpost covers approach, tools, models/APIs, libraries, data | 🟡 drafted | Claude → Codex review | `deliverables/devpost-draft.md`; `[PENDING]` numbers to fill from artifacts |
| 2 | Public repo URL works without special access | 🔴 **BLOCKED** | **Mehul** | Remote `main` still holds pre-cleanup history with raw images. Needs explicit MIT approval + verified clean-history force-push. **Do not publish before this.** |
| 3 | README includes limitations | ✅ | — | README §8 |
| 3b | README includes what would be improved with more time | ✅ | — | README §8b |
| 4 | README includes team contributions | ✅ | — | README §11 (solo + two agents) |
| 5 | End-to-end demo on **public** YouTube | 🔴 not recorded | **Mehul** | Script ready: `deliverables/video-script.md` |
| 6 | Devpost links the video | 🔴 | **Mehul** | After #5 |
| 7 | Video cleared for trademarks/copyright | 🟡 flagged | Mehul | **FedEx / Polar Air Cargo liveries in `fp_1`,`fp_2` must NOT appear.** Safe substitutes named in the script |
| 8 | Clean-vs-transformed robustness summary | ✅ preliminary | Claude | `results/robustness/summary.{json,md}`; regenerate on protected data |
| 9 | Error analysis with representative FPs and FNs | ✅ preliminary | Claude | `deliverables/error-analysis-note.md` + `results/robustness/cases/` |
| 10 | Parameter statement showing <2B compliance | ✅ | — | README §9 — 21,811,969 total, ~0.01% trainable |
| 11 | WildFake non-training safeguard documented | ✅ | — | 13,843-entry denylist; audit: 0 exact hits, 2 perceptual both verified unrelated; guard is fail-closed and aborted a real run |

## Technical work still open

| Item | State | Blocker |
|---|---|---|
| Feature extraction (12,000 sources) | 🟡 ~91% | finishing ~12:30 |
| Train the 7-rung ladder | ⏳ | needs the cache |
| **Does the cascade beat `quality_only`?** | ⏳ | the question that decides whether we have a detection result at all |
| Fit calibration + freeze one threshold | ⏳ | after the ladder |
| Untouched internal-test evaluation (3,000 sources) | ⏳ | after freeze |
| Sealed WildFake reference run (**once only**) | ⏳ | after freeze; dedupe to 3,719 unique before scoring (A-029) |
| Codex re-review of B-024 repair | ⏳ | Codex offline |
| Codex review of ~19 `[relay]` entries + A-031 breach | ⏳ | Codex offline |

## Hard rules that survive any schedule pressure

- The sealed reference subset is used **exactly once**, after the architecture is frozen, and never
  for fitting, threshold selection, or model choice.
- No public number without a committed artifact behind it.
- No claim of cascade benefit unless it beats **both** CF-only and quality-only under paired
  source bootstrap (Codex's B-028 control 2).
- Repo stays private until Mehul approves the licence and the clean-history push.
