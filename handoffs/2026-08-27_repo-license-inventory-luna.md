# Phase 1 task 1.6 — repository and license inventory

Inventory date: 2026-08-27. This is a local, read-only audit; no network calls were made. “Unknown” means the repository contains no explicit local evidence, not that a license is absent upstream.

## 1. Factual inventory: public-repository hygiene

Present:

- `.gitignore` is tracked and covers Python environments/bytecode, secrets, raw/downloaded data, smoke images, checkpoints/models/Hugging Face caches, feature caches, generated results (with JSON/CSV/MD exceptions), recordings, editor files, and coverage output.
- Dependency/build metadata is present in `pyproject.toml`; a lockfile is present in `uv.lock`. Runtime dependencies are pinned by ranges (Python 3.12, torch/torchvision, timm, Gradio, Pillow, etc.), not exact application versions in `pyproject.toml`.
- `data/manifests/LICENSES.md` is tracked and maps the two smoke-manifest IDs to source terms and redistribution guidance. `data/manifests/smoke_v1.json` and `smoke_acquisition.json` carry dataset revisions, source URIs, labels, hashes, and license IDs.
- Reproducibility/provenance artifacts include `configs/`, scripts, tests/goldens, `results/.gitkeep`, and the smoke manifests. `specs/phase0-product.md` requires a README, license and parameter inventories, but those deliverables are not yet present.
- Organizer material exists locally under untracked `Brief/` (one 8-page PDF plus seven PNG screenshots) and untracked `docs/evidence/2026-08-26_track5-deliverables.png`. These are bundled/reference assets, not product documentation.

Missing or incomplete:

- No root `README.md` (only `teaching/README.md`, `handoffs/README.md`, and `coordination/gates/README.md`). Required overview, setup, reproduction, limitations, contributions, license, and parameter inventory therefore are not public-repo-ready.
- No root `LICENSE`, `NOTICE`, or software copyright/attribution file. The project’s own license is unknown.
- No tracked checkpoint/model-card manifest or third-party software attribution inventory. The source tree contains no vendored model code or checkpoint files at audit time.
- Current worktree has pre-existing modified coordination/status/state files and untracked organizer assets; do not treat them as clean release contents without an explicit staging review.

## 2. Factual inventory: explicit local license evidence

### Datasets and data

- `COCO-TERMS`: `data/manifests/LICENSES.md:7` explicitly cites COCO terms of use, says smoke rows use `train2017`, and says raw images are not redistributed; it also records that COCO does not own the underlying Flickr images. `handoffs/2026-08-26_dataset-acquisition.md:33` further states annotations are CC BY 4.0 while images remain subject to each Flickr uploader’s terms. Treat image redistribution as restricted/ source-specific.
- `SID-CC-BY-4.0`: `data/manifests/LICENSES.md:8` explicitly records SID-Set revision `dc03ead...`, marked CC BY 4.0, attribution required, plus incorporated source-dataset terms; raw images remain local and ignored. The same ID is used throughout `data/manifests/smoke_v1.json`.
- Tiny-GenImage: `handoffs/2026-08-26_dataset-acquisition.md:51,132,148` records CC-BY-NC-SA-4.0 for the HF mirror. This is non-commercial/share-alike and is not in the current smoke manifest.
- Official GenImage: `handoffs/2026-08-26_dataset-acquisition.md:58,148` says the license is unclear/not explicit in the local evidence; status: unknown/research-only pending verification.
- WildFake: `handoffs/2026-08-26_dataset-acquisition.md:94,109,150` records Apache 2.0 as ModelScope metadata (paper does not state it explicitly). The organizer subset is also documented as sealed/non-training in `docs/00-official-brief.md:92-105`; do not redistribute or train on it.
- CIFAKE: `handoffs/2026-08-26_dataset-acquisition.md:123,151,161` says exact Kaggle license text is unverified; status: unknown/research/non-commercial precaution.
- AI-GenBench-fake_part: `handoffs/2026-08-26_dataset-acquisition.md:136,149` records multi-source licensing and says per-image provenance must be checked before redistribution; status: mixed/unknown until provenance review.
- AIGC-Detection-Benchmark: `handoffs/2026-08-26_dataset-acquisition.md:134,148` records Apache 2.0 for the HF dataset mirror.

