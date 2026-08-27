# Devpost description — DRAFT v1

> **Status:** Claude draft, Codex reviews and integrates (Phase 5R). Every number below is either
> measured and cited, or marked `[PENDING]` where the protected evaluation has not finished. **No
> `[PENDING]` may ship as a number without an artifact behind it.**

---

## Adaptive Forensic Cascade — detection that knows when it is wrong

### The problem, stated precisely

AI-image detectors report extraordinary accuracy. Ours does too: **AUROC 0.992 on clean images**.

Then somebody uploads the image.

Every platform recompresses, resizes and re-encodes what it receives. That is not an attack — it is
the normal path from camera roll to feed. And it is where published accuracy goes to die. On our
20-condition stress grid the same detector that scores 0.992 clean drops to **AUROC 0.647 under
Gaussian blur at sigma 2.0**.

The interesting part is not that it degrades. It is *how*.

**At one fixed operating point, the false-positive rate goes from 1.0% on clean images to 64.0% under
blur.** Same model, same threshold, same day — a 64x increase in wrongly accusing real photographs.
The model does not become uncertain; it becomes confidently wrong in one specific direction, pushing
**real photographs** toward "AI-generated". A moderation system built on that does not fail quietly.
It fails by accusing real users, at scale, on exactly the images that platform processing has touched
most.

(Measured on 400 sources at threshold 0.016, the operating point that yields 1% false positives on
clean images. At the naive 0.5 default the same condition gives 31.5% — the effect is not an artifact
of a badly chosen cut. Both numbers come from the same committed 8,000-row grid.)

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

**3. Abstain instead of guessing.** The output is not a binary verdict. It is a verdict plus a
reliability readout, and an explicit "uncertain" band. For a moderation workflow, an honest
"I cannot tell, route this to a human" is worth more than a confident coin flip.

### What we actually found

Three findings we did not expect, all of which changed the build:

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

`[PENDING]` The protected evaluation is running at submission time. The robustness table, the trained
router result, and the sealed reference-set run are reported from committed artifacts or not at all.

What we will not claim: that we solved JPEG at quality 30. We did not. Heavy compression and heavy
noise remain hard, and we report the conditions where the system fails alongside those where it works.

### Built with

- **Models:** Community Forensics 384 (MIT, 21.8M parameters) as the primary detector. LOTA (MIT)
  evaluated and rejected on measured evidence. Total pipeline well under the 2B parameter limit.
- **Libraries:** PyTorch (Apple Silicon MPS), timm, Hugging Face Hub, Pillow, NumPy, PyArrow,
  imagehash, Gradio, pytest, Ruff.
- **Data:** SID-Set (CC BY 4.0) for the training corpus; COCO train2017 for real smoke images; the
  organizers' WildFake reference subset used exactly once, for reference only, never for fitting.
- **Tools:** VS Code, git, `uv`, and two AI coding agents working as reviewing peers — every gate in
  this project was independently re-run by the agent that did not write it.
