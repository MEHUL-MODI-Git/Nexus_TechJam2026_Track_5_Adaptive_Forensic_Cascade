"""AUROC must not depend on input order.

R4, Codex review 2026-08-29. Several diagnostic scripts assigned unique
sequential ranks instead of average ranks for ties. Verdict retention is an
integer 0-20, so ties are pervasive: the published internal figure moved between
0.8615 and 0.8775 depending purely on row order. The corrected, tie-aware value
is 0.8696.

The rule this encodes: do not reimplement a metric that already exists in
`src.eval.metrics`.
"""

import numpy as np
import pytest

from src.eval.metrics import auroc


def test_canonical_auroc_is_order_invariant_under_heavy_ties():
    rng = np.random.default_rng(0)
    n = 3000
    # integer scores 0..20, exactly the retention distribution's shape
    scores = rng.integers(0, 21, size=n).astype(float)
    labels = (rng.random(n) < (scores / 25.0)).astype(int)
    scores01 = scores / 20.0

    base = auroc(labels, scores01)
    for _ in range(20):
        perm = rng.permutation(n)
        assert auroc(labels[perm], scores01[perm]) == pytest.approx(base, abs=1e-12)


def test_a_sequential_rank_implementation_would_be_order_dependent():
    """Demonstrates the bug this file guards against, so the guard has teeth."""
    def broken(scores, y):
        order = np.argsort(scores, kind="mergesort")
        ranks = np.empty(len(scores), float)
        ranks[order] = np.arange(1, len(scores) + 1)   # no tie averaging
        p, n = int((y == 1).sum()), int((y == 0).sum())
        return float((ranks[y == 1].sum() - p * (p + 1) / 2) / (p * n))

    rng = np.random.default_rng(1)
    n = 2000
    scores = rng.integers(0, 21, size=n).astype(float)
    labels = (rng.random(n) < (scores / 25.0)).astype(int)

    seen = {round(broken(scores[perm], labels[perm]), 6)
            for perm in (rng.permutation(n) for _ in range(15))}
    assert len(seen) > 1, "the broken implementation should vary with order"
    # and the tie-aware one must not
    stable = {round(auroc(labels[perm], scores[perm] / 20.0), 12)
              for perm in (rng.permutation(n) for _ in range(15))}
    assert len(stable) == 1


def test_diagnostic_scripts_use_the_canonical_implementation():
    """The three scripts whose published numbers were corrected must import it."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    for rel in ("scripts/diagnostics/retention_signal.py",
                "scripts/validate_on_holdout.py",
                "scripts/diagnostics/certificate_condition_budget.py"):
        text = (root / rel).read_text()
        assert "canonical_auroc" in text, f"{rel} does not use src.eval.metrics.auroc"
        assert "np.arange(1, len(" not in text, f"{rel} still ranks sequentially"


# --------------------------------------------------------------------------
# S2, Codex review 2026-08-29: the sealed reporter kept its own AUROC because it
# needs WEIGHTS (the per-file convention weights each unique image by how many
# times the organizers' archive contains it), and the canonical helper is
# unweighted. Its implementation subtracted half of each row's own negative
# weight, which averages a positive tied with the negative at the same sorted
# index and nothing else -- so rows tied at equal scores but different indices
# were treated as fully ordered and the result depended on input order.
# --------------------------------------------------------------------------

def _sealed_auroc():
    import importlib.util
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "sealed_reference_report", root / "scripts" / "sealed_reference_report.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sealed_reference_report"] = mod
    spec.loader.exec_module(mod)
    return mod.auroc


def test_sealed_auroc_scores_a_single_tied_pair_as_a_coin_flip():
    """The minimal case that exposed it: one positive and one negative at the
    same score. A tie is 0.5, in either row order -- it used to return 1.0/0.0."""
    a = _sealed_auroc()
    assert a([0.7, 0.7], [1, 0]) == pytest.approx(0.5)
    assert a([0.7, 0.7], [0, 1]) == pytest.approx(0.5)


def test_sealed_auroc_is_order_invariant_under_heavy_ties():
    a = _sealed_auroc()
    rng = np.random.default_rng(11)
    n = 4000
    scores = rng.integers(0, 12, size=n).astype(float) / 11.0   # pervasive ties
    labels = (rng.random(n) < (scores * 0.8 + 0.1)).astype(int)
    weights = rng.integers(1, 6, size=n).astype(float)          # per-file multiplicities
    base = a(scores, labels, weights)
    for seed in range(8):
        perm = np.random.default_rng(seed).permutation(n)
        assert a(scores[perm], labels[perm], weights[perm]) == pytest.approx(base, abs=1e-12)


def test_sealed_auroc_agrees_with_the_canonical_helper_at_unit_weights():
    """The deduplicated convention IS unit-weighted, so the two must not disagree."""
    a = _sealed_auroc()
    rng = np.random.default_rng(5)
    n = 3000
    scores = rng.integers(0, 21, size=n).astype(float) / 20.0
    labels = (rng.random(n) < scores).astype(int)
    assert a(scores, labels) == pytest.approx(auroc(labels, scores), abs=1e-12)


def test_sealed_weighted_auroc_matches_the_expanded_unweighted_one():
    """Weighting by file multiplicity must equal physically repeating the rows."""
    a = _sealed_auroc()
    rng = np.random.default_rng(3)
    n = 400
    scores = rng.integers(0, 8, size=n).astype(float) / 7.0
    labels = (rng.random(n) < 0.5).astype(int)
    weights = rng.integers(1, 4, size=n).astype(float)
    expanded_s = np.repeat(scores, weights.astype(int))
    expanded_y = np.repeat(labels, weights.astype(int))
    assert a(scores, labels, weights) == pytest.approx(auroc(expanded_y, expanded_s), abs=1e-12)


def test_the_published_sealed_aurocs_survive_the_correction():
    """The block is the method, not the numbers: nothing published may move."""
    import json
    from pathlib import Path
    art = Path(__file__).resolve().parents[1] / "results/sealed/reference-results.json"
    if not art.exists():
        pytest.skip("sealed artifact not present")
    conv = json.loads(art.read_text())["conventions"]
    assert round(conv["deduplicated"]["clean"]["auroc"], 4) == 0.9964
    assert round(conv["deduplicated"]["all_conditions"]["auroc"], 4) == 0.9821
    assert round(conv["per_file"]["all_conditions"]["auroc"], 4) == 0.9813
