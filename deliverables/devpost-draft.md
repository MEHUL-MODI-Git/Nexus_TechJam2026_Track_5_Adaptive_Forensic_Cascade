# Devpost description — draft v2

> **Status:** Claude draft, Codex reviews and integrates (Phase 5R). **Every number below is backed by
> a committed artifact and measured on data that fitted nothing** — the untouched internal test
> (3,000 sources x 20 conditions), the second holdout, the one-shot run on the organizers' sealed
> reference subset, or the ops measurement artifact. Each section says which.
> The smoke-set figures that opened the previous draft are gone: they came from a 400-source
> diagnostic pitting COCO reals against SID-Set fakes, a comparison we disowned once the JPEG/PNG
> format confound was found.
>
> **v2 (29 Aug):** adds the sealed reference benchmark, which the draft had omitted entirely;
> corrects the latency figures to the committed ops artifact (they had drifted a run behind) and
> the parameter enumeration to include the degradation reporter.

---

## Adaptive Forensic Cascade — detection that knows when it is wrong

**Demo video:** https://youtu.be/KUedfboxC-Q
**Code:** https://github.com/MEHUL-MODI-Git/Nexus_TechJam2026_Track_5_Adaptive_Forensic_Cascade

### The problem, stated precisely

AI-image detectors report extraordinary accuracy on clean data. Ours does too.

Then somebody uploads the image.

Every platform recompresses, resizes and re-encodes what it receives. That is not an attack — it is
the normal path from camera roll to feed. And it is where published accuracy goes to die.

We measured it on 3,000 held-back images across all 20 official transformations — 60,000 scored
views, on data no part of our system had ever seen. The off-the-shelf detector at its published
operating point catches **71.1% of AI images on clean inputs**. Add Gaussian noise at sigma 0.10 —
imperceptible, one slider in any photo app — and it catches **0.7%**.

Not degraded. **Erased.** Of the AI images it correctly identifies when clean, **26.6% flip to
"real"** the moment any transformation touches them.

It fails in the other direction too. At the operating point our own system runs, noise at sigma 0.10
makes it call **29.7% of genuine photographs AI-generated**. A moderation system built on that does
not fail quietly — it accuses real users, at scale, on exactly the images platform processing has
touched most.

That asymmetry is the problem we set out to address. Not "detect AI images" — that is largely solved
on pristine data. **Know when the detector's answer can no longer be trusted, and say so.**

### The approach

A cascade with a reliability router. Three ideas, in order of how much they matter:

**1. Measure the damage, not just the image.** Before asking "is this AI?", we measure what has been
done to the picture — blur, blockiness, noise, geometry. These quality descriptors are cheap, and
they turn out to carry the signal that matters: they tell the router *how much to trust the detector
on this specific image*.

**2. Probe the detector against itself.** We re-score each image under small, controlled perturbations
(a mild JPEG, a small crop, a slight resize). A detector that is genuinely confident barely moves. One
that is guessing swings. That instability is a reliability signal that needs no second model and no
ground truth.

**3. Price the answer, don't just give it.** Every verdict arrives with a reliability readout and an
explicit "uncertain" band, so a downstream system can decide what each answer is worth instead of
trusting them all equally. On the held-back test, deferring the least reliable 20% lifts accuracy
from **0.9090 to 0.9317** and worst-case recall from **0.8258 to 0.9136**, and the deferred images
score 0.8191 against 0.9317 for the kept ones — it declines on the images it would have got wrong.

**And then it failed the test that mattered more.** On the organizers' sealed set — a genuinely
different distribution — the same frozen policy deferred **26% of images and gained 0.0001 accuracy**
(kept 0.94123, deferred 0.94074). It separated nothing. The reliability head we *fitted* does not
generalise off its training distribution; the signal we *measured* (point 4 below) does, holding at
AUROC 0.8636 on a fresh holdout while the fitted head fell to 0.6478. We ship abstention disclosed
and we do not claim it as the contribution — knowing which of your confidence signals survives new
data is the more useful result.

