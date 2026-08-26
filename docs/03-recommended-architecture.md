# Recommended Architecture: Adaptive Forensic Cascade

> **Status: DECISION for implementation; individual expert slots remain conditional on Day-1/2 results.**

## System objective

Given image `x`, return:

- calibrated probability that it is AI-generated;
- decision: `REAL`, `AI-GENERATED`, or `UNCERTAIN`;
- separate reliability estimate;
- evidence summary showing expert agreement/stability and whether rescue was invoked;
- machine-readable diagnostics for evaluation.

The detector must remain useful when processing has weakened some forensic cues. It should avoid confident fake-to-real failures and spend more compute only when necessary.

## Architecture diagram

```text
                                  INPUT IMAGE x
                                       |
                         canonical decode / validation
                                       |
                  +--------------------+--------------------+
                  |                                         |
                  v                                         v
       PRIMARY GENERAL EXPERT                     CHEAP LOCAL EXPERT
       Community Forensics 384                         LOTA
       (OmniAID challenger)                    bit-plane / patch cue
                  |                                         |
          logit, embedding,                         logit, patch score,
          entropy/confidence                        optional local stats
                  |                                         |
                  +--------------------+--------------------+
                                       |
                       cheap image-quality descriptors
                       + expert confidence/disagreement
                       + primary mild self-probe stability
                                       |
                                       v
                         OUR RELIABILITY/FUSION ROUTER
                          weights + rescue probability
                                  /             \
                         reliable               uncertain
                            |                        |
                            |                        v
                            |               BEHAVIORAL RESCUE
                            |                     WaRPAD
                            |                 (RIGID backup)
                            |                        |
                            +-----------+------------+
                                        |
                                 final fused logit
                                        |
                          temperature + bias calibration
                                        |
                         +--------------+--------------+
                         |                             |
                 class probability              reliability score
                         |                             |
                         +--------------+--------------+
                                        |
                           REAL / AI / UNCERTAIN
                         + evidence and instability note
```

## Component contracts

Every expert adapter should implement the same logical interface:

```text
ExpertOutput
  expert_id
  raw_logit
  probability_after_expert_calibration
  optional_embedding
  optional_patch_scores
  inference_ms
  warnings
```

The adapter, not the router, is responsible for:

- exact model preprocessing;
- color mode and range;
- input size/cropping policy;
- checkpoint loading;
- mapping the model's class ordering to `P(fake)`;
- avoiding accidental softmax/sigmoid duplication;
- exposing deterministic inference;
- recording version, license, and parameter count.

## Step 1 - Canonical decode and validation

The input layer should:

1. decode using one documented library;
2. apply EXIF orientation;
3. convert to RGB while recording original mode;
4. reject or flag corrupted/unsupported files;
5. retain original width, height, format, bit depth if available, and file size;
6. never silently recompress the image before expert-specific preprocessing;
7. calculate a content hash for reproducibility.

This stage must not normalize away the forensic evidence. In particular, avoid a global resize before LOTA or other local experts unless their own official pipeline requires it.

## Step 2 - Primary general expert

### Default: Community Forensics 384

Outputs:

- raw fake logit `z_A`;
- calibrated primary probability `p_A`;
- optional penultimate embedding `h_A` if easily accessible;
- entropy `H_A`;
- runtime.

### Challenger: OmniAID

Use exactly one of Community Forensics or OmniAID as the production primary. Do not run both by default unless complementarity and latency justify it.

### Selection rule

Prefer the candidate that wins a multi-objective score emphasizing:

1. worst-family fake recall;
2. false-positive rate at the chosen operating point;
3. fake-to-real flip rate;
4. calibration;
5. inference reliability and latency.

A difference smaller than normal run-to-run or bootstrap uncertainty is not decisive. In a near tie, choose Community Forensics for simplicity.

## Step 3 - Cheap local expert

### Default candidate: LOTA

LOTA supplies a different low-level signal. Capture:

- raw logit `z_L`;
- calibrated probability `p_L`;
- selected-patch score/location if exposed;
- any normalization/bit-plane diagnostics;
- runtime.

### Important rule

The router must not contain hard-coded logic such as “if blur, trust LOTA.” Train from outcomes. LOTA's blur evidence is a reason to test it, not a production rule.

## Step 4 - Mild self-probes

The purpose of a self-probe is diagnostic:

> If a tiny, label-preserving change makes an expert's score swing, that expert's evidence may be locally fragile on this input.

Start with at most three deterministic probes on the primary expert:

1. mild JPEG, quality 92 or 90;
2. mild center crop, retaining 95-98%;
3. mild downscale/upscale, scale 0.90.

Optional fourth probe after ablation: Gaussian blur sigma 0.2-0.5.

Do not repeat the full Track 5 severity grid at inference time. That would multiply latency and convert evaluation transforms into expensive test-time augmentation.

For primary expert `A`, define features such as:

```text
scores_A = [p_A(x), p_A(T1(x)), p_A(T2(x)), p_A(T3(x))]

probe_mean_A       = mean(scores_A)
probe_std_A        = std(scores_A)
probe_range_A      = max(scores_A) - min(scores_A)
probe_max_delta_A  = max_i |p_A(x) - p_A(Ti(x))|
probe_flip_A       = any thresholded label differs
```

Stability is evidence about reliability, not a class label. A stable detector can be consistently wrong; that is why the router also needs expert scores, disagreement, class, quality, and supervised outcomes.

## Step 5 - Quality and disagreement features

Initial feature vector, intentionally small:

