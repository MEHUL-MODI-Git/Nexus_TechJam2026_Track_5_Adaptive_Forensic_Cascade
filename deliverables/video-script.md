# Demo video script — v4 (target ~4:30)

> **Status:** Claude draft (Phase 5R); Codex reviews. Every spoken number is filled from a committed
> artifact — see the numbers table at the end. Shots marked ✅ have been **executed and verified**
> on this machine; their real output is quoted inline so recording is transcription, not discovery.

## Read this before anything else

**There is no 3-minute rule.** `docs/00-official-brief.md` line 130 says only *"Submit a short
video"* — no duration anywhere in the brief. The "3-min" figure came from our own
`06-build-plan.md` (tasks 4.7 / 5.3) and propagated into v2/v3 of this script as a hard cap.

That self-imposed cap is why v3 had **no architecture beat at all**. Judging is Technical Execution
**35%**, Innovation & Problem Insight **20%**, Impact **20%**, Feasibility **15%**, Presentation
**10%** — so ninety seconds spent actually explaining the cascade buys more than the compression
saved. **v4 targets ~4:30 and stays under 5:00.** "Short" rules out rambling, not explaining.

## Assets — all staged and verified

| asset | path | state |
|---|---|---|
| Slide deck (12 slides) | `deliverables/video-slides.html` | ✅ built; `←/→` navigate, `F` fullscreen, `N` presenter notes (hidden by default so recordings stay clean) |
| Hook image, clean | `deliverables/video-assets/bird_clean.png` | ✅ staged |
| Hook image, noise σ=0.10 | `deliverables/video-assets/bird_noise_s010.png` | ✅ staged |
| Gradio UI | `.venv/bin/python -m src.app` → `http://127.0.0.1:7860` | ✅ launches, HTTP 200 |

### Trademark and copyright clearance — RESOLVED, and this is a change from v3

v3 asked Mehul to make a judgement call on a false-positive image showing a legible
**"HILLSBORO FIRE & RESCUE"** livery. **Do not use it.** All four of the worst false positives were
inspected and **every one is unusable**:

| case | why it is out |
|---|---|
| `real/ebaabab805ab2c4f.jpg` | legible public-agency fire livery |
| `real/4059199b800cce73.jpg` | photographer's copyright watermark burned into the frame |
| `real/71131f0a1b4a39e2.jpg` | two identifiable faces + a prominent third-party mural |
| `real/95efd34d1ad0803b.jpg` | identifiable face, product branding, visible ID badge |

That is not bad luck: the *real* half of the corpus is web-sourced photography, so its failure cases
carry other people's content by construction.

**The fix is to run the hook on an AI-generated image instead.** Synthetic images carry no privacy
or trademark exposure, and the image chosen — a yellow bird on a bunch of green bananas — is
instantly readable at 1080p. It is from **SID-Set (CC BY 4.0)**, so the closing card must carry
*"Synthetic sample image: SID-Set, CC BY 4.0"*. No decision is left for Mehul here.

This is also the **stronger** hook, because it demonstrates the headline metric directly instead of
a side-issue false positive.

---

## 0:00–0:35 — The hook ✅ verified

**On screen:** `bird_clean.png`, then `bird_noise_s010.png`. At playback size they look identical.
Terminal beneath runs the real CLI on each.

```
.venv/bin/python scripts/predict.py deliverables/video-assets/bird_clean.png --json
.venv/bin/python scripts/predict.py deliverables/video-assets/bird_noise_s010.png --json
```

**Verified output** — clean: primary `0.9995` → AI-GENERATED. Noise σ=0.10: primary **`0.0166`
→ REAL (missed)**, ours **`0.9986` → AI-GENERATED**, reliability `0.794` → **DEFERRED**.

> "This image is AI-generated. A state-of-the-art open detector agrees — ninety-nine point nine
> percent confident.
> This is the same image with a small amount of noise added. You can't see the difference.
> The same detector now says it's a real photograph. One point seven percent.
> Ours still catches it — and it also tells you it's less sure than usual, and routes it to a human."

**Why this shot:** three things in twenty seconds — the collapse, the rescue, and the honesty — all
from one command on one image.

