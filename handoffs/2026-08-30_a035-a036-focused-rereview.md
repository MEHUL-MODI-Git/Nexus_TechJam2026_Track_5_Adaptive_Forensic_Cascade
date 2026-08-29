# A-035/A-036 focused re-review — BLOCK remains narrowly

**Reviewer:** Codex (AGENT-B)  
**Boundary:** `cbe44b6..1c95147`  
**Verdict:** accept S1 and S3; accept the A-036 clean-checkout evidence with notes; keep the
Phase-4/release gate blocked on one S2 fail-closed defect and one residual S4 public-document defect.

The sealed prediction dump was not rerun or modified.

## Verification

- Focused gate:
  `78 passed` across threshold split, sealed guards, tied AUROC, probe semantics,
  clean-checkout tracking, published numbers and serving parity.
- Full repository suite: `769 passed, 1 skipped, 9 warnings` in 61.92 s.
- A-036 evidence is credible: its committed artifact records a clean clone at `578efa7`,
  `756 passed / 14 skipped / 0 failed`, both prediction CLIs returning zero, six images scored,
  and a cold 87.3 MB checkpoint download. The artifact honestly records that the existing
  interpreter/venv was reused, so dependency resolution was not part of that run.

## Accepted

### S1 — threshold split

Accepted. Future freezes now default threshold selection and its candidate grid to held-out dev.
Train reproduction requires the explicit deviation acknowledgement. The shipped threshold and
sealed results did not move. Public README wording now separates dev-selected rung from the
historically train-fitted threshold value.

### S3 — `probe_flip` drift

Accepted. The regression locks the measured values — 550 changed rows, max score delta 0.298885,
two verdict changes — and NIMS scopes its zero-disagreement statement to cache/live parity rather
than training/serving feature parity.

### S2 — tied AUROC and core completeness/identity repairs

The tie-group-weighted AUROC is correct, order-invariant and tested against the canonical metric.
Exact `(sha256, condition_id)` multiplicity, manifest image-set identity, label/group comparison and
the explicit inference-provenance limitation are substantive improvements. The tiny AUROC changes
do not alter any published four-decimal figure.

## Remaining blockers

### 1. S2 still does not fail closed on fields that directly weight/report public metrics

The manifest guard coerces `file_multiplicity` with `int(...)` for comparison, then later uses the
original float as the per-file weight. A manifest multiplicity of 1 therefore accepts dump values
such as 1.9. On a valid 40-row/two-source fixture, changing one source from 1 to 1.9 returned rc=0
and changed per-file effective weight from 40 to **58**.

`abstain` is likewise coerced with `bool(...)`. JSON string `"false"` is truthy, so a malformed row
returned rc=0 and changed deduplicated coverage from **0.525 to 0.500** on the same fixture.

Required repair: schema-validate every metric-bearing field before conversion. At minimum,
`file_multiplicity` must be a strict positive non-bool integer equal to the manifest count, and
`abstain` must be a JSON boolean when present. Add adversarial regressions proving these examples
are refused. Validate the optional reliability/primary score fields consistently as finite/ranged
numbers when present rather than relying on NumPy conversion failures.

This is summary-only work over the preserved dump. Do not invoke the model.

### 2. S4 left an explicitly shareable document materially stale

`handoffs/2026-08-28_system-state-and-honest-assessment.md` says its purpose is a **shareable
context dump** and was updated on 29 Aug. It still:

- labels LOTA simply `MIT`, conflating MIT code with Baidu weights carrying no stated licence;
- calls ablation thresholds `dev-fitted`, contradicting the recorded train-fit deviation; and
- says the sealed run is still in flight and Codex has not reviewed B-024/relay work.

Historical status is acceptable when clearly frozen as historical. This file instead declares
itself updated/shareable, so it must either be refreshed to current truth or prominently marked
superseded/non-public with a link to the current sources. Do not rewrite ground-truth docs 00–08.

## Non-blocking notes

- `summary_code_revision` truthfully records the Git HEAD at summary time, but that artifact was
  generated with uncommitted reporter changes. It therefore does not identify the exact summary
  implementation. The ledger already places it under `NOT_bound_to_the_rows`; adding a reporter
  SHA-256 and dirty-state flag on the next regeneration would make reproduction stronger.
- `verify_clean_checkout.py --source <remote>` records the source worktree's HEAD, not the cloned
  remote's checked-out HEAD. Before using it as proof of a public remote, derive the revision from
  the clone. Its current local-source artifact is unaffected.

## Gate consequence

Phase 4 is not rejected numerically: the preserved run is complete, the repaired AUROC is correct,
and the current suite is green. Acceptance remains blocked because the reporter still accepts
malformed values that silently change published metrics, and a deliberately shareable assessment
still contradicts the repaired release narrative. Both are narrow, summary/document-only repairs.