**4. Audit the verdict, not just the image.** The 20-condition stress grid we built to
*evaluate* the system turned out to be its best confidence signal. Run on a single image it
asks: how many of these 20 real-world transformations preserve this verdict? That number
predicts whether the verdict is wrong **better than the reliability head we trained for the
job** — AUROC 0.8696 against 0.7206 — and it catches 72.6% of the errors that head passes
with high confidence. So the product returns a **Forensic Robustness Certificate**:

```
Verdict: AI-GENERATED (p_fake 0.5739)
Verdict retention: 11 / 20 stress conditions
Forensic reliability: VERY LOW
  — verdicts at this retention were correct for 60.6% of held-out sources
Verdict changes under: jpeg_q30, noise_s0.05, contrast_+20, ...
```

The grades are the measured retention→accuracy relationship, not labels we chose, so the
number on screen is one we actually observed on 3,000 held-out images.

### What it does

Worst-transformation-family fake recall, on 3,000 untouched sources:

| | worst-family recall | clean FPR |
|---|---|---|
| Off-the-shelf detector, published default | 0.1227 | 0.0027 |
| **Our cascade** | **0.8258** | 0.0833 |

The naive comparison is +0.70. We do not report that number, because the two sit ~30x apart in
false-positive rate and some of the gain is simply a looser cut. So we handed the baseline a
threshold **fitted on the test set itself** to reproduce our exact operating point — leakage we grant
it and deny ourselves. The cascade still leads by **+0.49** (CI95 [+0.475, +0.508]). That is what we
report.

We publish what the same control takes away: at matched FPR the baseline **beats** us on blur, colour
and resize. Our entire advantage is `noise` and `jpeg`, the families where it collapses. We raise the
floor, not the ceiling — and on clean images we buy nothing at all (0.9613 vs 0.9620).

### And on the organizers' own reference data, scored exactly once

