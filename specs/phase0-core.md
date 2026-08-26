# SPEC — Phase 0 core (decode, transforms, CF adapter, prediction service, predict CLI)

> Author: Claude (heavy). Executors: Sonnet subagents implement module-by-module against this spec; Claude verifies each against its Definition of Done.
> **Status: v2 — FROZEN 2026-08-26 (~21:15).** All 10 "required before freeze" notes from `handoffs/2026-08-26_core-spec-review.md` are resolved inline below (marked `[N#]`). One item is a live proposal awaiting a single Codex ACK round: the `infer_dir.py` corrupt-file policy `[N9]` — it is a Phase-1 deliverable and does not block Phase-0 build.
> Changes after freeze require a CHANNEL message + DECISIONS entry + `PIPELINE_VERSION` bump if behavior-affecting.

## Global decisions (binding unless webinar contradicts)
- Python 3.12, `uv`-managed. Deps for Phase 0: `torch`, `torchvision`, `pillow`, `numpy`, `huggingface_hub`, `timm`, `imagehash`, `pyyaml`, `pytest` (`gradio` is product-side).
- Canonical in-memory image = **PIL Image, RGB, uint8**. Transforms are pure functions `(PIL, sha256) -> PIL`.
- Any float math happens in float32 [0,1]; convert back with `np.round(x*255).clip(0,255).astype(uint8)`. Rounding convention is part of the protocol.
- Determinism: no global RNG. Per-image seeds derived from content hash (see §2 noise).
- **Geometry guard [N7]:** every computed output dimension is `max(1, round(...))`. Applies to resize down, resize up, and crop. A 1×1 input must survive all 20 conditions.

### 0. `src/pipeline/version.py` — single version source [N4]
```python
PIPELINE_VERSION = "0.1.0"   # decode + transform behavior. Bump on ANY behavior change.
GOLDEN_VERSION   = "0.1.0"   # bumped in lockstep with PIPELINE_VERSION
```
- **No other module defines a version literal.** Every module that needs one imports from here; `configs/transforms.yaml` carries the same string and `load_transform_config()` asserts equality at import time (fail-fast on drift).
- Feature-cache keys, golden `expected.json`, threshold artifacts, and every results JSON embed `PIPELINE_VERSION`.
- **Numeric transform parameters live in `configs/transforms.yaml` only** [non-blocking note 3]; Python holds no duplicate literals — the registry reads the loaded config, and a startup assertion checks the yaml key set equals the 20 registry ids.

## 1. `src/pipeline/decode.py`
```python
@dataclass(frozen=True)
class DecodedImage:
    image: PIL.Image.Image      # RGB uint8, EXIF-orientation APPLIED
    sha256: str                 # of ORIGINAL file bytes
    phash: str                  # imagehash.phash(image), 64-bit hex
    orig_mode: str              # PIL mode before RGB convert, e.g. "RGBA", "CMYK", "L"
    orig_format: str | None     # "JPEG" | "PNG" | ... | None for raw bytes
    raw_width: int              # [N3] decoded size BEFORE exif_transpose
    raw_height: int
    width: int                  # [N3] POST-orientation, post-RGB size (canonical)
    height: int
    bit_depth: int | None       # [N3] bits per channel when PIL exposes it, else None
    file_bytes: int
    warnings: list[str]         # machine-readable codes, see below
```
- Order of operations: read bytes → sha256 → `PIL.Image.open` → record `orig_mode`/`orig_format`/`raw_width`/`raw_height`/`bit_depth` → `PIL.ImageOps.exif_transpose` → RGB convert → record `width`/`height` → phash.
- `bit_depth` [N3]: from `PIL.Image.Image.mode` bit table (`I;16`/16-bit PNG → 16, standard 8-bit modes → 8); `None` when not determinable. Recorded only — Phase 0 never branches on it.
- Alpha: composite on white, warning `alpha_discarded`. CMYK: convert, warning `cmyk_converted`. Palette/grayscale: convert, warning `mode_converted:<orig_mode>`. EXIF applied: warning `exif_transposed:<orientation>`.
- Unreadable/truncated input raises typed `DecodeError(path, reason)`. `PIL.ImageFile.LOAD_TRUNCATED_IMAGES` stays **False** — a truncated file is an error, not a silently padded image.
- MUST NOT resize, recompress, or strip data beyond RGB conversion.
- **DoD:** unit tests — EXIF-rotated JPEG (raw dims ≠ post dims, orientation warning); RGBA PNG composited; CMYK converted; 16-bit PNG records `bit_depth=16`; truncated file raises `DecodeError`; 1×1 image decodes; `sha256` matches `shasum -a 256`; `DecodedImage` is hashable/immutable.

