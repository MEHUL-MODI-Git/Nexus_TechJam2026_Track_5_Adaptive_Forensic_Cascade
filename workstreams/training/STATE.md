# training — router corpus, feature cache, router/fusion, calibration
**Owner: Claude · Status: 🔴 router repair BLOCKED (B-018) · 🟡 POST-LOTA REPLAN PROPOSED (A-023), awaiting Codex ACK · corpus acquired (14,999), full cache NOT yet run**

## ✅ Built (detail in `workstreams/training/CHANGELOG.md` — do not re-derive here)
- **Corpus acquisition** `scripts/build_router_corpus.py` — 14,999 sources acquired (silent-underfill
  defect R19 still open). **Both classes from SID-Set deliberately**: COCO-reals + SID-fakes would let
  the router learn dataset artefacts, and our quality descriptors would carry that shortcut in.
- **`src/router/feature_cache.py`** (30 tests) — spec v2: canonical cache key with refuse-to-append,
  **fail-closed denylist** (no denylist ⇒ refuses to build), sealed hit **aborts** the job, never skips.
- **`src/router/features.py` + `model.py`** (37 tests) — 43 features, every optional one a
  `(value, is_present)` pair so *missing* never reads as *measured*; standardizer fits on train rows only.
- **`src/router/calibration.py`** (30 tests) — frozen threshold objective: bootstrap worst-FAMILY fake
  recall, clean excluded from the minimum, severities pooled, `source_id` as the resampling unit.
- **`src/router/train.py`** (14 tests) — full ladder + explicit `router_earns_its_complexity` verdict.
  **Currently BLOCKED by B-018.**
- **`scripts/diagnostics/degradeprint_probe.py`** — the DegradePrint kill test; see CHANGELOG for the
  arm table. **Response branch failed; quality descriptors won by +39.3 pt.**

## ⚠️ FROZEN COMPUTE FACT — the 30k target does not fit the 12 h cap
Measured **7.83 rows/sec** on real 1024×1024 corpus images (pilot re-derives 7.55: 24,000 rows in
53 min). 30k sources ⇒ 21.3 h (**over cap**); **15k ⇒ 10.6 h (adopted)**; 12k ⇒ 8.5 h. The earlier
9.3 h figure came from 256px fixtures and was optimistic by ~2.3×. Per the frozen rule the response
is to shrink **source count, never coverage**. Same arithmetic kills a heavy second expert in the
cache: PGC ≈311M / GAPL ≈305M are ~14× CF-384, and 300,000 rows cannot absorb that (A-023 §3).
Batched inference is the obvious speed-up but it changes a reviewed adapter — proposed, not done.

## ▶ NEXT ACTION — strictly in this order (119 h to submit; the cache run is the critical path)
1. **Reply to B-018 itemised** (router repair BLOCK): consumed-field validation (`raw_logit=NaN`
   must fail, missing raw logits must not become 0.0), unknown-split/inconsistent-label rejection,
   checkpoint loader + save→load prediction-parity test, BCEWithLogits, the ≥2 pt kill gate, and the
   learnability test still passing probabilities into a logit API. **Counter item 3 with A-023's
   correction-head argument, not by removing the bias head.**
2. **Reply to B-016 E1–E5** (eval boundary) — Codex owns `src/eval/`; agree acceptance cases first.
3. **On Codex's A-023 ACK:** write the DECISIONS entry (both names), then implement the correction
   head and freeze the feature/probe set. **Embeddings stay OUT** unless Codex counters with evidence.
4. **Collect Codex's cache requests by ~17:00 today, bump the cache key ONCE**, re-verify goldens +
   fail-closed denylist, then **launch the 15k full cache run ~18:00 Thu → ~05:00 Fri (10.6 h)**.
   A second bump costs another 10.6 h and there is no room for one.
5. Fri: correction-head ladder + calibration + threshold on dev; promote diagnostic arms A/B/C/D to
   first-class ablation rows so the DegradePrint negative ships as a finding.

**Fallback if the cache run fails:** train on the existing 24,000-row pilot — already +39 pt on the
worst family. Say so honestly; it is a real result.

## Other open threads (do not lose)
- Probe set (JPEG 92 / crop 97 / resize 0.90) is provisional — but A-023 measured the probes' response
  features as near-worthless on top of quality, so **adding a 4th probe is NOT worth a cache-key bump**.
- Worst-group loss kill criteria: drop if clean BAcc −1 pt without +2 pt worst-group gain.
- R19 silent corpus underfill (14,999 vs 15,000 requested) still unfixed.

## Literal next command
```
cd "/Users/mehulmodi/MEHUL WORK/Hackathon/TechJam 2026" && \
  .venv/bin/python scripts/diagnostics/degradeprint_probe.py 0 && \
  tail -60 coordination/CHANNEL.md
```

## Hard constraints
- Denylist check runs before EVERY training job; sealed subset never fits anything (weights, thresholds, calibration, early stopping).
- COCO val2017 never in training reals. Same source's clean+transformed views stay in one split.
- One operating threshold across all conditions.

## Read next
| Task | Read |
|---|---|
| **The current plan** | `06-build-plan.md` **Phases 2R–5R** + `handoffs/2026-08-27_post-lota-replan.md` |
| Corpus/splits/denylist | `docs/04-training-and-data.md` |
| Kill criteria | `docs/08-risks-kill-criteria-open-questions.md` |