The reference subset was sealed from the first day: **nothing we ship** was trained on it,
thresholded on it, or chosen while looking at it. (One number below deliberately breaks that rule
in the *baseline's* favour, and says so.) After the architecture was frozen we ran it **once** —
8,719 unique images × 20 conditions = **174,380 rows, 0 failures**, through the same prediction
service the demo calls.

| | clean | all 20 conditions |
|---|---|---|
| AUROC | **0.9964** | **0.9821** |
| fake recall | 0.9680 | 0.9385 |
| false-positive rate | **0.0158** | 0.0570 |

Worst-family recall **0.8787** (`resize`), CI95 [0.8703, 0.8874] — *better* than the 0.8258 we
measured on our own held-out test, and the clean FPR constraint our internal test breached
(0.0833 against a 0.0756 cap) did not reproduce here at 0.0158.

**Two things did not transfer, and we report them as plainly as the wins.** Against a primary
baseline given our operating point — its threshold fitted on this very set, in its favour — our
advantage is **+0.09 here, not +0.49**. On this distribution the base detector is already strong,
so there is less left for a correction layer to do; our gain concentrates where the baseline is
weakest, which is the same finding seen from the other side. And **abstention does not generalise
to it at all**: the frozen policy defers 26% of images, and the deferred set is as accurate as the
kept set (0.9407 vs 0.9412). The reliability head was fitted on SID-Set. Deferring a quarter of the
images for no measurable gain is a real cost on this distribution, and we state it as one rather
than quietly reporting the run without it.

### What we actually found

Four findings we did not expect, all of which changed the build:

**Our own training data was broken, and we found it ourselves.** We deliberately drew both real and
fake images from a single dataset, specifically to avoid the classic trap of learning "this looks like
dataset A". It was not enough. Inside that dataset, **every real image is stored as JPEG and every
synthetic one as PNG** — so file format alone predicted the label for **100.00% of 15,000 images**.
Every file carried a `.jpg` extension regardless of its real bytes, which is why it went unseen. Our
own quality descriptors read it directly: `blockiness` alone separates the classes at AUROC 0.89.
We re-encoded every source to one container, and — because that only fixes part of it — added a
**mandatory "image statistics only" baseline to every comparison**, so no result of ours can be read
without knowing what plain pixel statistics achieve on the same data.

**The state-of-the-art second expert is unusable here, and we can say exactly why.** LOTA (ICCV 2025)
is excellent: AUROC 0.9996–0.9999 across eight generators. We obtained the weights, integrated them
against the authors' own code, and measured. It reads the **least-significant-bit plane** of a
randomly chosen 32×32 patch — which makes it non-deterministic (**0.31 score swing on the same image**)
and dependent on precisely the information that lossy compression destroys. Every image in its
published evaluation is a lossless PNG. On identical pixels re-encoded as JPEG q95, its AUROC falls to
**0.592 and its fake recall to 0.000** — it calls every AI image real. A detector that only works on
uncompressed images cannot help on a platform where every upload is recompressed. We report that as a
finding rather than shipping it as a dependency.

**Two more of our own ideas died, which is why we trust the ones that lived.** Our system
re-scores every image under three mild perturbations — 3 of its 4 forward passes. An 8-arm,
3-seed ablation found **no probe budget distinguishable from any other, including none at
all**: they cost 86% of inference time and buy nothing measurable. We also tried building an
evidence heatmap by occluding patches; a guard written *before* the experiment compared two
occlusion operators and found their maps correlate at 0.261, so the method measures the
artefacts its own masks create. Both are reported rather than quietly kept.

**The second expert failed twice, for the same structural reason — the most interesting thing we
learned.** After LOTA we integrated PGC (Apache-2.0, 306.7M parameters), which loads cleanly and,
unlike LOTA, is perfectly deterministic. It failed too: P(PGC correct | our cascade wrong) =
**0.5426**, a coin flip, with correction-minus-harm **-2451**. We tried confident-only override,
logit blending and per-family gating; the best variant nets **+1 across 12,000 images**.

Why both failed is the finding. A rescue only ever sees images the system already distrusts, and
those are dominated by noise and heavy JPEG. LOTA reads the least-significant-bit plane; PGC reads a
quantization residual. Both live in the high-frequency band — exactly what those degradations
destroy. **You cannot rescue noise-destroyed evidence with a detector that reads evidence from the
noise band.** So the escalation we ship goes to a human, not to a second model.

**The reference benchmark has substantial duplication.** Of the 8,843 AI images supplied for
demonstration, only **3,719 are unique** — 5,124 are byte-identical copies, some repeated five times.
Scored naively per file, some images count five times and confidence intervals come out far too
narrow. We deduplicate before scoring and report both conventions.

### Engineering

The parts we consider load-bearing:

- **One decision path.** CLI, batch inference and the demo UI all call the same prediction service.
  There is no separate demo code path that could flatter the numbers.
- **Failures are never scores.** A model that errors returns "unavailable", never a neutral 0.5 that
  silently averages into a verdict.
- **The evaluation cannot flatter us.** Producing a headline number requires a validated, loaded
  threshold artifact and exact method x source x condition coverage. A partial grid, a caller-supplied
  condition list, or a hand-constructed threshold object is structurally refused, not warned about.
- **Contamination is proven, not asserted.** We fingerprinted all 13,843 organizer reference images by
  SHA-256 and perceptual hash and audited every training source against them: **0 exact matches**, and
  the only 2 perceptual near-matches were opened by eye and confirmed unrelated (a Nokia phone against
  a glittery toilet; a crow against a skier). The check is fail-closed — it aborts the job rather than
  skipping a row, and it did abort a real run.
- **The system refuses to claim credit it has not earned.** Our comparison ladder includes a rung that
  uses no detector at all. When that rung wins, the report is structurally incapable of saying "the
  router earned its complexity". We caught that flag lying in exactly that case and fixed it.

### Honest status

Everything above comes from committed artifacts, and the failures are published beside the wins:

- **A constraint we set ourselves did not hold.** The threshold was selected under a clean
  false-positive cap of 0.0756; on unseen data it measured **0.0833**. We had pre-registered what to
  do if that happened and did it: report it, do not re-tune.
- **A rung we did not ship looks better on average.** Plain MLP has higher overall accuracy (0.9213
  vs 0.9090) and a lower clean FPR than the version we shipped. We selected on worst-case robustness
  by a rule fixed in advance; re-picking after seeing the test would be the exact leakage this
  protocol exists to prevent. The full table is published so a reader can disagree with our
  objective rather than be misled about its price.
- **Abstention has a blind spot.** It tracks noise almost perfectly (7% of clean images deferred,
  99% at sigma 0.10) but is nearly blind to blur — 0.03% deferred, where the error rate is elevated.
  Blur makes an image look *cleaner*, so the reliability head stays confident. Our worst individual
  errors all carry high reliability and would not be deferred.
- **The cascade costs 6.9x the baseline** in latency (134.6 ms vs 19.5 ms p50), almost all of it the
  probe passes. Adaptive escalation would have fixed that; it failed its gate, so we pay it always.

What we will not claim: that we solved heavy compression or heavy noise. We did not. They remain the
worst conditions and we report them.

### How this addresses the problem statement

Track 5 asks for detection that holds up "after images are compressed, cropped, reposted, or
lightly edited", and for a clear technical approach, an evaluation strategy, and discussion of
trade-offs. Point by point:

| The brief asks for | What we built | Evidence |
|---|---|---|
| Robustness under real-world transformation | A router that measures the damage to an image and corrects the detector's verdict accordingly. Worst-family detection **12.3% → 82.6%** | `results/internal-test/results.json` |
| Not just clean accuracy | Scored on all **20** official conditions, 60,000 predictions, one frozen threshold never tuned per condition | `deliverables/robustness-summary.md` |
| A clear evaluation strategy | Fitting, held-out test, a second holdout, and the organizers' sealed set scored **once** after freeze. One command re-verifies all 11 published tables against the artifacts and inputs behind them | `configs/frozen.yaml` |
| Trade-offs: robustness, generalisation, false positives | We publish the false-alarm cost (8.3% vs the 7.6% cap we set), the fair comparison against a baseline handed our operating point (**+49.2 pt**, not +70), and what did not transfer to the organizers' distribution | README §7–8 |
| Explainability | Every verdict carries a measured confidence grade, the detected damage type, and a certificate showing which transformations would flip it | live in the demo |

### Development tools used

VS Code · git · `uv` (dependency locking) · pytest (804 tests) · Ruff · Gradio for the demo UI ·
Apple M4 Pro laptop, PyTorch MPS — all training and evaluation ran locally, no cloud compute.

Two AI coding agents worked as reviewing peers: every cross-cutting contract was re-run by the
agent that did not write it. That process caught real defects, including an evaluator that
returned success while writing `NaN`, an AUROC that depended on row order, and a parameter
statement wrong by three orders of magnitude. The repair record is the commit history.

### Models and APIs used

| Model | Role | Parameters | Licence |
|---|---|---:|---|
| Community Forensics 384 (ViT-S/16) | Frozen primary detector, never fine-tuned, pinned to one revision | 21,811,969 | MIT (code + weights) |
| **Our reliability router (MLP + worst-group loss)** | **The contribution** — turns measured damage into a correction | **1,827** | this repo, MIT |
| Our degradation reporter | Names the damage type in the UI | 775 | this repo, MIT |
| **Total shipped** | | **21,814,571** — **1.09%** of the 2B limit | |

Integrated, measured and **rejected**: LOTA (ICCV 2025 — code MIT, weights unlicensed) and PGC
(Apache-2.0, 306.7M). Both read the high-frequency band, which is exactly what compression and
noise destroy. No external APIs are called; the system runs entirely locally.

### Libraries and frameworks used

PyTorch (Apple Silicon MPS backend) · timm · Hugging Face Hub · Pillow · NumPy · SciPy ·
imagehash · PyYAML · Gradio · pytest · Ruff.

### Datasets and assets used

| Dataset | Use | Licence |
|---|---|---|
| SID-Set | Training corpus — 15,000 sources, 7,500 per class | CC BY 4.0 (attribution required) |
| COCO train2017 | Real images for smoke tests | COCO Terms of Use |
| **WildFake reference subset** (COCO val2017 + DALL-E) | **Organizers' benchmark — sealed, never trained or tuned on, scored exactly once** | Organizer-provided |

COCO **val2017 never** appears in any training source, asserted by a test. The sealed subset is
excluded from every fitting step by a fail-closed denylist of 13,843 hashes that aborts the job
rather than skipping a row — and it did abort a real run. Contamination was audited by SHA-256 and
perceptual hash: **0 exact matches**, and the only 2 perceptual near-matches were opened by eye and
confirmed unrelated.

Demo video sample image: SID-Set, CC BY 4.0. No third-party trademarks or copyrighted content
appear in the video.
