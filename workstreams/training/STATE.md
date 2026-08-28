# training — router corpus, feature cache, router/fusion, calibration
**Owner: Claude · Status: 🟢 ARCHITECTURE FROZEN (mlp+worst-group, threshold 0.4667367651127279) · protected 12k fitting cache BUILT · internal-test cache extracting · one-shot test NOT YET RUN**

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

## 📌 THE FROZEN DECISION (28 Aug 14:59, `16d2e3b`; re-run at 16:32 reproduced it byte-identically)
Selected on **dev** worst-transformation-family fake recall, pre-registered rule, clean-FPR/BAcc constrained:

| rung | thr | dev worst-family recall |
|---|---|---|
| static_average | 0.12725 | 0.1849 |
| quality_only | 0.49680 | 0.5076 |
| logistic | 0.46491 | 0.6860 |
| mlp | 0.42994 | 0.7587 |
| **mlp+wg (SELECTED)** | **0.46674** | **0.8144** |

Worst family is `noise` for every rung; worst exact condition `noise_s0.10`. Paired source bootstrap vs
floors: **+0.630** over static average (CI95 0.613–0.645), **+0.307** over quality-only (0.283–0.331).
Constraint satisfied on dev: clean FPR 0.0736 ≤ 0.0756 cap; clean BAcc 0.9445 ≥ 0.9358 floor.
Model is 1,827 parameters, feature dim 38, geometry features excluded, expert `commfor_384` only.
**This is dev selection, NOT a reportable result** — `freeze.json` stamps itself `NOT_A_HEADLINE_RESULT`.

## ⚠️ OPEN QUESTION the internal test must answer — watch clean FPR
A pre-flight of the evaluator on the **first 300 of 3,000** internal-test sources (partial cache, balanced:
152 clean real rows) gave router worst-family **0.777** vs primary@0.5 **0.101**, paired delta **+0.678** —
consistent with dev, no collapse. **But clean FPR came out 0.1250 against the dev-fitted 0.0736**, which is
**2.4σ high** on that denominator and above the 0.0756 constraint the freeze was selected under. On a
partial, manifest-ordered subset this is a warning, not a finding. If the full 3,000 sources confirm it, the
honest report is that the threshold's clean-FPR constraint **holds on dev but not on unseen sources**, and
that must be published as a limitation — the threshold must NOT be re-tuned on the internal test to hide it.

## ▶ NEXT ACTION — in order
1. **Wait for the internal-test cache** (`build_feature_cache.py`, PID under `caffeinate`, `--evaluation-cache`).
   ETA ~17:30. It must finish stamping `role=evaluation` and `status=complete` or the evaluator refuses.
2. **Run the one-shot evaluation ONCE** (command below). No refitting, no threshold nudge, no rerun-for-a-nicer-number.
3. Fill README §7 Results from the emitted artifact only; resolve the clean-FPR question above explicitly.
4. Then hand to product for the release gate (repo public, MIT, clean-history push) — all still Mehul's calls.

## Literal next command
```
cd "/Users/mehulmodi/MEHUL WORK/Hackathon/TechJam 2026" && \
  .venv/bin/python scripts/evaluate_internal_test.py \
    --cache data/feature_cache/internal-test-v2 \
    --checkpoint results/router-fitting-v2/router.pt \
    --threshold-artifact results/router-fitting-v2/threshold-artifact.v1.json \
    --out results/internal-test/results.json
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
