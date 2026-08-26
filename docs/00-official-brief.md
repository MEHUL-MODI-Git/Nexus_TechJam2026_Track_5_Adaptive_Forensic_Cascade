# Official Track 5 Brief

> **Status: OFFICIAL**  
> Source of truth: organizer-provided **TikTok TechJam 2026 - Tracks & Problem Statements**, Track 5, pages 36-40.  
> Verification: the pages were text-extracted and visually inspected against the PDF on 26 August 2026.

This file intentionally preserves the organizer wording. Formatting has been converted to Markdown, table rows that crossed PDF page boundaries have been reconstructed, and links are made clickable. The organizer's spelling mistake in “augmentataions” is shown as written and marked `[sic]`.

## Track title

> **TRACK 5**  
> **Robust Detection of AI-Generated Images Under Real-World Transformations**

The brief also announces:

> Technical Workshop Webinar with Q&A will be held on 28 Aug, 5:00 to 5:45pm.

The PDF contains a “Click here to join the webinar!” hyperlink. The exact link target should be taken directly from the source PDF rather than retyped from this transcription.

## 5.1 Background - verbatim

> Generative AI tools are making it easier than ever to create highly realistic synthetic images at scale. This creates new risks for online platforms, including misinformation, impersonation, fraud, and reduced trust in digital content. In practice, detection becomes even harder after images are compressed, cropped, reposted, or lightly edited, so robust methods matter more than lab-only accuracy.

### What this makes important

This is not a clean-benchmark-only task. The official motivation is the gap between laboratory accuracy and redistributed or edited images. Our project therefore has to demonstrate graceful degradation, not merely a strong clean score.

## 5.2 Problem Statement - verbatim

> We want participants to build a prototype that can distinguish AI-generated images from authentic images with strong robustness under realistic post-processing and redistribution scenarios. The goal is not only to achieve good detection performance on clean data, but also to maintain accuracy after transformations such as blur, compression, color adjustment, cropping, or rescaling. Solutions should present a clear technical approach, an evaluation strategy, and thoughtful discussion of trade-offs such as robustness, generalisation, and false positives.

The brief then says:

> Note: We consider robustness against a subset of the following augmentataions. [sic]

### Exact organizer transformation grid

| Transform | Parameters | Real-world analog |
|---|---|---|
| JPEG Compression | `quality = 90, 70, 50, 30` | Social-media re-encode, messaging |
| Gaussian Blur | `kernel sigma = 0.5, 1.0, 2.0` | Out-of-focus |
| Resize | `scale 0.5x / 0.25x then upscale` | Thumbnail generation |
| Gaussian Noise | `sigma = 0.02, 0.05, 0.10` | Low-light sensor noise |
| Color Jitter | `brightness/contrast/sat. +/-20%` | Filter apps, auto-enhance |
| Center Crop | `crop 80%` | Profile-picture cropping, framing |

### Exactness notes for implementation