## 0:35–1:05 — Why this matters · SLIDES 2–3

> "Published detectors report near-perfect accuracy on clean images. But every platform recompresses
> and resizes what users upload. That's not an attack — it's the normal path from camera roll to feed.
> We measured it on three thousand images the system had never seen, across all twenty official
> transformations. Sixty thousand scored views.
> On clean images the off-the-shelf detector catches seventy-one percent of AI images. Add that
> imperceptible noise and it catches **zero point seven percent**.
> Not degraded. Erased. And it fails the other way too — at that noise level it calls nearly a third
> of *genuine* photographs AI-generated. It doesn't get uncertain. It gets confidently wrong."

## 1:05–1:35 — The insight · SLIDE 4

> "The failures aren't random, and that's the opening.
> Real photographs carry sensor noise. Generated images are smooth. Blur strips sensor noise, so
> blurring a real photo pushes it along exactly the axis the detector cares about — into the region
> where generated images live. Added noise buries the generator's fingerprint, which sits in that
> same high-frequency band.
> Which means: if we can measure **what was done to the image**, we can predict **how much the
> verdict is worth**."

## 1:35–2:15 — The architecture · SLIDE 5

> "So the system measures the damage before it judges the image.
> A canonical decode — we never re-compress before the expert sees the pixels.
> A frozen expert detector, twenty-one point eight million parameters, pinned to one exact revision,
> never fine-tuned.
> Then cheap descriptors of what's been done to the picture — blur, blockiness, noise — plus
> re-scoring the image under three mild perturbations to see how stable the score is.
> And then the actual contribution: a router of **one thousand eight hundred and twenty-seven
> parameters** that turns 'what was done to this image' into a correction to the verdict.
> One frozen threshold across all twenty conditions — never tuned per condition, because that would
> be leakage.
> The CLI, batch inference and the demo UI all call the same prediction service. There is no separate
> demo code path that could flatter these numbers."

## 2:15–2:55 — It works, and it knows when it doesn't ✅ verified

**On screen:** `audit_image.py` on the degraded image, then on the clean one.

```
.venv/bin/python scripts/audit_image.py deliverables/video-assets/bird_noise_s010.png
.venv/bin/python scripts/audit_image.py deliverables/video-assets/bird_clean.png
```

**Verified output, degraded:** raw detector `0.0166` → corrected `0.9986` (`+0.9820`, annotated
*"the router changed this verdict"*), reliability `0.794` **⚠ DEFERRED**, image history *"added noise
(100% confidence) ⚠ our detector is weakest here"*, certificate **17 / 20**, grade **LOW — correct
for 84.9%**, and it names the three conditions that flip it.
**Verified output, clean:** **20 / 20**, grade **HIGH — correct for 99.1%**, worst case 0.946 at jpeg_q30.

> "Here's the same image again, degraded. The raw detector missed it at zero point zero one six. The
> router corrects it to zero point nine nine — caught.
> But look at what else it says. It identifies that noise was added, and flags that noise is where
> we're weakest. Then it audits its own answer by re-running that verdict through all twenty
> transformations. Only seventeen survive, so it grades its own call **low** — verdicts this fragile
> are right about eighty-five percent of the time — and it names the three conditions that break it.
> Same command on the clean image: twenty out of twenty, grade high, ninety-nine percent.
> Those percentages aren't labels we picked. They're what we measured on three thousand held-out
> images."

## 2:55–3:35 — The result, and the fair version of it · SLIDES 6–8

> "Across the worst transformation family, the off-the-shelf detector catches **twelve percent** of
> AI images. Ours catches **eighty-three**.
> But that baseline runs at a thirty-times lower false-positive rate, so some of that gap is just a
> looser cut — and we're not going to pretend otherwise. So we handed the baseline our operating
> point, with its threshold fitted **on the test set itself**: leakage we grant it and deny ourselves.
> It reaches thirty-three percent. We still lead by **forty-nine points**. That's the number we publish.
> Here's every family, including the ones where we gain least — and the cost: our clean false-positive
> rate is eight point three percent, above the cap we set ourselves. We reported that rather than
> re-tuning to hide it."

