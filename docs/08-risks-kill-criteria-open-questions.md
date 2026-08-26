# Risks, Kill Criteria, and Open Questions

> **Status: ACTIVE DECISION GATES**  
> These criteria exist to prevent a seven-day project from becoming a publication-scale architecture with no trustworthy result.

## Kill criteria by idea

### Community Forensics as primary

Replace with OmniAID if OmniAID shows a clear, repeatable advantage in worst-family fake recall and flip rate without unacceptable FPR/latency. Keep Community in a near tie because it is simpler.

Kill/replace if:

- preprocessing cannot be made consistent/reproducible;
- checkpoint license/availability blocks submission;
- a challenger improves the main robustness objective by at least 2-3 points across held-out sources and remains practical.

### OmniAID challenger

Stop integration if it is not producing verified scores within 3-4 hours. Do not redesign the cascade around a router-inside-router unless its measured gain is substantial.

### LOTA

Keep only if at least one is true on held-out data:

- `P(LOTA correct | primary wrong)` is materially high, provisionally 15%+ overall or substantially higher in an important family;
- adding it improves worst fake recall by at least 2 points;
- it reduces flip rate or improves calibration at negligible cost.

Drop if:

- conditional correction is near the 4-6% examples discussed in the conversation;
- severe JPEG/noise causes harmful confident errors the router cannot suppress;
- its preprocessing destroys throughput or reproducibility;
- gains disappear under source-level bootstrap uncertainty.

### Mild self-probes

Keep only if probe features improve held-out reliability, worst-group performance, or risk-coverage beyond logits/disagreement/quality.

Drop or reduce probes if:

- improvement is under ~1 point and within noise;
- common-path latency rises by more than ~25% without clear benefit;
- probe instability correlates with class shortcuts rather than correctness;
- probes make the UI slower or brittle.

Try one probe at a time before three.

### MLP router

Use logistic regression instead if the MLP does not beat it meaningfully. Complexity is not innovation by itself.

Kill the router story if it cannot beat:

- strongest single expert;
- calibrated fixed-weight/logistic stacking;
- at least one headline robustness outcome.

### Smooth worst-group loss

Keep if it improves worst fake recall/accuracy without excessive clean/FPR regression.

Drop if:

- clean balanced accuracy falls more than 1 point without at least a 2-point worst-group gain;
- batch group estimates are too sparse/unstable;
- the same benefit comes from balanced sampling alone.

### Consistency loss

Drop immediately if it:

- suppresses useful expert diversity;
- hurts calibration;
- costs more than 1 clean point without at least 2 worst-group points;
- adds no gain beyond worst-group training.

Consistency remains an ablation, never a deadline blocker.

### WaRPAD rescue

Keep if selective invocation:

- corrects a meaningful portion of common-path mistakes;
- has low rescue-harm rate;
- improves worst fake recall, selective risk, or flips by ~2+ points;
- remains within latency budget with a reasonable rescue rate.

Drop or substitute RIGID if:

- integration takes more than 6 critical-path hours;
- it corrects fewer errors than it introduces;
- rescue rate exceeds roughly 40-50%, eliminating the adaptive-compute advantage;
- selective use performs no better than simple always-on fusion at matched compute.

### Fine-tuning

Stop if it improves in-domain transformations but hurts held-out generators or external data. Never allow fine-tuning to delay full evaluation.

### DEAR-inspired feature gate

Attempt only after the full simple cascade works. Kill after half a day without a clear, reproducible gain. Do not call it DEAR unless the actual method is implemented.

### Extra datasets

Do not download large datasets merely to make the project look comprehensive. Stop if disk/bandwidth threatens the working pipeline. A well-curated 40k-60k router corpus is sufficient for the initial design.

## System-level failure risks

### 1. Semantic shortcut learning

Risk: fake and real sources differ in content, resolution, or file format, so the router learns dataset identity.

Mitigation:

- matched semantic classes where possible;
- grouped source splits;
- compression/format alignment checks;
- external source-held-out tests;
- audit feature importance and simple source classifiers.

### 2. Transformation shortcut learning

Risk: router learns “JPEG means fake” because transformed class proportions differ.

Mitigation:

- apply every transformation to both real and fake images;
- balance class x transform groups;
- inspect real JPEG FPR and fake JPEG recall separately.

### 3. Leakage from organizer WildFake

Risk: direct/near duplicate enters training or thresholds are repeatedly tuned on the reference set.

Mitigation:

- exact/perceptual denylist;
- sealed evaluation after freeze;
- signed manifest and documented access.

### 4. Miscalibrated heterogeneous scores

