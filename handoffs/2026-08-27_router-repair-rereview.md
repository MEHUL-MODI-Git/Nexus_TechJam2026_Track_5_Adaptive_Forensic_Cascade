# B-018 router repair — Codex re-review

**Verdict: BLOCK**

This is a read-only re-review of the implementation at f9c6ecb (router files
unchanged by the later eval-only commits). No code, state, changelog, status, or
channel files were changed by this review.

## Verification run

- .venv/bin/python -m pytest tests/test_router.py tests/test_router_train.py tests/test_router_checkpoint.py -q
  → **98 passed** in 12.08s.
- .venv/bin/python -m ruff check src/router/model.py src/router/train.py tests/test_router.py tests/test_router_train.py tests/test_router_checkpoint.py scripts/train_router.py
  → **All checks passed**.
- .venv/bin/python -m pytest tests/ -q
  → **662 passed, 9 warnings** in 28.12s.
- git diff --check f9c6ecb^ f9c6ecb -- ...router files/tests...
  → clean.

## Positives

The following B-018 areas are supported by the focused tests and code review:

- T1’s core consumed-field checks reject NaN/missing/mismatched raw_logit,
  invalid probabilities, and non-boolean ok; the old invalid-score drop path
  is gone.
- T3 measures one-expert score changes and distinguishes
  fusion_weight_degenerate from score degeneracy. The measured correction is
  not suppressed.
- The kill gate requires either the 0.02 delta or non-overlapping bootstrap CIs.
- Class and reliability losses use BCE-with-logits.
- R22 ordering is enforced: placeholder provenance does not fit reliability,
  frozen provenance does, and stale reliability cannot be saved.
- Probability-mean and fixed-weight baselines are present; fixed weights are
  selected on train only; the six-rung ladder is present.
- Normal checkpoint save/load parity, including atomic replacement, passes the
  delivered tests. The ordinary save/load path reconstructs the tested model
  correctly.

## Blocking fixes required

### 1. Enforce the actual cache-key format

src/router/feature_cache.py::compute_cache_key emits a SHA-256 digest of
exactly 64 lowercase hexadecimal characters. src/router/train.py:61 uses
^[0-9a-f]{16,64}$, so truncated 16–63 character keys are accepted. A one-off
check setting every fixture row’s key to "a"*16 returned **ACCEPTED**.

Require the exact 64-character format (and retain the mixed-key rejection).

### 2. Reject malformed row containers and non-strict labels

At src/router/train.py:496, row["experts"] or {} accepts malformed falsey
containers such as experts=[] and silently turns them into all-experts-
unavailable exclusions. Explicit {"e1": None} is also treated as absent.
The required experts field must be a mapping; invalid containers must abort.

The label check at src/router/train.py:493 uses membership in (0, 1), which
accepts True, False, 1.0, and 0.0. A fixture with every label set to
True, 1.0, or 0.0 validated successfully. Require strict integer 0/1,
excluding booleans, before source-label consistency checks.

### 3. Make None threshold provenance controlled

threshold_is_frozen handles a falsey provenance, but document construction at
src/router/train.py:669-673 unconditionally calls
threshold_provenance.startswith(...). run_ladder(...,
threshold_provenance=None) therefore raises an unhandled AttributeError.
Normalize/reject invalid provenance so malformed input produces a controlled
fail-closed error and cannot crash outside the intended validation contract.

### 4. Make the v2 checkpoint loader genuinely fail closed

_REQUIRED_CHECKPOINT_KEYS at src/router/train.py:785-788 contains only the
seven old/base keys. The v2 provenance and selection fields are omitted from
required-key validation. Removing each of the following from a valid checkpoint
was accepted by load_checkpoint:

use_worst_group_loss, n_parameters, feature_names, hyperparameters,
reliability_head_fitted, cache_artifact_sha256, code_revision, and selection.

Require and validate every v2 payload field needed by the contract, including
types/shape consistency and the selection subfields. Also fail at load time on
the following mismatches, all of which currently loaded successfully in
one-off mutations:

- feature_spec["expert_ids"] different from expert_order;
- top-level feature_names different from feature_spec["feature_names"];
- standardizer feature_names different from the reconstructed feature spec;
- standardizer arrays with a shortened mean dimension.

Validate standardizer schema, names, array dimensions, finite numeric values,
and threshold validity before returning LoadedRouter. Preserve strict
weights_only=True behavior and do not retry unsafe loading.

### 5. Remove or repair the stale false T3 artifact claim

The tracked diagnostic artifact results/router-pilot/training.json:65-66
still contains fusion_comparison_degenerate and states that every rung
“necessarily emits the primary expert’s score unchanged.” That is precisely the
claim T3 deletes. It must not remain as an active repository artifact: remove it,
regenerate it with the repaired schema/wording, or clearly replace it with a
truthful diagnostic-only artifact that cannot be mistaken for the current
router result.

## Gate condition

The normal tests are green, but the exact cache-key requirement, strict malformed
input handling, and fail-closed v2 loader are acceptance-boundary issues. The
router repair remains **BLOCKED** until the fixes above are implemented and
re-reviewed with focused adversarial tests. No code was changed in this review.
