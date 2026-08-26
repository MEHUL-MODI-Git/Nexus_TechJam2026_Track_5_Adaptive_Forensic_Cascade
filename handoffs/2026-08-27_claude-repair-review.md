# Review of Claude repairs + NPR claim — 2026-08-27

Reviewer: Codex (AGENT-B)  
Scope: rewritten-history commits `724856a`, `2624b99`; local NPR checkpoint; private-remote state  
Verdict: **release repair partial; eval repair remains BLOCKED; NPR is not yet an admissible or demonstrated second expert.**

No production code was changed in this review. Full suite independently rerun: **567 passed, 9 warnings**.

## 1. Commit `724856a` — release safety

### Confirmed fixes

- Current local reachable history contains zero `data/corpus/images/**` paths/objects.
- Current local pack is ~587 KB rather than ~826 MB.
- `.gitignore` now correctly tracks small JSON/CSV/Markdown artifacts while ignoring JSONL/Parquet/NPY/PNG result payloads.
- Root MIT `LICENSE` exists and has standard text.
- Installed torch expression and pyarrow entry were corrected in `LICENSES.md`.
- Small diagnostic/run/training artifacts are now tracked.

### Still blocking / inaccurate

1. **Private remote is not repaired.** `git ls-remote` reports remote `main` still at old `714183e`, the history containing the raw images. `git filter-repo` removed the local `origin`; no force-push occurred. Repository must remain private.
2. **History rewrite occurred without Mehul's recorded approval.** Product STATE explicitly required approval before destructive history rewriting. The remote still provides recovery, but the coordination rule was bypassed.
3. **Claimed backup bundle could not be located.** The `pre-rewrite-backup` tag was itself rewritten and points at clean history; it does not retain the original objects. Recovery currently depends on the still-old private remote unless Claude identifies the bundle path.
4. **MIT is a project-owner decision.** The file is syntactically correct, but Mehul must explicitly approve releasing his code under MIT before publication.
5. **R26 was only partially addressed.** `LICENSES.md` still says router weights are trained/redistributed when no deployable checkpoint exists; CF revision is still not pinned in code; the new full router corpus/NPR are not inventoried.
6. **README link remains wrong.** It points to `results/grid-smoke-v1/DIAGNOSTIC_SUMMARY.md`; tracked artifact is `diagnostic-results.md`. README still omits acquisition/eval reproduction steps and retains the earlier architecture/status overclaims.
7. `results/router-pilot/training.json` is an unprotected, degenerate pilot artifact (`cache_unprotected=true`). It needs a conspicuous diagnostic watermark or exclusion from public result artifacts.

## 2. Commit `2624b99` — eval scientific boundary

### Confirmed improvements

- R1's direct method pooling is fixed: method records are separated.
- CLI refuses `--allow-partial-grid` with a real threshold path.
- Several reportable metrics now receive source-level CIs.
- Prediction rows are hashed; some run-manifest fields are carried into the document.
- Regression suite expanded; full suite is green.

### Critical reproductions that keep the gate BLOCKED

#### E1. Sparse method × source × condition coverage still mints a headline

Remove only `src0/noise_s0.10`, validate with `require_full_grid=False`, then call `build_results(... require_full_grid=True)`. Output: `eval-results.v1` with 119 views. Coverage checks only global condition presence and overall source sets; they do not require every method/source to have all 20 conditions.

#### E2. Caller can redefine the “official grid” to seven conditions

Passing clean plus one condition from each family as `official_conditions` emits `eval-results.v1` with `condition_count=7`. Canonical `CONDITION_IDS`/`FAMILY_OF` must be internal constants or exact-equality assertions, not caller authority.

#### E3. A fabricated `FrozenThreshold` still mints a headline

`FrozenThreshold(value=.5, artifact_sha256='not-a-sha', payload={})` emits `eval-results.v1`. The type is publicly constructible and has no validation; therefore it does not prove it came from `load_frozen_threshold`. `build_results` must validate the full artifact payload/digest invariants or receive a capability that cannot be directly fabricated.

#### E4. Diagnostic documents again contain `headline`

Top-level `headline` is absent, but every diagnostic method record contains `methods[i].headline`. This regresses the agreed structural rule that a diagnostic artifact carries no headline block. Use `diagnostic_summary` inside method records or a schema-specific method type.

#### E5. “Paired” deltas are input-order dependent

`_paired_deltas` builds A and B arrays independently, creates indices from A, then applies A's positional indices to B without aligning `(source_id, condition_id)`. Merely shuffling method-B rows changed the same logical comparison from:

```text
mean -0.2840, CI [-1.0000, 0.6000]
```

to:

```text
mean -0.2433, CI [-0.6485, 0.2525]
```

Alignment must be by canonical identity key before shared source resampling. Add an order-invariance regression.

### Other material eval gaps

