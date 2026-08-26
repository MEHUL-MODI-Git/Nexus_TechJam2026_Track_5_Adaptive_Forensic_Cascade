# SPEC — feature-cache row v1 (Phase 2 backbone)

> Author: Claude (heavy), owner of this contract per the A-006 §3 split. **Codex reviews.**
> **Status: v3 — 2026-08-27.** v2's internal inconsistency is resolved (Codex R9): the spec called the raw cache threshold-free while storing the threshold-dependent `probe_flip` in a row keyed without a threshold. **Resolution: `probe_flip` is REMOVED from the row and derived at consumption** from the stored `probe_scores` plus the expert's `p_fake` and whatever threshold is in force. The cache is now genuinely threshold-free, and a threshold change no longer silently invalidates rows it cannot detect. Schema bumped to `feature-cache-row.v2`. **Codex: this changes a frozen contract — please ACK or counter.**
>
> **Status: v2 — FROZEN 2026-08-27.** All 6 required fixes from Codex's B-009 APPROVE-WITH-FIXES applied (marked `[F#]`), plus its two preference calls (partition by `condition_id` with `source_group` as a column; entropy computed at consumption, not stored). Correcting a record error: the 2026-08-26 spec-freeze entry listed "feature-cache row v1" among the frozen contracts, but no schema had actually been written — only referenced. The golden scheme in that clause WAS real; this half was not. Freezing this file closes the gap.
> Consumers: the router trainer (Claude, Phase 2), the eval harness (Codex — a cached row must be replayable into `prediction-row.v1` without recomputation).

## 0. Why this exists

The router is trained on features, not images. Extracting those features means running every expert and every probe over ~30k sources × the transform grid — hours of compute we must not repeat by accident. The cache is therefore the one artifact that, if silently stale or subtly wrong, corrupts every number downstream while looking perfectly healthy.

Hence the two rules everything below serves:
1. **A row must carry enough provenance to prove which code produced it.** Version drift invalidates, never silently reuses.
2. **A row records what happened, including failure.** No imputation, ever.

## 1. Cache key and invalidation

A cached row is valid only for the exact `cache_key` that produced it:

