# DegradePrint / Quality-Correction Pilot v1

> **Status:** JOINT EXPERIMENT PROTOCOL — A-023/A-024/B-020
>
> **Purpose:** Test the smallest protected hypotheses before spending the full cache budget.

## Preliminary result boundary

`scripts/diagnostics/degradeprint_probe.py` is reproducible diagnostic evidence only. Its input is
an unprotected obsolete cache and it has no untouched test, paired bootstrap, or generator-held-out
split. It may motivate this protocol but cannot select the submission model or support a result.

## Data and split

- Build the sealed SHA+pHash denylist first and validate every source before extraction.
- Draw a small balanced protected pilot from fitting sources only.
- Preserve every source and all its transformed views in one outer fold.
- Use three outer source folds. Within each outer-training fold, create a source-disjoint inner-dev
  split for calibration and the single threshold; evaluate only on the untouched outer fold.
- Aggregate out-of-fold predictions once, then use paired source-level bootstrap uncertainty.
- State explicitly that SID-Set exposes no generator identity, so this tests unseen images rather
  than unseen generators.

## Frozen inputs

Use CF-384, official outer corruptions, direct quality descriptors, and only the existing optional
inner probes: JPEG92, crop96%, resize90%. Do not add embedding extraction, blur probes, heavy experts,
or a neural stable branch in this pilot. `probe_flip` is derived after each fold's threshold is fixed.

## Classification arms

Compare on identical held-out rows:

- A: primary raw logit;
- A2: calibrated primary;
- B: regularized primary + quality correction;
- C: B + probe-response features;
- D: primary + probe-response features without quality.

Report worst-family fake recall, fake-to-real flips, clean BAcc/FPR, AUROC/AP and paired source
bootstrap deltas. One threshold per fitted method is fixed across every condition.

Keep quality correction only if B beats A2 by at least 2 points in bootstrap-mean worst-family fake
recall with the paired 95% interval above zero, or yields a comparably clear flip/selective-risk gain,
while clean BAcc regresses <=1 point and clean FPR rises <=1 point.

Keep the DegradePrint logit-response contribution only if C beats B under the same rules. Otherwise
park it. Embedding drift remains deferred; reconsider only after all gates are green and the schedule
has at least 24 h margin.

## Reliability/probe gate

Using out-of-fold class predictions, compare an error predictor using quality-only features against
quality + probe-response features. At minimum report error-prediction AUROC and selective risk at
fixed 80% coverage with paired source-bootstrap uncertainty.

Keep the three probes in the long cache only if the quality+probe model improves reliability or
selective risk with its paired 95% interval excluding no gain. Otherwise remove probes before the
long cache; they add three forward passes per view and have not earned that cost.

## Output

Write a versioned diagnostic artifact containing data/config/code/checkpoint hashes, fold source
IDs, feature lists, fitted hyperparameters, threshold artifacts, per-fold and aggregated metrics,
paired intervals, failure counts and the explicit `NOT_A_HEADLINE_RESULT` watermark. Codex reviews
the math; Claude owns fitting code and the keep/park proposal; both agents record the gate decision.
