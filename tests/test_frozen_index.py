"""The frozen reproduction index must name commands that exist.

B-033 finding 3, Codex review 2026-08-31: `configs/frozen.yaml` listed
`scripts/abstention_report.py` and `scripts/probe_ablation.py`. Neither exists —
the real generators are `evaluate_abstention.py` and `probe_budget_ablation.py`.
The index still verified 10/10 because it checks HASHES, not whether the recorded
command could regenerate the artifact, so the defect was invisible to its own
green result.

That matters beyond tidiness: the demo video says every published table
regenerates from one command. With two commands naming nonexistent scripts, that
claim was false for a fifth of the index.
"""
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "configs" / "frozen.yaml"


@pytest.fixture(scope="module")
def index():
    if not CFG.exists():
        pytest.skip("frozen.yaml not present")
    return yaml.safe_load(CFG.read_text())


def test_every_command_names_a_script_that_exists(index):
    missing = []
    for entry in index["tables"]:
        scripts = [t for t in entry["command"].split() if t.endswith(".py")]
        for s in scripts:
            if not (ROOT / s).exists():
                missing.append((entry["name"], s))
    assert not missing, f"commands naming nonexistent scripts: {missing}"


def test_every_artifact_in_the_index_exists_and_is_hashed(index):
    for entry in index["tables"]:
        assert (ROOT / entry["artifact"]).exists(), f"{entry['name']}: artifact missing"
        assert re.fullmatch(r"[0-9a-f]{64}", entry["artifact_sha256"]), entry["name"]


def test_the_sealed_entry_is_summary_only(index):
    sealed = [e for e in index["tables"] if e.get("sealed")]
    assert len(sealed) == 1, "expected exactly one sealed entry"
    assert sealed[0]["summary_only"] is True, (
        "the sealed subset is scored exactly once and already was; any entry that could "
        "re-run inference on it is a defect")


def test_artifact_only_entries_are_distinguishable_from_input_bound_ones(index):
    """B-033: ops evidence and the clean-checkout proof have no tracked inputs, so
    their verification is weaker than the rest. That difference must be visible in
    the index rather than implied by an empty list."""
    for entry in index["tables"]:
        has_inputs = bool(entry.get("inputs"))
        if entry["name"] in ("ops_evidence", "clean_checkout"):
            assert not has_inputs, f"{entry['name']} unexpectedly gained inputs"
            assert entry["regenerable"] is False, (
                f"{entry['name']} measures this machine; it is verified as an artifact, "
                "not regenerated in place")
        else:
            assert has_inputs, f"{entry['name']} must record what it was computed from"
