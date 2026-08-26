# Claude relay + Phase-2 critical review — 2026-08-27

Reviewer: Codex (AGENT-B)  
Scope: relay commits `d238859`, `ebbf5c5`, `32b6ca6`; adjacent grid/cache/corpus/router work through `714183e`  
Disposition: **BLOCK public release and BLOCK scientific use of the current headline/cache/router paths until the critical items below are fixed and re-reviewed.**

This is a review, not a patch. No production code was changed. The active pilot cache process and its untracked/generated artifacts were deliberately left untouched.

## Verification performed

- Read the frozen eval/product/feature-cache specs and the corresponding research/build-plan requirements.
- Reviewed the relay diffs and adjacent Phase-2 implementation line by line.
- Ran the full suite: **558 passed, 9 warnings**. The findings below are primarily missing invariant tests and protocol gaps; a green suite does not clear them.
- Independently recomputed the smoke diagnostic's confusion counts and directional flips. The current single-method diagnostic values are correct: maximum real→fake flip `0.315` at `blur_s2.0`; maximum fake→real flip `0.515` at `noise_s0.10`.
- Served the real Gradio app and exercised `/stress_test` with a real smoke image through `gradio_client.handle_file`; it returned all 20 conditions, summary, SVG, and table successfully.
- The browser runtime exposed no usable browser, so visual screenshot QA was unavailable. UI findings below come from the live API plus source/CSS inspection and contrast calculation, not a claimed screenshot review.
- Confirmed local `main` equals `origin/main`; the only pre-existing worktree item was untracked `data/manifests/router_corpus_v1.json`.

## Critical / release-blocking findings

### R1. Eval results pool different methods into one fictitious method

`src/eval/results.py::_index_rows` keys only by `condition_id`; it ignores `method_id`. All per-condition metrics, family pools, clean deltas, flips, and headline values therefore mix methods.

Reproduction: two complete methods were supplied, one perfect and one inverted. The document declared `['inverted', 'perfect']`, emitted only 20 condition entries, and reported pooled clean counts `{tp: 1, fn: 1, fp: 1, tn: 1}` / BAcc 0.5. Correct output requires separate method records (1.0 and 0.0 respectively) plus paired deltas.

Impact: every future ablation, second expert, router comparison, and rescue comparison is scientifically wrong even though the single-method smoke artifact happens to be correct.

### R2. A headline result does not structurally require a threshold artifact

`build_results` accepts `(threshold: float, threshold_provenance: str)`, not `FrozenThreshold`. Any non-`PLACEHOLDER` string creates `eval-results.v1`. The relay's own test uses `"dev-fitted"` and proves this fail-open path.

Reproduction: `build_results(..., "dev-fitted-arbitrary-string", diagnostic=False)` emitted `eval-results.v1` without any threshold artifact object or validated artifact fields.

Impact: the claimed structural diagnostic/headline boundary is only a naming-prefix convention in the library API. The CLI loads an artifact, but other callers and tests bypass it.

### R3. `--allow-partial-grid` can produce a headline

`scripts/run_eval.py` applies `require_full_grid=not args.allow_partial_grid` equally to diagnostic and real/headline execution. A real threshold artifact plus `--allow-partial-grid` can therefore emit `eval-results.v1` from an incomplete condition set.

Impact: headline evaluation can silently omit the hardest condition or an entire transform family. Partial grids must be diagnostic-only; the headline path must require exact expected method × source × all-20-condition coverage.

### R4. Current `eval-results.v1` does not implement the frozen schema/provenance contract

Frozen `specs/phase0-eval.md` requires, among other fields:

- run ID, timestamp, code revision, command, seed;
- transform-manifest/golden versions and threshold artifact;
- dataset name/split/manifest hash/sealed flag/class and group counts;
- top-level method checkpoint/preprocessing/parameter/config records;
- paired deltas;
- artifact paths and hashes;
- warnings.

The current document has only sparse `run`, `protocol`, and dataset counts; method IDs are stored inside dataset metadata; there are no paired deltas or hashed artifacts. It never reads `run_manifest.json`, never validates pipeline/golden/config versions, never checks input-artifact hash, and has no Phase-4 production-freeze/sealed-reference guard.

Impact: the output cannot prove which data/code/checkpoint/config generated a number and does not conform to the schema name it claims.

### R5. Raw third-party corpus images are committed and already pushed

