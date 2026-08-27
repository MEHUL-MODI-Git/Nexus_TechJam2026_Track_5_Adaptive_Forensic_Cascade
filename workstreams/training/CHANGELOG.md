# CHANGELOG — training (newest first, append-only; corrections are new entries)

## 2026-08-27 17:35 — [relay] PROTECTED FITTING CACHE LAUNCHED (detached, ~9 h)

Running: `data/feature_cache/fitting-v2`, 11,998 sources x 20 conditions = **239,960 rows**, measured
**7.22 rows/sec** steady state, ETA ~**02:45**. Launched under `nohup caffeinate -ims`, **verified
reparented to PID 1**, so it survives this session ending, usage limits or the terminal closing.
Log: `logs/fitting_cache.log`. Resume is verified: rerunning the same command continues rather than
restarting.

**The first launch attempt was REFUSED by our own contamination guard, and that was correct.**
`feature_cache` aborted at startup on
`data/corpus/canonical/real/044398d7dca30781.jpg (phash within 6 of a sealed image)` — the crow-on-
white-sky source matching a sealed skier-in-snow at distance exactly 6. It is one of the two known
false positives I had already opened and confirmed unrelated.

**Resolved by dropping the data, not by arguing with the guard.** Three options existed: lower the
threshold to our calibrated 4, add an audited exception, or exclude the sources. Excluding wins on
every axis — it costs **2 sources out of 15,000 (0.017%)**, keeps the conservative threshold of 6
untouched, needs no override mechanism, and preserves the audit story that we never once overrode a
contamination refusal. Lowering a contamination threshold to retain two images would be an appalling
trade against the risk it guards.

Made principled rather than hand-typed: `build_role_manifests.py` now applies the SAME denylist rule
`feature_cache` uses and pre-excludes any flagged source, recording each with its distance in
`excluded_by_sealed_denylist`. A source the cache would reject can no longer reach a role manifest
and kill a 9-hour job at startup.

Roles after exclusion: internal test **1,500/1,500** (still exact), fitting **5,998 real / 6,000
fake**, train 4,498/4,500, dev 1,500/1,500. Still 0 clusters straddling roles or train/dev.

## 2026-08-27 — [relay] pre-launch probe caught a crash that would have fired at hour 8.5

Ran the B-020-mandated throughput re-measurement on 200 sources through the REAL launch path
(`launch_fitting.json` + the sealed denylist) rather than trusting the earlier figure.

**Measured 7.83 rows/sec**, reproducing the earlier measurement exactly. 200 sources / 4,000 rows in
9m06s. 12,000 fitting sources x 20 conditions = 240,000 rows => **8.51 h**, comfortably inside the
12 h cap. Extracting only the fitting role rather than all 15,000 saves ~2 h on its own.

**The probe earned its 9 minutes: extraction succeeded and then the script crashed printing its own
summary.** `KeyError: 'rows_written'` — the summary asked for `rows_written`/`decode_failures`, but
`build_cache` emits `rows_written_this_invocation`/`decode_failures_this_invocation` (named that way
because a resumed run writes fewer rows than the artifact holds). The failure fires AFTER all
extraction completes, so on the full job it would have crashed at the ~8.5 h mark and left a
perfectly good cache looking like a failed run. Fixed, and the summary now warns about missing keys
instead of raising.

**Resume verified end-to-end, not merely claimed.** Re-running the identical command against the
finished probe cache found all 4,000 rows present, wrote **0** new rows and exited clean.

**Cache health on the real path:** `denylist_protected: true`, `denylist_perceptual_protected: true`,
**`UNPROTECTED_SMOKE_ONLY: false`** — this is a genuinely protected cache, the thing every previous
one was not — `schema_version: feature-cache-row.v2`, `threshold_free: true`, 0 decode failures,
device `mps`, cache key `f5b1fa46…`.

## 2026-08-27 — [relay] canonicalized corpus, launch manifests, and a 42%-duplicate sealed set

