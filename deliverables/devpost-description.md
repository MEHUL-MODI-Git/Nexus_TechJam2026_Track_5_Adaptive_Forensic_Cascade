## Inspiration

AI image detectors publish extraordinary accuracy. Ours does too — **99.6% AUROC on clean images.**

Then somebody uploads the image.

Every platform recompresses, resizes and re-encodes what it receives. That isn't an attack; it's the normal path from camera roll to feed. So we took a state-of-the-art open detector and measured what survives it: 3,000 images it had never seen, put through all 20 transformations the brief lists, 60,000 scored predictions.

On clean images it catches **71.1%** of AI-generated images. Add Gaussian noise at sigma 0.10 — imperceptible, one slider in any photo app — and it catches **0.7%**.

Not degraded. **Erased.** And it fails the other way too: at that same noise level it calls nearly a third of _genuine photographs_ AI-generated.

The failure that bothered us most wasn't the errors. It was that **nothing on screen told you an error had happened.** The detector didn't become uncertain — it became confidently wrong, at the extremes of its range. Real photographs scored 0.9996. AI images scored 0.0001. A moderation system reading that score as confidence would act on both.

That is the problem we set out to fix.

## What it does

The **Adaptive Forensic Cascade** measures what has been _done to_ a picture before judging what the picture _is_.

- **Measure the damage.** Cheap descriptors — blur, blockiness, noise level, luminance — plus three self-probes that re-score the image under mild perturbations to see how stable the verdict is.
- **Correct the verdict.** A **1,827-parameter** reliability router combines the frozen detector's opinion with the damage measurements and corrects the score. That router is the entire contribution; everything else is frozen and downloaded.
- **Report what the answer is worth.** Every verdict carries a self-assessed reliability, the detected damage type, and on request a **Forensic Robustness Certificate** — the system re-runs its own verdict through all 20 transformations and reports how many survive.

Real output from the demo:

```
Verdict: AI-GENERATED (p_fake 0.9062)
Primary detector alone: 0.0993  ->  after router correction: 0.9062
Detected image history: JPEG compression (91% confidence)
Verdict retention: 18 / 20 stress conditions
Forensic reliability: MEDIUM
  - verdicts at this retention were correct for 94.9% of held-out sources
Verdict changes under: resize_0.25, bright_+20
```

That **94.9%** is not a label we chose. It is what we measured on 3,000 held-out images.

## Results

Detection rate on AI-generated images, measured on 3,000 held-back images across 20 conditions:

```
                                   baseline      OURS
  clean images                        71.1%     96.1%
  worst transformation family         12.3%     82.6%
  all 20 conditions                   56.7%     92.0%
  overall accuracy                    78.1%     90.9%
  false alarms on clean real photos    0.3%      8.3%
```

**The fair version of that comparison.** A detector catches more fakes simply by accusing more images, and the baseline is far more conservative than we are. So we handed it our exact false-alarm rate _and_ let it tune its threshold **on the test set itself** — an advantage we never took:

```
  baseline at its published default          12.3%
  baseline given our rate, tuned in its
      own favour on the test answers         33.4%
  OURS                                       82.6%

  lead = +49.2 points, CI95 [+47.5, +50.8]
         paired bootstrap over image sources
```

**That smaller number is the one we publish.**

**On the organizers' own reference set** — sealed from day one, scored exactly once after the architecture was frozen. 8,719 unique images x 20 conditions = **174,380 predictions, 0 failures**:

```
  clean AUROC                0.9964
  all-conditions AUROC       0.9821
  worst-family detection      87.9%   (vs 82.6% on our own test)
  clean false alarms          1.58%   (vs 8.33% on our own test)
```

It scored **better** on data we had never touched than on our own held-back set.

## How we built it

One decision path. The CLI, the batch script, the demo UI and the evaluation harness all import the same prediction service — there is no separate demo code that could flatter the numbers, and a parity test asserts identical scores across them.

```
canonical decode
  -> frozen expert  (CF-384, 21.8M params, pinned revision, never fine-tuned)
  -> damage descriptors + 3 self-probes
  -> reliability router  (1,827 params)          <- our contribution
  -> verdict + reliability + certificate
```

**Training.** 15,000 sources, 7,500 per class, split into a 12,000-source fitting half and an untouched 3,000-source internal test. A 7-rung comparison ladder — from _no detector at all_ up to an MLP with worst-group loss — under a selection rule fixed in advance: highest worst-family recall subject to clean false-positive and balanced-accuracy constraints. The winner's threshold was then frozen and never touched again.

Four disciplines shaped everything:

