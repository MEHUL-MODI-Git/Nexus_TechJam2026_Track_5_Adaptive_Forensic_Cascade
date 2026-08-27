# SPEC — Phase 2R eval scientific-boundary repair

> Author/semantic owner: Codex heavy. Mechanical executor: lighter Codex agent. Status:
> **IMPLEMENTATION-FROZEN 2026-08-27**. This operationalizes the already-jointly-ACKed E1–E5
> repair in Claude A-024 / Codex B-020; it does not change the frozen metric objective.

## Scope and ownership

Allowed implementation files:

- `src/eval/protocol.py`, `src/eval/results.py`, `src/eval/report.py`;
- `scripts/run_eval.py`;
- `tests/test_eval_protocol.py`, `tests/test_eval_results.py`.

Do not edit Claude-owned `src/pipeline/`, `src/experts/`, `src/router/`, `scripts/run_grid.py`,
configs, goldens, historical docs 00–08, or existing result artifacts. No metric formula, threshold
objective, transform, dataset split, or public claim changes are delegated.

## Frozen semantic decisions

### E1 — exact reportable coverage

`eval-results.v1` requires exactly one row for every
`(method_id, source_id, canonical_condition_id)`. For each method:

- every source has exactly the canonical 20 conditions;
- every condition covers the same source set;
- all methods cover the identical source set and identical `(source_id, condition_id)` keys;
- label identity agrees across methods.

Global condition presence is insufficient. A single missing source-view refuses reportable output.

### E2 — canonical grid authority

`src.pipeline.transforms.CONDITION_IDS` and `FAMILY_OF` are the only official registry. Remove
caller authority to redefine them from `build_results`/`run_eval` (or assert exact equality before
use; removal is preferred). Diagnostic input may contain a canonical subset but never unknown IDs.

### E3 — loaded threshold capability

`FrozenThreshold` must not be directly constructible by callers. Only `load_frozen_threshold(path)`
may create it after validating the complete `threshold-artifact.v1` payload and hashing the exact
loaded bytes. `build_results` accepts that loaded capability, rechecks its internal marker/digest
shape, and rejects fabricated objects. Validate:

- exact schema and all required fields;
- threshold and all probability/rate/recall fields finite in `[0,1]`;
- ordered two-value CI in `[0,1]`;
- positive integer dev source/row counts, non-negative fake-per-condition count;
- known worst family and transformed condition;
- bootstrap object using the producer's frozen keys: positive integer `n_replicates`, integer
  `seed`, `unit="source_id"`, `stratified_by="label"`, and `interval="percentile_95"`;
- lowercase SHA-256 dev/config hashes, non-empty objective/version/time/tie-break fields;
- artifact pipeline version equals the live `PIPELINE_VERSION`.

The loaded capability retains the exact loaded bytes; results assembly re-hashes them and confirms
they still decode to the validated payload. Tests must load a real artifact file; neither tests nor
production callers may use a private constructor shortcut. A hand-built `FrozenThreshold` must
fail before results assembly.

### E4 — diagnostics contain no headline field

No key equal to the literal string `headline` may occur anywhere in a
`diagnostic-results.v1` document. Per-method summaries use `diagnostic_summary`. Reportable method
records retain `headline`. Markdown selects the schema-appropriate key and keeps the diagnostic
watermark.

### E5 — keyed paired bootstrap

Align methods by sorted canonical `(source_id, condition_id)` keys before any arrays or bootstrap
indices are built. Verify key-set and label equality. The shared resampling unit remains
label-stratified `source_id`, carrying every transformed row for that sampled source. Shuffling one
method's input rows must leave point estimates and intervals byte-for-byte equal. Diagnostic
methods with unequal keys emit no paired delta and a warning (or fail explicitly); they never use
positional alignment.

## Provenance, freeze, and denominator boundary

Reportable output additionally requires a validated `eval-run-manifest.v1`; missing or legacy
manifests are diagnostic-only and must refuse `eval-results.v1`. The manifest contract is:

```text
schema_version: eval-run-manifest.v1
run_id, created_at, command: non-empty strings
code_revision: 40 lowercase hex
seed: integer
dataset: {name, split, manifest_path, manifest_sha256, sealed_reference}
protocol: {
  pipeline_version, golden_version,
  transform_manifest_path, transform_manifest_sha256,
  golden_manifest_path, golden_manifest_sha256
}
methods: [{
  method_id, checkpoint_versions: [non-empty str],
  preprocessing_versions: [non-empty str], parameter_count: non-negative int,
  config_sha256
}]
coverage: {
  expected_source_count, expected_view_count, successful_view_count, failure_count
}
failure_ledger: {path, sha256, count}
production_freeze: {
  schema_version: production-freeze.v1,
  manifest_sha256, code_revision, pipeline_version, golden_version,
  transform_manifest_sha256, threshold_artifact_sha256,
  method_ids, architecture_frozen, sealed_evaluation_authorized
}
```

