"""Every number we publish must still match its artifact.

The project rule is "no public number without a committed artifact behind it".
The failure mode this guards is drift: an artifact gets regenerated, the value
moves, and the README/Devpost/video script keep quoting the old one. That is how
a paper ends up lying without anyone deciding to lie.

If one of these fails, the fix is to update the prose (and re-check the claim it
supports), never to loosen the assertion.
"""

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"


def _load(rel):
    path = RESULTS / rel
    if not path.exists():
        pytest.skip(f"{rel} not present")
    return json.loads(path.read_text())


def test_headline_numbers_match_the_one_shot_artifact():
    r = _load("internal-test/results.json")
    assert round(r["router"]["worst_family_fake_recall"], 4) == 0.8258
    assert round(r["router"]["clean_fpr"], 4) == 0.0833
    assert round(r["router"]["clean_fake_recall"], 4) == 0.9613
    assert round(r["primary_at_0.5"]["worst_family_fake_recall"], 4) == 0.1227
    assert round(r["primary_at_0.5"]["clean_fake_recall"], 4) == 0.7107
    assert round(r["primary_at_0.5"]["per_condition"]["noise_s0.10"]["fake_recall"], 4) == 0.0073
    assert round(r["primary_flips"]["fake_to_real_flip_rate"], 4) == 0.2664
    assert round(r["router"]["per_condition"]["noise_s0.10"]["fpr"], 4) == 0.2967
    # The defensible gain is the FPR-matched one, not the flattering +0.70.
    assert round(r["paired_bootstrap_router_vs_primary_matched"]["mean_delta"], 4) == 0.4916
    assert round(r["primary_at_matched_clean_fpr"]["clean_fake_recall"], 4) == 0.9620


def test_abstention_numbers_match_their_artifact():
    a = _load("internal-test/abstention.json")
    assert round(a["all_images"]["accuracy"], 4) == 0.9090
    assert round(a["kept"]["accuracy"], 4) == 0.9317
    assert round(a["kept"]["worst_family_fake_recall"], 4) == 0.9136
    assert round(a["deferred"]["accuracy"], 4) == 0.8191
    # The policy must stay a frozen value chosen on dev, never a live percentile.
    assert a["dev_policy"]["selected_on"] == "dev split of the fitting cache"


def test_ablation_numbers_match_their_artifact():
    ab = _load("internal-test/ablation.json")["rungs"]
    # The two rows we publish because they cut against us.
    assert ab["quality_only"]["test"]["clean_fpr"] == 0.4393
    assert ab["mlp"]["test"]["overall_accuracy"] == 0.9213
    assert ab["mlp"]["test"]["clean_fpr"] == 0.0500
    assert ab["mlp+wg"]["test"]["overall_accuracy"] == 0.9090
    # Selection must still look like selection: the shipped rung wins worst-family.
    worst = {k: v["test"]["worst_family_fake_recall"] for k, v in ab.items()}
    assert max(worst, key=worst.get) == "mlp+wg"


def test_rescue_negative_result_still_negative():
    resc = _load("pgc/rescue.json")
    assert round(resc["test"]["P(pgc correct | router wrong)"], 4) == 0.5426
    assert resc["test"]["net"] == -2451
    assert resc["gate_passed"] is False, "if this ever passes, the README must change"