- **One threshold** across all 20 conditions. Tuning per condition would be leakage.
- **Failures are never scores.** A model that errors returns "unavailable", never a neutral 0.5 that averages into a verdict.
- **The evaluation cannot flatter us.** A headline requires a validated threshold artifact and exact method x source x condition coverage; a partial grid is structurally refused, not warned about.
- **Contamination is proven, not asserted.** All 13,843 organizer reference images fingerprinted by SHA-256 and perceptual hash, every training source audited against them: **0 exact matches**, and the only 2 perceptual near-matches were opened by eye and confirmed unrelated. The guard is fail-closed and it aborted a real run.

## Challenges we ran into

**The second expert failed twice, and why is the interesting part.** We integrated LOTA (ICCV 2025) and then PGC (306.7M parameters) as rescue models for images the cascade distrusts. Both failed. LOTA reads the least-significant-bit plane of a random patch — non-deterministic, and it collapses to AUROC 0.592 with **zero** detection on JPEG re-encoding. PGC is deterministic and loads cleanly, but P(PGC correct | our cascade wrong) = **0.5426**. A coin flip.

It took both failures to see the reason, and it is structural. A rescue only ever sees images the system already distrusts, and those are dominated by noise and heavy compression. LOTA reads the LSB plane; PGC reads a quantization residual. **Both live in the high-frequency band — exactly what those degradations destroy.** You cannot rescue noise-destroyed evidence with a detector that reads evidence from the noise band. So the escalation we ship goes to a human, not to a second model.

**Our own self-probing bought nothing.** An 8-arm, 3-seed ablation found no probe budget distinguishable from _none at all_ — while costing 86% of inference time. We report it rather than quietly keeping it.

**Two AI agents built this as reviewing peers,** and the review caught real defects: an evaluator that returned success while writing `NaN`, an AUROC that depended on row order, a parameter statement wrong by three orders of magnitude, and a documented reproduction command that had never actually been runnable. Each sits in the commit history with the reproduction that found it.

## What we learned

**Which of your confidence signals survives new data matters more than either signal's headline number.**

We built two. The _trained_ reliability head scores AUROC 0.7206 at predicting its own errors — but on a fresh holdout it **degraded to 0.6478**. The _measured_ signal — verdict retention across the 20-condition grid — scored 0.8696 and **held at 0.8636** on that same holdout.

The consequence is concrete, and we publish it: our abstention policy lifts accuracy by 2.26 points on our own distribution, and by **0.0001** on the organizers' — where it defers 26% of images for nothing. The signal we _measured_ generalised. The one we _fitted_ did not.

## Accomplishments that we're proud of

- **12.3% to 82.6%** worst-case detection, and **+49.2 points** against a baseline we deliberately handicapped in its own favour.
- **21,814,571 parameters — 1.09% of the 2B limit**, of which only 2,602 are ours to train. The contribution is the decision layer, not scale.
- Every published table regenerates and re-verifies from **one command**, checking each result against both the artifact and the inputs behind it: `run_eval.py --config configs/frozen.yaml` reports _11 verified, 0 drifted_.
- **804 automated tests**, plus a fresh-clone check that clones the repository and scores images to prove it runs for someone who isn't us.
- A constraint we set ourselves and then **missed in public**: our clean false-positive rate came in at 8.33% against the 7.56% cap we pre-registered. We reported it rather than re-tuning to hide it.

## What's next for Adaptive Forensic Cascade

- **Drop the self-probes.** Measured, they buy nothing and cost 86% of runtime. Removing them cuts inference to about 19 ms and audit mode from 80 forward passes to 20. We did not ship that change because it alters the frozen architecture the sealed benchmark measured.
- **Fit the reliability head on a mixed-source corpus.** Its failure to generalise is a data problem, not a design flaw.
- **Multi-generator training data.** Our corpus is single-source; generalisation is currently evidenced by the organizers' set rather than by our own training distribution.

## Built with

- **Models:** Community Forensics 384 (ViT-S/16, MIT, 21,811,969 params, pinned revision) · our reliability router (1,827 params) · our degradation reporter (775 params). LOTA and PGC were integrated, measured and rejected. **No external APIs — everything runs locally.**
- **Languages and frameworks:** Python 3.12 · PyTorch (Apple Silicon MPS) · timm · Hugging Face Hub · NumPy · SciPy · Pillow · imagehash · PyYAML · Gradio.
- **Tools:** VS Code · git · `uv` · pytest · Ruff · Apple M4 Pro laptop, no cloud compute.
- **Data:** SID-Set (CC BY 4.0) for the 15,000-source corpus · COCO train2017 for real smoke images · the organizers' WildFake reference subset, used exactly once for reference and never for fitting.