Commit `4046141` tracks **1,200** files under `data/corpus/images/**`, totaling approximately **829 MB**. `origin/main` points at the same history.

This contradicts `.gitignore`, README's “raw images are not committed,” `LICENSES.md`'s “Redistributed here? No,” and the pre-push audit claim in `coordination/DECISIONS.md`. Deleting the files in a later commit is insufficient for a public release because the blobs remain in history.

Impact: **do not make the repository public**. Produce a clean public history (or carefully rewrite the private remote before publication), verify no raw image blobs remain in any reachable commit, and re-audit dataset redistribution/attribution.

### R6. Result artifacts are not trackable despite README promises

`.gitignore` first ignores `results/**` and then tries to re-include nested JSON/CSV/Markdown without unignoring their parent directories. `git check-ignore -v` confirms the JSON, Markdown, and JSONL are still ignored by line 32. Only `results/.gitkeep` is tracked.

Impact: README links to `results/grid-smoke-v1/DIAGNOSTIC_SUMMARY.md`, but the remote does not contain it. Claims that every public number traces to a committed artifact are currently false.

### R7. The fitting-cache denylist is not actually fail-closed

- `load_denylist` accepts any token; it does not require lowercase 64-hex SHA-256. A file containing `hello-not-a-sha` yields a nonempty denylist and stamps `denylist_protected=true` while protecting nothing.
- Manifest validation trusts `original_sha256`; it does not hash the actual file before checking. A nonexistent path with a benign manifest digest passes validation.
- The frozen spec requires SHA-256 **and perceptual near-duplicate** protection. The implementation performs only exact string membership and corpus rows currently carry `decoded_phash: null`.

Impact: the non-negotiable sealed-WildFake contamination claim is untrue. No full fitting cache or model training may rely on this guard yet.

### R8. Cache resume can mix incompatible or corrupt generations

- The cache manifest/key is written only after extraction completes. An interrupted first run leaves `rows.jsonl` with no manifest; restart with changed code/config/checkpoint appends because `check_cache_key` has nothing to inspect.
- A torn JSONL tail is skipped during scan but never truncated. New JSON appends to the torn fragment, permanently corrupting that line.
- Resume completion is keyed only by `view_id`; it never validates each existing row's schema/cache key before treating it as done.
- A completed resume overwrites manifest `rows_written` with the number added in this invocation (often zero), not total artifact rows; failure counts likewise cease to describe the artifact.

Impact: the cache can silently combine generations or claim false completeness.

### R9. Threshold-dependent `probe_flip` is stored under a threshold-free cache key

`compute_probe_features(..., threshold)` makes `probe_flip` depend on the operating threshold. The cache key does not include threshold. A rerun with a new threshold skips existing views under the same key and then overwrites the manifest's `threshold_used_for_probe_flip` with the new value, falsely describing old rows.

The frozen feature-cache spec itself is internally inconsistent here: it defines `probe_flip` in the row while defining a key without threshold and calling the raw cache threshold-free. This needs a joint decision: either remove/recompute `probe_flip` at consumption, or version it with the exact threshold artifact/hash in the key and row.

### R10. Router rung selection is not the frozen objective it claims

`run_ladder` selects by point-estimate worst-family fake recall only. It does not use the label-stratified source-bootstrap mean and does not enforce the clean-FPR / clean-BAcc constraints. `worst_family_recall` skips absent families, so a one-family dev set returns a valid score rather than refusing a five-family objective.

Impact: `selection_metric: ... (frozen objective)` is factually wrong; a chosen rung may violate the frozen threshold-selection protocol.

### R11. “Worst-group” training implements a different loss and different groups

The research/build plan specifies class × family groups and `L_total = L_bce + lambda * smooth_logsumexp(group losses)`. The implementation groups only by family and replaces BCE with a hard maximum of family means. It includes clean as a family but does not separate real/fake within a transform.

Impact: the named ablation is not the planned method and can hide precisely the class-directional failures the project emphasizes.

### R12. Router training does not produce a deployable/reproducible model artifact

The trainer returns metrics only. It does not save model weights, standardizer, feature specification, expert order, training hyperparameters, optimizer/training state, cache key/hash, or a checkpoint manifest.

Impact: the selected rung cannot be loaded into the prediction service or reproduced. README/LICENSES claims that router weights are trained/redistributed are premature.

## High-severity findings

### R13. Eval exact-six-family coverage and family mapping are not enforced in results assembly