**Canonicalization landed and works.** All 15,000 sources re-encoded to JPEG q95 from decoded pixels
(`scripts/canonicalize_corpus.py`, 31 s, 4.2 GB, 0 failures). Verified: **all 15,000 are now JPEG**
(7,500 real + 7,500 synthetic), so the container no longer carries any class information. pHash
barely moved — mean shift **0.061**, max **2** — so the images are perceptually unchanged.

**Re-verified the role separation on the NEW pixels rather than assuming it survived.** A max shift of
2 on both sides of a pair could in principle pull a test image inside the threshold of a fitting one.
Measured after canonicalization: **min test-vs-fitting pHash distance is still 6**, and **0 pairs**
fall within the threshold of 4. Separation holds.

**Contamination re-audited on the canonical pixels:** 0 exact hits, 2 perceptual hits at distance 6 —
the same two already opened and shown to be unrelated. Still clean.

**Launch manifests built** (`scripts/build_launch_manifests.py`): `launch_fitting.json` (12,000) and
`launch_internal_test.json` (3,000). `relative_path` and `original_sha256` are REWIRED to the
canonical files, because `validate_manifest_rows` re-hashes the bytes it reads and refuses any
manifest that does not describe them — annotating a second column would have failed at launch. The
acquisition path/hash/pHash are preserved as `acquired_*` so provenance is intact.

**Finding, eval-affecting (A-029):** the organizers' sealed "DALL-E Advanced 8,843" contains only
**3,719 unique images**; 5,124 files are byte-identical duplicates, some repeated 5x. Confirmed as
their data, not our extraction — the same content-hash filename appears under five different
timestamped batch folders inside `DALLE.zip`. COCO val2017 is clean (5,000/5,000). Our denylist is
unaffected (set semantics), but scoring the sealed run per-file would weight 1,808 images up to 5x and
understate uncertainty badly. Sealed-run protocol proposal sent to Codex.

Relay work under PROTOCOL §6.

## 2026-08-27 — [relay] `quality_only` mandatory ladder rung + a verdict that could have lied

Adds the 7th rung agreed in A-027: `QualityOnlyRouter`, one linear layer over the router feature
vector, **no expert score at all**. Placed FIRST in the ladder. `static_average` remains the delta
baseline and clean-constraint reference, unchanged.

The point: our corpus lets image statistics alone separate the classes at ~0.95-0.99, so "adding
quality features helped" was never the right claim. The question is whether the cascade beats a model
that has only ever seen image statistics. This makes that comparison structural rather than optional.

**Verified the rung really is blind to the experts**, since a baseline that secretly peeks is worse
than no baseline: running it on identical features with expert logits of -50 and +50 gives bitwise
identical `p_fake` and `fused_logit`, weights are all zero, and the only mention of `expert_logits`
in `forward` is `torch.zeros_like` for shaping.

**Caught in review — a verdict that could have made its most flattering claim in exactly the case
that disproves it.** `quality_only` competes for selection like any other rung, so it can WIN. As
delivered, `router_earns_its_complexity` was `meaningful or separated`, computed against
`static_average` — so a no-expert model winning would have been reported as the router earning its
complexity. Fixed by splitting the claim rather than fudging it:

- `best_rung_uses_expert_scores` — new, explicit.
- `router_earns_its_complexity` now also requires it. Narrow claim: the learned machinery beat
  parameter-free fusion AND the winner actually consults an expert.
- `cascade_is_justified` — new composite: both of the above AND `beats_quality_only`.

Deliberately NOT collapsed into one flag: "the fusion machinery is justified" and "the cascade beats
plain image statistics" are different questions, and merging them would hide which one failed.
Two regression tests pin it.

Suite **662 -> 671**. Relay work under PROTOCOL §6; Codex reviews on return.

## 2026-08-27 — [relay] E3c verified closed (Codex had already fixed it)

My A-025 finding — `FrozenThreshold._from_loader` minting a headline capability from a two-key blob
stamped `held-out-dev` — was already fixed by Codex in `0a40ee8` before it went offline. Confirmed by
re-running my original exploit: it now fails at the constructor, which requires an internal capability
token, and `_validate_loaded_threshold` additionally re-validates the full `threshold-artifact.v1`
schema over the exact bytes. The provenance fallback is now `"unspecified"` rather than the
fitted-sounding default. Three regression tests added so the exploit stays dead. E1/E2a/E2b still
pass unchanged.

