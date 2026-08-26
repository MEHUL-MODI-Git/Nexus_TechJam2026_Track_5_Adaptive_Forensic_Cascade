# Research Landscape and Practical Model Review

> **Status: RESEARCH + DECISION**  
> Research cut-off: 26 August 2026.  
> Selection question: not “which paper has the best headline number?”, but “which downloadable components can produce complementary, transformation-robust evidence within seven days?”

## Executive conclusion

Robust AI-generated-image detection is not solved. AIGIBench evaluated 11 detectors across generalization, degradation, augmentation sensitivity, and test-time preprocessing and reported substantial real-world drops despite strong controlled results. DEAR identifies a specific **prediction asymmetry**: post-processing can leave real-image accuracy high while pushing generated examples toward the real class. DACOM argues that forensic systems should estimate whether a distorted input is even within a detector's reliable region.

That evidence changes the engineering goal:

> Do not promise a universal detector. Demonstrate that heterogeneous evidence plus sample-level reliability reduces transformation-induced fake-to-real errors relative to the strongest single detector.

## Evaluation lens

Every candidate is judged on six dimensions:

1. **Evidence family** - broad learned representation, local/noise, frequency, reconstruction, or perturbation behavior.
2. **Unseen-generator generalization** - does the training/evaluation include diverse generator families?
3. **Transformation evidence** - are corruptions directly evaluated, and how severe are they?
4. **Availability** - official code, checkpoint, license, and a workable inference path.
5. **Hackathon economics** - downloads, memory, preprocessing, forward passes, training requirements, and integration risk.
6. **Complementarity** - does it fix errors made by the primary detector, rather than merely agreeing with it?

## Candidate matrix

| Method | Evidence family | Public implementation status | Transformation evidence and caveat | Hackathon role |
|---|---|---|---|---|
| **Community Forensics 384** | Broad learned generator evidence | Official code, dataset, and Hugging Face checkpoint | Strong generalization basis; independent severe-degradation measurements suggest room remains | Default primary expert |
| **OmniAID** | Routed semantic experts + universal artifact expert | Official code and weights | Strong in-the-wild/generalization story; less direct evidence for the exact severe Track 5 grid | Day-1 primary challenger |
| **LOTA** | Low bit-plane/noise + high-gradient patch | Official code/checkpoint; lightweight | Very strong reported blur robustness; JPEG tests only 100/95/90/85, not 70/50/30 | Cheap complementary expert if ablation earns it |
| **WaRPAD** | Cropping/perturbation behavior using self-supervised embeddings | Official code; training-free | Directly evaluates JPEG to 50, crop to 50%, noise to 0.125; still no proof for JPEG 30 | Behavioral rescue expert |
| **RIGID** | Embedding stability under tiny noise | Official code; training-free | Reports corruption robustness and generalization | Backup behavioral option; simpler conceptual predecessor |
| **RA-Det** | Learnable perturbation + semantic/discrepancy/low-level branches | Official code | Strong average improvement; recommended 8 GPUs and batch 256 | Research reference, not first-week training dependency |
| **DEAR** | Post-hoc feature dissection and channel pruning | Official code/checkpoints/data released July 2026 | Targets compression/resizing fake-to-real asymmetry | Inspiration or stretch ablation, not core |
| **SAFE** | Crop-first preprocessing, color/rotation aug, patch masking | Official code and checkpoint | Transformation-aware training improves open-world generalization | Borrow training ideas; optional baseline |
| **AIDE** | Hybrid visual artifacts + noise + semantics | Official paper/code/checkpoints | Strong Chameleon motivation; heavier multi-expert stack | Benchmark if setup is easy; not initial architecture |
| **PROBE** | Generator-space boundary exploration/hard fake mining | Official repo; some release TODOs remain | Primarily unseen-generator generalization, not Track 5 corruption routing | External baseline/inspiration, not core training loop |
| **DRCT** | Diffusion reconstruction + contrastive training | Official code and DRCT-2M assets | Strong cross-generator logic; diffusion reconstruction is expensive | Literature baseline/longer-term option |
| **SSP / ESSP** | One simple local patch/noise pattern | SSP code/checkpoints public; ESSP repo still says forthcoming | ESSP is designed for blur/compression, but not currently a dependable integration | Do not depend on unreleased ESSP |
| **FerretNet** | Local pixel dependencies | Public research implementation | One cited robustness appendix collapses near chance at JPEG 75 | Explicit negative example |
| **MCAN** | RGB, high-frequency, and chromatic cue aggregation | Research reference; no clean official integration identified in prior pass | Supports diverse-cue hypothesis | Conceptual support only |
| **RAID (bit-reversed images)** | Bit-reversal-based robustness | Very recent July 2026 paper/code | Too new for confidence without reproduction | Watchlist/challenger only |