```text
z_A, p_A, entropy_A
z_L, p_L, entropy_L
|p_A - p_L|
sign agreement / threshold agreement
probe_mean_A, probe_std_A, probe_range_A, probe_max_delta_A, probe_flip_A
log(width), log(height), aspect_ratio, megapixels
blur proxy (e.g. variance of Laplacian, normalized)
JPEG/blockiness proxy
noise proxy
contrast and luminance statistics
```

Candidate features should be standardized using training data only. Record missing indicators rather than inventing values when an expert or descriptor fails.

Do not train a brittle classifier to declare an exact history such as “JPEG quality 50.” Real images can undergo chained transformations and may begin with unknown encoding. Quality descriptors are weak context, not ground truth.

## Step 6 - Reliability/fusion router

### Minimal architecture

```text
input: approximately 15-30 scalar features
  -> Linear(32)
  -> GELU
  -> Dropout(0.1)
  -> Linear(16)
  -> GELU
  -> two heads
       fusion weights over available experts
       rescue probability / reliability
```

This is likely tens of thousands of parameters or fewer.

### Fusion

For common-path logits `z_A` and `z_L`:

```text
[w_A, w_L] = softmax(router_weight_head(features))
z_common = w_A * z_A + w_L * z_L + b_router
```

Keep an alternative simple baseline:

```text
z_linear = beta_A*z_A + beta_L*z_L + beta_q*quality + b
```

If the MLP does not beat a regularized logistic stacker, use the simpler model.

### Rescue trigger

Let `r(x)` be rescue probability. Invoke WaRPAD when one or more validated conditions hold:

- `r(x) >= tau_rescue`;
- common-path predictive entropy exceeds a threshold;
- absolute expert disagreement is large;
- self-probe instability is high;
- the input is outside the validated quality region.

The final implementation should use one learned/validated policy, not a pile of ad hoc OR rules. Rules are useful only as a fallback while training data is prepared.

## Step 7 - Behavioral rescue

### Preferred: WaRPAD

Run WaRPAD only after escalation. Add its score `z_W`, runtime, and internal summary features if exposed.

Final fusion can be:

```text
z_rescued = gamma_A*z_A + gamma_L*z_L + gamma_W*z_W + b_rescue
```

where weights are a separate calibrated logistic model or the same router with a mask indicating WaRPAD availability.

### Backup: RIGID

If WaRPAD cannot be integrated reliably or is too slow, substitute RIGID. Do not silently change the behavioral method; report the final choice and rerun all ablations.

## Step 8 - Calibration

Class probability and reliability are separate outputs.

Calibrate the final class logit on a held-out development split:

```text
z_cal = (z_final + b) / T
p_fake = sigmoid(z_cal)
```

Fit `T > 0` and `b` without touching the official WildFake reference subset.

Calibrate the reliability head against an explicit target, for example whether the final prediction is correct at the chosen operating threshold. Evaluate reliability with ECE/Brier score and risk-coverage curves.

## Step 9 - Decision and abstention

Example operating policy:

```text
if reliability < tau_abstain:
    decision = UNCERTAIN
elif p_fake >= tau_fake:
    decision = AI-GENERATED
else:
    decision = REAL
```

Thresholds must be chosen on the development set under a documented objective. Possible objectives:

- maximize worst-family balanced accuracy with `FPR <= target`;
- maximize fake recall subject to acceptable FPR;
- minimize selective risk at a required coverage.

Do not choose thresholds separately on each test transformation; that leaks condition knowledge and inflates performance.

## Example outputs

### Reliable agreement

```text
Result: AI-GENERATED
Calibrated probability: 0.91
Detection reliability: HIGH

Primary evidence: high
Local forensic evidence: high
Expert agreement: high
Probe stability: stable
Behavioral rescue: not invoked
```

### Uncertain severe degradation

```text
Result: UNCERTAIN (leans AI-GENERATED)
Calibrated probability: 0.63
Detection reliability: LOW

Strong compression/blockiness detected
Primary evidence is unstable under mild probes
Experts disagree
Behavioral rescue invoked
Recommended action: manual review / no automatic moderation
```

These are display examples, not measured outputs.

## Failure behavior

The system should degrade safely:

- If LOTA fails to initialize, primary plus calibration can still run, but reliability must reflect the missing expert.
- If self-probes time out, fall back to score/disagreement/quality routing and emit a warning.
- If WaRPAD times out, return the common-path score only as low reliability or uncertain.
- If the image is too small for meaningful patches, avoid invented upsampling certainty; flag the condition.
- If all experts agree confidently but quality is far outside the development distribution, lower reliability rather than assume correctness.

## Latency budget

Measure, do not assume. Report:

- decode and quality-feature time;
- primary time;
- LOTA time;
- probe overhead;
- router/calibration time;
- WaRPAD rescue time;
- p50/p95 end-to-end common-path latency;
- p50/p95 rescued latency;
- percentage of images rescued;
- peak GPU/CPU memory.

Adaptive compute is only a practical advantage if the rescue rate is bounded and common-path latency is visibly lower than always-on WaRPAD.

## Architecture acceptance criteria

The final cascade should be accepted only if, on held-out sources:

- it improves worst-transformation fake recall over the selected primary;
- it does not create an unacceptable false-positive increase;
- it reduces fake-to-real transformation flip rate;
- it is at least as well calibrated after post-hoc calibration;
- its rescue pathway adds benefit at the chosen latency budget;
- its gains survive bootstrap confidence intervals or repeated seeds;
- every retained component has a positive ablation contribution.

If these conditions fail, submit the strongest simpler variant and explain the rejected ideas.

