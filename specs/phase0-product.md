# SPEC — Phase 0 product (scaffold, smoke manifest, Gradio v0)

> Author: Codex (heavy). Mechanical scaffold/download/UI wiring may be delegated to a light subagent only after this spec is jointly frozen; Codex reviews every diff and runs the DoD. Status: FROZEN v1 — approved by Claude in A-010 and finalized by Codex in B-008. Behavior-affecting changes require CHANNEL + DECISIONS.

## 1. Repo scaffold (task 0.1)

Local scaffold:

```text
src/{pipeline,experts,router,eval,app}/
scripts/  configs/  tests/  results/
data/manifests/  docs/  specs/  coordination/
```

- `uv` project, Python `>=3.12,<3.13`, src-layout packages, pytest configuration.
- `.gitignore` excludes raw datasets, checkpoints, model caches, feature caches, local results containing large/sensitive assets, `.env`, OS/editor files, and rendered demo recordings.
- Small manifests/configs/golden fixtures and representative aggregate results remain trackable.
- Do not modify files already owned by Claude while scaffolding; create directories/package markers only after task claims are recorded.
- Local `git init` is part of 0.1. Creating/pushing a public GitHub repository is a separate external action after Mehul confirms repository owner/name and credentials.

## 2. Core-facing prediction service contract

Gradio and `scripts/infer_dir.py` must call an importable Python service, not spawn `scripts/predict.py` as a subprocess. Claude owns the Phase-0 implementation; Codex consumes/reviews it.

Minimum successful result:

```text
schema_version: "prediction.v1"
image: {sha256, width, height, format, warnings}
transform_id: str
p_fake: float                    # finite [0,1], higher = fake
forced_prediction: int           # one configured threshold
decision: str                    # Phase 0 REAL / AI-GENERATED
reliability: float | null         # null until a validated estimator exists
experts: list[ExpertOutput]
rescue_invoked: bool
inference_ms: {total, components}
warnings: list[str]
```

Phase 0 labels the verdict/score as a baseline model output, not a calibrated real-world probability. Router, `UNCERTAIN`, fusion weights, and rescue fields become active only when validated.

Failure result is typed separately and never invents a score. The UI renders the error/warnings without crashing.

## 3. Smoke dataset manifest (task 0.7)

Target: approximately 200 real + 200 fake source images.

- Real: fixed sample from COCO **train2017**, never val2017.
- Fake: fixed licensed GenImage or fully-synthetic SID-Set slice chosen after access/license verification; no tampered/partial images.
- Download/copy mechanics may be delegated; Codex verifies licenses, counts, hashes, labels, and forbidden-source checks.
- Raw data is not committed unless redistribution is explicitly permitted and strategically justified.

Manifest v1, one row per clean source:

```text
manifest_version
sample_id
source_id
relative_path
label                         # 0 real, 1 fully generated
class_name
dataset
dataset_split
dataset_revision
source_uri
source_group                 # real source or generator/model
generator
license_id
original_sha256
decoded_phash
width
height
format
selection_seed
```

Requirements:

- Selection is deterministic and balanced by class; seed and source revision are recorded.
- Exact duplicate SHA-256 within/across classes is rejected.
- Perceptual-near-duplicate scan is reported; threshold must be jointly fixed before router corpus work.
- A hard string/source assertion rejects `val2017` paths or metadata.
- Clean source and every future transformed view retain the same `source_id` and split.
- A license inventory maps every `license_id` to terms/source and whether redistribution is allowed.

## 4. Gradio v0 (task 0.8)

Single-page layout:

1. Header: project name plus one-sentence scope (“robust AI-image detection prototype”).
2. Upload/input panel: click/drag image, supported-format note, Analyze button.
3. Result card: `REAL` or `AI-GENERATED`, baseline `p_fake` score, clear provisional/research disclaimer.
4. Evidence row: CF-384 score, inference latency, decode/preprocessing warnings.
5. Collapsed technical details: dimensions, source format, content-hash prefix, model/config version.
6. Error state: concise decode/inference failure with no fabricated verdict.

Rules:

- No reliability badge until reliability is trained/validated.
- Do not label an uncalibrated expert score as real-world probability.
- Keyboard-accessible controls, readable contrast, no color-only verdict distinction.
- Uploaded images are processed locally and not persisted by the app unless explicitly enabled.
- Phase 0 excludes full-grid stress testing; the Phase-1 button adds it against the same importable prediction service.

## 5. Required directory inference (Phase 1, gate-tested thereafter)

CLI:

```text
python scripts/infer_dir.py INPUT_DIR --output predictions.json
```

Canonical output is a deterministic JSON array ordered by normalized relative path:

```json
[
  {"image_path": "relative/path.jpg", "pred": 0.873}
]
```

- For every successfully decoded image, `pred` is finite numeric `[0,1]`, higher = AI-generated.
- Additional keys are permitted only after confirming they will not break the organizer consumer; default output stays minimal.
- Unsupported/unreadable recognized image files never receive an invented confidence. Default behavior emits one row per recognized file, using `{"image_path": ..., "pred": null, "error": "decode_failed"}` on failure, exits 0 after writing the complete JSON, and prints a failure summary to stderr. `--errors {null,skip,strict}` controls policy (`null` default; `skip` omits failed rows; `strict` exits nonzero on the first failure). Gate smoke uses `strict`; judge-facing default remains `null` so output rows cannot silently misalign with input paths.
- Atomic output write, deterministic ordering, case-insensitive supported extensions, bounded memory, per-file error isolation.
- Batch inference uses the same config, preprocessing, calibration, and prediction service as CLI/Gradio/eval.

Standing gate smoke: two valid images of each class, nested-path/order check, one corrupt-image behavior check, JSON schema/range validation, and equality with direct service predictions.

## 6. Definition of Done

### 0.1

- Project installs from the lockfile on Python 3.12; imports work; tests discover; secrets/data/checkpoints are ignored; no ownership collision.

### 0.7

- Counts/labels/source revisions/licenses/hashes validate; COCO val2017 guard passes; manifest reproduces selection.

### 0.8

- Fresh upload produces the same score as the importable prediction service; error input is safe; UI claims are accurate; local launch command documented.

### Required addendum

- `scripts/infer_dir.py` output remains a gate item from Phase 1 onward.
- README eventually includes overview, setup/install, reproduction, limitations/future work, solo contribution, license and parameter inventories.
- Code comments explain non-obvious forensic/protocol choices without narrating obvious syntax.

## 7. Deferred decisions

- Public GitHub owner/name and creation timing.
- Fake smoke source after license/access verification.
- Final corrupt-file JSON behavior for the organizer batch interface.
- Gradio styling beyond v0 and the Phase-1 stress-panel plot layout.