Validation rules:

- transform and golden hashes must equal the bytes of the canonical repository files; their
  versions must equal live `PIPELINE_VERSION`/`GOLDEN_VERSION`;
- the referenced dataset manifest must be JSON with an `images` list; its exact source IDs and
  each source's label/dataset/source-group/path identity must equal the prediction rows. Merely
  matching a caller-supplied count is not evidence of an intact denominator;
- method IDs equal the prediction rows exactly; every method has complete checkpoint,
  preprocessing, parameter and config provenance;
- `coverage.expected_source_count` equals observed sources;
  `expected_view_count == sources * methods * 20`; successful views equal observed rows;
- failure-ledger bytes must decode as `eval-failure-ledger.v1` with a `failures` list whose length
  equals its declared count and coverage failure count; an arbitrary hashed file is not a ledger;
- failure ledger count equals coverage failure count and
  `successful_view_count + failure_count == expected_view_count`;
- reportable output requires zero failures. A warning is not sufficient for a shrunken denominator;
- run ID equals the prediction rows' sole run ID, and manifest/eval bootstrap seeds agree;
- run/freeze code, pipeline, golden, transform, threshold and method identities match exactly;
- the freeze `manifest_sha256` equals SHA-256 of canonical compact/sorted JSON for the freeze
  payload with `manifest_sha256` omitted, so it binds rather than merely resembles a digest;
- `architecture_frozen` is true;
- sealed-reference output additionally requires `sealed_evaluation_authorized=true`; non-sealed
  output records the flag but does not require it;
- dataset manifest, transform manifest, golden manifest, failure ledger, config, freeze and
  threshold digests are 64 lowercase hex. Artifact paths are non-empty and repository-relative.

The results JSON must distinguish `dataset.manifest_sha256` from
`protocol.transform_manifest_sha256`, carry code/freeze/method provenance, derive class/group
counts from rows, and never hardcode `sealed_reference=false`.

## Additional fail-closed repairs

- Validate `PlaceholderThreshold.value`, bootstrap replicate count/seed and ECE bins before metric
  work. Replicates must be a positive integer; seed an integer; ECE bins positive.
- When all directional flips are zero, record the deterministic first canonical transformed
  condition attaining zero instead of `null`.
- Markdown writes in `run_eval.py` are atomic using an eval-owned helper, like JSON writes.
- `run_eval.py` catches protocol/provenance/coverage validation errors, prints `REFUSED: ...`, and
  exits non-zero without writing a report.

## Executable acceptance tests (write before production edits)

1. **E1 sparse view:** remove one `(method, source, condition)` after partial validation; reportable
   build raises `CoverageError` mentioning exact method/source/condition coverage.
2. **E2 seven-grid injection:** there is no public caller-controlled official-grid path, or passing
   a seven-condition override raises before metric work.
3. **E3 fabrication:** direct `FrozenThreshold(...)` construction fails; malformed payload/digest
   invariants refuse; a loaded valid temporary artifact succeeds.
4. **E4 recursive schema scan:** recursively collect keys from a diagnostic document and assert
   `headline` is absent.
5. **E5 order invariance:** shuffle method-B rows only and assert identical `paired_deltas`.
6. Different paired key sets/labels cannot produce paired deltas.
7. Missing/legacy run manifest refuses reportable output; diagnostics still render with a warning.
8. Wrong transform hash, wrong golden hash/version, missing method provenance, inconsistent counts,
   non-zero failure denominator, missing/mismatched freeze, and unauthorized sealed run each refuse.
9. A manifest citing a larger or identity-mismatched dataset source list refuses. Valid non-sealed
   and valid sealed-authorized manifests produce provenance-complete
   `eval-results.v1`.
10. Placeholder NaN/out-of-range, zero/boolean replicates, invalid seed/ECE bins refuse.
11. All-zero flips name the first canonical transformed condition.
12. JSON and Markdown atomic-write tests leave no temp files.

## Verification and landing gate

The heavy owner must review the full diff, rerun the E1–E5 adversarial reproductions independently,
run focused eval tests, Ruff on touched Python, and the full suite. No code lands and no gate packet
is posted unless every acceptance test passes. Existing smoke output remains diagnostic; this
repair does not promote or rewrite it.