## Community Forensics

### What it is

Community Forensics was built around the thesis that generator diversity is a primary bottleneck. Its dataset contains approximately **2.7 million generated images from 4,803 generator models**, spanning systematically sampled Hugging Face models, selected open models, and commercial generators. The dataset card lists **2,760,270 rows** and roughly **1.08 TB**. A smaller paired subset is about 11% of the generated collection; the official repository describes it as roughly **278 GB**.

The public `OwensLab/commfor-model-384` checkpoint is reported at approximately **21.8M parameters**, comfortably below the Track 5 limit.

The conversation research recorded the paper's broad/comprehensive evaluation at approximately **0.987 mAP** and **0.893 mean accuracy** across its paired multi-generator evaluation. These are useful evidence of a strong starting point, but they are not Track 5 robustness results and should always be cited with the original evaluation protocol.

### Why it is the default primary

- Broad generator exposure gives a plausible basis for unseen-generator generalization.
- It is compact enough for repeated inference and mild self-probes.
- A single checkpoint and score make integration and calibration straightforward.
- It gives us a strong starting baseline without recreating a CVPR-scale training run.

### What it does not prove

Training across thousands of generators does not guarantee survival of JPEG 30, 0.25x resampling, or strong noise. The conversation research cited an independent 2026 robustness evaluation with approximately 79.1% accuracy at JPEG 30, 83.5% under random crop, and 89.0% after 0.5x downsampling on that evaluator's data. These figures are context, not transferable TechJam predictions. We must reproduce performance on our own controlled grid.

### Practical decision

Start with Community Forensics 384. Do not fine-tune it until the frozen baseline, calibration, and router are established. Replace it with OmniAID only if a clean Day-1 shootout shows a meaningful advantage across the Track 5 stress grid, not a single average score.

## OmniAID

### What it is

OmniAID uses a hybrid mixture-of-experts architecture with semantic specialists for categories such as humans, animals, objects, scenes, and anime, plus an always-on universal artifact expert. Its official repository reports public training/testing code and weights, router-based automatic inference, LoRA-style fine-tuning, and DINOv3 support. The repository recommends later weights with stronger augmentation for real-world generalization.

The earlier research pass recorded author-reported results for a Mirage-trained configuration of about **97.2% on GenImage, 91.4% on Chameleon, and 88.4% on Mirage-Test**. These datasets and metrics differ; the figures establish competitiveness, not superiority on the organizer's exact transformations.

### Strengths

- Strong in-the-wild and semantic-diversity motivation.
- Separates content-dependent semantic defects from content-agnostic artifacts.
- Public weights make it a credible challenger rather than a paper-only idea.

### Why it is not hard-coded as the primary

- It is operationally more complex than a single compact detector.
- It already contains a router, making a router-around-router architecture harder to explain and debug.
- Its published strengths are not identical to severe transformation robustness; exact JPEG 30 and resize 0.25x evidence must come from our benchmark.

### Decision

Give OmniAID one bounded Day-1 integration attempt. Compare it to Community Forensics at matched data, thresholds, and transformations. Choose the primary based on worst-transformation fake recall, false-positive rate, prediction flips, latency, and setup reliability.

## LOTA

### What it is

LOTA, “LOw-biT pAtch,” extracts noise-like information from lower bit planes, normalizes it, selects a high-gradient patch, and classifies using a lightweight noise-based or noise-guided head. The ICCV 2025 paper reports **98.9% average accuracy on GenImage**, strong cross-generator results, roughly **23.6M parameters**, and millisecond-level extraction/inference; the conversation notes quote roughly **4 ms** in the authors' environment.

