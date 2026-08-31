# Demo video script — v5 (target ~5:00)

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
saved. **v5 targets ~5:00.** "Short" rules out rambling, not explaining.

**v5 fixes a regression I introduced in v4.** v4's asset table and checklist both said "for the UI
beat" while the script contained no UI beat at all — I dropped the Gradio and `infer_dir.py` shots
from v3 while making room for architecture. The brief's wording is *"such as inference results,
dashboard, or model predictions"* — examples, not requirements, so CLI alone would technically
satisfy it. But Technical Execution (35%) explicitly rewards *"the demo runs reliably"*, Impact
(20%) rewards value to real users, and `infer_dir.py` is itself a required deliverable. **The
product now leads the video**, and the terminal supports it rather than replacing it.

## One framing decision, made on evidence (read before recording)

**Do not sell "routes it to a human" as the contribution.** Our own sealed-set result argues against
it, and a judge who reads the repo will find that before we tell them:

| | internal test (SID-Set) | sealed set (COCO + DALL-E) |
|---|---|---|
| images deferred | 20.1% | **26.0%** |
| accuracy gain from deferring | **+2.26 points** | **+0.0001 points** |
| deferred-set accuracy | 0.8191 — clearly worse, so it *is* separating | 0.9407 vs 0.9412 kept — separating **nothing** |

Abstention is driven by the **fitted reliability head**, which degraded to AUROC 0.6478 on a fresh
holdout. The **certificate** is driven by **verdict retention**, which held at 0.8636 there against
0.8696 internally. One of our two confidence signals survived a distribution shift and one did not,
and we know which.

So the claim the video makes is: **every verdict arrives with a grade we measured, and the grade
holds up on data from a different distribution.** Abstention is reported as a measured result that
did **not** transfer — which is a strength, because we tested it externally and published the
failure rather than quoting the in-distribution number alone.

It still ships: it is advisory, it helps in-distribution, and the sealed benchmark was scored with
it — removing it now would leave our one official number describing a system we do not ship.

## What the video must show, and why — mapped to the brief

The brief's only demand is: *"Demonstrates your solution working end-to-end (e.g. inference results,
dashboard, model predictions)."* Those are **examples, not a checklist** — any one of them satisfies
it. We show all three, because each one buys a different judging criterion.

| beat | what it proves | criterion it serves |
|---|---|---|
| UI: upload → verdict → the card naming the router's correction | the solution works end-to-end, on a real interface | **required** · Impact 20% |
| UI: stress test → certificate + chart | the *idea* is real and visible, not asserted | Innovation 20% |
| Architecture slide | deliberate, explained design | **Technical Execution 35%** |
| `audit_image.py` cutaway | UI and CLI are one system | Technical Execution |
| `infer_dir.py` batch run | the brief's own required batch interface | **required deliverable** |
| Engineering receipts (suite + frozen reproduction) | "the demo runs reliably", reproducibility | Technical Execution 35% · Feasibility 15% |
| FPR-matched slide + limitations | claims are disciplined, not cherry-picked | Innovation · Feasibility |
| Sealed-benchmark slide | validated on the organizers' own data | Impact · Feasibility |
| Latency / parameter figures | proportionate resource use, buildable beyond a prototype | **Feasibility 15%** |

**Hard rules for what must NOT appear on screen:**
- No image from the organizers' sealed reference set — it is the official benchmark and stays sealed.
- No false-positive case from `results/robustness/cases/` — all four were inspected and every one
  carries third-party content (livery, watermark, faces, branding). Use the staged synthetic image.
- No local absolute paths, tokens, API keys, or personal filenames — `cd` into the repo and use
  relative paths throughout.
- The closing card must carry *"Synthetic sample image: SID-Set, CC BY 4.0"*.

## Assets — all staged and verified

| asset | path | state |
|---|---|---|
| Slide deck (12 slides) | `deliverables/video-slides.html` | ✅ built; `←/→` navigate, `F` fullscreen, `N` presenter notes (hidden by default so recordings stay clean) |
| Hook image, clean | `deliverables/video-assets/bird_clean.png` | ✅ staged |
| Hook image, noise σ=0.10 | `deliverables/video-assets/bird_noise_s010.png` | ✅ staged |
| Gradio UI | `.venv/bin/python -m src.app` → `http://127.0.0.1:7860` | ✅ launches, HTTP 200; analyze 0.4 s, stress 3.4 s |
| UI look, pre-checked | `deliverables/video-assets/ui-preview.html` | ✅ static render of the REAL UI output — open it before recording to judge framing/zoom |

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

