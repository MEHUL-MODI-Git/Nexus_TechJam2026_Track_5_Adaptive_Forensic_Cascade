# CHANGELOG — training (newest first, append-only; corrections are new entries)

## 2026-08-27 — 2R.2 corpus audit: sealed denylist built, corpus proven clean, two real defects found

Four measurements, three new scripts (`scripts/hash_corpus.py`, `scripts/build_denylist.py`,
`scripts/diagnostics/corpus_near_duplicates.py`), all Ruff clean. Nothing here fits anything; this is
the contamination and integrity groundwork B-020 §4 requires before the long cache run.

**1. The corpus is 1,200 sources smaller than every document says.** The manifest lists 14,999
sources; only **13,799** exist on disk. The missing 1,200 are **exactly** the pilot set — the ~829 MB
of SID-Set images Codex found tracked in git, deleted during the local history cleanup. The manifest
was never updated, so `acquired: 14999` has been wrong in every plan, STATE and STATUS since. Also
confirms R19 from the other side: the acquisition run took 7,500 real + 7,499 fake and wrote the
manifest anyway, one short, with no assertion on the requested count.

Consequence for the record: the 24k pilot feature cache can still be REPLAYED (the features are
cached) but can no longer be RE-EXTRACTED, because its source images are gone. The DegradePrint
diagnostic remains reproducible via `scripts/diagnostics/degradeprint_probe.py`; it is not
reproducible from images. Worth one honest line wherever that diagnostic is cited.

**2. Byte integrity is perfect.** All 13,799 present images were re-decoded through the canonical
pipeline: **0 SHA-256 mismatches** against the acquisition manifest, 0 decode failures among files
that exist. Nothing has rotted, been resaved, or been swapped.

**3. The perceptual-duplicate threshold was miscalibrated, and I checked it by eye instead of
trusting it.** At the `feature_cache` default of Hamming ≤6 the corpus shows 135 clusters, 172
redundant sources, **1 apparently cross-label cluster** — a "real" and a "fake" that look identical,
which would be a labelling scandal. It is not real. Opening the images: the pair at distance 6 is **a
girl in a paddling pool and an AI puppy**. A second distance-6 pair (Nokia phone / glittery toilet)
false-positives the same way — 64-bit pHash collides on coarse layout (bright subject, dark ground).
Verified in the other direction too: distance **0** (snowboarder, two samples of one prompt) and
distance **4** (three engineers in a tunnel, two samples of one prompt) are genuine near-duplicates.

**Calibrated threshold: Hamming ≤4** for role/split separation — verified true-positive at 0 and 4,
verified false-positive at 6. At ≤4: **53 clusters, 112 sources, 59 redundant, 0 cross-label, and 29
clusters straddling the current train/dev boundary.** Those 29 are real leakage: the current dev
split contains near-copies of training images, so today's dev numbers are optimistic. Also note 13 of
the 135 clusters at ≤6 were single-linkage chaining artefacts, not tight groups.

**Policy decision (mine, as owner): group, do not delete.** A near-duplicate cluster becomes one
grouping unit assigned whole to a role and split, exactly as `source_id` already is. This removes the
leakage at zero data cost; deleting 59 sources to solve a bookkeeping problem would be the worse
trade. The `feature_cache` sealed-denylist default of 6 stays as it is — for CONTAMINATION the risk
is asymmetric (a false positive drops one training image; a false negative is fatal), so a loose
threshold is the right default there and a tight one is right for dedup. Different jobs, different
numbers, both now justified by measurement rather than by a shared default.

**4. The sealed denylist exists, and the corpus is clean.** Mehul approved fetching COCO val2017;
5,000 images downloaded to gitignored `data/sealed/`, fingerprinted through the canonical decode path,
and written as `data/manifests/sealed_denylist.txt` in `load_denylist`'s exact format (SHA-256 +
`phash=`). Hashing is not fitting: the images were read once and handed to nothing.

Audit of all 13,799 corpus sources against it: **0 exact hits. 2 perceptual hits, both at exactly
distance 6, both opened and both visually unrelated** (Nokia phone vs toilet; a crow on white sky vs a
skier in snow — again the bright-subject/dark-ground collision). The minimum observed distance between
any corpus image and any sealed image is 6.