- “Subset” means the public brief does **not** promise that every listed condition will be used in final judging. It also does not authorize us to ignore the list: the strongest evaluation still covers the complete grid.
- The brief does not define JPEG library, chroma subsampling, resize interpolation, blur kernel truncation, pixel-value convention for Gaussian noise, or whether color adjustments are individual or composed. These are [open protocol questions](08-risks-kill-criteria-open-questions.md#official-protocol-questions).
- The most defensible public benchmark will state all such choices and use deterministic seeds.
- “Resize” must downscale first and then upscale; testing only a permanently smaller image is not equivalent.
- “Crop 80%” should be implemented as an 80%-sized center crop, then adapted to the model input without quietly changing the stated crop severity.

## 5.3 Constraints & Scope - verbatim

| Category | Constraints & Scope Details |
|---|---|
| **In scope** | Image-level AIGC detection, robustness to common image transformations, feature engineering, model design, evaluation design, error analysis, and explainability ideas |
| **Out of scope** | Full production deployment, platform-wide moderation systems, and non-image modalities such as video or audio |
| **Limits** | Assume a hackathon-scale prototype, limited compute, and no access to internal production systems. Teams should optimise for a convincing proof of concept rather than a production-grade service. Note: Participants must use models with `<2B parameters`. |
| **Allowed assumptions** | Teams may use public or properly licensed datasets, create their own transformed test cases, and make reasonable assumptions about deployment context as long as those assumptions are stated clearly. |

### Binding design implications

- Public pretrained models are allowed, assuming their licenses permit the use.
- The `<2B` limit applies to models used by the solution. Document per-component and aggregate parameter counts; ask the webinar whether the limit is per model or total pipeline if that affects a candidate.
- The prototype does not need platform integration, online moderation infrastructure, video/audio support, or production SLAs.
- Error analysis and explainability are explicitly in scope, so a reliability readout is relevant even if it is not itself the detector.
- A seven-day, limited-compute solution should prioritize frozen checkpoints, small trainable components, reproducible evaluation, and a robust demo.

## 5.4 Available Resources & Data - verbatim

The brief lists:

> - Public or properly licensed image datasets for AIGC detection and image forensics.  
> - Self-created transformed samples using operations such as blur, compression, cropping, color adjustment, or rescaling.  
> - Public documentation for relevant machine learning and computer vision libraries.

Organizer-listed datasets:

- [SID-Set on Hugging Face](https://huggingface.co/datasets/saberzl/SID_Set)
- [CIFAKE on Kaggle](https://www.kaggle.com/datasets/birdy654/cifake-real-and-ai-generated-synthetic-images)
- [WildFake on ModelScope](https://modelscope.cn/datasets/hy2628982280/WildFake/summary)

The brief adds:

> For this modelscope dataset, please translate it via the translation button before use.

### Validation Dataset (for Demonstration Purposes Only) - verbatim

> We choose a subset of WildFake for participants to demonstrate their models' performance and track iterative improvements. This dataset serves only as a reference benchmark and will not contribute to the final score. Do not use the following data during training.

Specifically:

| Class | Dataset | Number |
|---|---|---:|
| Non-AIGC | COCO val2017 | 4,998 |
| AIGC | DALL-E Advanced | 8,843 |
| **Total** |  | **13,841** |

### Data boundary we will enforce

- **Never train or fit on these 13,841 examples.** That includes router weights, expert fine-tuning, thresholds, temperature scaling, bias correction, probe selection, feature selection, or early stopping.
- The brief permits demonstration and iterative tracking, but repeated manual optimization on this set can still produce evaluation overfitting. We will keep it sealed until the pipeline and metrics are defined, then use it as a reference benchmark.
- Generate SHA-256 and perceptual hashes for the sealed subset and reject exact or near duplicates from every training source.
- Report that this subset does not determine the organizer's final score.

## 5.5 Expected Deliverables - verbatim structure

### 1. Written Project Description (via Devpost)

Provide a clear written description that includes:

- How the solution addresses the problem statement.
- Development tools used, with examples in the brief including VSCode, Colab, and Jupyter.
- Models or APIs used.
- Libraries and frameworks used, with examples including Hugging Face Transformers, PyTorch, scikit-learn, and pandas.
- Datasets and assets used.

### 2. Public Code/GitHub Repository

Submit a link to a public code/GitHub repository containing a README that includes:

- A brief reflection on the solution's limitations and what would be improved with more time.
- Team member contributions, where applicable for non-solo teams.

### 3. Demo Video

Submit a short video that:

- Demonstrates the solution working end to end, such as inference results, dashboard, or model predictions.
- Is uploaded to YouTube and set to public visibility.
- Is linked in the Devpost description.
- Does not include third-party trademarks or copyrighted content without permission.

### 4. Robustness Evaluation Summary

> Include a compact table or visual summary comparing performance on clean images versus transformed images.

### 5. Error Analysis Note

> Highlight representative false positives, false negatives, and any trade-offs in the proposed approach.

### Deliverable acceptance checklist

- [ ] Devpost description covers approach, tools, models/APIs, libraries/frameworks, data/assets.
- [ ] Public repository URL works without special access.
- [ ] Repository README includes limitations and future improvements.
- [ ] Repository README includes team contributions if applicable.
- [ ] Short end-to-end demo is on public YouTube.
- [ ] Devpost links the video.
- [ ] Video has cleared trademark and copyright review.
- [ ] Clean-versus-transformed robustness summary is present.
- [ ] Error analysis includes representative false positives and false negatives.
- [ ] Model count/parameter statement demonstrates compliance with `<2B`.
- [ ] Official WildFake non-training safeguard is documented.

## 5.6 Judging Criteria - official wording and weights

| Criterion | Weight | Official definition |
|---|---:|---|
| **Technical Execution** | **35%** | The solution demonstrates strong engineering fundamentals, such as well-structured code, thoughtful architecture, and effective use of APIs or models. The demo runs reliably, and the technical complexity reflects deliberate, capable decision-making. |
| **Innovation & Problem Insight** | **20%** | The project demonstrates originality in both idea and approach. It stands out for the sharpness of its problem understanding - how clearly the team has framed the challenge, why it matters, and how directly the solution addresses it. |
| **Impact & Relevance** | **20%** | The project has clear potential to deliver value to real users or stakeholders - with meaningful reach, tangible benefit, and relevance that goes beyond solving for the hackathon prompt alone. |
| **Feasibility & Practicality** | **15%** | The solution is realistic and buildable beyond a prototype. The approach is technically and operationally sustainable - resource usage is proportionate, the architecture holds under real-world conditions, and the implementation is grounded rather than speculative. |
| **Presentation & Communication** | **10%** | The team communicates their work with clarity. **[Final Event Only]:** The pitch tells a coherent story; from problem to solution to potential, and the team is able to respond to questions with depth, demonstrating genuine understanding of their own project. |

### How our plan maps to judging without altering the requirements

| Judging area | Evidence we should present |
|---|---|
| Technical Execution | Reproducible transform pipeline, frozen expert adapters, tested router, graceful failure, latency/compute profile, deterministic evaluation. |
| Innovation & Problem Insight | Show fake-to-real degradation asymmetry, heterogeneous evidence failure modes, self-probed reliability, adaptive rescue, and ablations. |
| Impact & Relevance | Moderation-assistance workflow with high/medium/low reliability and abstention instead of unsafe overconfidence. |
| Feasibility & Practicality | Small trainable router, frozen pretrained experts, selective expensive inference, replaceable expert interface. |
| Presentation & Communication | One clear failure story, one architecture diagram, one clean-vs-stress chart, one case study, one honest limitation. |

## What the official brief does not require

The released specification does **not** state:

- A minimum accuracy threshold.
- That every listed transformation must be solved.
- That JPEG quality 30 failure disqualifies a submission.
- A ban on public pretrained detectors.
- A requirement to train a foundation detector from scratch.
- A requirement to always return a binary answer with no abstention.
- The hidden final test distribution or scoring formula.
- A production deployment.

These absences support a focused prototype, but they are not permission to overclaim. The target is measurable improvement with transparent limitations.