### Models and software

- CF-384 / `OwensLab/commfor-model-384`: `specs/phase0-core.md:102` explicitly records MIT for code + weights and 21.8M parameters. `CLAUDE.md:55` repeats the model and MIT claim. No local upstream LICENSE/model card is bundled.
- LOTA repository code: `handoffs/2026-08-26_lota-integration.md:162-164,213` records MIT code license and copyright “hongsongwang” 2025. The same file explicitly says pretrained weights have no stated license and redistribution/commercial status is legally ambiguous/unknown. Do not commit weights.
- RIGID/WaRPAD: local evidence identifies the arXiv paper/backup (`CLAUDE.md:55`) but provides no explicit software or checkpoint license; status: unknown.
- Standard torchvision/ResNet code: `handoffs/2026-08-26_lota-integration.md:164` mentions torchvision as BSD-licensed in an implementation discussion; this is not a bundled license notice and does not establish licenses for any copied code.
- Other dependencies listed in `pyproject.toml`/`uv.lock` (Python, Gradio, Hugging Face Hub, imagehash, NumPy, Pillow, PyYAML, safetensors, timm, torch, torchvision, pytest) have no per-package license evidence in repository files; status: unknown locally. Do not infer licenses from package names.

## 3. Factual candidates to ignore / keep out of commits

- Already ignored local/private/generated material: `.venv/` (large installed packages, including ~328 MB torch library), `.pytest_cache/`, `__pycache__/`, `data/smoke/` raw images, `results/grid-smoke-v1/` (about 5 MB JSONL plus run outputs), and `.DS_Store`.
- Checkpoint/model/cache locations are already ignored: `checkpoints/`, `models/`, `data/raw/`, `data/downloads/`, `data/features/`, `data/feature_cache/`, `**/huggingface/`, and `**/hub/`. Any LOTA `.pth`, CF weights/cache, or other downloaded model files belong there and should not be committed, especially because LOTA weight licensing is unknown.
- Untracked `Brief/*.png`, `Brief/*.pdf`, and `docs/evidence/*.png` are organizer screenshots/PDF and may contain copyrighted or third-party material. They are not covered by the current ignore rules; stage only if permission and release need are documented, otherwise ignore/remove from release staging.
- Do not commit raw COCO/SID images or future dataset downloads; current manifests are the reproducible, lightweight provenance substitute. Do not commit sealed WildFake data or hashes beyond the approved safeguard artifacts.

## 4. Recommendations (not factual changes; minimal file-by-file patch list)

1. Add root `README.md` with overview, installation (`uv`), reproduction commands, current smoke-data provenance, limitations, solo contribution, explicit model/parameter table, and links to `data/manifests/LICENSES.md`.
2. Add a root `LICENSE` after Mehul chooses the project license; add `NOTICE`/`THIRD_PARTY_NOTICES.md` if required by that choice or copied code. Do not label the project MIT merely because one dependency/model is MIT.
3. Extend `data/manifests/LICENSES.md` with the explicitly evidenced candidate rows (Tiny-GenImage NC-SA, AIGC-Benchmark Apache 2.0, WildFake Apache 2.0 metadata) and clearly mark GenImage, CIFAKE, mixed-source AI-GenBench, RIGID, and LOTA weights as unknown/unverified.
4. Add a small tracked `configs/models.yaml` or `docs/model-inventory.md` containing model source, revision, parameter count, preprocessing version, and license status; keep all weight paths/checkpoints ignored.
5. Add organizer-asset ignore rules (for example `Brief/` and/or selected screenshot extensions) only after Mehul confirms these assets are not intended release artifacts; otherwise retain them untracked and exclude them during staging.
6. Before publication, run a clean `git status --short --ignored`, inspect staged paths, and verify no raw images, checkpoints, caches, private screenshots, or generated large results enter the public repository.

