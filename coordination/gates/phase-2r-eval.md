# Phase 2R eval repair gate — Codex owner packet

**Owner:** Codex (AGENT-B)  
**Commit:** `ff943c7a4a41723c23a066540c74e514b95d707e`  
**Requested reviewer:** Claude (AGENT-A)  
**Owner verdict:** READY FOR PEER RE-REVIEW; Phase 2R.1 eval remains unaccepted until reviewer ACK.

## Execution provenance

Mehul's model-economy pattern was followed visibly:

1. Codex heavy froze `specs/phase2r-eval-repair.md` in `c4a62f4`.
2. A lighter Codex agent wrote the bounded tests/implementation in the six permitted eval files.
3. Codex heavy reviewed every changed line, rejected two green-suite mistakes (test-only private
   threshold construction and bootstrap keys incompatible with the actual calibration producer),
   sent a bounded correction pass back, then independently added the missing provenance adversarial
   matrix and corrected dataset composition from view counts to source counts.

No Claude-owned router/core code was staged or committed.

## E1–E5 evidence

| gate | executable boundary now enforced |
|---|---|
| E1 exact coverage | one missing method/source/condition view refuses reportable output even when every condition exists globally |
| E2 canonical grid | caller overrides must exactly equal live `CONDITION_IDS`/`FAMILY_OF`; a seven-condition grid refuses |
| E3 threshold artifact | direct `FrozenThreshold(...)` construction fails; loader validates the complete real producer schema, retains exact bytes, and assembly re-hashes/re-parses them |
| E4 diagnostic schema | recursive key scan confirms no literal `headline` exists anywhere; methods use `diagnostic_summary` |
| E5 pairing | methods align by sorted `(source_id, condition_id)`; shuffling method B leaves the complete paired-delta block identical; unequal keys emit no diagnostic delta |

## Provenance/freeze/denominator evidence

- `eval-results.v1` requires `eval-run-manifest.v1`; legacy/missing manifests remain diagnostic-only.
- Dataset manifest bytes are hashed and parsed; exact source IDs plus label/dataset/group/path
  identities must match rows. A four-source result citing the real 400-source smoke manifest refuses.
- Transform hash is the actual `configs/transforms.yaml` hash, separate from the dataset hash;
  pipeline/golden versions and bytes are validated against live canonical files.
- Every method carries checkpoint/preprocessing/parameter/config provenance; run ID and bootstrap
  seed must match; class/group counts use independent sources, not 20 correlated views.
- Failure ledger must be hashed `eval-failure-ledger.v1`; any non-zero or inconsistent denominator
  refuses reportable output.
- Production-freeze digest binds its canonical payload; run/code/pipeline/golden/transform/
  threshold/method identities must match. Sealed output additionally requires an explicit boolean
  authorization.
- Placeholder/control validation, deterministic zero-flip attribution, and atomic JSON/Markdown
  writes are covered.

## Independent verification

```text
.venv/bin/python -m pytest tests/test_eval_protocol.py tests/test_eval_results.py tests/test_run_grid.py -q
85 passed in 2.53s

.venv/bin/ruff check src/eval/protocol.py src/eval/results.py src/eval/report.py \
  scripts/run_eval.py tests/test_eval_protocol.py tests/test_eval_results.py
All checks passed!

.venv/bin/python -m pytest -q
630 passed, 9 warnings in 24.14s
```

The full-suite number is from the shared working tree while Claude's uncommitted router repair was
also present; the focused eval/run-grid result isolates this commit's gate. `git diff --check`
passes.

Real-artifact CLI check over `results/grid-smoke-v1/prediction_rows.jsonl`: 8,000 rows / 400
sources validated, diagnostic JSON+Markdown written atomically, schema `diagnostic-results.v1`, no
literal `headline` key, legacy run manifest visibly warned as diagnostic-only. Existing tracked
diagnostic artifacts were not rewritten or promoted.

## Reviewer request

Please rerun the focused command and adversarially inspect E1–E5 plus the dataset/failure/freeze
guards. Reply APPROVE / APPROVE-WITH-NOTES / BLOCK in CHANNEL. A pass clears only the eval half of
Phase 2R.1; training B-018 and protected-data prerequisites remain independently blocking.
