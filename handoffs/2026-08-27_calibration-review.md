# Calibration / threshold module peer review (Codex heavy)

**File reviewed:** `src/router/calibration.py` + `tests/test_calibration.py`

**Scope:** metric/protocol correctness before Phase-2 dev fitting.
**Verdict:** APPROVE-WITH-FIXES. Nothing here blocks Phase-0 or Phase-1 baseline measurement; do not fit/freeze a Phase-2 artifact until the required items land.

## Required fixes before Phase-2 use

1. **Validate the dev protocol, not only array lengths.** `DevSet` must reject scores outside `[0,1]`, unknown family IDs, condition↔family mismatches, and inconsistent labels for a `source_id`. Threshold selection must require both classes on clean and all six official transformed families with fake rows. Skipping an absent family silently changes a six-family objective into a five-family objective; exploratory helpers may skip, but the artifact-producing path must fail closed.
2. **Validate candidates and define tie-breaking.** Add finite `[0,1]` checks and boundary candidates (`0.0`, `1.0`) to the observed-score grid. When bootstrap objective values tie, select deterministically by: higher clean balanced accuracy, then lower clean FPR, then higher threshold. Record the tie-break in the artifact. The current ascending first-win rule quietly favors the lowest threshold/highest FPR among equal-robustness candidates.
3. **Validate the artifact on construction/load.** Threshold/probability/rate fields finite and bounded; counts non-negative; required provenance non-empty for a frozen artifact. Save atomically. A test/sealed runner should load through a validating constructor, never raw JSON trust.
4. **Harden calibration helpers.** Reject empty arrays, non-binary labels, non-finite bias/temperature, invalid probability ranges, and invalid ECE bin counts. Use a numerically stable sigmoid for extreme logits. `expected_calibration_error` must fail on invalid scores/labels rather than binning them silently.
5. **One entropy definition really means one.** `calibration.binary_entropy` is declared canonical, but `features.binary_entropy_array` reimplements the formula. Vectorize/import the canonical helper or move one validated array implementation to a neutral module and have both consumers call it; add scalar/array parity tests.

## Interpretation correction for the write-up

The smoke table demonstrates an **operating-point/threshold-selection** gain (and motivates later probability calibration); it does not isolate a calibration gain. Say “held-out calibration + threshold selection can recover the poor placeholder operating point,” not “calibration alone adds ~15 BAcc points.” No smoke threshold is a fitted or headline result.

## Behaviors already correct

- six-family objective excludes clean;
- severities pool within family;
- label-stratified source bootstrap moves views together;
- infeasible selection does not relax constraints;
- exact-condition result is reported separately;
- temperature+bias form is appropriately small;
- ECE includes probability endpoints.
