# Phase 0 core gate — Claude evidence packet

**Owner:** Claude · **Submitted:** 2026-08-27 · **Verdict requested from:** Codex

## Scope delivered
- **0.2 decode** · **0.3 all 20 official transforms** · **0.4 golden tests** · **0.5 CF-384 adapter** · **0.6 sanity check (both halves)**.
- Beyond Phase 0 (built early, unblocked): `PredictionService` + `scripts/predict.py`, `scripts/infer_dir.py` (required deliverable), 1.4 quality descriptors, doc-03 step-4 self-probes, `src/router/calibration.py`, `src/router/{features,model}.py`.

## Evidence

### Suite
```text
.venv/bin/python -m pytest tests/ -q
387 passed, 47 warnings
```
Core-owned: decode 14 · transforms 144 · golden 63 · expert contract 11 · service parity 8 · infer_dir 18 · quality 29 · probes 17 · calibration 30 · router 37.

### 0.6 sanity — BOTH halves PASS (independently re-run by Claude on MPS)
```text
.venv/bin/python scripts/sanity_check.py --manifest data/manifests/smoke_v1.json
MPS-vs-CPU consistency (5 images, tolerance 1e-2): worst |delta| = 4.28e-05 -> PASS
Clean-smoke separation: 200 real / 200 fake scored
  mean p_fake real=0.0007  fake=0.5056
  AUROC = 0.9923 (floor 0.9) -> PASS
```
Reproduces Codex's CPU run exactly on a different backend — cross-verified, not merely re-asserted.

### Independent verification of the product gate's data claims
Re-derived from the artifacts rather than trusting the packet:
```text
rows=400  labels={real:200, fake:200}
val2017 occurrences (manifest + acquisition): 0
distinct sha256: 400 | any sha mapped to >1 source_id: 0     <- the [F1] rule
re-hashed 40 random images from disk: 0 missing, 0 sha mismatches
all 400 manifest files present on disk
license_ids: {SID-CC-BY-4.0: 200, COCO-TERMS: 200} — both documented in LICENSES.md
splits: {validation: 200 (SID-Set), train2017: 200 (COCO)}
```

### FINDING — the default 0.5 threshold is badly miscalibrated (clean smoke, diagnostic only)
AUROC 0.9923 conceals a poor operating point: the model RANKS almost perfectly but the default cut sits in the wrong place.

| threshold | fake recall | FPR | BAcc |
|---|---:|---:|---:|
| **0.500** (current placeholder) | **0.530** | 0.000 | 0.765 |
| 0.100 | 0.685 | 0.000 | 0.843 |
| 0.016 | 0.850 | 0.010 | 0.920 |
| 0.005 | 0.895 | 0.020 | 0.938 |

**At the default we miss 47% of AI-generated images.** Fake-score percentiles show why: p25=0.057, p50=0.575 — a large mass of true fakes scores far below 0.5, while reals sit at p99=0.008.

This independently CONFIRMS the third-party claim recorded as UNVERIFIED in `handoffs/2026-08-26_commfor-integration.md` (that the useful threshold is ~0.016, not 0.5). It is now verified on our own data.

**Discipline:** this is a DIAGNOSTIC on the smoke set, which is not a dev split. **No threshold is frozen from these numbers and none may be.** The operating point is selected in Phase 2 on a held-out dev split by the frozen objective (`src/router/calibration.py`). Recorded here as motivation and as a demo caveat, not as a result.

## Known gaps / notes
- `configs/predict.yaml` still carries `threshold: 0.5` with `threshold_provenance: PLACEHOLDER-uncalibrated-phase0`. Given the finding above, the Gradio demo will call roughly half of AI images "REAL". Correct fix is Phase-2 calibration; interim mitigation is presentation-side (see CHANNEL A-018).
- LOTA parked by Mehul; cascade currently N=1 expert. Router/feature code handles N=1 with missing-indicators (tested).
- Phase-0 exit test is met on the core side; Gradio half is evidenced in the product packet.
