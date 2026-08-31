# Deviation record — the decision threshold was fitted on train, not held-out dev

**Raised by:** Codex (AGENT-B) peer review, 2026-08-29, finding R2
**Accepted by:** Claude (AGENT-A), same day. **Requires Mehul's call on submission acceptability.**

## What the protocol required

our evaluation protocol: *"Threshold/calibration fitting occurs only on held-out dev;
test/external/sealed runners never expose a fitting path."*

## What the code did

`scripts/freeze_router.py` builds both batches (lines 88-90) but passes the **train** rows and
**train** scores to `select_threshold` (lines 100-109). The emitted artifact therefore records
`n_dev_sources: 8998` / `n_dev_rows: 179960` — the 12,000-source fitting split's train half —
while README §6 and several deliverables described it as dev.

The rung *selection* (`mlp+wg` over four alternatives) WAS made on held-out dev, and the
internal test, the second holdout and the sealed reference set were never touched by any
fitting step. So the deviation is confined to where the threshold value came from.

## Measured impact

Counterfactual on the true 3,000-source dev split, computed independently by Codex:

| | threshold | dev worst-family | dev clean FPR |
|---|---|---|---|
| frozen (train-fitted) | 0.4667367651 | 0.81444 | 0.07600 |
| dev-fitted counterfactual | 0.4636303604 | 0.81565 | 0.07667 |

A 0.003 difference in threshold and ~0.001 in worst-family recall. There is also no sign of
the optimism this class of error usually produces: the frozen threshold generalised *upward*,
to 0.8258 on the internal test, 0.8289 on the fresh holdout and 0.8787 on the sealed set.

## Why the threshold was NOT changed

The sealed reference subset may be scored exactly once and has already been scored at
0.4667367651. Re-fitting the threshold would leave our only official benchmark number describing
a system we no longer ship — a worse defect than the one being corrected. The same reasoning
blocks adopting the probe-free variant (README §8b).

## Disposition

1. Public wording corrected everywhere to state exactly where each component was fitted.
2. Threshold unchanged; artifact left as-is with this record explaining its `n_dev_*` fields.
3. `scripts/freeze_router.py` is **not** patched, because patching it would make the code
   disagree with the artifact it produced. Any future freeze must pass `dev_rows`.
4. **Open for Mehul:** whether a train-fitted threshold is acceptable for submission given the
   measured impact above. Our recommendation is yes, disclosed — but it is not our call.
