# Phase-1 input artifact audit (task 1.1)

Mechanical, read-only audit of `results/grid-smoke-v1/prediction_rows.jsonl` against `specs/phase0-eval.md` and the exact official condition table in `docs/05-evaluation-and-ablations.md`. No metrics or threshold decisions are calculated here.

## Files and identity

- Rows: 8,000 total; one `method_id` (`commfor_384`), one `run_id` (`grid-20260826T151856Z`), 400 unique `source_id`s, and 8,000 unique `sample_id`s.
- Run manifest reports `n_sources=400`, `rows_written=8000`, `decode_failures=0`, and `expert_failures=0`; these agree with the row file for row/source counts.
- SHA-256 `prediction_rows.jsonl`: `ebf8b842ce9eb005b146a4cda3faf1fcad543a6d39f6eacd6da0da3af2a75e60`.
- SHA-256 `run_manifest.json`: `90a5985d60137d1b100d2123f765601f1a01da22bd4b2c7b68084ee8e4724e68`.

## Classes, conditions, and pairing

Class counts by source group (each group has 200 sources × 20 views): `SID-Set-full-synthetic`: label 1 = 4,000; `COCO-train2017`: label 0 = 4,000. Overall labels are 4,000 real and 4,000 AI-generated. Dataset fields are `SID-Set` (4,000 rows) and `COCO` (4,000 rows).

All 20 official IDs are present, with identical per-condition counts: 200 label-0 and 200 label-1 for each of: `clean`, `jpeg_q90`, `jpeg_q70`, `jpeg_q50`, `jpeg_q30`, `blur_s0.5`, `blur_s1.0`, `blur_s2.0`, `resize_0.5`, `resize_0.25`, `noise_s0.02`, `noise_s0.05`, `noise_s0.10`, `bright_-20`, `bright_+20`, `contrast_-20`, `contrast_+20`, `saturation_-20`, `saturation_+20`, `crop_0.8`. No unknown condition IDs were found. Every source has exactly 20 conditions, including `clean`; no missing clean views.

Duplicate key `(method_id, source_id, condition_id)`: 0 duplicate keys (8,000 unique keys; maximum multiplicity 1).

Across views of each source, no inconsistent values were found for `label`, `dataset`, or `source_group` (also no inconsistencies for `run_id` or `method_id`).

## Score validation

No invalid, non-finite, or out-of-range `p_fake` values. All 8,000 are JSON floats; observed range is `[0.000000073253172096, 0.9999982118606567]`.

## Schema presence and observed types

Every row has the following fields, with these observed JSON types: `schema_version` string; `run_id` string; `method_id` string; `sample_id` string; `source_id` string; `image_path` string; `content_sha256` string; `label` integer; `dataset` string; `source_group` string; `condition_id` string; `family` string; `p_fake` float; `raw_logit` float; `reliability` null; `decision` null; `rescue_invoked` null; `inference_ms` float; `warnings` list; `pipeline_version` string.

The row artifact therefore includes all core input-contract fields except the optional structured `expert_failures` field (it is absent rather than null), and has extra `family`, `raw_logit`, and `pipeline_version` fields. The observed nulls for reliability/decision/rescue are consistent with an unfitted single-expert smoke run; this audit does not interpret them as metric availability.

## Frozen threshold artifact

No locally present frozen threshold artifact was found. `configs/predict.yaml` references only `threshold: 0.5` with provenance `PLACEHOLDER-uncalibrated-phase0`; it does not contain the required frozen artifact metadata (value, objective, dev-manifest hash, config hash, fitting code version, timestamp). Thus the input rows are not accompanied by a local frozen threshold artifact referenced by the eval contract.

