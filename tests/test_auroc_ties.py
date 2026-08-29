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
