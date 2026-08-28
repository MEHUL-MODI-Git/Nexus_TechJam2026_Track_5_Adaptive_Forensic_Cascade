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


def test_retention_signal_numbers_match_their_artifact():
    """README section 7's audit-mode claims. These were computed ad-hoc before an
    artifact existed, which is precisely the drift this file guards against."""
    d = _load("robustness/retention-signal.json")
    a = d["auroc_predicting_wrong_clean_verdict"]
    assert a["reliability_head"] == 0.7206
    assert a["verdict_retention"] == 0.8650
    assert a["combined"] == 0.8863
    # retention must BEAT the head we trained for the job — that is the claim
    assert a["verdict_retention"] > a["reliability_head"]
    bs = d["blind_spot"]
    assert bs["n"] == 157
    # README quotes these to 2dp; the artifact keeps 4. Assert the published
    # precision, not more than we claim.
    assert bs["mean_retention"] == pytest.approx(14.40, abs=0.005)
    assert bs["mean_retention_high_reliability_and_correct"] == pytest.approx(19.00, abs=0.005)
    # the separation is the point, not the exact value
    assert bs["mean_retention_high_reliability_and_correct"] - bs["mean_retention"] > 4.0


def test_certificate_grade_bands_match_the_measured_accuracies():
    """The UI quotes an accuracy per grade. It must be the observed one."""
    from src.app.certificate import GRADE_BANDS

    d = _load("robustness/retention-signal.json")["grade_bands_measured"]
    for _minimum, grade, quoted in GRADE_BANDS:
        if grade in d:
            assert abs(d[grade]["clean_verdict_accuracy"] - quoted) < 0.001, (
                f"{grade}: UI quotes {quoted}, data says "
                f"{d[grade]['clean_verdict_accuracy']}"
            )


def test_probe_ablation_still_says_probes_buy_nothing():
    d = _load("probe-ablation/dev-results.json")["arms"]
    none, all3 = d["none"], d["jpeg+crop+resize"]
    assert none["n_forward_passes"] == 1
    assert all3["n_forward_passes"] == 4
    # the pre-registered rule: CI95 upper bound on the loss below 2 points
    assert none["paired_loss_vs_all3"]["ci95_high"] < 0.02


def test_evidence_audit_is_still_void():
    d = _load("evidence-audit/validation.json")
    assert d["guard_passed"] is False
    assert d["median_operator_agreement"] < 0.5