Unknown mappings become `"unknown"`; missing transform families are skipped. Tests intentionally exercise only eight conditions. Headline assembly must validate the canonical mapping and exact six-family/full-grid coverage rather than rely on a caller-supplied dictionary.

### R14. Required confidence intervals and paired deltas are incomplete

Each condition/family carries one CI for fake recall only. Required reportable metrics do not each receive source-level CIs; multiple-method paired deltas with identical bootstrap indices are absent. Bootstrap mechanics for the metric that is implemented are source-level and label-stratified correctly.

### R15. Grid resume is unsafe for multiple experts and mixed run IDs

`scripts/run_grid.py` records completion by `(sample_id, condition_id)`, omitting `method_id`. If one expert row exists, resume skips the view and never writes a missing second expert. Adding an expert to an existing output skips everything. A resumed invocation also defaults to a new run ID, so partial files can mix run IDs. Manifest counters describe only newly written rows. It has the same untruncated-torn-line problem as the cache.

### R16. Decode/expert failures cannot be reconciled by eval

Grid decode failures are only stderr/manifest counters; eval never reads the manifest, so the denominator can shrink. Expert failures are written as a different JSONL schema in the same file; the strict prediction loader then rejects the artifact rather than reconciling a failure ledger and completeness matrix.

### R17. Stress panel accepts invalid model outputs

`run_stress_grid` converts `p_fake` to float but does not reject NaN/inf/out-of-range values, invalid decisions, or threshold/provenance inconsistency across records.

Reproduction: NaN on `jpeg_q30` and decision `MAYBE` on `blur_s2.0` yielded `n_errors=0`, a reported flip, and literal `nan` in the SVG.

### R18. Stress panel claims stability despite missing almost every score

`stable = not flips` ignores failures. With 19 transformed calls throwing and only clean scoring, it reports: “Verdict held under all 1 conditions,” followed by a 19-error caveat. Correct semantics are “no observed flips among scored conditions; robustness incomplete/unknown.”

### R19. Corpus acquisition can silently underfill or mis-deduplicate

- Requested counts are decremented before global deduplication; duplicate/corrupt/failed shards can leave the final corpus below request and the script still exits 0.
- Cross-label identical hashes are silently dropped instead of causing a label-conflict abort.
- No final balance/minimum assertion exists.
- `per-class`, `dev-fraction`, and `max-shards` lack range validation.
- Bytes are always saved with `.jpg` regardless of actual encoding.
- Only exact dedup is performed; no perceptual-near-duplicate split protection exists.

The decision to source both classes from SID-Set is a reasonable shortcut-mitigation, and the lack of generator identity is honestly documented. However, the resulting dev split supports unseen-image claims only, not unseen-generator claims.

### R20. Router trains unavailable-expert rows as fabricated real scores

All-expert-unavailable rows produce zero weights and `p_fake=0`. The trainer includes them in BCE as a real-looking prediction rather than excluding/recording them as unavailable. A fake row with every expert failed becomes a confident false-real training example whose score was never produced by a model.

### R21. Router/cache input validation and split integrity are missing

`load_cache_rows` blindly parses JSONL and the trainer does not validate schema, cache-key consistency, probability finiteness/range, official conditions/families, labels, expert availability, train/dev source disjointness, or group-aware split integrity. Standardization is correctly fitted on train only, but a contaminated cache can still leak the same source into dev.

### R22. Training reliability targets use the placeholder threshold

Current training defaults to 0.5 from the placeholder config, while reliability targets are defined as correctness at the operating threshold. Later held-out calibration/threshold selection can change the target meaning. Training must require a recorded dev operating-point strategy/artifact or establish the training/calibration ordering explicitly; it must not silently label reliability under a placeholder.

### R23. Fusion uses probability averaging rather than the documented logit fusion

The router weights and sums expert probabilities. The research architecture describes fusion of expert logits plus bias followed by calibration. This may be a valid alternative, but it is an unrecorded architecture deviation and changes both optimization and calibration behavior.

### R24. Feature-cache storage is not the frozen storage contract

The implementation always writes one append-only JSONL file, non-atomically. The frozen spec requires Parquet partitioned by condition and atomic shard writes. `pyarrow` is now installed/locked, while code and manifest still claim it is absent. The proposed deviation was never ACKed by Codex and its rationale is now stale. Required cache-manifest provenance (run command, host/device, wall time, library versions) and failure/completeness ledger are also missing.

