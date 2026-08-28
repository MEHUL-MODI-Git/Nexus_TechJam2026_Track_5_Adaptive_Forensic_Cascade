# Demo video script — v2 (target 2:45–3:00)

> **Status:** Claude draft (Phase 5R); Codex reviews. **Every number is now filled from the untouched
> internal test** (3,000 sources × 20 conditions) and backed by a committed artifact — no `[NUMBER]`
> placeholders remain. v1's figures came from the 400-source smoke grid we later disowned; they have
> been replaced, not adjusted.
>
> **ASSET COMPLIANCE — read before recording.** The brief forbids third-party trademarks and
> copyrighted content.
> - **Do NOT use** `results/robustness/cases/false_positives/fp_1…` or `fp_2…` — the FedEx and Polar
>   Air Cargo liveries are clearly legible.
> - The strongest protected false-positive case, `real/ebaabab805ab2c4f.jpg`, shows fire apparatus
>   with **"HILLSBORO FIRE & RESCUE" legible**. A public-agency marking is lower risk than a
>   corporate one, but **Mehul should make the call** or pick a substitute before recording.
> - Safe fallback: any FP case with no legible text — check the frame at 1080p before using it.
> - Check any frame showing a browser tab, desktop or file path for personal information.

---

## 0:00–0:20 — The hook, stated as a number

**On screen:** a real photograph, unmodified. Verdict panel: **REAL**. Then the same photo, visibly
softened by blur. Verdict flips to **AI-GENERATED**, score ~1.00.

> "This is a real photograph. Our detector agrees.
> This is the same photograph, blurred about as much as a slightly out-of-focus phone snap.
> It now says AI-generated, with 99.9% confidence.
> Nothing changed except focus."

**Why this shot:** it states the whole problem in twenty seconds using our own system failing.
Leading with your own failure is the most credible thing in the video.

## 0:20–0:50 — Why this matters, not just that it happens

**On screen:** the per-condition table from README §7 — clean row highlighted, then noise and JPEG.

> "Published detectors report near-perfect accuracy on clean images. But every platform recompresses
> and resizes what users upload. That's not an attack — it's the normal path from camera roll to feed.
> We tested on three thousand images the system had never seen, across all twenty official
> transformations. Sixty thousand scored views.
> The off-the-shelf detector catches seventy-one percent of AI images on clean inputs. Add
> imperceptible noise and it catches **zero point seven percent**.
> Not degraded. Erased. Twenty-seven percent of the AI images it gets right when clean flip to 'real'
> the moment anything touches them.
> And it fails the other way too: at that same noise level, nearly a third of *genuine* photographs
> get called AI-generated.
> It doesn't get uncertain. It gets confidently wrong, in both directions."

## 0:50–1:25 — The insight

**On screen:** side by side — a smooth-content real photo (sky, tarmac) and a texture-rich scene,
with their scores under blur.

> "The false positives aren't random. Our worst ones are photographs dominated by large smooth
> regions — open sky, asphalt — with hard-edged objects in front of them.
> Here's why. Real photographs carry sensor noise. Generated images are smooth.
> Blur removes sensor noise, so blurring a real photo pushes it along exactly the axis the detector
> cares about, into the region where generated images live.
> Which means the damage done to an image tells you how much to trust the answer."

## 1:25–2:10 — The solution, running

**On screen:** live Gradio stress panel. Drop an image, run the 20-condition grid, watch the
score-vs-condition chart draw with verdict flips marked. Then a single analysis showing the
primary → corrected line and the reliability readout.

> "So we don't build a detector that never breaks. We build one that knows when it's breaking.
> Before judging the image we measure what's been done to it — blur, blockiness, noise. We also probe
> the detector against itself: re-score under small perturbations. A confident model barely moves; a
> guessing one swings.
> A router of **one thousand eight hundred and twenty-seven parameters** turns those signals into a
> correction and a reliability score.
> Worst-case recall goes from twelve percent to **eighty-three**.
> And where it still can't be trusted, it abstains. Deferring the least reliable twenty percent lifts
> accuracy from ninety-one to ninety-three — and it's declining on the images it would have got
> wrong. For a moderation queue, 'route this to a human' beats a confident coin flip."

**On screen:** `scripts/infer_dir.py` running over a folder.

> "Same decision path for the UI, the CLI and batch inference — there's no separate demo code."

## 2:10–2:40 — Rigour, briefly and concretely

**On screen:** terminal, three fast cuts.

> "Three things we'd want a reviewer to check.
> One — we found a flaw in our own training data: real images stored as JPEG, fakes as PNG, so file
> format alone predicted the label a hundred percent of the time. We found it, fixed it, and added a
> baseline that uses no detector at all, so no result of ours can be read without knowing what plain
> image statistics achieve.
> Two — we tried **two** state-of-the-art second experts and rejected both, for the same reason. They
> read the high-frequency band, and that's exactly what noise and compression destroy. You can't
> rescue noise-destroyed evidence with a detector that reads the noise band. So we escalate to a
> human instead, and we publish the negative result.
> Three — our headline is measured against a baseline we deliberately handicapped in its own favour,
> with its threshold fitted on the test set. We still win by forty-nine points."

## 2:40–3:00 — Close

**On screen:** the verdict panel showing an abstention, reliability readout visible.

> "Accuracy on clean images is the easy number. The useful one is what happens after compression —
> and whether the system tells you when it no longer knows.
> Worst-case recall **0.83** on three thousand images nothing in our pipeline had ever seen, and a
> full list of the conditions where we still fail. Code, evaluation harness and every artifact are in
> the repo."

---

## Numbers used, and where they come from

| claim in script | value | artifact |
|---|---|---|
| primary clean fake recall | 0.7107 | `results/internal-test/results.json` |
| primary recall at noise σ=0.10 | 0.0073 | same |
| primary fake→real flip rate | 0.2664 | same |
| cascade FPR at noise σ=0.10 | 0.2967 | same |
| cascade worst-family recall | 0.8258 | same |
| primary worst-family recall | 0.1227 | same |
| FPR-matched advantage | +0.4916 | `results/internal-test/results.json` |
| router parameters | 1,827 | `results/router-fitting-v2/router_reliability.pt` |
| abstention accuracy lift | 0.9090 → 0.9317 | `results/internal-test/abstention.json` |
| format shortcut | 100.00% of 15,000 | README §8 |

## Shot list / recording checklist

- [ ] Gradio panel running locally, window sized so text is legible at 1080p
- [ ] One trademark-cleared real photo that flips under blur (see ASSET COMPLIANCE above)
- [ ] README §7 tables open for the table shots
- [ ] `scripts/infer_dir.py` run prepared on a small folder
- [ ] An abstention case ready to show live (a noise-degraded image reliably triggers it)
- [ ] Terminal font ≥ 16pt; no personal paths, tokens or filenames in frame
- [ ] All spoken numbers cross-checked against the table above
