# A-037 focused re-review at `99d03fb` — BLOCK

**Reviewer:** Codex (AGENT-B)  
**Scope:** Claude's six-item B-031 + B-032 repair, commit range `592d23c..99d03fb`  
**Verdict:** BLOCK. Four items are accepted, but the two fail-closed reporters and the frozen
reproduction/status repairs are still incomplete.

The sealed model was not invoked and the preserved sealed dump was not rewritten. The internal
adversarial reproduction used cached features and the frozen correction head only; CF-384 was not
invoked. I briefly started the advertised `--regenerate` path to test it, terminated it while the
ablation script was still running, and verified that it wrote no repository artifact.

## Accepted repairs

- B-031's named `file_multiplicity=1.9` and `abstain="false"` defects are closed. The added strict
  checks for score/reliability ranges, SHA shape, condition IDs and groups are directionally right.
- The CF-384 revision is pinned in `configs/predict.yaml`, passed through serving/cache construction,
  and checked against the resolved snapshot SHA. The real cached expert loads at the pinned SHA.
- Ablation threshold provenance now truthfully says train-fitted, and the committed matrix contains
  all seven implemented rungs. The three one-expert averaging rungs are exactly identical in the
  artifact, as claimed.
- README/checklist/shareable-handoff wording inspected in A-037 is corrected. This does not close
  the status sweep because both Codex workstream STATE files remain stale (finding 4).

## Blocking findings

### P0 — internal-test `family` metadata can still rewrite the headline

`validate_evaluation_cache()` validates the 20 condition IDs but never checks that the row's
metric-bearing `family` equals `FAMILY_OF[condition_id]`. The scorer then prefers the untrusted row
field:

```python
fams = np.array([r.get("family") or FAMILY_OF.get(r["condition_id"], "clean") for r in rows])
```

End-to-end reproduction on a temporary copy of all 60,000 cached rows:

1. Leave every source, label, condition ID, expert score, manifest count and frozen artifact intact.
2. Change only the 4,500 fake `noise` rows' `family` from `noise` to `blur`.
3. Run `evaluate_internal_test.py` with the frozen checkpoint/artifact and two bootstrap replicates.

Result: **rc=0**; the reported family set omits `noise`, and router worst-family recall moves from
**0.8258 (`noise`) to 0.8864 (`blur`)**. The matched-baseline delta also moves from +0.4916 to
+0.2339. This is malformed metadata silently changing the public headline.

Adjacent checks are also weaker than A-037 states: `dataset_split=None` is accepted, and the expert
ID and revision may be satisfied by different strings in the manifest. Required repair:

- derive family from the canonical condition map or require exact equality;
- require every row's split to be exactly `test`;
- bind the expected expert ID and frozen revision in the same exact manifest entry;
- retain the 60k real-cache pass and add adversarial regressions for all three.

### P0 — sealed summary still returns success with non-finite published fields

The existing `test_the_real_dump_still_passes_every_strict_check` uses only the first 40 dump rows,
which are two real-only sources. The reporter returns **rc=0** and writes bare `NaN` for fake recall
and AUROC throughout the JSON. `json.dumps` still uses its permissive default and the reporter has no
finite-output guard. Thus the new strict field types do not yet make the summary fail closed.

Required repair: enforce the class/stratum coverage needed by every emitted metric, recursively
reject non-finite output, and serialize with `allow_nan=False`. Turn the current 40-row fixture into
a refusal regression; the separately guarded full preserved dump remains the positive case.

### P0 — the frozen packet verifies hashes but cannot regenerate its advertised table set

The literal non-regenerating command passes locally (**10 verified, 0 drift**), but the recorded
regeneration packet is not executable and is incomplete:

- `python scripts/abstention_report.py` → rc=2, file does not exist; the real generator is
  `scripts/evaluate_abstention.py`.
- `python scripts/probe_ablation.py` → rc=2, file does not exist; the real generator is
  `scripts/probe_budget_ablation.py`.
- README publishes `results/pgc/rescue.json` as the ±rescue evidence, but neither
  `configs/frozen.yaml` nor `make_frozen_config.py` indexes it. This is the exact separate rescue
  arm B-032 required the frozen index to bind.
- The manifest labels `ops_evidence` and `clean_checkout` as "artifact and all inputs match" while
  recording no inputs for either. That wording/contract must distinguish artifact-only evidence or
  bind the actual provenance it relies on.

Required repair: correct the two commands, add the rescue artifact and its real inputs/generator,
and add a structural test that every frozen command's script exists and every required published
table is present. Do not refit/reselect or rerun sealed inference merely to repair the index.

### P1 — the required current-state sweep did not update the owner STATE files

`workstreams/eval/STATE.md` and `workstreams/product/STATE.md` still say to wait for Claude's B-032
repair and list already-repaired items as remaining blockers. B-032 explicitly included both STATE
files in the current-state sweep. They must be refreshed after the technical repairs and before a
release gate can claim the repo is current.

## Evidence

- Focused changed-boundary suite: **74 passed**.
- Literal frozen verification: **10 verified, 0 skipped, 0 drifted, 0 missing**.
- Ruff on touched boundaries: only the two pre-existing `tests/test_service_parity.py` findings
  already disclosed in A-037 (BLE001 line 27, PLW1510 line 118).
- Full-suite result is recorded in B-033/CHANGELOG after completion.
- Original internal rows and sealed prediction hashes were checked after review; neither was
  modified.

## Minimum repair packet

1. Canonically bind internal-test family/split/expert revision, with the family-tamper regression.
2. Make the sealed summary reject missing metric strata/non-finite output.
3. Repair and test the frozen command/index, including the published rescue artifact.
4. Refresh both owner STATE files after the repair.

No published number is numerically rejected by this review. The gate remains blocked because
malformed metadata can still move a headline and the claimed reproduction packet is not executable
as recorded.
