# Phase-4 exit review at `53680dd` — BLOCK

**Reviewer:** Codex (AGENT-B)  
**Scope:** Phase 4 tasks 4.1–4.7 and the exact exit test in `06-build-plan.md`  
**Verdict:** BLOCK. The measured results are not numerically rejected, but the frozen evaluation
and release surfaces do not yet meet the repo's own fail-closed/reproducibility contract.

The sealed model was not invoked and its prediction dump was not modified.

## Evidence run

- Current focused protocol/publication suite: **102 passed**.
- Same code boundary's full suite from B-031: **769 passed, 1 skipped, 9 warnings**.
- Independently inspected the current internal cache: **60,000 rows, 3,000 sources, exactly one of
  every official condition per source, consistent labels, split=`test`, zero malformed expert
  score rows**. This supports the current numbers, but the reporter does not enforce those facts.
- Ran the literal Phase-4 exit command from the build plan:

  ```text
  uv run python scripts/run_eval.py --config configs/frozen.yaml
  usage: run_eval.py ... --rows ROWS ...
  error: the following arguments are required: --rows
  ```

  `configs/frozen.yaml` does not exist and `run_eval.py` has no `--config` argument.

## Blocking findings

### P0 — the Phase-4 exit test is absent

The ground-truth build plan requires:

```text
scripts/run_eval.py --config configs/frozen.yaml
```

to reproduce every reported table from the feature cache. There is no frozen config and the
canonical evaluator only accepts prediction-row CLI flags. README §5 reproduces the old 8,000-row
placeholder smoke diagnostic, not the protected internal-test, ablation, abstention, rescue,
holdout, sealed-summary or ops tables that are actually published.

Required repair: add one tracked frozen reproduction manifest/config and an executable entry point
that validates exact inputs/artifact hashes and regenerates or verifies every published table. The
sealed branch must be summary-only over the preserved dump—never model inference.

### P0 — the actual headline reporter bypasses the accepted fail-closed evaluator

`scripts/evaluate_internal_test.py:131-191` checks only `manifest.role`, loads cache rows directly,
does not validate row schema or exact source × condition coverage, hashes the manifest but not the
rows, and serializes with JSON's default `allow_nan=True`.

Direct reproduction:

1. copied the real complete manifest into a temporary cache;
2. supplied 39 rows from two sources, with the second source missing one of its 20 conditions;
3. invoked the reporter with the frozen checkpoint/artifact and two bootstrap resamples.

It returned **rc=0**, wrote `n_rows=39`, `n_sources=2`, and emitted `NaN` paired headline statistics.
The copied manifest still claimed the full 60,000-row cache. This is precisely the boundary that
the accepted `src.eval` harness was built to refuse.

Required repair: use a test/evaluation-cache validator that enforces strict schema, manifest/cache
key and row-file identity, expected row/source counts, exactly one canonical condition per source,
consistent labels/splits and finite metrics before scoring. Reject non-finite output and write JSON
with `allow_nan=False`. Prefer routing this reporter through the canonical eval boundary rather than
maintaining a second evaluator.

The real local cache passed an independent version of these checks, so this finding rejects the
reporter's proof, not the current numerical values.

### P0 — the production expert is not frozen in the serving config

Phase 4.1 says the architecture is frozen, but `configs/predict.yaml` carries no expert revision and
`PredictionService` constructs `CommForExpert(device=...)`; the adapter therefore receives its
default `revision=None`. `LICENSES.md` already records this as an open release task. A fresh clone
downloads whichever Hugging Face revision is current, not necessarily the recorded
`6076002bf0d9dd37537f965ee2f06f826c333b61` used by the feature caches.

The clean-checkout proof shows today's mutable download runs; it does not freeze tomorrow's bytes.
The freeze artifact also names checkpoint paths without hashing the expert weights.

Required repair: pin the expert revision in the serving config and pass it through every factory;
fail closed if the resolved revision differs. Bind the resolved expert/checkpoint identity into the
frozen manifest. This does not refit the router or rerun sealed data.

### P1 — Phase-4.2's generator and artifact still assert false threshold provenance

`scripts/ablation_matrix.py` repeatedly says every rung uses a **dev-fitted** threshold, including
the committed artifact note. Lines 99–108 actually compute candidate scores/grid and call
`select_threshold` on `train_rows`. README was corrected to “train half,” but its cited artifact
and generator still contradict it.

The script also calls itself the “full ablation ladder” while its `RUNGS` contains five rows and
omits the implemented `probability_mean` and `fixed_weights` rungs. Probe-free and rescue ablations
exist in separate artifacts, but there is no frozen reproduction index that maps them to the Phase
4.2 matrix.

Required repair: correct the generator/artifact provenance to train-fitted without changing the
thresholds, and either include the omitted rows/arms or explicitly document their one-expert
identity and link every separate ±probe/±rescue artifact from the frozen reproduction manifest.
No re-selection is permitted.

### P1 — the release-facing status contradicts the shipped system

README lines 6–9 still say **Phase 2**, baseline-only deployment and router deployment pending;
line 38 says real router training is not accepted. Lines 47–69 in the same file say the trained
router, frozen threshold and abstention are served and evaluated. The submission checklist still
says A-033 awaits Codex re-review, even though B-030/B-031 superseded it. The explicitly shareable
system-state handoff remains stale as recorded in B-031.

Required repair: one repo-wide current-state sweep covering README, submission checklist, STATUS,
workstream STATEs and the shareable handoff. Historical log entries may remain historical; current
headers/status blocks may not contradict one another.

### Existing P0 — B-031 is still open

No repair landed after B-031. The sealed summary still accepts fractional `file_multiplicity` and
string `"false"` abstention values that silently move reported metrics. Its strict-schema tests and
the shareable-document repair remain required.

## Phase-4 items that are substantively present

- The architecture/router/threshold artifacts exist and are tracked; no recommendation here
  changes the selected system or threshold.
- The one sealed prediction run is preserved and numerically complete. Do not rerun it.
- README §7 contains a compact clean-versus-transformed protected-data summary.
- `deliverables/error-analysis-note.md` contains representative FPs/FNs and limitations.
- Ops evidence and a fully numbered video script exist.
- The public video, trademark choice, licence approval, remote-history rewrite and repo-public
  switch remain Mehul's owner actions; the Phase-4 insurance/public recording is not yet done.

## Minimum repair packet for focused re-review

1. Close B-031's strict sealed field schemas.
2. Add strict internal-test cache/coverage/finite-output guards with the 39-row reproduction as a
   regression.
3. Implement the frozen Phase-4 reproduction command/manifest with exact input and artifact hashes.
4. Pin and enforce the CF-384 revision on the live path.
5. Correct ablation provenance/scope without selecting or tuning anything.
6. Sweep current release-status prose.

Then request one focused gate. None of these requires sealed inference or threshold/model refitting.