The paper also reports over **98.2%** accuracy in a GAN-to-diffusion transfer direction and over **99.2%** in a diffusion-to-GAN direction in its evaluated setting. As with all paper numbers here, those results are tied to the authors' splits and preprocessing.

### Why it is attractive

- It is a genuinely different evidence family from broad semantic/representation detectors.
- It is cheap enough to test without committing the whole system to it.
- The paper's blur experiment is unusually strong: the conversation research records roughly **97-98% around Gaussian blur sigma 2-3**, beyond Track 5's maximum sigma 2.

### Critical JPEG caveat

LOTA's reported JPEG sweep uses qualities approximately **100, 95, 90, and 85**. Track 5 includes **70, 50, and 30**. Low-bit signals are precisely the kind of evidence severe compression can overwrite. Therefore:

- do not call LOTA a JPEG-robust model;
- do not assign it a fixed “blur expert” role by hand;
- let measured complementarity and the router decide when it helps;
- downweight or remove it if severe post-processing destroys its evidence.

### Decision

Integrate LOTA as the first cheap secondary expert because it makes the evidence portfolio more diverse at modest cost. Delete it if it rarely corrects primary-expert errors or harms calibration/worst-group performance.

## WaRPAD

### What it is

WaRPAD is a training-free NeurIPS 2025 method built on self-supervised vision models. It measures embedding sensitivity to perturbations along high-frequency directions derived by Haar wavelets, then uses a patching/rescaling procedure motivated by robustness to random resized crops. Its final score aggregates across patches.

### Why it fits Track 5

The paper evaluates corruption settings overlapping the official grid:

- JPEG down to quality **50**;
- center crop down to **50%**;
- Gaussian noise up to sigma **0.125**.

Track 5 asks for crop 80% and noise up to 0.10, both within that reported range. JPEG 30 remains outside the reported evidence.

### Why it is not always-on at first

WaRPAD requires multiple patches/perturbation computations and a self-supervised backbone. This makes it heavier than a single LOTA pass. Running it only for uncertain cases creates a product-like adaptive-compute story and limits latency.

### Decision

Use WaRPAD as the preferred rescue expert after the primary-plus-LOTA path works. Trigger it on calibrated uncertainty, expert disagreement, high estimated degradation, or self-probe instability. Benchmark it against RIGID before finalizing.

## RIGID and RA-Det

### Shared idea

Appearance-driven detectors ask what artifacts are visible. Behavioral methods ask how the image's representation changes under controlled perturbation.

RIGID observes that natural images preserve more stable foundation-model representations under tiny noise than generated images and compares original versus perturbed embeddings. It is training-free and model-agnostic with public code.

RA-Det extends the robustness-asymmetry idea with:

- a learnable perturbation module;
- semantic foundation features;
- discrepancy statistics between clean and perturbed embeddings;
- low-level residual features.

The RA-Det repository reports an average improvement of **7.81 percentage points** across 14+ generators. However, its recommended training uses **8 GPUs**, total batch size **256**, and warns that smaller batches degrade its statistics.

### Decision

- RIGID: reserve as a practical backup if WaRPAD integration or latency fails.
- RA-Det: cite as strong evidence for the behavioral cue, but do not train it during the seven-day critical path.
- Do not use both WaRPAD and RA-Det merely to have more experts; they may be less complementary to each other than either is to LOTA.

## DEAR

### Finding that matters

DEAR argues that post-processing creates **prediction asymmetry**: detector accuracy on real images can remain high while generated examples collapse toward “real.” It uses inpainted diagnostic images, computes Regional Activation Discrepancy for feature channels, prunes both extremes of the channel distribution, freezes the backbone, and retrains the classifier.

The prior research notes highlighted WEBP settings where DEAR improved fake-image accuracy by roughly **15-38 points**, depending on the base detector and compression condition. The range illustrates the size of the asymmetry in that paper; it should not be presented as an expected gain for Community Forensics or JPEG 30.

### Relevance