## 2026-08-27 — [relay] 2R.2 role manifests: 12,000 fitting + 3,000 untouched internal test

`scripts/build_role_manifests.py`. Splits the 15,000-source corpus into the two roles B-020 §4
requires, enforcing the separation rather than trusting it.

**Near-duplicate clusters are the unit of assignment, not `source_id`.** Two samples of the same
prompt are the same picture for leakage purposes, so a cluster is assigned WHOLE to one role and one
split. Nothing is deleted — the leak closes at zero data cost, where dropping the 59 redundant
sources would have cost data to solve a bookkeeping problem.

**Threshold is Hamming <= 4, calibrated by opening images, not taken from a default.** At distance 0
(snowboarder) and 4 (engineers in a tunnel) the pairs are genuinely two samples of one prompt; at
distance 6 they are a girl in a paddling pool and an AI puppy. `feature_cache`'s sealed-denylist
default of 6 is deliberately left alone: contamination has the opposite risk asymmetry, where a false
positive costs one training image and a false negative is fatal.

Result: **14,926 clusters, 65 multi-source, 0 cross-label** (the single cross-label cluster seen at
threshold 6 was a chaining artefact and disappears at 4).

| role | real | fake |
|---|---:|---:|
| fitting / train | 4,500 | 4,500 |
| fitting / dev | 1,500 | 1,500 |
| internal test (untouched) | 1,500 | 1,500 |

**Verified independently of the script's own self-report:** 15,000 sources total, **0 source-id
overlap**, **0 SHA-256 overlap**, 15,000 distinct decoded hashes, **0 clusters straddling roles**,
**0 straddling train/dev**, and — the number that actually matters — the **minimum pHash distance
between ANY internal-test image and ANY fitting image is 6**, comfortably outside the threshold of 4
and at a distance already shown to be visually unrelated. The internal test set is genuinely
untouched. For contrast, the previous naive split had **29 clusters straddling train/dev**, so every
dev number computed before today was optimistic.

Relay note: taken alone under PROTOCOL §6 while Codex is offline. Codex reviews on return.

## 2026-08-27 — all downloads moved inside the repo; a 12 GB purge that purged nothing

Mehul's instruction: anything downloaded belongs in the project directory only. Auditing that found
**13 GB outside it**, in `~/.cache/huggingface`, and a bug that put most of it there.

**Both download sites now use a repo-local cache.** New `src/pipeline/hf_cache.py` sets `HF_HOME` to
`data/hf_cache/` (git-ignored) and is called at module import in `src/experts/commfor.py` and
`scripts/build_router_corpus.py` — before either lazily imports `huggingface_hub`, since that library
reads `HF_HOME` at ITS import. An `HF_HOME` already set in the environment is respected.

**Moved, not re-downloaded:** `datasets--saberzl--SID_Set` (12 GB) and
`models--OwensLab--commfor-model-384` (83 MB) moved into `data/hf_cache/hub/` — same filesystem, so
instant. Two unrelated `docling-project` caches (506 MB) were left alone; they belong to something
else. Verified afterwards: CF-384 loads from the new location at the same revision `6076002b` with
**21,811,969 parameters**, matching the documented 21.81M, and the suite is **662 passed**.

**The real cause of the 12 GB: `--purge` never purged.** `hf_hub_download` returns a path under
`snapshots/` that is a SYMLINK into `blobs/`. The purge branch called `Path(path).unlink()`, deleting
the symlink and leaving the ~490 MB blob behind — while printing nothing to suggest otherwise. Result:
`snapshots/*/data/` was **empty** while `blobs/` held **27 orphaned files totalling 12 GB**. The
comment above that branch even explained the disk cost it was failing to avoid. Now the link is
resolved before unlinking and both are removed.

**Also added `--start-shard`.** In `--augment` mode it defaults to one past the highest shard the
existing manifest consumed (measured: shards 0..26, so a top-up starts at 27). Every source in a
consumed shard is already held or already rejected, so re-reading them is pure waste; this turns a
top-up from a full re-scan into a short one.

