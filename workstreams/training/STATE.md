# training — router corpus, feature cache, router/fusion, calibration
**Owner: Claude · Status: 🔴 2R.1 router repair IN FLIGHT (B-018 ACKed, no counter) · corpus 14,999 · full cache NOT launched**

## ✅ Built (detail in `workstreams/training/CHANGELOG.md` — do not re-derive here)
- **`scripts/build_router_corpus.py`** — 14,999 sources (silent-underfill defect **R19 open**). **Both
  classes from SID-Set deliberately**: COCO-reals + SID-fakes would teach the router dataset artefacts.
- **`feature_cache.py`** (30 tests) — canonical key with refuse-to-append, **fail-closed denylist** (no denylist ⇒ refuses to build), sealed hit **aborts** the job rather than skipping.
- **`features.py` + `model.py`** (37 tests) — 43 features, each optional one a `(value, is_present)` pair; standardizer fits on train rows only.
- **`calibration.py`** (30 tests) — frozen threshold objective: bootstrap worst-FAMILY fake recall, clean excluded from the minimum, severities pooled, `source_id` as the resampling unit.
- **`train.py`** (14 tests) — full ladder + `router_earns_its_complexity` verdict. **Under repair now.**
  `scripts/diagnostics/degradeprint_probe.py` holds the DegradePrint arm table; see CHANGELOG.

## ⚠️ EVIDENCE BOUNDARY — the 24k pilot is diagnostic only
`UNPROTECTED_SMOKE_ONLY`, obsolete `feature-cache-row.v1`, random source-held-out dev, **no untouched
test, no generator-held-out split, no paired source bootstrap**. It **parks** the logit-response branch
(+0.8 pt, unstable sign, ~+2 pt bar); it does not *kill* it. The quality arm (+39.3 pt worst-family) is a
**hypothesis for the correction head, not a result**, and clean FPR is *not* lower on average (.0437 vs
.0458). It may debug code; it may **not** train a submitted model or mint a headline. **Corrected
fallback (B-020 §5):** if the protected cache fails, ship CF-384 + an honestly calibrated threshold if one
exists + the accepted stress UI and diagnostic table — *not* a pilot-trained router.

## ⚠️ FROZEN COMPUTE FACT — 30k does not fit the 12 h cap
Measured **7.83 rows/sec** on real 1024×1024 images (the old 9.3 h figure came from 256px fixtures,
optimistic ~2.3×). 30k ⇒ 21.3 h (**over**); **15k ⇒ 10.6 h (adopted)**. Frozen rule: shrink **source
count, never coverage** — which also keeps PGC (≈311M, ~14× CF-384) out of the cache entirely.

## ▶ NEXT ACTION — strictly in this order (the cache run is the critical path)
1. **Land the B-018 repair.** A delegated lighter model is implementing `specs/router-repair-b018.md`
   (consumed-field validation, fail-closed split/source-label/cache-key, weight-vs-score degeneracy,
   ≥2 pt-or-CI kill gate, BCE-with-logits, two-stage reliability, baseline rungs, atomic checkpoint +
   save→load parity). **Claude reviews the diff adversarially and verifies before landing; Codex
   re-reviews at the 2R.1 gate.**
2. **2R.2 corpus repair before any fitting:** fix R19; acquire exactly **15,000 / 7,500 per class**; split
   into a protected **12,000-source fitting manifest** + an **untouched 3,000-source internal test**;
   enforce exact-SHA *and* perceptual near-duplicate separation across roles; a source lives in one split.
3. **Protected mini-pilot on `feature-cache-row.v2`**: do the three expensive probes earn their cache
   cost beyond quality descriptors? If not, drop them **before** the long run.
4. **Bump the cache key ONCE**, re-verify goldens + fail-closed denylist, then launch the 15k cache
   (~10.6 h). A second bump costs another 10.6 h and there is no room for one.
5. Then the honest ladder (raw/calibrated primary → quality-conditioned correction → smallest justified
   MLP → +worst-group), freeze calibration/threshold, and **only then** fit reliability.
- Open threads: the probe set (JPEG 92 / crop 97 / resize 0.90) is provisional and a 4th is **not** worth a cache bump; drop worst-group loss if clean BAcc −1 pt without +2 pt worst-group gain.

## Literal next command
```
cd "/Users/mehulmodi/MEHUL WORK/Hackathon/TechJam 2026" && \
  .venv/bin/python -m pytest tests/test_router.py tests/test_router_train.py -q
```

## Hard constraints
- Denylist check runs before EVERY training job; the sealed subset never fits anything. COCO val2017
  never in training reals. A source's clean + transformed views stay in one split.
- One operating threshold across all conditions; never tuned per condition.

## Read next
| Task | Read |
|---|---|
| The current plan | `coordination/PLAN-UPDATE-2026-08-27.md` (docs 00–08 are history) |
| Router repair / corpus | `specs/router-repair-b018.md` · `docs/04-training-and-data.md` |