## 2. `src/pipeline/transforms.py` — the official grid
One registry: `TRANSFORMS: dict[str, Callable[[PIL.Image, str], PIL.Image]]` keyed by condition id; second arg = image sha256 (seeding only). Condition ids exactly as in `docs/05` stress matrix:
`clean, jpeg_q90, jpeg_q70, jpeg_q50, jpeg_q30, blur_s0.5, blur_s1.0, blur_s2.0, resize_0.5, resize_0.25, noise_s0.02, noise_s0.05, noise_s0.10, bright_-20, bright_+20, contrast_-20, contrast_+20, saturation_-20, saturation_+20, crop_0.8`.

Transform families (for the threshold objective, §2 of `specs/phase0-eval.md`): `jpeg`(4), `blur`(3), `resize`(2), `noise`(3), `color`(6), `crop`(1) = 19 transformed conditions + `clean` = 20.

Exact implementations (parameters read from `configs/transforms.yaml`):
- **clean:** identity — returns the input object unchanged (no re-encode, no copy-through-array).
- **JPEG(q):** PIL save to `BytesIO`, `format="JPEG", quality=q, subsampling=2` (4:2:0), `optimize=False`, `progressive=False`; reopen; `convert("RGB")`. Manifest records all four encoder flags.
- **Blur(σ) [N6]:** `torchvision.transforms.v2.functional.gaussian_blur(t, kernel_size=[k, k], sigma=[σ, σ])` with `k = 2*ceil(3σ)+1` (odd), **σ passed explicitly** (never left to torchvision's kernel-size-derived default). Tensor path: uint8 HWC → `float32 CHW in [0,1]` → blur → clip [0,1] → uint8 via the global rounding convention. **Boundary/padding: torchvision `gaussian_blur` pads `reflect`** — recorded in the manifest as `padding_mode: reflect` (docs 05 requires the boundary mode be stated). True Gaussian convolution; NOT PIL's box-blur approximation.
- **Resize(s):** bilinear, `antialias=True`. Down to `(max(1,round(H*s)), max(1,round(W*s)))` then BACK to the original `(H, W)`, same interpolation and antialias settings. Down-then-up is mandatory; the output is always the original size.
- **Noise(σ) [N5]:** float32 [0,1]; add `rng.normal(0, σ, shape)` (independent per channel); clip [0,1]; back to uint8.
  **Byte-exact seed:** `payload = f"{orig_sha256}:{condition_id}".encode("ascii")` (single ASCII colon `0x3A`, no whitespace, lowercase hex sha); `digest = hashlib.sha256(payload).hexdigest()`; `seed = int(digest[:16], 16)` — the first 16 hex characters of the digest string, parsed **big-endian** (`int(str, 16)` is big-endian by definition, so digest bytes 0..7 are the high-order bytes); `rng = np.random.default_rng(seed)`. σ is in [0,1] units (stated assumption, webinar Q5).
- **Color(prop, ±20%):** `torchvision.transforms.v2.functional.adjust_{brightness,contrast,saturation}` with factor 0.8 / 1.2, ONE property per condition (6 endpoint conditions; composed jitter is a separate unofficial suite later). Same float32 [0,1] tensor path and rounding convention as blur.
- **Crop 0.8:** center crop to `(max(1,round(0.8*H)), max(1,round(0.8*W)))` — 80% per side (64% area; stated assumption, webinar Q7). Left/top offsets `floor((H-h)/2)`, `floor((W-w)/2)`. Output **STAYS at cropped size**; each adapter applies its own input policy. Never resize back here.
- **DoD:** golden tests (§3) pass; each function property-tested — output dtype/mode always uint8/RGB; output size equals the documented rule for every condition; determinism (same input + id twice → byte-identical arrays); 1×1 and 3×3 inputs survive all 20 conditions.

## 3. `tests/golden/` + `tests/test_transforms_golden.py`
- 3 checked-in source PNGs (small, self-made: photo-like crop, smooth gradient, textured noise — no third-party content), each ≤256px.
- `tests/golden/expected.json`:
  `{"pipeline_version": ..., "golden_version": ..., "sources": {src: {cond_id: {"sha256": <of raw uint8 RGB bytes>, "shape": [H,W,3], "mode": "RGB"}}}}`
  — shape and mode are **inside the hashed record** so the artifact is self-describing [non-blocking note 1]; the hash itself covers the raw array bytes only.
- Regeneration script `scripts/regen_golden.py`; the test fails if `expected.json` differs from the computed values, and a separate test asserts `expected.json["pipeline_version"] == PIPELINE_VERSION` — so a behavior change without a version bump fails CI.

## 4. `src/experts/base.py` — expert contract (FROZEN)
```python
@dataclass(frozen=True)
class ExpertOutput:                # SUCCESS ONLY — never constructed for a failure [N1]
    expert_id: str                 # "commfor_384" | "lota" | "warpad" | "rigid"
    raw_logit: float               # finite, higher = more likely AI-generated (adapter maps polarity)
    p_fake: float                  # finite [0,1] = doc-03 `probability_after_expert_calibration` [N2]
    inference_ms: float
    embedding: np.ndarray | None   # in-memory only; see serialization rule [N2]
    patch_scores: list[float] | None
    warnings: list[str]
    model_version: str | None = None   # OPTIONAL v1 extension, jointly ACKed (A-006 §2 / B-006) [N2]

class ExpertInferenceError(Exception):   # [N1] per-image recoverable failure
    expert_id: str; reason_code: str; message: str; image_sha256: str | None
class ExpertInitError(Exception):        # [N1] expert unavailable for the whole run
    expert_id: str; reason_code: str; message: str
```
- **[N1] Success/failure separation.** `ExpertOutput` fields are non-null for a successful inference (`raw_logit` and `p_fake` finite, always). A per-image failure raises `ExpertInferenceError`; the cascade catches it, records `{expert_id, reason_code, message}` in the prediction record's `expert_failures`, marks that expert unavailable **for that image**, and degrades per doc 03. **No logit or probability is ever invented.**
- **[N1] Initialization failure** (checkpoint missing, weights corrupt, device unavailable) raises `ExpertInitError` at registry build time: the expert is absent from the run, the run manifest records the reason, and the cascade proceeds with the remaining experts. Zero available experts = fatal run error, not a fabricated verdict.
- **[N2] Field mapping,** documented explicitly: `p_fake` **is** doc-03 `probability_after_expert_calibration` (Phase 0: a plain sigmoid of `raw_logit`, no per-expert calibration fitted yet — the name is stable, the contents gain calibration in Phase 2 without a schema change). `raw_logit` is doc-03 `raw_score`.
- **[N2] `model_version`** is an optional v1 extension (default `None`): populated on the live predict path (Gradio/CLI display, `prediction.v1`); **omitted in feature-cache rows**, where the run manifest carries checkpoint identity once.
- **[N2] Embedding serialization rule:** `embedding` is never JSON-serialized. `to_json_dict()` drops it and sets `"embedding_present": bool`, `"embedding_dim": int | None`. Feature caches store embeddings as a separate float32 array keyed by `(source_id, condition_id, expert_id)`; JSON carries the key, not the vector. Same rule for `patch_scores` above 64 entries (summary stats + array key instead).
```python
class Expert(Protocol):
    expert_id: str; param_count: int; license: str; model_version: str | None
    def predict(self, img: DecodedImage) -> ExpertOutput: ...   # raises ExpertInferenceError
```
- Adapter (not caller) owns: preprocessing, device, class-order mapping to P(fake), exactly one sigmoid, determinism (`torch.inference_mode()`, `model.eval()`).

## 5. `src/experts/commfor.py` (details verified in `handoffs/2026-08-26_commfor-integration.md`)
- Load: `ViTClassifier.from_pretrained("OwensLab/commfor-model-384")` (PyTorchModelHubMixin; deps: torch, timm, huggingface_hub). ViT-Small/patch16/384, 21.8M params, MIT (code + weights).
- **Gotcha:** checkpoint `config.json` hardcodes `device: "cuda"` — explicitly override to `mps`/`cpu` at load. MPS correctness is UNVERIFIED upstream: the sanity script also runs 5 images on CPU and asserts `|logit_mps − logit_cpu| < 1e-2`, else falls back to CPU and warns.
- Preprocessing (author-confirmed, main branch): `Resize(440)` shorter-edge → `CenterCrop(384)` → `ToTensor()` [0,1] → `Normalize(mean=[0.485,0.456,0.406], std=[0.229,0.224,0.225])`, RGB.
- Output: RAW logit; adapter applies sigmoid exactly once; label convention real=0/fake=1 → high = AI-generated (matches our polarity, no flip needed).
- `model_version` = HF repo revision SHA recorded at load.
- **DoD:** sanity script `scripts/sanity_check.py` — ≥20 real + ≥20 fake smoke images; report per-class mean `p_fake` + AUROC. **Clean-smoke AUROC ≤ 0.9 halts the build and triggers diagnosis** (preprocessing alarm) — it is explicitly NOT an automatic model rejection, since smoke-source composition affects the value [non-blocking note 2]. Plus the MPS-vs-CPU consistency check above.

## 6. `src/pipeline/service.py` — importable prediction service [N8]
**The single decision path.** Gradio, `scripts/predict.py`, `scripts/infer_dir.py`, and the eval harness all import this; nothing spawns a CLI subprocess and nothing re-implements thresholding.
```python
class PredictionService:
    def __init__(self, config: Config, experts: list[Expert], threshold: float): ...
    def predict_image(self, path_or_bytes, transform_id: str = "clean") -> PredictionRecord
    def predict_decoded(self, img: DecodedImage, transform_id: str = "clean") -> PredictionRecord
```
- `PredictionRecord` = `prediction.v1`, matching `specs/phase0-product.md` §2 field-for-field (I own the schema, Codex consumes it): `schema_version, image{sha256,width,height,format,warnings}, transform_id, p_fake, forced_prediction, decision, reliability(null in Phase 0), experts[], expert_failures[], rescue_invoked, inference_ms{total,components}, warnings, pipeline_version, threshold_used`.
- Phase 0 `p_fake` = CF-384's `p_fake` (naive mean once >1 expert exists; the router replaces this in Phase 2). `decision` ∈ {`REAL`,`AI-GENERATED`} — `UNCERTAIN` only when the abstention layer is validated. `reliability` stays `null` until an estimator exists.
- Decode failure raises `DecodeError` to the caller (typed); every-expert failure raises a typed `PredictionError`. **The service never returns a fabricated score.**
- **DoD:** service returns identical `p_fake` for the same image via all three entry points (CLI, direct import, Gradio) — asserted in `tests/test_service_parity.py`.

## 6a. `scripts/predict.py` — thin CLI [N8]
`python scripts/predict.py IMG [--transform cond_id] [--json]` → builds the service, calls `predict_image`, prints a table (expert, p_fake, latency, warnings) plus the verdict, or emits `prediction.v1` JSON with `--json`. **Contains no decision logic** — argument parsing, formatting, exit codes only.

## 6b. `scripts/infer_dir.py` — REQUIRED official deliverable (build in Phase 1)
Per `docs/00a-brief-addendum-2026-08-26.md` (evidence: `docs/evidence/2026-08-26_track5-deliverables.png` [N10]): takes an image directory, outputs a JSON array of `{image_path, pred}`, `pred` ∈ [0,1] float, higher = AI-generated (our final calibrated `p_fake`; until the router exists, CF-384's calibrated score). Thin wrapper over `PredictionService` — same config, preprocessing, calibration.
- Deterministic ordering by normalized relative path; atomic write; case-insensitive extension match; bounded memory; per-file error isolation; progress logging.
- **[N9] Corrupt/unreadable file policy — PROPOSAL, needs one Codex ACK round** (counter to `specs/phase0-product.md` §5, which defaults to omitting failed rows):
  **Default:** emit a row for **every recognized image file**, so the array length always equals the input count and a judge harness that zips paths to predictions cannot silently misalign. A file that fails to decode gets `{"image_path": ..., "pred": null, "error": "decode_failed"}` — a null, never an invented float. Process exits 0; a stderr summary reports the failure count.
  **Flags:** `--errors {null,skip,strict}` (default `null`; `skip` omits failed rows; `strict` exits nonzero on the first failure). Our own gate smoke runs `--strict` so a regression cannot hide.
  **Rationale:** the addendum's binding text says the JSON contains `image_path` and `pred` *for each image* — a missing row violates that more visibly than a null does, and null satisfies "no invented score". If Codex prefers `skip` as the default, one CHANNEL round settles it before Phase 1 build; Phase 0 is unblocked either way.

## 7. `configs/transforms.yaml`
All numeric parameters + library/version pins + `PIPELINE_VERSION`. **Single authoritative value path** [non-blocking note 3]: the registry reads this file; Python holds no duplicate numeric literals; a startup assertion checks the yaml key set equals the 20 registry ids and that the version string matches `src/pipeline/version.py`.

## Explicitly out of Phase 0
LOTA adapter (Phase 1, spec addendum after `handoffs/2026-08-26_lota-integration.md`), quality descriptors, probes, router, eval harness (Codex spec), Gradio (Codex spec), `infer_dir.py` (Phase 1).

## Build order & verification chain
`version.py` → decode → transforms → golden → `experts/base.py` → CF adapter → service → sanity → predict CLI. Each step: Sonnet implements → Claude reviews the diff against its DoD → commit `[claude]`.