- It directly targets compression/resizing fragility.
- It warns us that average accuracy can hide catastrophic fake recall.
- It motivates feature stability analysis and post-hoc adaptation.

### Integration caveat

The released DEAR variants are tied to specific ResNet-50-based detectors and their diagnostic/refinement process. Porting it to Community Forensics is not a two-line operation. A TechJam-specific “transformation-stable feature gate” is possible, but it is a stretch ablation, not a prerequisite.

### Decision

Borrow the diagnosis and evaluation lens. Attempt feature gating only after the cascade and full benchmark are stable.

## SAFE

SAFE studies biases created by the training pipeline itself:

1. aggressive resizing weakens forensic artifacts, so crop-first preprocessing can be preferable;
2. color/semantic shortcuts can be reduced using ColorJitter and RandomRotation;
3. local awareness can be encouraged using patch-based random masking.

The paper reports improvements of about **4.5% accuracy** and **2.9% average precision** on its open-world evaluation, and the official repository includes a checkpoint.

### Decision

Use SAFE as a baseline if setup is quick and borrow its crop/masking/color lessons in router-data construction or any later fine-tuning. Do not add it automatically as a fourth production expert.

## AIDE

AIDE was motivated by a “sanity check” on nine off-the-shelf detectors using the challenging Chameleon data, where many generated images were classified as real. It combines visual/artifact, noise/low-level, and semantic features.

The paper reports improvements of roughly **3.5 points** on AIGCDetectBenchmark and **4.6 points** on GenImage over the compared state of the art in its setup. Packaged AIDE variants may be much heavier than the compact Community/LOTA path; the conversation noted checkpoint packaging around **0.9B parameters** for some variants, which is under the official limit but still costly for a seven-day multi-expert demo.

This supports the core hypothesis that different transformations damage different cues. However, AIDE is a larger hybrid system, overlaps with the multi-cue role our cascade already fills, and is a less economical first integration than Community Forensics plus LOTA.

### Decision

Treat AIDE as a strong optional baseline or fallback if its packaged checkpoint is easy to run. Do not make it a critical dependency.

## PROBE

PROBE explores regions of a generator's representation/manifold where a detector struggles and creates hard fake examples for refinement. It primarily addresses unseen-generator generalization rather than post-processing robustness.

The conversation research recorded average balanced accuracy of approximately **78.1% for a PROBE ResNet-50 detector** and **93.9% for a PROBE DINOv2 detector** across seven benchmarks. Before relying on those checkpoints, verify that the exact weights and evaluation code referenced by the paper are present in the pinned repository revision.

The official ICML 2026 repository is useful, but its README still exposes release TODOs for parts of evaluation, fine-tuning, and boundary exploration. This maturity risk makes it unsuitable as a core seven-day training process.

### Decision

Use its hard-example philosophy when analyzing difficult modern generators. If downloadable detector weights run cleanly, include them in the detector shootout; otherwise cite it as future work.

## DRCT

DRCT reconstructs real and generated images through a diffusion process and uses contrastive training on original/reconstructed categories. It reports over a ten-point cross-set improvement in the paper context and provides code/dataset assets.

The idea is powerful for diffusion generalization but reconstruction adds substantial compute and environment complexity. It also creates another data-generation pipeline, poorly matched to the fastest path to a working demo.

### Decision

Do not put DRCT on the critical path. It belongs in the literature review and post-hackathon roadmap.

## SSP and ESSP

SSP selects a simple local patch to exploit natural-camera noise patterns that generators may neglect. ESSP adds enhancement/perception ideas intended to improve blur and compression robustness.

The official repository currently says that only SSP code is released and ESSP code “will be released soon.” Official SSP checkpoints are tied to individual GenImage sources and external analysis has found mixed cross-dataset behavior.

### Decision

SSP can be a local baseline. Do not base the architecture on unavailable ESSP code.

## Additional methods and negative evidence

### FerretNet

FerretNet is a compact local-pixel-dependency detector, but the prior research pass recorded a fall from approximately 95.9% clean accuracy to 50.2% at JPEG 75 in its robustness appendix. This is a cautionary example: tiny, high-clean-accuracy forensic methods can be the most fragile under compression.

