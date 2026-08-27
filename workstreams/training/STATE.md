# training — router corpus, feature cache, router/fusion, calibration
**Owner: Claude · Status: 🟡 2R.1 router repair LANDED + owner-verified (660 tests) — awaiting Codex re-review · corpus 14,999 · full cache NOT launched**

## ✅ Built (detail in `workstreams/training/CHANGELOG.md` — do not re-derive here)
- **`scripts/build_router_corpus.py`** — R19 fixed; corpus now exactly 15,000 / 7,500 per class. Its
  "both classes from SID-Set removes dataset artefacts" rationale is DISPROVEN (see correction below).
- **`feature_cache.py`** (30 tests) — canonical key with refuse-to-append, **fail-closed denylist** (no denylist ⇒ refuses to build), sealed hit **aborts** the job rather than skipping.
- **`train.py`** — B-018 repaired: six-rung ladder, fail-closed consumed-field/split/label/key validation,
  measured (never suppressed) one-expert score change, ≥2 pt-or-CI kill gate, BCE-with-logits, enforced
  two-stage reliability, atomic checkpoint + `load_checkpoint` parity. **Awaiting Codex re-review.**
  `scripts/diagnostics/degradeprint_probe.py` holds the DegradePrint arm table; see CHANGELOG.

## ⚠️ EVIDENCE BOUNDARY — the 24k pilot is diagnostic only AND format-confounded
**⚠️ CORRECTION, NARROWED.** The JPEG/PNG format shortcut is real (100.00% of sources) and inflates
**clean-row** separability: quality-only hits dev AUROC 0.9867 there, blockiness alone 0.89. But my
first, broader withdrawal of the +39.3-pt result was WRONG: measured over 3 seeds, a quality-ONLY arm
scores **0.0505** worst-family recall — worse than primary-only (0.2107) — so the gain requires the
primary and is not the shortcut. Cite no clean-row quality claim; re-measure the worst-family gain on
the protected cache before publishing it.

`UNPROTECTED_SMOKE_ONLY`, obsolete `feature-cache-row.v1`, random source-held-out dev, **no untouched
test, no generator-held-out split, no paired source bootstrap** — and now format-confounded on top. It
**parks** the logit-response branch (+0.8 pt, unstable sign, ~+2 pt bar); it does not *kill* it. It may
debug code; it may **not** train a submitted model or mint a headline. **Corrected fallback (B-020 §5):**
if the protected cache fails, ship CF-384 + an honestly calibrated threshold if one exists + the
accepted stress UI and diagnostic table — *not* a pilot-trained router.

## ⚠️ FROZEN COMPUTE FACT — 30k does not fit the 12 h cap
Measured **7.83 rows/sec** on real 1024×1024 images (the old 9.3 h figure came from 256px fixtures,
optimistic ~2.3×). 30k ⇒ 21.3 h (**over**); **15k ⇒ 10.6 h (adopted)**. Frozen rule: shrink **source
count, never coverage** — which also keeps PGC (≈311M, ~14× CF-384) out of the cache entirely.

## ▶ NEXT ACTION — strictly in this order (the cache run is the critical path)
1. **Review Codex's eval gate (B-023, NEEDS-REPLY)** — independently rerun E1–E5, dataset identity,
   loaded-threshold bytes, failure ledger, freeze binding, sealed authorization. Verdict owed.
   The B-018 repair is landed and owner-verified (660 tests, per-rung checkpoint parity 0.00e+00);
   **A-025 posted, Codex's re-review is what clears my half of 2R.1.**
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
