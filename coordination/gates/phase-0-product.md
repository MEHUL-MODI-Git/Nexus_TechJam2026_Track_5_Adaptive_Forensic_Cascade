# Phase 0 product gate — Codex evidence packet

**Owner:** Codex · **Submitted:** 2026-08-27 ~00:45 SGT · **Verdict requested from:** Claude

## Scope delivered

- **0.1 scaffold:** local Git repository; Python `>=3.12,<3.13`; uv lockfile; src package build; runtime/dev dependencies; pytest discovery; raw data/checkpoints/caches/secrets ignored.
- **0.7 smoke set:** 200 COCO train2017 real + 200 SID-Set validation `label=1`/`full_synthetic_*` fake images, deterministic seed `20260826`, immutable source revisions, acquisition provenance, manifest v1, canonical hashes/pHashes, license inventory, val2017 guard.
- **0.8 Gradio v0:** importable `PredictionService` only; local upload/analyze path; baseline-score/disclaimer language; CF-384 evidence, latency, warnings, technical provenance; typed no-verdict error state; injected fake service for tests; industrial/editorial accessible theme.

## Evidence

### Reproducible environment and suite

```text
env UV_CACHE_DIR=/tmp/techjam-uv-cache uv sync --offline
.venv/bin/pytest -q
350 passed, 47 warnings in 10.46s
```

The remaining warnings are upstream deprecations in pinned Gradio 5/Pillow code paths, not failures. Package imports (`src.pipeline`, `src.experts`, `src.eval`, `src.app`, `safetensors`) pass. `pytest --collect-only` discovers the suite.

### Smoke-data integrity

Artifacts:

- `data/manifests/smoke_acquisition.json` — 400 durable source records, no expiring signed URLs.
- `data/manifests/smoke_v1.json` — 400 validated manifest rows.
- `data/manifests/LICENSES.md` — source terms and redistribution policy.
- raw images under ignored `data/smoke/images/` (50 MB; never committed).

Verified:

```text
real=200 fake=200
source revisions:
  COCO mirror 036f3f8291db64d17faad9b09e59dd30bb65c4d7 (train only)
  SID-Set dc03ead57929879319ce30a82bfcfb8d317b10bd (validation label=1 only)
exact SHA duplicates: 0
pHash pairs at Hamming <=0/2/4/6: 0/0/0/0 (cross-class all 0)
val2017 occurrence in acquisition/manifest: 0
```

Generator identity is not exposed by SID-Set's public row schema, so these rows use a dataset-level source group. This is explicitly smoke-only and cannot be reused as the generator-grouped router corpus.

### Real adapter separation

```text
.venv/bin/python scripts/sanity_check.py --manifest data/manifests/smoke_v1.json
CF-384 21.81M params, CPU
200 real / 200 fake scored
mean p_fake real=0.0007 fake=0.5056
clean AUROC=0.9923 (required floor >0.9) — PASS
```

This is a smoke alarm only, not a headline estimate and not used for threshold fitting.

### Gradio exit test

- `env GRADIO_SERVER_PORT=8960 .venv/bin/python -m src.app` served `http://127.0.0.1:8960` using the real configured CF-384 service.
- HTTP response carried title `Adaptive Forensic Cascade`, custom theme CSS, 14 components, and exactly one `/analyze` dependency from image input to five outputs.
- `tests/test_app.py` asserts actual service score formatting equals direct `PredictionService.predict_image`, injected-service behavior, safe errors, invalid/non-finite/out-of-range rejection, and callback wiring.
- No connected visual-browser surface was available in this Codex session; live server/config/handler behavior were verified, but pixel-level screenshot QA remains a Phase-1 polish note.

## Hard-constraint audit

- COCO val2017 rejected in code and absent from both manifests.
- WildFake sealed subset was never downloaded, evaluated, fitted, or inspected.
- Raw datasets are ignored; only manifests/licenses are trackable.
- UI calls the importable prediction service and does not duplicate threshold logic.
- UI calls Phase-0 score a baseline research result, not a calibrated real-world probability; no reliability badge.
- One configured threshold is displayed from the core service; no transform-specific thresholds.

## Exit-test result

**PASS, pending peer review.** A local user can upload an image and receive a real CF-384-backed verdict/score; corrupt/invalid service outputs cannot fabricate a verdict. The full clean-smoke separation exceeds the >0.9 diagnostic floor.

## Requested reviewer commands

```bash
env UV_CACHE_DIR=/tmp/techjam-uv-cache uv sync --offline
.venv/bin/pytest -q
.venv/bin/python scripts/validate_smoke_manifest.py data/manifests/smoke_v1.json --root .
.venv/bin/python scripts/sanity_check.py --manifest data/manifests/smoke_v1.json
python -m src.app
```

Review outcome in CHANNEL: `APPROVE`, `APPROVE-WITH-NOTES`, or `BLOCK`.
