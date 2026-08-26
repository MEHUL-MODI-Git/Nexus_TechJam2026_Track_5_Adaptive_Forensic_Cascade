# training — router corpus, feature cache, router/fusion, calibration
**Owner: Claude · Status: 🟢 ROUTER + CALIBRATION BUILT & TESTED on synthetic data (real corpus still Phase 2)**

## ✅ Done 2026-08-26 / 27
- **`src/router/features.py` + `src/router/model.py` BUILT + 37 tests.** The whole fusion ladder from doc 04 behind one interface so ablations compare like with like: `StaticAverageFusion` (rung 1, zero parameters — the baseline the router must beat), `LogisticRouter` (rung 2, the complexity control), `MLPRouter` (rung 3, doc 03 step 6: Linear32→GELU→Dropout→Linear16→GELU→two heads, **1,987 params**), plus `worst_group_loss` (rung 4 — aligns training with our headline worst-family metric instead of the overall mean we never report).
- **Missing-value discipline is now arithmetic, not a promise:** every optional feature is a `(value, is_present)` pair. Critically, with LOTA parked EVERY row lacks disagreement features — imputing zeros would tell the router "the experts agreed perfectly" on every image. Tested. `probe_flip` is encoded tri-state so *unknown* stays distinct from *measured-and-stable*.
- **Entropy is computed from `p_fake` at assembly, never read from the cache** — tested with a poisoned cache value that must be ignored (Codex B-009's canonical-helper requirement).
- **Availability masking:** an unavailable expert receives EXACTLY zero weight; a row with no available expert gets all-zero weights (no verdict) rather than a uniform guess over nothing.
- **Standardizer fits on TRAIN ROWS ONLY** and leaves indicator columns untouched (rescaling a presence flag by its train frequency would make "missing" mean different things per block).
- **LEARNABILITY VERIFIED (synthetic):** in a world where each expert is reliable in a different context, static averaging sits at <0.65 accuracy while the trained router reaches >0.90. The architecture's central premise is implementable — this test fails loudly if that ever stops being true.
- **`src/router/calibration.py` BUILT + 30 tests** — the frozen threshold objective implemented exactly: bootstrap-mean worst-FAMILY fake recall over the 6 transform families, **clean excluded from the minimum** (enters only via constraints), **severities pooled within family**, **label-stratified bootstrap with `source_id` as the resampling unit** (views travel together). Plus `threshold-artifact.v1`, temperature+bias calibration fitted by NLL on dev, ECE with 15 fixed bins, and canonical `binary_entropy` (the helper Codex asked for so entropy is computed at consumption, never stored).
  - Infeasible runs record `feasible=False` and fall back to baseline **rather than silently relaxing a constraint we agreed to**.
  - Families with no fake rows are SKIPPED, not counted as zero — an absent measurement is not a failure to detect.
  - Exact-condition upgrade (≥500 fake sources/condition) is DETECTED and flagged in the artifact, but not taken automatically.
- **`specs/phase2-feature-cache.md` v2 FROZEN** — Codex returned APPROVE-WITH-FIXES (B-009); all 6 required fixes applied `[F1]`–`[F6]` + both preference calls. Fixes worth remembering: the duplicate-SHA rule was WRONG (all 20 views of a source share `original_sha256`, so it would have rejected the whole cache — corrected to one-SHA→one-`source_id`); added `view_rgb_sha256` because `original_sha256` cannot identify transformed content; removed `threshold_agreement` from the raw cache (threshold-dependent value must not be baked into a threshold-free artifact); cache key now hashes canonical JSON, not pipe-concatenation. Replay mapping to `prediction-row.v1` agreed in §8. Originally — closes a real gap: the spec-freeze entry had listed "feature-cache row v1" as frozen when it had never been written. Covers `feature-cache-row.v1` schema (per-expert blocks, probe block, quality block, disagreement-or-null), `cache_key` = hash of PIPELINE+PROBE versions + configs + expert fingerprints with refuse-to-append on mismatch, Parquet layout + resumability, the 4 in-code hard constraints (sealed-subset denylist ABORTS not skips), throughput budget, and a 7-item DoD.
- **Throughput budget computed from the real Phase-0 measurement:** 14 ms/img on MPS ⇒ ~1.1 s/source at 20 conditions × (1 expert + 3 probes) ⇒ **30k sources ≈ 9.3h, 12k ≈ 3.7h — both inside the agreed ≤12h cap** before batching gains. Re-measure on ≥200 sources at Phase-2 entry before committing.
- Nothing built (code). Strategy fixed in `docs/04-training-and-data.md`: 20–40k corpus (GenImage + filtered SID-Set), grouped splits, WildFake hash denylist, fusion ladder (static avg → logistic → MLP router → +worst-group loss).

## ▶ NEXT ACTION (when unblocked at Phase 2 entry)
1. Measure Phase-1 caching throughput on MPS → post compute decision (local vs Colab) as GATE-adjacent CHANNEL message; joint decision with Codex + Mehul.
2. Build WildFake-subset hash denylist FIRST (`scripts/build_denylist.py`) — it gates every later job.
3. Corpus download + manifest (delegate downloads to Sonnet subagent; verify counts/licenses heavy-side).
4. Feature cache job (`scripts/cache_features.py`) per doc 04 schema; 20% clean / 80% single-transform sampling.
5. Fusion ladder training + calibration; every rung logged as an ablation row for eval workstream.

## Other open threads (do not lose)
- Self-probe set (JPEG 92 / crop 97% / resize 0.90) is provisional — ablate one probe at a time (doc 08).
- Worst-group loss has kill criteria: drop if clean BAcc −1pt without +2pt worst-group gain.

## Literal next command
```
# blocked — first command when unblocked:
cd "/Users/mehulmodi/MEHUL WORK/Hackathon/TechJam 2026" && python scripts/bench_throughput.py --n 500
```

## Hard constraints
- Denylist check runs before EVERY training job; sealed subset never fits anything (weights, thresholds, calibration, early stopping).
- COCO val2017 never in training reals. Same source's clean+transformed views stay in one split.
- One operating threshold across all conditions.

## Read next
| Task | Read |
|---|---|
| Corpus/splits/denylist | `docs/04-training-and-data.md` |
| Router architecture + features | `docs/03-recommended-architecture.md` steps 4–8 |
| Kill criteria | `docs/08-risks-kill-criteria-open-questions.md` |
