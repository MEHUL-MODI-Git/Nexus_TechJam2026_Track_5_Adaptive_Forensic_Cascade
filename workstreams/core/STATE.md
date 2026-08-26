# core — decode, transforms, expert adapters, predict path
**Owner: Claude · Status: 🟢 PHASE 0 (0.2–0.6) + infer_dir + 1.4 + probes GREEN (306 tests) · 0.6 half-done pending Codex 0.7 · LOTA parked**

## ✅ Done 2026-08-26 (evening → ~22:10)
- Spec freeze: `specs/phase0-core.md` **v2 FROZEN**, all 10 Codex review notes resolved (`[N#]` inline), 3 non-blocking notes adopted. Recorded in DECISIONS + CHANNEL A-010.
- **0.2 decode** · **0.3 transforms (all 20)** · **0.4 golden tests** · **0.5 CF-384 adapter** · **0.6 sanity (MPS half)** — all built, all tests green. Plus `PredictionService` (the single decision path) + `scripts/predict.py`. Detail: `workstreams/core/CHANGELOG.md`.
- **First real measurements:** MPS-vs-CPU worst |Δlogit| = **1.48e-05** (tolerance 1e-2) → MPS trusted, no CPU fallback. CF-384 = **21.81M params**, `@6076002b`. **~14 ms/image** on MPS (~70 img/s) — above the 10 img/s Phase-2 escalation threshold.
- 2 protocol deltas found by tests (blur kernel clamp for <7px images; `DecodedImage` immutable-not-hashable) — CHANGELOG + CHANNEL A-011. Goldens unchanged, `PIPELINE_VERSION` still 0.1.0.

## ▶ NEXT ACTION
1. **Blocked-ish, not blocking:** finish **0.6** by running `scripts/sanity_check.py --manifest data/manifests/smoke_v1.json` once Codex's **0.7** smoke manifest lands (needs ≥20 real + ≥20 fake). Script already handles the missing file cleanly. Clean-smoke AUROC ≤0.9 ⇒ HALT and diagnose preprocessing (NOT auto model rejection).
2. **Awaiting one Codex ACK:** `infer_dir.py` corrupt-file default (A-010 item 3 — my null-row-per-image counter vs product §5 omit-row). Phase 1 item; does not block.
3. When Codex's 0.1 scaffold lands: confirm my modules sit inside it cleanly (`pyproject.toml` packaging, pytest config discovering `tests/`), re-run the suite, then `[claude]` commit.
4. **Phase 1 (my side):** `scripts/infer_dir.py` ✅ built (18 gate tests, policy ACKed) · **1.4 quality descriptors** ✅ built (29 tests). **1.2 LOTA PARKED by Mehul** (revisit later). Impact assessed: promoting RIGID (training-free) keeps the cascade two-expert, so disagreement + fusion features survive and the router keeps both heads; costs are a weaker/slower expert 2 and overlap with WaRPAD rescue. **Before committing: verify the RIGID repo exists as our notes claim and check its backbone param count against the <2B rule.** Self-probes (doc 03 step 4) ✅ built — they are the reliability signal that does NOT depend on a second expert existing.

## Other open threads (do not lose)
- Webinar 28 Aug may change transform params — spec + `configs/transforms.yaml` are parameterized; any change ⇒ `PIPELINE_VERSION` bump + `scripts/regen_golden.py` + cache bump + DECISIONS entry.
- OmniAID: one bounded ≤3h attempt Phase 1, only if schedule green.
- LOTA weights are Baidu-Netdisk-only (`handoffs/2026-08-26_lota-integration.md`) — may need Mehul to fetch.

## Literal next command
```
cd "/Users/mehulmodi/MEHUL WORK/Hackathon/TechJam 2026" && .venv/bin/python -m pytest tests/ -q && tail -40 coordination/CHANNEL.md
```

## Hard constraints
- Never resize/recompress before expert preprocessing. Transform changes ⇒ `PIPELINE_VERSION` bump + golden regen + cache-version bump.
- Sealed WildFake subset: never input to any fitting.
- Sigmoid applied exactly once, inside the adapter. Failures never become scores.

## Read next
| Task | Read |
|---|---|
| Build anything | `specs/phase0-core.md` v2 (the frozen contract) |
| What exists already | `workstreams/core/CHANGELOG.md` |
| LOTA adapter | `handoffs/2026-08-26_lota-integration.md` |
| CF adapter details | `handoffs/2026-08-26_commfor-integration.md` |