Risk: one expert's logit scale dominates fusion without being more accurate.

Mitigation:

- inspect score distributions;
- use per-expert calibration if necessary;
- fuse logits with regularization;
- compare with rank/probability alternatives.

### 5. Stable but wrong predictions

Risk: self-probes are stable, so reliability is high despite systematic error.

Mitigation:

- never equate stability with correctness;
- include supervised correctness targets, disagreement, source diversity, and quality;
- evaluate risk-coverage on held-out generators.

### 6. LOTA destroyed by encoding

Risk: low-bit evidence is already altered by image delivery, decoding, or JPEG.

Mitigation:

- preserve original bytes/decode path;
- evaluate by source format and JPEG severity;
- allow router to suppress LOTA;
- delete LOTA if complementarity is not real.

### 7. Rescue latency explosion

Risk: most images are escalated, so the cascade is effectively always-on WaRPAD plus overhead.

Mitigation:

- report rescue rate;
- optimize trigger at a fixed compute budget;
- compare always-on WaRPAD;
- simplify if adaptive compute is not achieved.

### 8. Confidence language overclaims

Risk: users read `91%` as probability the image was generated by AI in the real world.

Mitigation:

- label as calibrated model score under the evaluation distribution;
- show reliability separately;
- allow uncertainty;
- include limitations and no-provenance disclaimer.

### 9. Licensing/repository risk

Risk: model, data, or weights cannot be redistributed or used in the demo.

Mitigation:

- build license inventory before integration;
- link downloads rather than redistribute when required;
- use only licensed demo assets;
- document checkpoint terms.

### 10. Hidden final distribution mismatch

Risk: hidden data includes novel generators, chained transforms, screenshots, edits, or domains absent from development.

Mitigation:

- source-held-out and modern-generator external tests;
- RRDataset/social-transmission test if feasible;
- abstention for out-of-reliable-region inputs;
- avoid tuning to a single official reference distribution.

## Official protocol questions

Ask in the webinar or organizer channel:

1. Is `<2B parameters` per component, total loaded parameters, or the largest single model?
2. Which subset of augmentations may be judged, and are severities exactly as listed?
3. Which JPEG encoder/chroma-subsampling settings will be used?
4. Which resize interpolation and order are used for downscale/upscale?
5. Is Gaussian noise sigma measured in a `[0,1]` range?
6. Is color jitter applied one property at a time, randomly, or jointly?
7. Does “crop 80%” mean 80% of width/height or 80% of area?
8. Are transformations single or chained?
9. Is the hidden metric accuracy, balanced accuracy, AP/AUROC, or another score?
10. Are abstentions allowed, and how are they scored?
11. Does the official reference subset ship as exact files whose hashes can be denylisted?
12. Can other non-overlapping portions of WildFake be used for training, assuming contamination safeguards?
13. Are commercial API detectors allowed, or must all inference be local/publicly reproducible?

Until answered, state assumptions explicitly and keep the evaluation code parameterized.

## Research questions to answer by Day 2

- Does Community Forensics or OmniAID win on worst fake recall?
- Does LOTA correct primary failures, especially blur/crop, without dangerous JPEG errors?
- Which transformation creates the largest fake-to-real flip rate?
- Does probability disagreement predict error?
- Does primary self-probe instability predict error after conditioning on transform severity?
- Can a logistic stacker beat static average?

## Research questions to answer by Day 4

- Does the MLP router beat logistic stacking?
- Does the smooth worst-group term improve severe fake recall?
- Does WaRPAD correct uncertainty-enriched common-path failures?
- What rescue threshold gives the best accuracy/latency trade-off?
- Does calibrated reliability produce a monotonic risk-coverage curve?
- Is an `UNCERTAIN` option useful at realistic coverage?

## Questions that can remain open after the hackathon

- publication-level novelty versus DACOM and other dynamic routing work;
- robustness to adaptive adversaries;
- partially edited image localization;
- video/audio extension;
- provenance metadata fusion such as C2PA;
- continual learning for new generators;
- production monitoring, fairness, policy thresholds, and appeal processes;
- cross-platform calibration under unknown prevalence.

## Definition of done

The project is done when:

- official constraints/deliverables are satisfied;
- the final configuration is frozen and reproducible;
- a strong single baseline exists;
- every retained component has an ablation;
- clean and complete transformation results are reported;
- fake recall, FPR, drops, worst case, and flips are present;
- confidence/reliability claims have calibration evidence;
- official reference data was not used for fitting;
- one or more meaningful robustness gains are measured;
- limitations, including severe JPEG if unresolved, are explicit;
- the public demo works end to end.

