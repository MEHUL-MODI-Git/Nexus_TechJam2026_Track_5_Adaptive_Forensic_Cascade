# SPEC — router repair (B-018 / A-024 ACK), bounded implementation contract

> Author: Claude (heavy owner, training workstream). **Implementation is delegated to a lighter
> model under the model-economy rule; Claude reviews the diff adversarially and runs verification
> before landing.** Codex re-reviews at the 2R.1 gate.
> Scope: `src/router/{model.py,train.py}`, `tests/test_router.py`, `tests/test_router_train.py`,
> plus one new `tests/test_router_checkpoint.py`. **Do not touch** `src/eval/`, `src/app/`,
> `src/router/feature_cache.py`, `src/router/calibration.py`, `src/router/features.py`,
> `src/pipeline/`, or any file owned by Codex.
>
> Every numbered item below is a required change with its own acceptance test. Implement exactly
> what is written. If an instruction appears to conflict with existing code, STOP and report the
> conflict rather than choosing an interpretation.

## 0. Constants to add (top of `src/router/train.py`)

```python
CHECKPOINT_SCHEMA = "router-checkpoint.v2"      # bumped: payload gained provenance fields
LOGIT_PROB_TOLERANCE = 1e-4    # |sigmoid(raw_logit) - p_fake| must not exceed this
MIN_MEANINGFUL_DELTA = 0.02    # doc 05/08 kill gate: 2 points of worst-family fake recall
VALID_SPLITS = ("train", "dev")
```

## 1. T1 — validate every field the trainer CONSUMES, and abort on malformed rows

`validate_cache_rows` currently checks `p_fake` while `build_batch` consumes `raw_logit`, and a
missing `raw_logit` silently becomes `0.0` for an `ok: true` expert.

For each row, for each expert id in `expert_ids`, take `block = (row.get("experts") or {}).get(eid)`.

- If `block` is absent or `block.get("ok")` is exactly `False` → the expert is unavailable for that
  row. Do not validate its scores.
- `ok` must be a real `bool` (`isinstance(block["ok"], bool)`). Anything else (string `"true"`,
  `1`, `None`) → `raise ValueError` naming the row's `source_id`, `condition_id` and expert id.
- If `ok is True`, ALL of the following must hold or `raise ValueError` (never a silent drop):
  - `p_fake` is present, a real number, finite, and `0.0 <= p_fake <= 1.0`;
  - `raw_logit` is present, a real number, and finite;
  - `abs(1/(1+exp(-raw_logit)) - p_fake) <= LOGIT_PROB_TOLERANCE`. Compute the sigmoid in
    `float` with an overflow-safe expression (use `math.exp` on the negative of `abs`, or
    `float(1/(1+math.exp(-x)))` guarded for `|x| > 700`).
  The error message must state which field failed and its value.
- Rows where EVERY expert is unavailable stay a counted exclusion
  (`dropped_all_experts_unavailable`), unchanged. That is a real runtime outcome, not corruption.
- Delete the `dropped_invalid_scores` DROP path: invalid scores now abort. Keep the key in the
  returned report with value `0` **only if** removing it breaks an existing artifact consumer;
  otherwise remove the key and the corresponding `document` field
  `rows_dropped_invalid_scores`. Search the repo before deciding, and report which you did.
- `build_batch` must no longer use `float(block.get("raw_logit", 0.0))`. For an available expert
  read `float(block["raw_logit"])` directly (a `KeyError` here is now impossible because
  validation ran). Unavailable experts keep the `0.0` placeholder with `available=False` — that
  value is masked out and never reaches the fusion.

Acceptance tests (`tests/test_router_train.py`):
- `test_nan_raw_logit_is_rejected` — an `ok: true` block with valid `p_fake` and
  `raw_logit=float("nan")` raises `ValueError`, and the message mentions `raw_logit`.
- `test_missing_raw_logit_is_rejected` — `ok: true` block with no `raw_logit` key raises.
- `test_logit_probability_mismatch_is_rejected` — `p_fake=0.9`, `raw_logit=0.0` raises.
- `test_consistent_logit_and_probability_pass` — `raw_logit=1.0`,
  `p_fake=1/(1+exp(-1.0))` validates cleanly.
- `test_non_bool_ok_is_rejected` — `"ok": "true"` raises.
- Update `test_non_finite_score_is_dropped` → `test_non_finite_score_is_rejected` (now raises).

## 2. T2 — split, source-label, and cache-key integrity are fail-CLOSED

In `validate_cache_rows`, before the existing overlap check:

- Every row must have `dataset_split` in `VALID_SPLITS`. Anything else (including missing,
  `"test"`, `"TRAIN"`) → `raise ValueError` naming the offending value.
