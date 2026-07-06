"""The 30-day / 6-month boundaries are legal deadlines — pin them in tests.

Every test passes evaluation_date so results are reproducible regardless of
when the suite runs.
"""

import pytest

from fairclaim.backend.mcp_server.server import lookup_remedy_tier


def test_day_30_is_still_tier_0():
    result = lookup_remedy_tier("2026-06-01", evaluation_date="2026-07-01")
    assert result["applicable_tier"] == "TIER_0"
    assert result["days_since_delivery"] == 30


def test_day_31_is_tier_1():
    result = lookup_remedy_tier("2026-06-01", evaluation_date="2026-07-02")
    assert result["applicable_tier"] == "TIER_1"


def test_tier_0_offers_repair_and_replacement_too():
    # s.23 is available at the consumer's choice within the 30 days — the
    # tool must not foreclose it.
    result = lookup_remedy_tier("2026-06-20", evaluation_date="2026-07-01")
    assert set(result["available_remedies"]) == {"full_refund", "repair", "replacement"}
    assert "s.23" in result["statutory_basis"]


def test_tier_0_burden_is_on_the_consumer():
    # The s.19(14) presumption does not cover the short-term right to reject.
    result = lookup_remedy_tier("2026-06-20", evaluation_date="2026-07-01")
    assert result["burden_of_proof"] == "consumer"


def test_tier_1_within_six_months_burden_on_trader():
    result = lookup_remedy_tier("2026-03-01", evaluation_date="2026-07-01")
    assert result["applicable_tier"] == "TIER_1"
    assert result["burden_of_proof"] == "trader"


def test_tier_1_after_six_months_burden_on_consumer():
    result = lookup_remedy_tier("2025-12-01", evaluation_date="2026-07-01")
    assert result["applicable_tier"] == "TIER_1"
    assert result["burden_of_proof"] == "consumer"


def test_six_month_mark_handles_month_end():
    # 31 Aug + 6 months clamps to 28 Feb (no 31 Feb) — the day after is
    # outside the presumption window.
    on_mark = lookup_remedy_tier("2025-08-31", evaluation_date="2026-02-28")
    after_mark = lookup_remedy_tier("2025-08-31", evaluation_date="2026-03-01")
    assert on_mark["burden_of_proof"] == "trader"
    assert after_mark["burden_of_proof"] == "consumer"


def test_tier_2_after_failed_repair():
    result = lookup_remedy_tier(
        "2026-05-01", repair_or_replacement_attempted=True, evaluation_date="2026-07-01"
    )
    assert result["applicable_tier"] == "TIER_2"
    assert set(result["available_remedies"]) == {"price_reduction", "final_reject_refund"}
    assert "No deduction for use" in result["notes"]


def test_tier_2_motor_vehicle_deduction_note():
    result = lookup_remedy_tier(
        "2026-05-01",
        repair_or_replacement_attempted=True,
        is_motor_vehicle=True,
        evaluation_date="2026-07-01",
    )
    assert "motor vehicles" in result["notes"]


def test_future_delivery_date_rejected():
    with pytest.raises(ValueError):
        lookup_remedy_tier("2026-08-01", evaluation_date="2026-07-01")


# ---------------------------------------------------------------------------
# Claim-strength / practical-barriers layer — provability, not entitlement.
# ---------------------------------------------------------------------------


def test_recent_case_with_proof_is_a_strong_claim():
    result = lookup_remedy_tier(
        "2026-06-20", has_proof_of_purchase=True, evaluation_date="2026-07-01"
    )
    assert result["claim_strength"] == "strong"
    assert result["practical_barriers"] == []


def test_over_a_year_and_no_proof_is_a_weak_claim():
    # The scenario that started this: >1yr ago, no proof of purchase, wants a
    # refund. Both obstacles apply, so the claim is weak and both barriers are
    # surfaced — the tier is still Tier 1, the entitlement is not the issue.
    result = lookup_remedy_tier(
        "2025-05-01", has_proof_of_purchase=False, evaluation_date="2026-07-01"
    )
    assert result["applicable_tier"] == "TIER_1"
    assert result["claim_strength"] == "weak"
    assert len(result["practical_barriers"]) == 2
    joined = " ".join(result["practical_barriers"]).lower()
    assert "proof of purchase" in joined
    assert "six months" in joined


def test_past_six_months_with_proof_is_moderate():
    result = lookup_remedy_tier(
        "2025-12-01", has_proof_of_purchase=True, evaluation_date="2026-07-01"
    )
    assert result["claim_strength"] == "moderate"
    assert len(result["practical_barriers"]) == 1
    assert "six months" in result["practical_barriers"][0].lower()


def test_recent_but_no_proof_is_moderate():
    result = lookup_remedy_tier(
        "2026-06-20", has_proof_of_purchase=False, evaluation_date="2026-07-01"
    )
    assert result["claim_strength"] == "moderate"
    assert len(result["practical_barriers"]) == 1
    assert "proof of purchase" in result["practical_barriers"][0].lower()


def test_unknown_proof_is_left_out_of_scoring():
    # None (never established) must not be treated as False.
    within = lookup_remedy_tier("2026-06-20", evaluation_date="2026-07-01")
    assert within["claim_strength"] == "strong"
    assert within["practical_barriers"] == []


def test_out_of_time_claim_is_weak_and_flagged():
    # Past the 6-year limitation period — claim may be out of time regardless
    # of proof of purchase.
    result = lookup_remedy_tier(
        "2019-01-01", has_proof_of_purchase=True, evaluation_date="2026-07-01"
    )
    assert result["claim_strength"] == "weak"
    assert any("out of time" in b.lower() for b in result["practical_barriers"])


def test_just_inside_limitation_is_not_flagged_out_of_time():
    result = lookup_remedy_tier(
        "2020-08-01", has_proof_of_purchase=True, evaluation_date="2026-07-01"
    )
    assert not any("out of time" in b.lower() for b in result["practical_barriers"])