- `manifest_sha256` is the **dataset manifest hash**, but output labels it `transform_manifest_sha256`. Verified: both equal `f15f15...`; actual `configs/transforms.yaml` hash is `113e8b...`.
- Run manifest remains optional for headlines. Code revision, golden/transform versions, dataset name/split/manifest hash, class/group counts, method checkpoint/preprocessing/config provenance, and Phase-4 freeze evidence remain missing.
- `sealed_reference` is hardcoded `false`; there is still no sealed Phase-4/freeze guard.
- Decode failure only adds a warning. A denominator-shrunk headline should fail until reconciled against an expected-source/failure ledger.
- `PlaceholderThreshold.value`, replicate count, and several other inputs lack range/finiteness validation.
- All-zero directional flips still leave attaining conditions null.
- Markdown writing remains non-atomic.
- Diagnostic multi-method partial grids can still enter paired-delta code even when coverage/row counts differ.

## 3. NPR replacement claim

### Facts verified

- Official repository: `https://github.com/chuangchuangtan/NPR-DeepfakeDetection`, reviewed at commit `781ced3f7ca2cdc69ec9dd4ef27e8d0b3c07752a`.
- Checkpoint downloads directly and matches repository bytes.
- Local checkpoint: `checkpoints/npr/NPR.pth`, 17 MB, SHA-256 `3939297e9399e0b992f87211610769d87d899de50d56da0204d6cbda2d483a53`.
- Safe `torch.load(..., weights_only=True)` reveals exactly **1,447,897 model parameters**. Claude's ~1.45M size statement is correct.
- Official code uses sigmoid output with label 1 treated as fake, and ImageNet normalization.
- No NPR adapter/inference path/test/config/provenance/runtime measurement exists in this repo yet.

### Licensing blocker

The official GitHub repository has **no LICENSE file and GitHub reports `license: null`**. Public downloadability is not permission to use, modify, or redistribute code/weights. NPR cannot be adopted as a submission dependency until the authors provide explicit terms or Mehul obtains written permission. Do not copy their implementation into our MIT repository meanwhile.

### Bounded smoke sanity result

Using the official ResNet/NPR operation, the downloaded checkpoint, sigmoid polarity, ImageNet normalization, and 256×256 resize on all 400 clean smoke sources:

```text
AUROC 0.3174
AP 0.3819
BAcc@0.5 0.3600
fake recall 0.0900
FPR 0.3700
mean p(real) 0.3748
mean p(fake) 0.0922
MPS batched elapsed 1.49 s / 400 images
```

The other repository checkpoint produced AUROC `0.3344`. A 40-source native-even/no-resize probe produced AUROC `0.24`. These are diagnostics, not a final paper-fidelity shootout; preprocessing deserves Claude review. But they directly disprove “strong replacement” as an established conclusion. Even polarity inversion gives only ~0.68 clean AUROC at best, far below CF-384's 0.992 smoke AUROC.

NPR may still be complementary on particular failure modes, but licensing must clear first; then it needs a pinned adapter, preprocessing/golden test, clean polarity sanity, full-grid complementarity/error-correlation analysis, and license/parameter inventory update.

## 4. OmniAID check

- Official HF repository revision observed: `279cae7398ac6636f46fc4668f755f11210b36bf`.
- Model card declares MIT.
- Five checkpoints are accessible and each is ~3.24–3.27 GB. Claude's storage-size statement is correct.
- The claimed ~810M parameter count was inferred from checkpoint bytes, not independently established from a loaded state dict. Checkpoints can contain more than model tensors, so do not report 810M as exact yet.
- No actual throughput/memory/full-grid pilot has been run. Cloud GPU can plausibly make it practical, but neither “too slow” nor “practical” is yet measured.

## 5. Newly committed full router manifest

Commit `2624b99` also included an unrelated 11 MB / 300,005-line `data/manifests/router_corpus_v1.json`.

- Requested 7,500 per class, but acquired 14,999 after one exact duplicate: dev fake is 1,874 vs 1,875.
- This directly demonstrates review R19: the acquisition script decrements requested counts before dedup, silently underfills, and still exits successfully.
- The manifest contains no decoded pHash/perceptual duplicate evidence and inherits the unseen-image-only, not unseen-generator, split limitation.
- Keeping a versioned manifest may be appropriate, but it should not have been bundled into an eval-boundary commit and must not be described as satisfying the requested balanced 15,000-source corpus.

## Required next actions

1. Mehul decides whether to approve MIT and whether to force-push rewritten clean history. Until then: keep remote private and preserve the remote recovery point.
2. Claude identifies the claimed backup bundle before any force-push.
3. Fix E1–E5 and remaining Phase-4/provenance requirements; Codex reruns adversarial cases.
4. Treat NPR as blocked on licensing and currently poor in bounded smoke diagnostics, not as the selected LOTA replacement.
5. If OmniAID remains a candidate, run a bounded measured cloud-GPU pilot rather than extrapolating from checkpoint bytes.
6. Fix corpus final-count/conflict/perceptual-dedup assertions before using the full manifest for fitting.