- Every row must carry a non-empty string `cache_key` matching `^[0-9a-f]{16,64}$`
  (the canonical digest produced by `feature_cache.py` — verify the actual format there and use
  it; if it is not a hex digest, use the exact format that module emits and say so in the diff
  note). An absent or malformed key → `raise ValueError`.
- A `source_id` must have exactly one `label` across all its rows → otherwise `raise ValueError`
  listing the source id and both labels.
- A `source_id` must have exactly one `dataset_split` across all its rows → otherwise
  `raise ValueError` (this subsumes and strengthens the existing train/dev overlap check; keep
  the overlap check and its test as well).
- Required top-level fields on every row: `source_id` (non-empty str), `condition_id`, `label`,
  `dataset_split`, `cache_key`, `experts`. Missing → `raise ValueError` naming the field.

In `run_ladder`, after splitting and BEFORE training, assert dev sufficiency:
- dev rows must contain both labels 0 and 1 → else `raise ValueError`;
- dev rows must contain fake rows for all six `TRANSFORM_FAMILIES` → else `raise ValueError`
  naming the missing families. (This is the same guarantee `worst_family_recall(require_all=True)`
  gives, but raised up front with a clearer message before minutes of training are spent.)

Acceptance tests:
- `test_unknown_split_is_rejected`, `test_missing_cache_key_is_rejected`,
  `test_inconsistent_source_label_is_rejected`, `test_source_split_must_be_consistent`,
  `test_missing_required_field_is_rejected`,
  `test_dev_missing_a_family_is_rejected_before_training`,
  `test_dev_with_one_class_is_rejected`.

## 3. T3 — delete the false degeneracy claim; measure the change instead

The learned bias head means a one-expert router CAN change the score. The artifact's claim that
every rung "necessarily emits the primary expert's score unchanged" is false and must go.

- Rename `fusion_degenerate` / the document field `fusion_comparison_degenerate` to
  **`fusion_weight_degenerate`** (`len(expert_ids) < 2`). Its documented meaning is now narrow:
  *the fusion WEIGHTS are degenerate (a softmax over one available slot is 1.0)*. It says nothing
  about the fused score.
- Add document field `single_expert_learned_correction: bool` = `fusion_weight_degenerate`.
  When true, the honest description of rungs 3+ is a **single-expert learned correction** over the
  primary logit, not fusion.
- For every rung record, add a measured field
  `max_abs_p_fake_change_vs_static: float` — the max over dev rows of
  `|rung.p_fake - static_average.p_fake|`. Compute it in `run_ladder` after all rungs are trained
  (train `static_average` first and keep its dev `p_fake` array). `static_average`'s own value is
  exactly `0.0`.
- `router_earns_its_complexity` must NO LONGER be suppressed by `fusion_weight_degenerate`
  (see §4). Suppressing a measured score change is what the review called scientifically false.
- Rewrite `verdict_note` for the degenerate case to say exactly this (wording may be tightened but
  not weakened): with one expert the fusion weights are 1.0 by construction, so rungs differ only
  through the learned bias/quality correction and the reliability head; the comparison is therefore
  a test of **single-expert learned correction**, not of fusion; a second expert is required before
  any conclusion about fusion is drawn.
