# eval — harness, metrics, ablations, error analysis
**Owner: Codex · Status: ✅ PHASE 2R REPAIR ACCEPTED/CLOSED · ROUTER/DATA BLOCKERS REMAIN**

## ✅ Current evidence
- Commit 0a40ee8: E3c fixed with shared full threshold-artifact schema validation, sentinel,
  exact forged-artifact regression, and fail-safe "unspecified" provenance.
- A-025 peer verdict on B-023: APPROVE-WITH-NOTES; eval half of Phase 2R.1 is accepted/closed.
- Evidence: 70 focused tests; full shared-tree suite **662 passed / 9 warnings**; Ruff clean.
- Real 8,000-row diagnostic CLI: 400 sources, no literal headline, diagnostic-only warning intact.
- The 24k DegradePrint/quality run remains unprotected diagnostic evidence only; it cannot select a
  submission model, mint a headline, or serve as a trained fallback.
- Router B-018 is separately **BLOCKED** by Codex re-review; see
  handoffs/2026-08-27_router-repair-rereview.md.

## 🟢 Gate status
- E1–E5 plus E3c and the provenance/freeze/denominator boundary are accepted/closed.
- No protected cache may launch: router B-018 and corpus/manifest prerequisites remain blocking.
- No release/public-history action is authorized by this continuity update.

## ▶ NEXT ACTION
1. Wait for Claude’s bounded heavy correction spec → lighter implementation → heavy verification
   of B-018, then re-review the corrected router gate.
2. Do not launch protected compute while the router/data gates are blocked.
3. After both 2R.1 halves and the protected data roles pass, review the mini-pilot and candidate
   comparisons under the repaired harness.

## Literal next command
```
cd "/Users/mehulmodi/MEHUL WORK/Hackathon/TechJam 2026" && \
.venv/bin/python -m pytest tests/test_router.py tests/test_router_train.py tests/test_router_checkpoint.py -q
```

## Hard constraints
- One frozen threshold per method across every condition; incomplete/partial is diagnostic-only.
- Sealed WildFake subset: one run after production freeze; never fitting or component selection.
- Every public number needs method/data/code/config/artifact hashes and source-level uncertainty.
