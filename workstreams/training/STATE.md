# training — router corpus, feature cache, router/fusion, calibration
**Owner: Claude · Status: 🟢 PHASE 3 COMPLETE · cascade SERVED on the live path (parity 0 verdict disagreements) · abstention SHIPS (defer 20% → accuracy 0.9090→0.9317, worst-family 0.8258→0.9136) · second-expert rescue KILLED on evidence (P(correct|wrong)=0.5426, net −2451) · full ablation + ops evidence published**

## ✅ Built (detail in `workstreams/training/CHANGELOG.md` — do not re-derive here)
- **`build_router_corpus.py`** — corpus exactly 15,000 / 7,500 per class, split into a **12,000-source
  protected fitting manifest** + an **untouched 3,000-source internal test**. Roles are separate manifests.
- **`feature_cache.py`** (30 tests) — fail-closed denylist; a sealed hit **aborts**. Fired on the real launch.
- **`train.py`** — 7-rung ladder, fail-closed validation, ≥2 pt-or-CI kill gate, two-stage reliability,
  atomic checkpoints with a fail-closed loader.
- **`freeze_router.py`** — fits every rung, applies the pre-registered selection rule, writes
  `threshold-artifact.v1.json`, and now saves the **deployable checkpoint** `router.pt` (tracked, 17 KB).
- **`evaluate_internal_test.py`** — one-shot evaluator; loads frozen weights + threshold, fits nothing,
  refuses any cache not stamped `role=evaluation`.

## 📌 THE FROZEN DECISION (`16d2e3b`; re-run reproduced it byte-identically)
Pre-registered rule on **dev**: highest worst-family fake recall among rungs meeting the clean
FPR/BAcc constraints. Selected **mlp+wg @ 0.4667367651127279** — dev worst-family 0.8144, against
mlp 0.7587, logistic 0.6860, quality_only 0.5076, static_average 0.1849. 1,827 params, dim 38,
geometry excluded, expert `commfor_384` only. Dev clean FPR 0.0736 ≤ 0.0756 cap. Full table and
bootstraps in the CHANGELOG. **Dev selection is not a reportable result** — see the test result above.

## ✅ RESOLVED — the watch item went against us and we published it
Clean FPR is **0.0833** on the untouched test against 0.0736 fitted on dev and the **0.0756 cap the
threshold was selected under** — over by 0.77 pt, as the 300-source pre-flight warned. The
pre-registered response was honoured: reported as a limitation, **threshold unchanged**. Also
published: at matched FPR the primary beats the cascade on blur/colour/resize and ties on crop, so
the cascade's advantage is `noise` + `jpeg` only, and it buys nothing on clean images
(0.9613 vs 0.9620). Artifacts: `results/internal-test/{results,fpr-matched-baseline}.json`.

## ▶ NEXT ACTION — nothing technical is open here; the remaining gates are Mehul's
1. **Training/core work is complete for submission.** Do not refit, re-threshold, or re-run the
   one-shot evaluator to improve a number — the result is frozen and written up.
2. Remaining blockers are release-side and belong to product + Mehul: repo public, MIT approval,
   verified clean-history force-push, CF revision pin, final truthfulness audit.
3. **B-024 round 2 was APPROVED in B-029.** What is open is Codex's re-review of the R1–R8
   packet (A-033) as amended by A-034 — in progress as of 29 Aug. Release and Phase-4
   acceptance stay blocked until it clears, and neither is ours to clear.
4. The sealed WildFake reference run is Phase 4 and **has not been touched** — one run, only when
   Mehul authorises it, scored with the A-029 deduplication protocol (8,843 files, 3,719 unique).

## ⚠️ Two sessions, one working tree
Two Claude sessions were live here simultaneously and both built the same FPR-matched control.
Nothing was lost, but before starting work confirm no other session is active: `git log --oneline -3`
then `ps aux | grep -c "[c]laude"`.

## Literal next command
```
cd "/Users/mehulmodi/MEHUL WORK/Hackathon/TechJam 2026" && git log --oneline -5 && \
  sed -n '/## 7. Results/,/## 8./p' README.md
```

## Hard constraints
- Denylist check runs before EVERY training job; the sealed subset never fits anything. COCO val2017
  never in training reals. A source's clean + transformed views stay in one split.
- One operating threshold across all conditions; never tuned per condition. **The internal test is
  one-shot: nothing may be fitted, selected, or re-thresholded on it.**

## Read next
| Task | Read |
|---|---|
| The current plan | `coordination/PLAN-UPDATE-2026-08-27.md` (docs 00–08 are history) |
| The frozen decision | `results/router-fitting-v2/freeze.json` · `threshold-artifact.v1.json` |
