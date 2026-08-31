# Submission checklist — deadline Mon 1 Sept 12:00, target 09:00

Derived verbatim from the brief's own "Deliverable acceptance checklist"
(`docs/00-official-brief.md` §5.5). **Owner column says who can actually close it** — several
items only Mehul can.

| # | Requirement | State | Owner | Evidence / what remains |
|---|---|---|---|---|
| 1 | Devpost covers approach, tools, models/APIs, libraries, data | ✅ **draft v2, all numbers protected** | Claude → Codex review | `deliverables/devpost-draft.md` — no `[PENDING]` left; withdrawn smoke figures removed. **v2 (29 Aug)** adds the sealed reference benchmark (it had been omitted), and fixes latency + parameter figures against their artifacts |
| 2 | Public repo URL works without special access | 🔴 **BLOCKED** | **Mehul** | Remote `main` still holds pre-cleanup history with raw images. Needs explicit MIT approval + verified clean-history force-push. **Do not publish before this.** **Verified separately that a clean clone RUNS** at `578efa7`: 756 passed / 0 failed, `predict.py` and `infer_dir.py` both rc=0 (6 images, 0 failures) — `results/clean-checkout/verification.json`. What remains is the history and licence decision, not the code. |
| 3 | README includes limitations | ✅ | — | README §8 |
| 3b | README includes what would be improved with more time | ✅ | — | README §8b |
| 4 | README includes team contributions | ✅ | — | README §11 (solo + two agents) |
| 5 | End-to-end demo on **public** YouTube | 🟡 **being recorded now** | **Mehul** | Cheat sheet **v3** (`deliverables/RECORDING-CHEAT-SHEET.md`, 11 moments, **4:58**) + 8-slide deck (`deliverables/video-slides.html`) + staged images. `scripts/video_setup.py` runs pre-flight and refuses READY unless `scripts/verify_video_claims.py` passes **162 checks** binding every spoken number to live output. **The brief sets no duration — 'short video' only; the 3-min cap was ours** |
| 6 | Devpost links the video | 🔴 | **Mehul** | After #5 |
| 7 | Video cleared for trademarks/copyright | ✅ **RESOLVED — no owner call needed** | Claude | All four worst false positives were inspected and **all four are unusable** (fire livery / photographer's watermark / identifiable faces + mural / face + branding + ID badge) — the real half of the corpus is web-sourced, so its failure cases carry third-party content by construction. The hook now runs on an **AI-generated** image instead: no privacy or trademark exposure, and it demonstrates the headline metric directly. Requires the SID-Set CC BY 4.0 attribution card |
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
| Sealed WildFake reference run (**once only**) | ✅ **RUN ONCE, 29 Aug, after freeze** | 8,719 unique images x 20 conditions = **174,380 rows, 0 failures**; deduplicated per A-029. Clean AUROC 0.9964, all-conditions 0.9821, worst-family 0.8787. Reported with both things that did *not* transfer (advantage +0.09 not +0.49; abstention buys 0.0001 here). Artifact `results/sealed/reference-results.json`, dump SHA-256 `db1d2148…`. **Never to be re-run.** |
| Codex re-review of B-024 repair | ✅ **APPROVED** in B-029 (29 Aug) | all five repairs present |
| Codex peer-review gate | 🔴 **BLOCK open (B-032)** | Superseded chain: B-029 → R1–R8 → B-030 → S1–S4 → B-031 → **B-032 Phase-4 exit audit**. Accepted so far: B-024 r2, R1/R4/R5/R7, S1/S3, the clean-checkout evidence. Open: reproduction/provenance surfaces (frozen exit command, strict reporter schemas, expert revision pin, ablation provenance, status prose) — **not** the measured results, which Codex independently checked and did not reject. Release and Phase-4 acceptance stay blocked until it clears. |

## Decisions only Mehul can make (nothing below is an agent's call)

| Decision | What we recommend | Where the evidence is |
|---|---|---|
| **Make the repo public** — requires MIT approval and a verified clean-history force-push, because remote `main` still holds pre-cleanup history containing raw images | Do it only after the open Codex gate (B-032) clears | `workstreams/product/STATE.md` |
| **A train-fitted decision threshold** — the frozen threshold was selected on the fitting split's train half, not on held-out dev, contrary to our own eval spec | **Ship it, disclosed.** Measured impact is 0.003 in threshold and ~0.001 in dev worst-family recall, and it generalised *upward* on all three untouched sets. Re-fitting would leave our only sealed-set number describing a system we do not ship | `coordination/DEVIATION-2026-08-29-threshold-split.md` |
| **The fire-apparatus false-positive frame** — the strongest protected FP case carries a legible public-agency livery | Substitute a case with no legible text unless you are comfortable | `deliverables/video-script.md`, ASSET COMPLIANCE block |

## Hard rules that survive any schedule pressure

- The sealed reference subset is used **exactly once**, after the architecture is frozen, and never
  for fitting, threshold selection, or model choice.
- No public number without a committed artifact behind it.
- No claim of cascade benefit unless it beats **both** CF-only and quality-only under paired
  source bootstrap (Codex's B-028 control 2).
- Repo stays private until Mehul approves the licence and the clean-history push.
