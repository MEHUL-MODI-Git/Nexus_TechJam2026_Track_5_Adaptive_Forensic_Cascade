# Codex peer review — `specs/phase0-core.md` draft v1

**Verdict:** APPROVE-WITH-NOTES for planning; freeze after the contract/protocol notes below are resolved. No architecture change requested.

## Required before spec freeze

1. **Separate successful expert output from failure.** Keep `ExpertOutput` non-null for successful inference. Define a typed `ExpertInferenceError` (or enclosing failure record) for per-image failure; the cascade catches it, marks the expert unavailable, and follows doc-03 degraded behavior. Do not invent logits/probabilities. State initialization-failure behavior separately.
2. **Resolve concrete field mapping.** `p_fake` is acceptable as the concrete name for doc-03 `probability_after_expert_calibration` if documented explicitly. `model_version` is a useful extension but was not in the logical frozen field list; either jointly ACK it as a v1 extension or place checkpoint/preprocessing metadata in the run manifest. Embeddings need an explicit JSON serializer/omission rule.
3. **Add missing decode metadata.** Record raw/original width and height separately from post-EXIF decoded width/height, and retain bit depth when available, matching doc 03. Clarify that `width`/`height` in the current dataclass are post-orientation.
4. **Centralize pipeline version.** One canonical code/config version source should be imported, not independently copied into every module where values can drift. Golden and feature-cache keys must embed it.
5. **Make noise seed byte-exact.** Specify delimiter and encoding, e.g. SHA-256 of ASCII `"<original_sha256>:<condition_id>"`; define whether the first 16 hex digits are interpreted big-endian (integer parsing implies this).
6. **Complete blur manifest.** Explicitly pass sigma and record torchvision's padding/boundary behavior and tensor conversion/range. Docs 05 requires blur boundary mode.
7. **Guard tiny images.** Resize/crop output dimensions must be `max(1, round(...))`; otherwise tiny but valid inputs can generate zero-sized dimensions.
8. **Importable prediction path.** `scripts/predict.py` should be a thin CLI over an importable Python prediction service consumed by Gradio, batch inference, and eval. Avoid subprocess coupling or duplicate decision logic.
9. **Unreadable batch inputs.** The addendum requires `image_path`/`pred` for scored images but does not justify an invented float for decode failures. Agree a judge-safe null/error or filtering/failure policy; see `specs/phase0-product.md` §5.
10. **Correct source references.** The addendum/spec/decision text names the screenshot with an ASCII space before `PM`, while the actual filename contains a narrow no-break space. Prefer a valid repository-relative link or rename a copied evidence asset through an agreed shared-file action.

## Accepted provisional transform decisions

- PIL JPEG, explicit 4:2:0, non-optimized/non-progressive (add `progressive=False` to manifest).
- Bilinear antialiased downscale then upscale to original size.
- Gaussian noise in float32 `[0,1]` with clipping and deterministic per-image/condition seed.
- Six individual color endpoints at factors 0.8/1.2.
- Center crop retaining 80% of each side and staying cropped until expert-specific preprocessing.

All remain stated assumptions pending the 28-Aug webinar. Any change requires pipeline/golden/cache version bump before retained headline measurements.

## Non-blocking notes

- Golden hashes over raw RGB bytes are acceptable if tests separately assert mode and exact output shape; including shape/mode in the hashed payload would make the artifact more self-describing.
- The clean-smoke AUROC >0.9 gate is a useful preprocessing alarm, but failure should trigger diagnosis rather than automatic model rejection because smoke-source composition can affect the value.
- Avoid duplicating transform numeric parameters between Python and YAML; YAML/config plus validation should have one authoritative value path.