**Therefore: no COCO val2017 image is in our training corpus, by exact hash and by inspected
perceptual match.** That is now a measured claim with an artifact behind it, not an assumption. The
DALL-E Advanced half (8,843) is still unhashed and needs Mehul's ModelScope account; the denylist and
this audit must be described as covering the real half only until that lands.

**Not done yet:** the 12,000/3,000 role split, the top-up to exactly 15,000/7,500-per-class, and the
R19 exact-count assertion in `build_router_corpus.py`.

## 2026-08-27 — B-018 router repair landed (heavy spec -> light implementation -> heavy verification)

Codex's B-018 BLOCK is repaired against the frozen contract `specs/router-repair-b018.md`. Execution
followed Mehul's model-economy directive visibly: I wrote the spec and its acceptance cases, a lighter
model implemented the bounded diff, and I verified it adversarially before landing. Suite **630 -> 660
passed**, Ruff clean on every touched file.

**T1 — the trainer now validates what it CONSUMES.** `validate_cache_rows` checked `p_fake` while
`build_batch` consumed `raw_logit`, and a missing `raw_logit` silently became `0.0` for an `ok: true`
expert — a fabricated neutral score. Now: `ok` must be a real `bool`; an available expert must carry a
finite in-range `p_fake` AND a finite `raw_logit` AND satisfy `|sigmoid(raw_logit) - p_fake| <= 1e-4`.
Corruption **aborts** instead of silently shrinking the denominator, so the `dropped_invalid_scores`
drop path is deleted (no external consumer; searched the repo). The one honest exclusion —
every expert failed for a row — is still counted and reported.

**T2 — split/label/key integrity is fail-closed.** Unknown or missing `dataset_split`, a malformed
`cache_key` (must match the sha256 hex digest `feature_cache.compute_cache_key` emits), a `source_id`
with two labels, or a `source_id` on both sides of the split now raise. `run_ladder` additionally
asserts dev sufficiency (both classes, all six families) BEFORE training, so a malformed dev split
fails in milliseconds rather than after minutes of fitting every rung.

**T3 — the false degeneracy claim is deleted, and the effect is MEASURED.** The artifact claimed a
one-expert router "necessarily emits the primary expert's score unchanged". That was false: the
learned bias head moves it. `fusion_comparison_degenerate` becomes `fusion_weight_degenerate` (a
narrow claim about the WEIGHTS only), `single_expert_learned_correction` is recorded alongside it, and
every rung now reports `max_abs_p_fake_change_vs_static`. **My own verification measured the
one-expert learned rungs moving the dev score by up to 0.1003** (static/probability-mean/fixed-weight
rungs move it by exactly 0.0, as they must) — independently reproducing the effect Codex measured at
0.2747 on real data. A measured score change is never suppressed again.