**[F6]** The key hashes a CANONICAL JSON OBJECT — `json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")` — never pipe-concatenated values, whose component boundaries are ambiguous (a value containing `|` could forge another key's digest):

```python
key_object = {
    "feature_schema_version": "feature-cache-row.v1",
    "pipeline_version": PIPELINE_VERSION,
    "probe_version": PROBE_VERSION,
    "transform_config_sha256": ...,
    "probe_config_sha256": ...,
    "expert_fingerprints": ["<expert_id>@<model_version>", ...],  # sorted
}
cache_key = sha256(json.dumps(key_object, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
```
`manifest.json` stores **that exact object** alongside the digest, so the key is always re-derivable and auditable.

- Any change to decode/transform behavior, probe definitions, expert checkpoints, or this schema produces a different key. **Rows under a different key are never reused, never partially merged.**
- The cache directory stores a `manifest.json` carrying the key, its component parts, the run command, host/device, wall-clock, and library versions (`torch`, `torchvision`, `pillow`, `numpy`).
- **Startup assertion:** if the computed key differs from the manifest's, the job REFUSES to append. It either starts a new cache directory or exits — it must never mix.

## 2. Row schema — `feature-cache-row.v1`

One row per `(source_id, condition_id)`. Expert-level values are nested per expert so N experts need no schema change.

```text
schema_version: "feature-cache-row.v1"
cache_key: str

# --- identity / provenance (from the dataset manifest, never from filenames) ---
# [F2] Identity, reconciled with the product smoke-manifest (whose `sample_id`
# identifies a CLEAN SOURCE, not a view). The cache never redefines that field.
source_sample_id: str           # the dataset manifest's sample_id (clean source)
view_id: str                    # DETERMINISTIC: f"{source_sample_id}:{condition_id}"
source_id: str                  # clean view and all transformed views share this
relative_path: str              # [F2] source path, retained for replay
condition_id: str               # one of the 20 official ids, or "clean"
family: str                     # jpeg|blur|resize|noise|color|crop|clean
label: int                      # 0 real, 1 AI-generated
dataset: str
dataset_split: str              # train|dev  (test/sealed NEVER cached for fitting)
source_group: str               # generator or real-source grouping (split unit)
generator: str | null
original_sha256: str            # of the ORIGINAL SOURCE FILE BYTES -- shared by all
                                # 20 views of a source; CANNOT identify a view
view_rgb_sha256: str            # [F3] sha256 of the canonical TRANSFORMED RGB array
                                # bytes; this is what eval's content_sha256 maps to
decoded_phash: str
license_id: str

# [F4] Preserved so replay can populate prediction-row.v1.warnings and so
# preprocessing anomalies stay auditable after the images are gone.
view_warnings: list[str]        # decode + transform warnings for this view

# --- per-expert block (dict keyed by expert_id) ---
experts: {
  "<expert_id>": {
    raw_logit: float,           # finite; higher = AI-generated
    p_fake: float,              # finite [0,1]
    inference_ms: float,        # NOTE: binary entropy is NOT stored -- it is a pure
                                # function of p_fake and a stored copy can drift from
                                # its source. One canonical helper computes it at
                                # consumption (Codex B-009).
    embedding_key: str | null,  # key into the sidecar array store; NEVER inline
    embedding_dim: int | null,
    warnings: list[str],        # [F4] successful-expert warnings, kept for replay
    ok: true
  } | {
    ok: false,                  # FAILURE ROW -- no score fields at all
    reason_code: str,
    message: str
  }
}

# --- probe block (per expert; doc 03 step 4) ---
probes: {
  "<expert_id>": {
    probe_scores: {probe_id: float},   # successful probes only
    n_probes_ok: int,
    probe_mean: float | null,
    probe_std: float | null,
    probe_range: float | null,
    probe_max_delta: float | null,
    # probe_flip REMOVED in v3 (R9): threshold-dependent, so it cannot live in a
    # threshold-free cache. Derive at consumption via
    # `src.router.features.derive_probe_flip(block, base_p_fake, threshold)`.
    probe_failures: [{probe_id, reason_code, message}]
  }
}

# --- quality descriptors (quality-descriptors.v1, computed on the TRANSFORMED view) ---
quality: {width, height, megapixels, aspect_ratio, is_portrait,
          blur_varlap, blockiness, noise_sigma,
          luminance_mean, luminance_std, saturation_mean,
          clipped_low_frac, clipped_high_frac}

# --- cross-expert features: PRESENT ONLY when >=2 experts succeeded ---
# [F5] `threshold_agreement` REMOVED: it is threshold-artifact-dependent, and a
# threshold-free raw cache must not bake in a threshold that later changes.
# It is computed at train/eval consumption instead. Pairwise form is used so the
# schema is defined for N>2 experts (a single abs_p_diff is not).
disagreement: {
  pairwise_abs_p_diff: {"<expert_a>|<expert_b>": float},  # sorted id pair keys
  max_abs_p_diff: float,
  mean_abs_p_diff: float,
  n_experts_ok: int
} | null                        # null when fewer than 2 experts succeeded

extracted_at: str               # ISO-8601 UTC
```

### Non-negotiable field rules
- **`ok: false` blocks carry NO score fields.** A failed expert must be structurally incapable of contributing a number (mirrors `ExpertInferenceError`, core spec §4).
- **`probe_flip: null` means unknown.** A default `false` would tell the router "stable" about an image we could not probe — the single most dangerous imputation available here.
- **`disagreement: null` when <2 experts succeeded.** With the LOTA decision open, single-expert rows are expected and legal; the router must consume a missing-indicator, not a zero.
- **Standardization happens at TRAIN time from train-split statistics only** — never precomputed into the cache, or dev leaks into the scaler.
- Embeddings live in a sidecar float32 store keyed by `embedding_key`; JSON/Parquet carries the key. (Core spec §4 [N2].)

## 3. Storage

- **Parquet**, partitioned by `condition_id` (the router samples by condition; the eval harness filters by it).
- Sidecar embeddings: one `.npy` per `(condition_id, expert_id)` shard plus an index; written only if an expert exposes embeddings.
- **Append-only with resumability:** the job writes shard-at-a-time and records completed `(source_id, condition_id)` pairs, so an interrupted 12-hour extraction resumes instead of restarting. Resume verifies `cache_key` first (§1).
- Atomic shard writes (temp + rename), matching `infer_dir.py`'s discipline.

## 4. Hard constraints (enforced IN CODE, before extraction starts)

1. **Sealed-subset denylist.** SHA-256 (and perceptual near-duplicate) check against the sealed WildFake reference subset — COCO val2017 4,998 + DALL-E Advanced 8,843 — runs BEFORE any extraction. A single hit ABORTS the job; it does not skip-and-continue, because a silent skip hides a contaminated manifest.
2. **`val2017` string/source assertion** on every path and metadata field (product spec §3 rule, applied here too).
3. **`dataset_split` may only be `train` or `dev`.** Any test/external/sealed row in a fitting cache is a hard error.
4. **[F1] Duplicate rule, corrected.** All 20 legitimate views of one source SHARE `original_sha256`, so a naive "reject duplicate SHA" rule would reject the entire cache. The real check is: **one `original_sha256` must map to exactly one `source_id`** — the same bytes appearing under two different source identities means a contaminated or double-counted manifest. Enforced at manifest-validation time, before extraction.

## 5. Throughput budget (ties to the Phase-2 compute decision)

- Measured Phase-0 baseline: **~14 ms/image** for CF-384 on MPS (~70 img/s), single-image, no batching.
- Cost per source ≈ `20 conditions × (n_experts + n_probes_on_primary)` forward passes. With 1 expert + 3 probes that is ~80 passes/source ≈ **1.1 s/source** at the measured rate.
- 30k sources ⇒ ~9.3 h; 12k ⇒ ~3.7 h. **Both inside the agreed ≤12h projection**, before any batching gains.
- **Decision rule (already frozen):** if the measured projection exceeds 12 h at Phase-2 entry, shrink SOURCE COUNT — never transform coverage, class balance, or family/severity coverage.
- Batching and a `--limit` smoke mode are required before the full run; the projection is re-measured on ≥200 sources, never assumed.

## 6. Definition of Done

1. `cache_key` mismatch refuses to append (tested).
2. Interrupted job resumes without recomputing completed pairs and without duplicating rows (tested).
3. A failing expert yields `ok: false` with no score fields; a failing probe shrinks `n_probes_ok`; all-probes-fail yields `null` summaries (tested).
4. Single-expert rows produce `disagreement: null`, not zeros (tested).
5. Denylist abort fires on a planted sealed-subset hash (tested — this is the one that protects the headline claim).
6. **Every SUCCESSFUL cached expert block replays into a valid `prediction-row.v1` without inference** (tested jointly with Codex), per the mapping in §8. An `ok: false` block **cannot** yield a prediction row — `p_fake` is required — so it goes to a separate failure/completeness ledger, and headline evaluation FAILS if expected method x source x condition coverage is incomplete. Fusion/router outputs get their own method-specific prediction artifacts.
7. Throughput re-measured on ≥200 sources and the projection recorded in the manifest before the full run.

## 7. Resolved review items (Codex B-009)
- **Partitioning:** by `condition_id` — confirmed right for full-condition evaluation and router sampling. `source_group` stays a COLUMN (not a partition; its cardinality is too high) and serves the grouped split.
- **Entropy:** computed at consumption from `p_fake` via one canonical helper with tests, never stored. A stored derived value can disagree with its source.

## 8. Replay mapping: cached row -> `prediction-row.v1` (Codex-specified, Claude conforms)

For each **successful** expert block:

| prediction-row.v1 | source |
|---|---|
| `run_id` | cache `manifest.json` run_id |
| `method_id` | `expert_id` |
| `sample_id` | `view_id` |
| `source_id`, `image_path`, `label`, `dataset`, `source_group`, `condition_id` | cache row (`image_path` from `relative_path`) |
| `content_sha256` | **`view_rgb_sha256`** (not `original_sha256`) |
| `p_fake` | `experts[<id>].p_fake` |
| `reliability` | `null` |
| `decision` | `null` — eval recomputes at the frozen threshold |
| `rescue_invoked` | `null` |
| `inference_ms` | `experts[<id>].inference_ms` |
| `expert_failures` | all `ok:false` blocks on the row |
| `warnings` | `view_warnings` + that expert's `warnings` |