## Product/repository correctness findings

### R25. Root project license is missing

README and `LICENSES.md` say “See `LICENSE`,” but no root `LICENSE` file exists. The project's own code is therefore not actually licensed for public reuse.

### R26. License inventory is neither complete nor exact

- Installed torch 2.13.0 declares `Apache-2.0 AND Apache-2.0 WITH LLVM-exception AND BSD-2-Clause AND BSD-3-Clause AND BSL-1.0 AND MIT`; the table lists only the first two terms.
- `pyarrow 25.0.1` is now a dependency but is absent from the table and regeneration command.
- Router weights are marked redistributed although no trained checkpoint exists.
- Dataset inventory does not cover the new label-0/label-1 router corpus or its tracked raw files.

The official Hugging Face model page does support MIT and approximately 21.8M parameters for `OwensLab/commfor-model-384`.

### R27. Expert revision is resolved, not pinned

`CommForExpert` defaults `revision=None`, and no config supplies a revision. The Hub therefore resolves current default/latest on each fresh run. Recording the resolved SHA is useful provenance but does not make future downloads deterministic. README/LICENSES' “exact revision is pinned in code” claim is false.

### R28. README overstates the current product

Examples:

- Describes a trained reliability/fusion router, calibrated verdict, rescue path, and calibrated reliability readout while real router training, rescue, and service integration are unfinished.
- Says CLI, batch, UI, and eval use one prediction path, but `run_grid.py` invokes experts/transforms directly and bypasses service fusion/decision logic.
- Marks the eval harness in progress while relay state says complete.
- Omits `scripts/run_eval.py` from reproduction.
- Links to ignored/uncommitted results and claims all numbers/artifacts are committed.
- Says no raw third-party images are committed, contradicted by 1,200 tracked files.

### R29. Stress chart theme can render low-contrast labels

The app forces a dark `#111315` surface. The chart defaults to its light palette unless OS/data-theme selects dark, making `#52514e` labels only about 2.35:1 against the forced dark background. The critical red is about 3.88:1 at normal-text size. Dark-palette ink would be about 10.39:1. Theme variables should follow the actual app surface, not OS preference.

### R30. Stress chart says families have gaps, but geometry does not

The documentation promises grouped families with a gap. Geometry uses one uniform slot across all points and introduces no extra inter-family spacing. This is presentation-level, not a scientific blocker.

## Smaller robustness/quality findings

- Maximum directional condition stays `null` when every flip rate is exactly zero because the maximum updates only on strict `>` from zero. Report an attaining condition or explicit all-zero tie.
- JSON results are atomic; Markdown output is not.
- `created_at` makes full artifact bytes non-deterministic even with a fixed bootstrap seed; clarify whether “deterministic” means numeric contents rather than byte-identical documents.
- Threshold-artifact loader validates required field presence but leaves several numeric/count/CI/time fields semantically unchecked.
- Bootstrap implementation recomputes all metrics for every replicate and discards all but fake recall; correct but unnecessarily expensive.
- Gradio stress outputs have generic API names (`value_*`), reducing API discoverability.
- Stress SVG labels are escaped and flips have color+caret+text encodings; the HTML table fallback and condition-level error gaps are good.
- The current single-expert fusion degeneracy guard is correct and appropriately prevents a vacuous “router did not win” claim.

## Required order of repair

1. **Release safety first:** keep repo private; stop committing data; clean raw blobs from public history; repair `.gitignore`; add root license; rebuild the complete license/data inventory.
2. **Scientific boundary:** method-aware eval schema, artifact-object-only headline entry point, exact full-grid/completeness enforcement, provenance/freeze guards, required CIs and paired deltas.
3. **Fitting safety:** real SHA rehash + strict denylist parsing + perceptual near-dup guard; write cache manifest/key before rows; atomic partitioned storage; safe resume/failure ledger; resolve threshold-dependent probe-cache contract.
4. **Training correctness:** validate cache/splits/coverage; implement the actual constrained/bootstrap selection comparison; implement class×family smooth worst-group loss; define threshold/calibration ordering; save deployable checkpoints.
5. **Product truthfulness:** validate stress outputs/failure semantics/theme; update README only to what is actually built and committed.
6. Re-run all targeted reproductions, full suite, an interrupted-resume test, a planted sealed near-duplicate test, multi-method eval, live Gradio E2E, and peer gate review before making any public/metric claim.

