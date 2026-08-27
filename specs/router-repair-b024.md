# SPEC — router repair round 2 (B-024 BLOCK), bounded implementation contract

> Author: Claude (heavy owner, training). Implementation delegated to a lighter model per the
> model-economy rule; Claude verifies adversarially. **Codex re-reviews; Claude may not self-clear
> this gate** (B-028).
> Scope: `src/router/train.py`, `tests/test_router_train.py`, `tests/test_router_checkpoint.py`.
> Do NOT touch `src/eval/`, `src/pipeline/`, `src/router/{features,calibration,feature_cache}.py`,
> `scripts/`, or `data/`. A 9-hour extraction is running: do not start GPU work.
> Every item is a required change with its own test. If an instruction conflicts with the code,
> STOP and report rather than choosing an interpretation.

## 1. Cache-key format must be the ACTUAL format (B-024 §1)

`_CACHE_KEY_RE` is `^[0-9a-f]{16,64}$`, which accepts a truncated key. `feature_cache.compute_cache_key`
emits a full sha256 hex digest. Tighten to **exactly 64 lowercase hex**: `^[0-9a-f]{64}$`.

Tests: `test_truncated_cache_key_is_rejected` (a 32-char key raises), and
`test_full_length_cache_key_is_accepted` (64 hex passes). Verify against a real key first —
`f5b1fa463f98727aa7b960ad425d84af0e4df9db3943b0cf9ff9d4b18b8ef47d` is one this repo produced.

## 2. Strict label and expert-container types (B-024 §2)

In `validate_cache_rows`, malformed containers currently degrade into silent
`dropped_all_experts_unavailable` exclusions, which is the exact failure mode T1 existed to end.

- `label` must be an `int` in `{0, 1}` and NOT a `bool` (`isinstance(v, bool)` must be rejected;
  note `True == 1` in Python, so a bool would otherwise pass). A float `1.0` must also raise.
- `row["experts"]` must be a `Mapping`. A list, string, or `None` must `raise ValueError` naming
  the `source_id` — never fall through to "no experts available".

Tests: `test_bool_label_is_rejected`, `test_float_label_is_rejected`,
`test_non_mapping_experts_is_rejected`, and confirm none of these becomes a silent exclusion by
asserting `dropped_all_experts_unavailable` is unchanged in a control case.

## 3. `None` threshold provenance must be controlled, not an AttributeError (B-024 §3)

`run_ladder`'s document builds `threshold_provenance.startswith("PLACEHOLDER")`, which raises
`AttributeError` when provenance is `None`. `threshold_is_frozen` already handles `None` safely;
the warning path does not.

Normalise once at the top of `run_ladder`: treat `None` as the string `"unspecified"` and use that
everywhere downstream, so a missing provenance is an unfrozen threshold rather than a crash.

Tests: `test_none_threshold_provenance_does_not_crash` (asserts `run_ladder` returns a document,
`reliability_fitted is False`, and provenance is recorded as `"unspecified"`).

## 4. `load_checkpoint` must validate everything it claims to (B-024 §4)

Mutated checkpoints currently load. Extend `load_checkpoint` to require and cross-check:

- every v2 provenance/selection field present in `save_checkpoint`'s payload
  (`use_worst_group_loss`, `n_parameters`, `hyperparameters`, `reliability_head_fitted`,
  `cache_artifact_sha256`, `code_revision`, `selection`) — missing any raises `ValueError` naming it;
- `selection` must contain `best_rung`, `improvement_over_baseline`, `router_earns_its_complexity`,
  `improvement_is_meaningful`, `improvement_is_outside_uncertainty`;
- `expert_order` equals `feature_spec["expert_ids"]`;
- top-level `feature_names` equals `feature_spec["feature_names"]`;
- standardizer `schema_version`, `feature_names` and vector lengths agree with the rebuilt
  `FeatureSpec`, and `mean`/`scale` are all finite with `scale > 0`;
- `threshold` is a finite float in `[0, 1]`;
- `rung` is one of the known ladder rung names.

Each failure raises `ValueError` naming the specific field. Keep the existing schema-version and
feature-dim-drift checks.

Tests in `tests/test_router_checkpoint.py`, each mutating ONE field of a genuine saved checkpoint and
asserting a `ValueError` that names it: `test_load_rejects_missing_provenance_field`,
`test_load_rejects_missing_selection_field`, `test_load_rejects_expert_order_mismatch`,
`test_load_rejects_feature_names_mismatch`, `test_load_rejects_standardizer_mismatch`,
`test_load_rejects_non_finite_standardizer`, `test_load_rejects_out_of_range_threshold`,
`test_load_rejects_unknown_rung`. The existing round-trip parity test must still pass unchanged.

## 5. (Claude handles item 5 directly — do not touch `results/`.)

## 6. Definition of done

1. `.venv/bin/python -m pytest tests/ -q` fully green; report before/after counts (currently 671).
2. `.venv/bin/python -m ruff check src/router/train.py tests/test_router_train.py
   tests/test_router_checkpoint.py` clean.
3. Report every decision where the spec left a choice, and anything not implementable as written.
4. Do NOT commit, do NOT edit STATE/CHANGELOG/STATUS/CHANNEL.