The 27 orphaned blobs are kept until the top-up finishes — `hf_hub_download` can reuse an existing
blob rather than re-fetch it — and are then deletable. With the purge fixed, no future run leaks.

## 2026-08-27 — sealed denylist COMPLETE (13,843 entries); corpus clean against the whole reference subset

Mehul asked how to obtain the organizers' DALL-E Advanced half. The answer turned out to be better
than "download 1.29 TB": `scripts/fetch_sealed_dalle.py` retrieves **exactly** the sealed subset and
nothing else.

**How the subset was identified without downloading images.** WildFake's `label_csv_files/dalle3.csv`
(1.3 MB) has an `IsAdvanced` column. It contains **8,843 rows, every one `IsAdvanced=1`**, all under
`./Diffusion_based/DALLE/Advanced/DALLE3` — an exact match for the brief's "DALL-E Advanced 8,843".
`dalle2.csv` is 55,638 rows, all `IsAdvanced=0`. So the organizers' subset is a directory, and its
identity is confirmed by count rather than assumed.

**How 2.84 GB replaced 25.6 GB.** Those images live inside one `DALLE.zip` of 25.6 GB / 64,495
entries. ModelScope's API 302s to a CDN that advertises `accept-ranges: bytes`, so the archive's
ZIP64 central directory (8 MB) was read by range request and parsed directly. The 8,843
`Advanced/DALLE3` entries proved **perfectly contiguous** — measured span/total = **1.000** — so a
single range request over bytes 22,741,786,039..25,579,485,327 retrieves the subset and no more.
Local file headers were then walked by signature and inflated: **8,843 extracted, 0 skipped**. The
script REFUSES to run if the entry count is not exactly 8,843, rather than guessing at a subset whose
layout has changed.

**Denylist now covers the complete sealed reference subset:** `data/manifests/sealed_denylist.txt`,
**13,843 entries** (SHA-256 + pHash) = 5,000 COCO val2017 + 8,843 DALL-E Advanced. The brief's figure
is 13,841 (4,998 + 8,843); we carry all 5,000 val2017 images, a deliberate **superset** — two extra
banned fingerprints can only over-protect.

**Contamination audit re-run against the full 13,843:** all 13,799 corpus sources checked.
**0 exact hits. 2 perceptual hits, both at distance 6, both against COCO, and both are the pairs
already opened and verified unrelated** (Nokia phone vs glittery toilet; crow on white sky vs skier in
snow). **Zero hits from the DALL-E Advanced half.** Minimum observed distance between any corpus image
and any sealed image is 6, i.e. no corpus image is closer to a sealed image than the false-positive
floor we calibrated by eye.

**The hard constraint is now a measured claim with an artifact behind it**, not an assumption:
no organizer reference image — real or AI — is in our training corpus. `feature_cache.py`'s
fail-closed denylist gate can now be satisfied honestly, which unblocks the protected cache run.

Side benefit: the sealed images are on disk (gitignored `data/sealed/`), so the Phase 4R single
sealed evaluation run no longer needs a download. They stay out of every fitting path; the denylist
guard is what enforces that, and it aborts rather than skips on a hit.

**R19 fixed in the same pass** (`scripts/build_router_corpus.py`). Root cause: `needed[label] -= 1`
counted RAW rows while exact-SHA dedup ran only after the acquisition loop, so a duplicate silently
became a shortfall — exactly how a run asked for 7,500/class wrote 7,499. Dedup now happens *during*
acquisition via a `seen` set threaded through `extract_shard`, so `needed` counts unique sources; the
post-loop dedup became a fatal post-condition check; the manifest records `acquired_per_class`; and
the script **refuses to write an underfilled manifest** unless `--allow-underfill` is passed
explicitly. Added `--augment` to top up an existing manifest, dropping rows whose image is missing
from disk — which is what the 1,200 deleted pilot rows are.

Implemented heavy-direct rather than delegated: acquisition dedup and contamination boundaries are
exactly what the model-economy rule reserves for the owner.

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