- Replace `test_single_expert_fusion_is_flagged_as_vacuous` with
  `test_single_expert_reports_weight_degeneracy_not_score_degeneracy` (asserts
  `fusion_weight_degenerate is True`, `single_expert_learned_correction is True`, and that the
  document contains no claim of unchanged scores) and replace
  `test_degenerate_flag_overrides_a_spurious_improvement` with
  `test_one_expert_score_change_is_measured_not_suppressed` (asserts every rung record has a
  finite `max_abs_p_fake_change_vs_static` and that the static rung's is 0.0).

## 4. Kill gate — a positive delta is not a win

Replace `"router_earns_its_complexity": bool(delta > 0.0) and not fusion_degenerate` with three
explicit fields:

```python
meaningful = bool(delta >= MIN_MEANINGFUL_DELTA)
separated  = bool(best["dev_worst_family_ci95"][0] > baseline["dev_worst_family_ci95"][1])
```
- `"improvement_is_meaningful": meaningful`  (>= 2 points)
- `"improvement_is_outside_uncertainty": separated`  (best CI95 low above baseline CI95 high)
- `"router_earns_its_complexity": bool(meaningful or separated)`
- `"kill_gate": {"min_meaningful_delta": MIN_MEANINGFUL_DELTA, "rule": "delta >= 2 points OR
  best CI95 low above baseline CI95 high, subject to the clean constraints"}`

Acceptance tests: `test_tiny_positive_delta_does_not_earn_complexity` (construct a document by
calling `run_ladder` on a fixture where the delta is < 0.02 and the CIs overlap; assert
`router_earns_its_complexity is False` while `improvement_over_baseline > 0`) and
`test_kill_gate_fields_are_present`.

## 5. BCE with logits (doc 04), for both heads

- `FusionOutput` gains a field `reliability_logit: torch.Tensor | None` placed AFTER
  `reliability`. Every rung that has a reliability head returns the pre-sigmoid value there;
  `StaticAverageFusion` returns `None` for both.
- In `train_rung`, replace the class loss with
  `torch.nn.functional.binary_cross_entropy_with_logits(out.fused_logit, batch.labels,
  reduction="none")`. Remove the `clamp(1e-6, 1-1e-6)` probability path.
- The reliability term (when fitted, see §6) becomes
  `binary_cross_entropy_with_logits(out.reliability_logit, target)` where `target` is unchanged
  (`reliability_targets(out.p_fake.detach(), batch.labels, threshold)`).
- Acceptance test `test_class_loss_uses_logits` — assert `train_rung` runs and that
  `FusionOutput.reliability_logit` satisfies `sigmoid(reliability_logit) == reliability`
  (atol 1e-6) for `LogisticRouter` and `MLPRouter`.

## 6. R22 — two-stage ordering, enforced, not warned about

A reliability head trained against a PLACEHOLDER operating point learns a target that changes
meaning once the real threshold is fitted. A warning does not prevent that.

- Add a module-level helper:
  ```python
  def threshold_is_frozen(provenance: str) -> bool:
      """True only for a validated, fitted operating-threshold artifact."""
      p = (provenance or "").strip()
      return bool(p) and not p.upper().startswith(("PLACEHOLDER", "UNSPECIFIED")) \
          and p.lower() != "unspecified"
  ```
- `train_rung` gains keyword `fit_reliability: bool = True`. When `False`:
  - exclude every parameter whose name starts with `reliability_head` from the optimizer
    (use `model.named_parameters()`);
  - skip the reliability loss term entirely;
  - record `"reliability_head_fitted": False` in the rung record.
  When `True`, record `True`. Keep the existing `reliability_head` boolean (head exists) as is.
- `run_ladder` computes `fit_reliability = threshold_is_frozen(threshold_provenance)` and passes
  it to every rung. Add document fields `"reliability_fitted": fit_reliability` and
  `"reliability_stage_note"`: when not fitted, the text must state that reliability/abstention is
  stage 2 and is deliberately NOT fitted until the class threshold is frozen (Codex R22), so no
  stale target is trained or saved.
- `save_checkpoint` must **refuse** (`raise ValueError`) to persist a checkpoint whose
  `reliability_head_fitted` is True while `threshold_is_frozen(threshold_provenance)` is False.
- Keep `threshold_provenance_warning` as an additional field.
- Acceptance tests: `test_placeholder_threshold_does_not_fit_reliability` (document says
  `reliability_fitted is False`, every rung record says `reliability_head_fitted is False`),
  `test_frozen_threshold_provenance_fits_reliability`, and
  `test_checkpoint_refuses_stale_reliability`.

## 7. Missing baseline rungs (doc 05 ladder)

Add two parameter-free/near-free baselines to `src/router/model.py` and to the ladder:

- `class ProbabilityMeanFusion(nn.Module)` — mean of `sigmoid(expert_logit)` over AVAILABLE
  experts, then `fused_logit = torch.logit(p.clamp(1e-6, 1 - 1e-6))`. Zero parameters. Rows with
  no available expert emit `p = 0.0` weights exactly as `_masked_weights` does today, and their
  `p_fake` must be `0.5` (logit 0) rather than NaN — assert this in a test.
- `class FixedWeightFusion(nn.Module)` — fixed, non-learned weight vector over experts, applied
  in LOGIT space with availability masking and renormalisation (reuse `_masked_weights` by
  feeding it `log(w)` broadcast to the batch, or renormalise the fixed weights over the available
  mask directly — either is acceptable, but weights for unavailable experts must be exactly 0 and
  the available ones must sum to 1). Registered as a buffer, not a parameter.
- Trainer support: `train_rung` accepts rung names `"probability_mean"` and `"fixed_weights"`.
  For `"fixed_weights"`, the weight vector is chosen by a coarse grid search on the **TRAIN split
  only** (never dev): for `n_experts == 1` the vector is `[1.0]`; for `n_experts >= 2` search the
  simplex in steps of 0.1 and keep the vector maximising train worst-family fake recall
  (`worst_family_recall(..., require_all=False)` on train). Record the chosen vector in the rung
  record as `"fixed_weights": [...]` and record `"fixed_weights_selected_on": "train split only"`.
- Ladder order becomes: `static_average`, `probability_mean`, `fixed_weights`, `logistic`,
  `mlp`, `mlp` (worst-group). `static_average` remains THE baseline for delta and the clean
  constraints.
- Acceptance tests: `test_probability_mean_is_the_mean_of_probabilities` (two experts, hand
  computed), `test_probability_mean_no_available_expert_is_half`,
  `test_fixed_weights_are_selected_on_train_only` (the record states it and the rung has zero
  trainable parameters), `test_ladder_contains_all_six_rungs`.

## 8. T4 — a real, fail-closed, atomic checkpoint with provenance

In `src/router/train.py`:

- `save_checkpoint(document, path, threshold, *, cache_artifact_sha256: str | None = None)`:
  - payload gains: `"use_worst_group_loss"` (of the selected rung), `"n_parameters"`,
    `"feature_names"` (already inside `feature_spec`; keep both), `"hyperparameters"`
    (`{"epochs", "lr", "seed", "hidden", "hidden2", "dropout", "lambda_worst", "temperature"}`
    — read the actual defaults used, do not invent values; if a rung did not use one, omit it),
    `"reliability_head_fitted"`, `"cache_artifact_sha256"`, `"code_revision"`
    (`git rev-parse HEAD` via `subprocess` with a 5-second timeout, `None` on any failure — never
    raise), `"selection"` (`{"best_rung", "improvement_over_baseline",
    "router_earns_its_complexity", "improvement_is_meaningful",
    "improvement_is_outside_uncertainty"}`).
  - Save ATOMICALLY: `torch.save` to `path.with_suffix(path.suffix + ".tmp")` then
    `os.replace(tmp, path)`.
  - The §6 stale-reliability refusal happens BEFORE any bytes are written.
- New `load_checkpoint(path) -> LoadedRouter` where
  `@dataclass LoadedRouter: model, spec: FeatureSpec, standardizer: Standardizer, threshold: float,
  payload: dict`:
  - `torch.load(path, map_location="cpu", weights_only=True)`. Fail closed: if that raises, do NOT
    retry with `weights_only=False`; re-raise with a message saying the checkpoint is untrusted.
  - Validate `schema_version == CHECKPOINT_SCHEMA` → else `ValueError` naming both versions.
  - Validate presence of every required key → else `ValueError` naming the missing key.
  - Reconstruct the module by `rung` name using `feature_spec["dim"]` and
    `len(expert_order)`; `load_state_dict(..., strict=True)`; `model.eval()`.
  - Rebuild the `Standardizer` from its json dict and the `FeatureSpec` from `expert_ids`;
    if `spec.dim != feature_spec["dim"]` or `spec.names != feature_spec["feature_names"]`
    → `ValueError` (the code has drifted from the checkpoint).
- New `tests/test_router_checkpoint.py`:
  - `test_save_load_prediction_parity` — build a fixture cache, `run_ladder`, `save_checkpoint`,
    `load_checkpoint`, then run the loaded model on the SAME dev batch tensors and assert
    `torch.allclose(p_loaded, p_original, atol=1e-6)`. This is the deployability test; it must
    exercise the real ladder output, not a hand-built module.
  - `test_load_rejects_wrong_schema_version`, `test_load_rejects_missing_key`,
    `test_load_rejects_feature_dim_drift`, `test_save_is_atomic_no_tmp_left_behind`,
    `test_checkpoint_records_provenance` (asserts the new keys exist and
    `use_worst_group_loss` matches the selected rung's record).

## 9. Test fix — the learnability test must use the logit API

`tests/test_router.py::test_router_can_learn_to_beat_static_average` builds probabilities and
passes them as `expert_logits`. Convert with `torch.logit(p.clamp(1e-6, 1 - 1e-6))` so the test
exercises the real fusion space. The test's assertion (routed beats static average) must still
pass; if it does not after the conversion, STOP and report — do not weaken the assertion.

## 10. Ruff

`ruff check --fix` the touched files, then resolve the remainder by hand (unused imports, import
order, quoted annotations, the duplicated `import torch` inside
`tests/test_router_train.py::test_checkpoint_is_deployable`). Do not reformat unrelated code.

## 11. Definition of done

1. `.venv/bin/python -m pytest tests/ -q` — full suite green, no skips introduced.
2. `.venv/bin/python -m ruff check src/router/ tests/test_router.py tests/test_router_train.py
   tests/test_router_checkpoint.py` — clean.
3. Report, in the final message: the pass count before and after, every file touched, every
   decision taken where the spec left a choice (§1 report-key question, §7 FixedWeight masking
   approach, §2 cache-key format), and anything you could not implement as written.
4. Do NOT commit, do NOT edit STATE/CHANGELOG/STATUS/CHANNEL — the heavy owner lands those.