### MCAN

MCAN aggregates RGB, high-frequency, and chromatic cue experts. It supports the scientific premise for cue diversity, but without a clean official integration it is not a seven-day dependency.

### RAID, July 2026

The new “bit-reversed images” approach is worth a quick watchlist check because it explicitly claims robustness/generalization and has public code. It is too recent to replace tested choices without local reproduction.

## Benchmark conclusions

### AIGIBench

AIGIBench covers 23 fake subsets and four evaluation dimensions: multi-source generalization, degradation robustness, augmentation sensitivity, and test-time preprocessing. Its central conclusion is that high controlled accuracy does not mean the field is solved; common augmentation gives limited or nuanced benefits.

### GenImage

GenImage contains more than one million real/fake pairs across 1,000 ImageNet classes and eight generator families. It supplies cross-generator and degraded-image evaluation patterns and semantically aligned real/fake structure. It is valuable for router training and source-held-out evaluation, but its generators are no longer sufficient as the only modern test.

### SID-Set

SID-Set is described by the SIDA work as approximately **300,000 authentic, fully synthetic, and tampered images**, with detailed annotations and social-media-oriented realism. The earlier conversation noted a roughly **210,000-example training split**. For this binary Track 5 prototype, use authentic and fully synthetic examples first and exclude partial tampering unless the task definition is intentionally expanded.

### CIFAKE

CIFAKE pairs CIFAR-10 real images with Stable Diffusion 1.4 generations at very low native resolution. It is useful for a smoke test or weak baseline, but a model trained primarily on it can learn resolution, dataset, or old-generator shortcuts that say little about 2026 redistributed images.

### T2I-CoReBench image archive

The conversation research cited approximately **172,800 generations from about 40 modern text-to-image models**, including newer diffusion, autoregressive, and unified systems. The live archive is evolving, so pin a revision and derive exact counts from its manifest. Because it is principally a generated-image resource, use it for modern fake-recall/generalization testing unless a genuinely matched real set is constructed.

### Chameleon

Chameleon intentionally contains AI images that are challenging for human perception and exposed a strong fake-to-real failure mode in existing detectors. Use it as an external generalization test if licensing and downloads are practical.

### RRDataset

RRDataset contains scenario-diverse real/generated images and repeated transmission through platforms including Telegram, WeChat, Facebook, QQ, WhatsApp, X, Instagram, and Tinder, plus re-digitization conditions. It is an excellent “beyond synthetic transforms” external test.

## The actual two-plus-one model decision

### First two to integrate

1. **Community Forensics 384** - default broad primary, because it is small, public, and trained on extraordinary generator diversity.
2. **LOTA** - cheap orthogonal local/bit-plane expert, because its evidence and failure modes should differ from the primary.

This order differs from the earlier deep-research recommendation of Community Forensics + WaRPAD as the first two. The reason is implementation economics: LOTA is inexpensive enough to run broadly, while WaRPAD's perturbation/patch procedure is more naturally deployed selectively. This is an execution ordering, not a claim that LOTA is more robust overall.

### Optional third / rescue

3. **WaRPAD** - behavioral rescue expert, called only when the first path is unreliable.

### Challenger and backups

- Primary challenger: OmniAID.
- Behavioral backup: RIGID.
- Training-policy baseline: SAFE.
- Hybrid baseline if convenient: AIDE.

## Evidence required before an expert earns its slot

For expert `B` relative to primary `A`, calculate:

`P(B correct | A wrong)`

and report it by transformation and class. Also measure:

- error correlation;
- worst-group fake-recall change after adding the expert;
- false-positive change;
- calibration change;
- latency and memory;
- stability across random seeds and held-out generators.

A complementary paper story is not enough. An expert stays only if it measurably repairs useful errors.

## Bottom line

The fixed architectural concept is:

```text
PRIMARY GENERAL DETECTOR
        +
CHEAP ORTHOGONAL FORENSIC EXPERT
        -> RELIABILITY GATE
             -> confident: return calibrated result
             -> uncertain: invoke behavioral rescue
```

The model names remain replaceable. The architecture must follow the Track 5 stress data, not loyalty to any paper.
