# core — decode, transforms, expert adapters, predict path
**Owner: Claude · Status: 🟢 Phase 0 core COMPLETE (0.2–0.6 all green) + infer_dir + 1.4 + probes · ⏸ candidate-expert work GATED behind 2R.1**

## ✅ Built (detail in `workstreams/core/CHANGELOG.md` — do not re-derive here)
- **0.2 decode · 0.3 transform grid (20 conditions) · 0.4 golden tests · 0.5 CF-384 adapter · 0.6 sanity** — all
  done 2026-08-26/27. Plus `PredictionService` (the single decision path), `scripts/predict.py`,
  `scripts/infer_dir.py` (REQUIRED deliverable, 18 gate tests), **1.4 quality descriptors** (29 tests),
  **self-probes** (doc 03 step 4, 17 tests).
- **0.6 is DONE, both halves.** MPS≡CPU worst |Δlogit| **1.48e-05** (tol 1e-2) ⇒ MPS trusted, no CPU
  fallback. Clean-smoke **AUROC 0.9923** reproduced independently on MPS against Codex's CPU run.
- **Measurements on record:** CF-384 = **21.81M params** @ revision `6076002b`; **~14 ms/image** MPS
  (~70 img/s) on 256px fixtures — but real 1024×1024 corpus throughput is **7.83 rows/sec** end-to-end
  with three probes (training STATE holds the cache arithmetic). The default 0.5 threshold is badly
  miscalibrated (fake recall 0.530); ~0.016 gives 0.850 recall — no threshold is frozen from smoke data.
- 2 protocol deltas found by tests (blur kernel clamp <7px; `DecodedImage` immutable-not-hashable),
  logged A-011. Goldens unchanged, `PIPELINE_VERSION` still 0.1.0.

## ⚠️ Model-slot reality (post-LOTA, jointly adopted A-023/A-024/B-020)
- **CF-384 remains the production primary.** Its HF revision is **not pinned in code** — disclosed in the
  README; pinning is a pending repo-mechanics item, not a core-code defect.
- **LOTA reproduction is OFF the schedule** (weights Baidu-gated). **NPR is excluded** — no upstream
  licence and AUROC 0.3174 in a bounded clean-smoke sanity run. **GAPL code integration is licence-blocked**
  (MIT on the HF card only; the official repo has no LICENSE).
- **PGC (Apache-2.0, HF, ~311M) is the one licensed heavy candidate**, and only as a bounded
  preflight/selective-rescue challenger. It is ~14× CF-384, so it enters neither the common path nor the
  15k training cache without a measured ≤12 h extraction plan. WaRPAD/RIGID are attempted only after the
  common path passes its gates. Claude owns every `src/experts/` adapter (B-020 §6).

## ▶ NEXT ACTION — core is deliberately idle until the repair gate clears
1. **Do nothing new in `src/experts/` until 2R.1 passes** (router B-018 repair + eval E1–E5 repair, both
   under peer re-review). Adding a candidate now would invalidate the cache key a second time.
2. **Then, and only then:** PGC preflight — provenance, output polarity, exact parameter count, peak
   memory, per-forward latency on M4 Pro — written up before any grid run. Paper-faithful preprocessing
   is the whole point of this workstream; no adapter lands without a parity test against the reference.
3. Keep the transform pipeline frozen. Any change ⇒ `PIPELINE_VERSION` bump + `scripts/regen_golden.py`
   + cache-version bump + DECISIONS entry. (The 28 Aug webinar that could have forced this was dropped.)
4. Batched CF inference is the obvious throughput win but it modifies a reviewed adapter — proposed, not
   done, and not to be started mid-repair.

## Literal next command
```
cd "/Users/mehulmodi/MEHUL WORK/Hackathon/TechJam 2026" && \
  .venv/bin/python -m pytest tests/ -q && tail -40 coordination/CHANNEL.md
```

## Hard constraints
- Never resize/recompress before expert preprocessing. Sigmoid applied exactly once, inside the adapter.
- Failures never become scores (`ok: false`, never a 0.0 logit).
- Sealed WildFake subset: never an input to any fitting, at any point, for any component.

## Read next
| Task | Read |
|---|---|
| The current plan | `coordination/PLAN-UPDATE-2026-08-27.md` (active overlay) |
| Build anything in core | `specs/phase0-core.md` v2 (the frozen contract) |
| What exists already | `workstreams/core/CHANGELOG.md` |
| CF adapter details | `handoffs/2026-08-26_commfor-integration.md` |