**Kill gate.** `delta > 0` no longer counts as a win: `router_earns_its_complexity` now requires
`delta >= 0.02` (doc 05/08's 2 points of worst-family fake recall) **or** the best rung's CI95 low
sitting above the baseline's CI95 high, with the clean constraints still binding.

**BCE-with-logits** on `fused_logit` for the class head and on the new `reliability_logit` for the
reliability head (doc 04); the clamped-probability path is gone.

**R22 two-stage ordering is ENFORCED, not warned about.** `threshold_is_frozen(provenance)` gates it:
under a placeholder threshold the reliability head's parameters are excluded from the optimizer and
its loss term is skipped, and `save_checkpoint` **refuses** to persist a checkpoint whose reliability
head was fitted while the threshold is not frozen. A stale reliability target can no longer be trained
or saved.

**Missing baseline rungs restored** (doc 05): `ProbabilityMeanFusion` (probability-space mean, 0
parameters — so R23's "fuse in logit space" choice is tested rather than asserted) and
`FixedWeightFusion` (a non-learned vector grid-searched on the **TRAIN split only**, held as a buffer).
The ladder is six rungs: static_average, probability_mean, fixed_weights, logistic, mlp, mlp+worst-group.

**T4 — a real, deployable, fail-closed checkpoint.** `save_checkpoint` writes atomically (`.tmp` +
`os.replace`) and records `use_worst_group_loss`, `n_parameters`, `feature_names`, the exact
hyperparameters the rung actually used, `reliability_head_fitted`, `cache_artifact_sha256`,
`code_revision`, and the selection block. New `load_checkpoint` loads under `weights_only=True` and
**never retries unsafely**, validates schema version, required keys and feature-spec drift, then
reconstructs via the same `_construct_router` the trainer uses so the two paths cannot drift.

**My verification beyond the delivered tests** (`660 passed` reproduced independently): the full
document survives the real JSON artifact path with no in-memory `_key` leakage; **save->load
prediction parity holds to max|delta| = 0.00e+00 for all six rungs individually**, including
`fixed_weights`' buffer (`[0.0, 1.0]` restored exactly) and the MLP's hyperparameter-dependent shape;
NaN `raw_logit` and unknown splits abort through the real `run_ladder` path, not merely in the
validator; and `threshold_is_frozen` rejects the actual config default (`"unspecified"`).

**One defect I found and fixed myself** (heavy-direct, too small to delegate safely — recorded per the
model-economy rule): `scripts/train_router.py` still branched on the deleted
`fusion_comparison_degenerate` via `.get()`, so it degraded silently — and it degraded on **exactly the
configuration we are about to run** (N=1, CF-384 only), dropping the single-expert framing from the
CLI while its dead text still asserted the score was unchanged. Replaced with the honest
`single_expert_learned_correction` branch that prints the measured largest score change and no longer
returns early, so the verdict line is reached in the one-expert case as T3 requires.

**Not claimed:** none of this is evidence about the router's value. It makes the trainer honest enough
to produce such evidence from a protected cache that does not exist yet.

## 2026-08-26 — Workstream initialized
Why: Mehul requested session-continuity + dual-agent framework (26 Aug).
What: STATE.md created with Phase-0/next actions from 06-build-plan.md. No code exists yet.

## 2026-08-27 10:20 — DegradePrint response branch measured and failing; correction-head proposal
`scripts/diagnostics/degradeprint_probe.py` (new, DIAGNOSTIC-only, Ruff clean). Runs the update
pack's own cheap kill test (doc 10 §11, bar ~+2 pt) on the EXISTING 24,000-row pilot cache at zero
new compute — the cache already stores `probes.<expert>.probe_scores`, so no extraction was needed.

Four arms, grouped split by `source_id`, one threshold rule (train-fitted clean FPR 5%), so arms
differ only in feature set. Dev worst-family (`noise` in every arm and seed) fake recall:

| arm | features | s0 | s1 | s2 | mean |
|---|---|---:|---:|---:|---:|
| A | primary logit | .2062 | .2196 | .2062 | **.211** |
| B | + quality descriptors | .5771 | .6168 | .6188 | **.604** |
| C | + quality + response signature | .5771 | .6028 | .6562 | **.612** |
| D | primary + response only | .2292 | .2635 | .2687 | **.254** |

- **C − B = +0.000 / −0.014 / +0.038.** Mean +0.8 pt, sign unstable → **fails doc 10 §12.**
- Doc 10 §18's own named risk realized: probes encode *severity*, and badly (D−A = +4.3 pt) next to
  quality descriptors measuring it directly (B−A = **+39.3 pt**).
- **Task 1.4 quality descriptors are the largest measured gain in the project**, at a *lower* clean FPR.
- Scope limit on record: logit-space half only. Embedding drift untested — no row carries an
  embedding (`experts.<id>.embedding_key` null throughout); testing it costs a cache rebuild.

Consequence for the router: `results/router-pilot/training.json`'s four identical rungs are evidence
that **fusion was the router's only lever**, not that its 43 features are weak — they already carry
the 39-point signal with no way to apply it. Proposed (A-023, needs Codex ACK + DECISIONS entry):
**router head becomes a CORRECTION head over the primary logit conditioned on quality + reliability
features**, fusion re-entering only if a second always-on expert earns its slot. This makes
`fusion_comparison_degenerate` obsolete rather than merely inaccurate, resolving B-018 item 3 by
deleting the claim rather than the bias head.

