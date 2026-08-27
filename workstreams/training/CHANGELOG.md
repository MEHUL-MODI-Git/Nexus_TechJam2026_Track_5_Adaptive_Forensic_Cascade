# CHANGELOG — training (newest first, append-only; corrections are new entries)

## 2026-08-26 — Workstream initialized
Why: Mehul requested session-continuity + dual-agent framework (26 Aug).
What: STATE.md created with Phase-0/next actions from 06-build-plan.md. No code exists yet.

## 2026-08-27 10:20 — DegradePrint response branch measured and failing; correction-head proposal
`scripts/diagnostics/degradeprint_probe.py` (new, DIAGNOSTIC-only, Ruff clean). Runs the update
pack's own cheap kill test (doc 10 §11, bar ~+2 pt) on the EXISTING 24,000-row pilot cache at zero
new compute — the cache already stores `probes.<expert>.probe_scores`, so no extraction was needed.

Four arms, grouped split by `source_id`, one threshold rule (train-fitted clean FPR 5%), so arms
differ only in feature set. Dev worst-family (`noise` in every arm and seed) fake recall:

| arm | features | s0 | s1 | s2 | mean |
|---|---|---:|---:|---:|---:|
| A | primary logit | .2062 | .2196 | .2062 | **.211** |
| B | + quality descriptors | .5771 | .6168 | .6188 | **.604** |
| C | + quality + response signature | .5771 | .6028 | .6562 | **.612** |
| D | primary + response only | .2292 | .2635 | .2687 | **.254** |

- **C − B = +0.000 / −0.014 / +0.038.** Mean +0.8 pt, sign unstable → **fails doc 10 §12.**
- Doc 10 §18's own named risk realized: probes encode *severity*, and badly (D−A = +4.3 pt) next to
  quality descriptors measuring it directly (B−A = **+39.3 pt**).
- **Task 1.4 quality descriptors are the largest measured gain in the project**, at a *lower* clean FPR.
- Scope limit on record: logit-space half only. Embedding drift untested — no row carries an
  embedding (`experts.<id>.embedding_key` null throughout); testing it costs a cache rebuild.

Consequence for the router: `results/router-pilot/training.json`'s four identical rungs are evidence
that **fusion was the router's only lever**, not that its 43 features are weak — they already carry
the 39-point signal with no way to apply it. Proposed (A-023, needs Codex ACK + DECISIONS entry):
**router head becomes a CORRECTION head over the primary logit conditioned on quality + reliability
features**, fusion re-entering only if a second always-on expert earns its slot. This makes
`fusion_comparison_degenerate` obsolete rather than merely inaccurate, resolving B-018 item 3 by
deleting the claim rather than the bias head.

