# Demo video script — DRAFT v1 (target 2:45–3:00)

> **Status:** Claude draft (Phase 5R); Codex reviews. Recordable as-is once the router is trained;
> the `[NUMBER]` placeholders are the only things that must be filled from committed artifacts.
>
> **ASSET COMPLIANCE — read before recording.** The brief forbids third-party trademarks and
> copyrighted content. **Do NOT use** `results/robustness/cases/false_positives/fp_1…` or `fp_2…` —
> the FedEx and Polar Air Cargo liveries are clearly legible. **Safe substitutes:** the breaking-wave
> false positive, or the F-22 (military aircraft, no commercial mark). Check any frame showing a
> browser tab, desktop, or file path for personal information before upload.

---

## 0:00–0:20 — The hook, stated as a number

**On screen:** a real photograph, unmodified. Verdict panel: **REAL**, high reliability.
Then the same photo, visibly softened by blur. Verdict flips to **AI-GENERATED**, confidence ~1.00.

> "This is a real photograph. Our detector agrees — real, high confidence.
> This is the same photograph, blurred about as much as a slightly out-of-focus phone snap.
> The detector now says it's AI-generated, with 99.99% confidence.
> Nothing about the image changed except focus."

**Why this shot:** it states the whole problem in twenty seconds, using our own system failing.
Do not hide it — leading with your own failure is the most credible thing in the video.

## 0:20–0:50 — Why this matters, not just that it happens

**On screen:** the robustness table from `results/robustness/summary.md`, clean row highlighted, then
the noise and blur rows.

> "Published detectors report near-perfect accuracy, and on clean images ours does too — AUROC 0.99.
> But every platform recompresses and resizes what users upload. That's not an attack, it's the
> normal path from camera roll to feed.
> Under mild noise, this detector catches 1.5% of AI images — down from 53%.
> Under blur, at the threshold that gives 1% false positives on clean photos, it wrongly accuses
> 64% of real ones.
> It doesn't get uncertain. It gets confidently wrong, in both directions."

## 0:50–1:25 — The insight

**On screen:** side-by-side of two real photos — a low-texture one (sky/water) and a texture-rich
street scene — with their scores under blur.

> "The false positives aren't random. Of the nine real photos most confidently misclassified,
> eight were aircraft against open sky. We measured it: the photos it gets right have 2.66 times
> more fine texture than the ones it gets wrong.
> Here's why. Real photographs carry sensor noise. Generated images are smooth.
> Blur removes sensor noise — so blurring a real photo pushes it, along exactly the axis the
> detector cares about, into the region where generated images live."

## 1:25–2:10 — The solution, running

**On screen:** live Gradio stress panel. Drop an image, hit the 20-condition grid, watch the
score-vs-condition chart draw with verdict flips marked.

> "So we don't try to build a detector that never breaks. We build one that knows when it's breaking.
> Before judging the image, we measure what's been done to it — blur, blockiness, noise, geometry.
> We also probe the detector against itself: re-score under small perturbations. A confident model
> barely moves; a guessing one swings.
> A small router — [NUMBER] parameters — turns those signals into a reliability score.
> Under conditions where the detector can't be trusted, the system abstains instead of guessing.
> For a moderation queue, 'route this to a human' beats a confident coin flip."

**On screen:** `scripts/infer_dir.py` running over a folder, emitting rows with verdict + reliability.

> "Same decision path for the UI, the CLI, and batch inference — there's no separate demo code."

## 2:10–2:40 — Rigour, briefly and concretely

**On screen:** terminal, three fast cuts.

> "Three things we'd want a reviewer to check.
> One — we found a flaw in our own training data: real images stored as JPEG, fakes as PNG, so file
> format alone predicted the label 100% of the time. We found it, fixed it, and added a baseline
> that uses no detector at all, so no result of ours can be read without knowing what plain image
> statistics achieve.
> Two — we tested the state-of-the-art second expert and rejected it. It scores 0.9996 on lossless
> images and calls every AI image real once you compress them.
> Three — we proved we never trained on the organizers' reference set: every image fingerprinted,
> zero matches, and the check aborts the run rather than skipping a row."

## 2:40–3:00 — Close

**On screen:** the verdict panel with an abstention, reliability readout visible.

> "AUROC on clean images is the easy number. The useful one is what happens after compression —
> and whether the system tells you when it no longer knows.
> [NUMBER] on the untouched internal test set. Code, evaluation harness and every artifact are in
> the repo."

---

## Shot list / recording checklist

- [ ] Gradio panel running locally, window sized so text is legible at 1080p
- [ ] One trademark-free real photo that flips under blur (wave or F-22)
- [ ] `results/robustness/summary.md` open for the table shot
- [ ] `scripts/infer_dir.py` run prepared on a small folder
- [ ] Terminal font ≥ 16pt; no personal paths, tokens or filenames in frame
- [ ] All `[NUMBER]` placeholders filled from committed artifacts
- [ ] Uploaded to YouTube as **public**, link added to the Devpost description