## 3:35–4:05 — The organizers' benchmark · SLIDE 10

> "The organizers' reference set was sealed from day one — never trained on, never thresholded on.
> After the architecture was frozen we scored it **once**: a hundred and seventy-four thousand rows,
> zero failures. Clean AUROC nought point nine nine six.
> Two things didn't transfer, and they're on the slide next to the wins: against a properly-tuned
> baseline our advantage there is nine points, not forty-nine — and abstention buys nothing on that
> distribution. We publish both."

## 4:05–4:30 — Rigour and close · SLIDES 11–12

> "Three things we'd want a reviewer to check.
> We found a flaw in our own training data — every real image stored as JPEG, every fake as PNG, so
> file format alone predicted the label a hundred percent of the time. We found it, fixed it, and
> added a baseline that uses no detector at all.
> We tried two state-of-the-art second experts and rejected both, for the same structural reason:
> they read the high-frequency band, which is exactly what noise and compression destroy. You can't
> rescue noise-destroyed evidence with a detector that reads the noise band. So we escalate to a
> human instead.
> And we killed five of our own ideas this way — including our own self-probing, which costs
> eighty-six percent of our runtime and buys nothing measurable. We report all of it.
> Twenty-one point eight million parameters. One percent of the limit. A hundred and thirty-five
> milliseconds on a laptop.
> An honest 'route this to a human' beats a confident coin flip."

**Final card:** repo URL · *"Synthetic sample image: SID-Set, CC BY 4.0"*

---

## Numbers used, and where they come from

| claim in script | value | artifact |
|---|---|---|
| primary clean fake recall | 0.7107 | `results/internal-test/results.json` |
| primary recall at noise σ=0.10 | 0.0073 | same |
| cascade recall at noise σ=0.10 | 0.7897 | same |
| primary fake→real flip rate | 0.2664 | same |
| **worst-family: primary → cascade** | **0.1227 → 0.8258** | same |
| FPR-matched baseline | 0.3342 | same |
| FPR-matched advantage | **+0.4916** CI95 [+0.4753, +0.5083] | same |
| cascade clean FPR (over our own cap) | 0.0833 vs 0.0756 | same |
| overall accuracy | 0.9090 | same |
| per-family table (slide 8) | all seven rows | same |
| hook image, clean / noise | primary 0.9995 / **0.0166**; ours 0.9999 / **0.9986** | live CLI, reproduced above |
| certificate: degraded / clean | 17/20 LOW 84.9% · 20/20 HIGH 99.1% | `results/robustness/retention-signal.json` |
| retention beats reliability head | 0.8696 vs 0.7206 | same |
| abstention lift | 0.9090 → 0.9317; worst-family 0.8258 → 0.9136 | `results/internal-test/abstention.json` |
| sealed: rows / clean AUROC / all-cond / worst | 174,380 / 0.9964 / 0.9821 / 0.8787 | `results/sealed/reference-results.json` |
| sealed non-transfers | +0.09 advantage; abstention +0.0001 | same |
| router parameters | 1,827 | `results/router-fitting-v2/router_reliability.pt` |
| shipped total / share of cap | 21,814,571 / 1.09% | `results/ops/ops-evidence.json` |
| latency p50 | 134.6 ms (19.5 ms baseline) | same |
| probes buy nothing | no arm distinguishable, 86% of runtime | `results/probe-ablation/dev-results.json` |
| format shortcut | 100.00% of 15,000 | README §8 |

**Say "twelve to eighty-three", not "eleven to eighty-one".** The artifact says 0.1227 → 0.8258.

## Recording checklist

- [ ] Deck open at `deliverables/video-slides.html`, `F` for fullscreen, notes **off**
- [ ] Terminal font ≥ 18pt, window sized so `audit_image.py` output fits without wrapping
- [ ] Warm the model first (run one `predict.py`) so no download/first-load pause is recorded
- [ ] `.venv/bin/python -m src.app` running for the UI beat
- [ ] No personal paths, tokens, or filenames in frame — `cd` to the repo and use relative paths
- [ ] Final card carries the SID-Set CC BY 4.0 attribution
- [ ] Upload to YouTube as **public**, then paste the link into the Devpost description
