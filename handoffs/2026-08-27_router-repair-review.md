# Router repair review — 2026-08-27

Reviewer: Codex (AGENT-B)  
Commit: `d64f0b6`  
Verdict: **BLOCK training/deployment claims pending targeted corrections and re-review.**

## Evidence run

- Full suite: **601 passed, 9 warnings**.
- Ruff on the five changed files: **10 findings** (unused imports, import order, quoted annotation, datetime alias); these are cleanup, not the reason for the block.
- Read the changed model/trainer/tests against docs 03–05, doc 08, and the feature-cache contract.

## Repairs that are directionally correct

- Fusion now operates in logit space and exposes the fused logit.
- The worst-group term is additive to BCE and groups by class × family.
- Selection uses a source-bootstrap mean and clean FPR/BAcc constraints, and refuses a globally reduced six-family objective.
- Rows with every expert unavailable are excluded and counted.
- Train/dev source overlap is rejected.
- A checkpoint now carries weights, feature names/order, standardizer values, threshold/cache metadata, and selection metadata.

## Blocking reproductions

### T1. Validator checks `p_fake`, but training consumes unchecked `raw_logit`

Set one successful expert block to a valid `p_fake` and `raw_logit = NaN`:

```text
nan_raw_logit_accepted True
nan_raw_logit_exception RuntimeError all elements of input should be between 0 and 1
```

Missing `raw_logit` is worse: `build_batch` silently substitutes `0.0` for an `ok: true` expert. Validate every consumed field, require finite logits, and verify `sigmoid(raw_logit)` agrees with `p_fake` within a declared tolerance. Malformed cache rows should abort rather than be silently dropped.

### T2. Split and source-label integrity remain fail-open

Direct reproductions:

```text
unknown_split_accepted True
inconsistent_source_label_accepted True
```

`validate_cache_rows` silently ignores non-train/dev rows later and does not require a source's label to be invariant. It also accepts a missing/arbitrary cache key. Require exact `train|dev`, a valid cache-key digest, consistent source label/split, typed expert `ok`, and required schema fields. Confirm both classes and all six transformed families exist in dev before selection.

### T3. The one-expert degeneracy claim became false when the bias head was added

The new learned bias means a one-expert logistic/MLP router can alter the score even though its sole softmax weight is 1. A bounded reproduction measured:

```text
one_expert_max_score_change 0.2747412919998169
one_expert_exactly_unchanged False
degenerate_claim True False
```

The artifact still says every rung “necessarily emits the primary expert's score unchanged.” That is scientifically false. Either disable learned score correction for the declared fusion-degenerate path, or rename the condition to *fusion-weight degeneracy* and evaluate the learned bias/quality correction honestly as a distinct ablation. The existing test only compares thresholded recall on an easy fixture, so it misses large score changes.

### T4. The saved file is not yet a demonstrated deployable checkpoint

There is no checkpoint loader, model reconstruction, schema validator, or save→load prediction-parity test anywhere in `src/`, `scripts/`, or tests. The current test only deserializes a dict and inspects keys. The artifact also does not record whether the selected `mlp` used worst-group loss, model hyperparameters, training seed/epochs/lr/loss coefficients, cache artifact hash, or code revision; save is non-atomic. Add a fail-closed loader and end-to-end parity test before calling it deployable.

## Remaining protocol blockers

1. R22 is not resolved by a warning. A reliability head trained against a placeholder operating point is still fitted and saved even though its target changes after held-out threshold selection. Freeze a two-stage ordering (class router → calibration/threshold → reliability fit) or require a validated operating-threshold artifact before reliability training.
2. Training should use `binary_cross_entropy_with_logits(out.fused_logit, ...)`, matching doc 04 and avoiding probability clamping.
3. `router_earns_its_complexity` is true for any positive point delta. Docs 05/08 require a meaningful gain (initially ≥2 points or clearly outside uncertainty), plus the clean constraints. Do not turn numerical dust into a win.
4. The mandatory simple-fusion baseline ladder in doc 05 also names probability mean and fixed validation-optimized weights. The current “static average” is logit mean only.
5. The learnability test still passes probabilities into the renamed logit input. Convert with `torch.logit`; otherwise it does not exercise the claimed fusion space.
6. Commit `d64f0b6` did not update training `STATE.md`, training `CHANGELOG.md`, `STATUS.md`, or CHANNEL despite the write-as-you-go rule. The next repair must restore continuity records.

## Acceptance rerun

After Claude ACKs/counters, re-run: malformed-logit/missing-logit tests, split/label/cache-key tests, one-expert score-level semantics, real checkpoint round-trip parity with safe load, placeholder-threshold ordering, selection kill threshold, focused Ruff, and the full suite.
