# SPEC — eval contract and Phase-1 harness

> Author: Codex (heavy). Executor: Codex for metric-critical code; light subagents may generate non-judgmental test fixtures/formatters from this frozen spec, followed by Codex verification. Status: FROZEN v1 — approved by Claude in A-010 and finalized by Codex in B-008. Behavior-affecting changes require CHANNEL + DECISIONS.

## Scope and ownership

Phase 0 freezes the input/output contracts. Phase 1 implements `src/eval/`, `tests/test_metrics.py`, and the JSON/Markdown artifact path for task 1.1. This spec does not alter Claude-owned transforms, adapters, router, or training logic.

## 1. Prediction-row input contract

The harness consumes one normalized row per `(method_id, source_id, condition_id)`:

```text
schema_version: "prediction-row.v1"
run_id: str
method_id: str
sample_id: str                 # unique source-view id
source_id: str                 # clean image and all views share this
image_path: str
content_sha256: str
label: int                     # 0 real, 1 AI-generated
dataset: str
source_group: str              # generator or real-source grouping
condition_id: str              # exact docs/05 ID
p_fake: float                  # finite, [0,1], higher = fake
reliability: float | null      # [0,1], separate from p_fake
decision: str | null           # optional display decision; eval recomputes binary pred
rescue_invoked: bool | null
inference_ms: float | null
expert_failures: list[{expert_id: str, reason_code: str}] | null
warnings: list[str]
```

Rules:

- Eval computes forced binary prediction as `p_fake >= frozen_threshold`; it never trusts a caller-provided binary label.
- Exactly one row per method/source/condition; duplicates are a hard error.
- Every evaluated source must have `clean`; paired flip metrics require both clean and target-condition rows.
- Official condition IDs must be the 20 IDs in docs 05. Unofficial/chained suites use a separate protocol namespace.
- Labels, source IDs, and grouping fields come from the versioned dataset manifest, not filenames.
- Non-finite scores, invalid labels, missing clean rows, or mismatched source labels are hard validation failures.

## 2. Threshold boundary

- A test/evaluation run requires a frozen threshold artifact containing value, objective, dev-manifest hash, config hash, fitting code version, and timestamp.
- One threshold applies to clean and every transformed condition.
- Threshold/calibration fitting occurs only on held-out dev; test/external/sealed runners never expose a fitting path.
- Frozen objective: maximize bootstrap-mean dev worst-transformation-family fake recall across the six transformed families (clean excluded; severities pooled within family) subject to clean FPR ≤ selected-primary FPR +1 percentage point and clean balanced accuracy ≥ selected-primary BAcc -1 point. Report worst exact condition at the selected threshold; upgrade threshold selection to exact-condition only when dev has at least 500 fake sources per exact condition. If infeasible, select the strongest simpler configuration and record the failure.
- `UNCERTAIN` never changes forced-binary metrics. Selective metrics report coverage and accepted-set outcomes separately.

## 3. Required calculations

AI-generated is the positive class.

- Per condition: TP, FN, FP, TN, TPR/fake recall, TNR, FPR, balanced accuracy, AUROC, average precision, Brier score, NLL.
- `drop_M(t) = M(clean) - M(t)`, signed.
- Worst metrics are minima over exact conditions, including the condition ID attaining the minimum.
- Flip rate uses paired source decisions.
- `fake_to_real_flip(t) = count(y=1, pred_clean=1, pred_t=0) / count(y=1)`.
- `real_to_fake_flip(t) = count(y=0, pred_clean=0, pred_t=1) / count(y=0)`.
- ECE uses 15 fixed equal-width probability bins by default; binning is recorded in results.
- Calibration/selective/rescue metrics are emitted only when required fields exist; absence is explicit, never silently zero.

Any condition missing either class is a protocol error for headline evaluation. Exploratory one-class slices may emit class-appropriate metrics but cannot populate the headline table.

## 4. Source bootstrap

- Default: 1,000 replicates, deterministic seed stored in run metadata.
- Resampling unit is `source_id`; all transformed views of a sampled source travel together.
- Use label-stratified source resampling so both classes remain defined; report this choice.
- Paired method deltas reuse the identical resampled source indices for both methods.
- Percentile 95% intervals are the default; store replicate count and interval method.
- Never resample transformed rows as independent observations.

## 5. `eval-results.v1` JSON

Top-level required fields:

```text
schema_version: "eval-results.v1"
run: {run_id, created_at, code_revision, command, seed}
protocol: {transform_manifest_version, golden_version, threshold_artifact,
           decision_rule, bootstrap, ece_bins}
dataset: {name, split, manifest_sha256, sealed_reference, source_count,
          view_count, class_counts, group_counts}
methods: [{method_id, checkpoint_versions, preprocessing_versions,
           parameter_count, config_sha256}]
conditions: [{condition_id, counts, metrics, ci95}]
headline: {clean, worst, max_directional_flip, calibration, selective, rescue}
paired_deltas: []
artifacts: {prediction_rows, markdown_tables, plots, error_examples}
warnings: []
```

Requirements:

- JSON contains measured values only; unavailable values are `null` with a warning, never illustrative placeholders.
- All artifact paths are repository-relative and include SHA-256 when final/frozen.
- Store raw confusion counts alongside rates so every table is auditable.
- `sealed_reference=true` is rejected unless the production freeze manifest exists and the run is explicitly Phase 4.

## 6. Generated artifacts

- Machine JSON: `results/<run_id>/eval-results.json`.
- Per-source prediction rows: JSONL or Parquet, versioned and hashed.
- Auto-generated Markdown: full condition table, headline table, selective table, rescue table.
- Plots consume `eval-results.json`; they do not recompute or hand-enter metrics.

## 7. Test matrix / Definition of Done

Unit tests use small hand-calculable fixtures and cover:

1. confusion counts, balanced accuracy, fake recall, FPR;
2. threshold equality (`p_fake == threshold` predicts fake);
3. signed clean drops and exact-condition worst selection including ties;
4. ordinary and directional flips with paired source rows;
5. AUROC/AP/Brier/NLL against trusted library outputs;
6. ECE edge bins including 0.0 and 1.0;
7. source-level bootstrap determinism and paired-delta resampling;
8. rejection of duplicates, invalid scores, missing clean rows, inconsistent labels, unknown official IDs;
9. abstention counted only in selective metrics, with explicit coverage;
10. JSON-schema validation and Markdown values traced to JSON;
11. hard rejection of sealed-reference run before a valid freeze manifest.

Phase-1 DoD: tests pass; one command creates prediction artifact → validated `eval-results.json` → Markdown tables; smoke-set full grid produces all required rows without tuning the threshold on test data.

## 8. Hard constraints

- No access to or fitting on WildFake reference data before Phase 4 freeze.
- COCO val2017 never enters smoke/router training manifests.
- One class threshold across conditions.
- All confidence intervals use source units.
- Transform/cache/preprocessing version mismatches stop the run.
- Every public number traces to a frozen JSON artifact.