## 0:00–0:40 — The hook, in the product ✅ verified

**On screen:** the Gradio app — "Forensic Lab" header. Drag in `bird_clean.png`, click
**Analyze image**. Then drag in `bird_noise_s010.png` and analyze again.

```
.venv/bin/python -m src.app        # http://127.0.0.1:7860
```

**Verified output** — clean: **AI-GENERATED**, p_fake `0.9999`, CF-384 `0.9995`.
Noisy: **AI-GENERATED**, p_fake `0.9986`, and the card itself prints
**"Primary CF-384 alone: 0.0166 → after router correction: 0.9986"**. Latency ~223 ms. 0.4 s per analyze.

> "This image is AI-generated. A state-of-the-art open detector agrees — ninety-nine point nine
> percent confident.
> This is the same image with a small amount of noise added. You can't see the difference.
> Watch the detector's own score: **one point seven percent**. It now calls it a real photograph.
> Our system still catches it — and it shows you exactly that: the raw detector alone missed this,
> and the correction is what saved it."

**Why this shot:** the collapse and the rescue in the product's own words, on one image, in the UI a
reviewer would actually use — not a claim in a terminal.

## 0:40–1:10 — Why this matters · SLIDES 2–3

> "Published detectors report near-perfect accuracy on clean images. But every platform recompresses
> and resizes what users upload. That's not an attack — it's the normal path from camera roll to feed.
> We measured it on three thousand images the system had never seen, across all twenty official
> transformations. Sixty thousand scored views.
> On clean images the off-the-shelf detector catches seventy-one percent of AI images. Add that
> imperceptible noise and it catches **zero point seven percent**.
> Not degraded. Erased. And it fails the other way too — at that noise level it calls nearly a third
> of *genuine* photographs AI-generated. It doesn't get uncertain. It gets confidently wrong."

## 1:10–1:40 — The insight · SLIDE 4

> "The failures aren't random, and that's the opening.
> Real photographs carry sensor noise. Generated images are smooth. Blur strips sensor noise, so
> blurring a real photo pushes it along exactly the axis the detector cares about — into the region
> where generated images live. Added noise buries the generator's fingerprint, which sits in that
> same high-frequency band.
> Which means: if we can measure **what was done to the image**, we can predict **how much the
> verdict is worth**."

## 1:40–2:20 — The architecture · SLIDE 5

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

## 2:20–3:00 — It knows when it doesn't know ✅ verified

**On screen:** same image still loaded in the UI. Click **Stress-test this image**. (~3.4 s — do not
cut the wait, it is the system doing 80 forward passes.) Chart and certificate fill in.

**Verified output:** *Forensic robustness certificate · Verdict AI-GENERATED (p_fake 0.9986,
threshold 0.4667) · Verdict retention **17 / 20** stress conditions · Forensic reliability: **LOW** —
verdicts at this retention were correct for **84.9%** of held-out sources · Worst-case score against
this verdict: 0.413 at blur_s1.0*, then the conditions that flip it.

> "And this is the part we think matters most. The system audits its own answer: it re-runs that
> verdict through all twenty transformations and counts how many survive.
> Seventeen out of twenty. So it grades its own call **low** — verdicts this fragile are right about
> eighty-five percent of the time — and it names the conditions that break it.
> That percentage isn't a label we chose. It's what we measured on three thousand held-out images.
> Run the clean version and it's twenty out of twenty, grade high, ninety-nine percent."

**Cutaway (~8 s):** the same certificate from the CLI, to show it is one system, not a UI feature:

```
.venv/bin/python scripts/audit_image.py deliverables/video-assets/bird_clean.png
```

**Verified:** **20 / 20**, grade **HIGH — correct for 99.1%**, worst case 0.946 at jpeg_q30.

## 3:00–3:20 — Batch, and one decision path ✅ verified

**On screen:** terminal.

```
.venv/bin/python scripts/infer_dir.py deliverables/video-assets --output predictions.json
```

**Verified output:** `found 2 image(s)` → `[2/2] scored` → `2 scored, 0 failed`, emitting
`[{"image_path": "bird_clean.png", "pred": 0.9999}, {"image_path": "bird_noise_s010.png", "pred": 0.9986}]`.

> "The same system runs as a batch interface over a folder — and the UI, the command line and the
> evaluation harness all call one prediction service. There is no separate demo code path that could
> flatter these numbers."

