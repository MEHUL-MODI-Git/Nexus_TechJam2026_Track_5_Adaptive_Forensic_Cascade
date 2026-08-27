# eval — harness, metrics, ablations, error analysis
**Owner: Codex · Status: ✅ REPAIR ACCEPTED · CLAUDE RELAY ACTIVE (B-028)**

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
- Container-leak audit is clean: eval metrics do not consume format, extension, encoded size or
  filename-derived features. The SID-Set confound is upstream in decoded source pixels.
- B-028 ACKs a mandatory `quality_only` baseline and requires claims against both CF-only and
  quality-only; Claude holds temporary `[relay]` authority while Codex is limit-blocked.

## 🟢 Gate status
- E1–E5 plus E3c and the provenance/freeze/denominator boundary are accepted/closed.
- No protected cache may launch: router B-018 and corpus/manifest prerequisites remain blocking.
- No release/public-history action is authorized by this continuity update.

## ▶ NEXT ACTION
1. Claude continues under B-028 relay; tag Codex-owned changes `[relay]` and preserve review-first.
2. Add/report `quality_only` only under A-027/B-028 controls; do not revive confounded +39.3 claim.
3. Do not launch protected compute while router/data gates remain blocked.

## Literal next command
```
cd "/Users/mehulmodi/MEHUL WORK/Hackathon/TechJam 2026" && \
tail -n 120 coordination/CHANNEL.md
```

## Hard constraints
- One frozen threshold per method across every condition; incomplete/partial is diagnostic-only.
- Sealed WildFake subset: one run after production freeze; never fitting or component selection.
- Every public number needs method/data/code/config/artifact hashes and source-level uncertainty.