## 3:20–4:00 — The result, and the fair version of it · SLIDES 6–8

> "Across the worst transformation family, the off-the-shelf detector catches **twelve percent** of
> AI images. Ours catches **eighty-three**.
> But that baseline runs at a thirty-times lower false-positive rate, so some of that gap is just a
> looser cut — and we're not going to pretend otherwise. So we handed the baseline our operating
> point, with its threshold fitted **on the test set itself**: leakage we grant it and deny ourselves.
> It reaches thirty-three percent. We still lead by **forty-nine points**. That's the number we publish.
> Here's every family, including the ones where we gain least — and the cost: our clean false-positive
> rate is eight point three percent, above the cap we set ourselves. We reported that rather than
> re-tuning to hide it."

## 4:00–4:25 — The organizers' benchmark · SLIDE 10

**This is a WIN slide — deliver it as one.** On the organizers' own data the system beat its own
internal numbers: worst-family **87.9%** against 82.6%, and clean false-alarm rate **1.58%** against
8.33% — inside the cap our internal test breached. Lead with that; the caveat is one sentence.

> "The organizers gave everyone a reference set. We sealed it on day one — never trained on it,
> never tuned to it, never looked at the results while making decisions.
> After the architecture was frozen we ran it **once**. A hundred and seventy-four thousand rows,
> zero failures. And it did **better** than our own test: eighty-eight percent on the worst
> transformation family against eighty-three, and false alarms at one and a half percent — five
> times better, and comfortably inside the cap we'd set ourselves and missed internally.
> We also measured what didn't carry over, because a result you haven't stress-tested isn't a
> result. On this easier distribution our lead over a properly-tuned competitor narrows to nine
> points, and the confidence signal we *measured* held while the one we *trained* did not.
> We'd rather be the team that knows which is which."

## 4:25–4:40 — Engineering receipts ✅ verified

**On screen:** two commands, fast cuts. This is the cheapest thirty seconds of Technical Execution
credit in the whole video — it shows the work is reproducible rather than claimed.

```
.venv/bin/python -m pytest tests/ -q
.venv/bin/python scripts/run_eval.py --config configs/frozen.yaml
```

**Verified:** `787 passed, 1 skipped` · and `10 verified, 0 verified with absent inputs, 0 drifted,
0 missing` — every published table checked against the artifact it came from *and* the inputs that
produced it.

> "Every table in this video regenerates from one command, and every number is checked against the
> artifact it came from — inputs included. Seven hundred and eighty-seven tests pass."

## 4:40–5:00 — Rigour and close · SLIDES 11–12

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
> A score you can price is worth more than a score you can't."

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
| hook image, clean / noise | primary 0.9995 / **0.0166**; ours 0.9999 / **0.9986** | live UI + CLI, reproduced above |
| UI stress panel on the degraded image | 17/20, LOW, 84.9%, worst 0.413 at blur_s1.0 | live UI, reproduced above |
| batch interface | 2 scored, 0 failed | `scripts/infer_dir.py`, reproduced above |
| certificate: degraded / clean | 17/20 LOW 84.9% · 20/20 HIGH 99.1% | `results/robustness/retention-signal.json` |
| retention beats reliability head | 0.8696 vs 0.7206 | same |
| abstention lift, in-distribution | 0.9090 → 0.9317; worst-family 0.8258 → 0.9136 | `results/internal-test/abstention.json` |
| **abstention, out-of-distribution** | defers 26.0%, gain **+0.0001**; kept 0.94123 vs deferred 0.94074 | `results/sealed/reference-results.json` |
| retention held, reliability head did not | 0.8636 vs 0.6478 on the fresh holdout | `results/holdout/validation.json` |
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
- [ ] `.venv/bin/python -m src.app` running **before you hit record** — the first analyze loads the
      model; warm it once so no load pause is filmed
- [ ] Browser zoom so the verdict card and stress chart are legible at 1080p; hide bookmarks bar
- [ ] No personal paths, tokens, or filenames in frame — `cd` to the repo and use relative paths
- [ ] Final card carries the SID-Set CC BY 4.0 attribution
- [ ] Open `deliverables/video-assets/ui-preview.html` first and set browser zoom from it
- [ ] Nothing from the sealed set and nothing from `results/robustness/cases/` on screen
- [ ] Upload to YouTube as **public**, then paste the link into the Devpost description
