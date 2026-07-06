"""CRA 2015 KB tools (backend/mcp_server/server.py): the deterministic legal
facts the reasoning agents ground themselves in. Citation lookups must
normalize whatever section spelling a model produces, and the blacklist
pattern-matcher must map each trigger to the right candidate sections.
"""

import pytest

from fairclaim.backend.mcp_server.server import (
    DISCLAIMER,
    STATUTORY_STANDARDS,
    classify_clause_guidance,
    get_disclaimer,
    get_statutory_standard,
    lookup_remedy_tier,
)


# ---------------------------------------------------------------------------
# get_statutory_standard — models spell sections every possible way.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("spelling", ["s.9", "S.9", "s9", "9", "  s.9  "])
def test_section_lookup_normalizes_spellings(spelling):
    assert get_statutory_standard(spelling) == STATUTORY_STANDARDS["s.9"]


@pytest.mark.parametrize("unknown", ["s.99", "s.7", "banana"])
def test_unknown_section_returns_verification_pointer(unknown):
    result = get_statutory_standard(unknown)
    assert result.startswith("Unknown section")
    assert "legislation.gov.uk" in result


def test_section_30_guarantee_is_citable():
    # s.30 is the T&C/email guarantee signal; it must be in the curated set so
    # the citation guard keeps it instead of stripping it as uncurated.
    assert "s.30" in STATUTORY_STANDARDS
    text = get_statutory_standard("s.30")
    assert "guarantee" in text.lower()
    assert "in addition to" in text.lower()


def test_disclaimer_tool_returns_the_canonical_disclaimer():
    text = get_disclaimer()
    assert text == DISCLAIMER
    assert "not a substitute" in text
    assert "Citizens Advice" in text


# ---------------------------------------------------------------------------
# classify_clause_guidance — every blacklist trigger, and its section mapping.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "clause, expected_pattern, expected_sections",
    [
        ("No refunds under any circumstances.", "no_refunds", ["s.31"]),
        ("All items are sold as seen.", "sold_as_seen", ["s.31"]),
        ("All sales are final.", "all_sales_final", ["s.31"]),
        ("Goods are not guaranteed to be fit for any purpose.", "not_guaranteed_fit", ["s.31"]),
        ("No returns accepted after purchase.", "no_returns", ["s.31"]),
        ("The customer must prove any defect existed at delivery.", "consumer_must_prove", ["s.19"]),
        (
            "We exclude all liability for death or personal injury howsoever caused.",
            "excludes_death_injury_liability",
            ["s.65"],
        ),
    ],
)
def test_each_blacklist_pattern_matches_and_maps_sections(clause, expected_pattern, expected_sections):
    result = classify_clause_guidance(clause)
    assert result["likely_blacklisted"] is True
    assert expected_pattern in result["matched_patterns"]
    for section in expected_sections:
        assert section in result["candidate_sections"]


def test_combined_clause_accumulates_sections():
    clause = "No refunds; the buyer must prove any fault existed at delivery."
    result = classify_clause_guidance(clause)
    assert set(result["candidate_sections"]) >= {"s.31", "s.19"}


def test_clean_clause_routes_to_fairness_test():
    result = classify_clause_guidance("Returns are accepted within 30 days with proof of purchase.")
    assert result["likely_blacklisted"] is False
    assert result["matched_patterns"] == []
    assert result["candidate_sections"] == []
    assert "fairness test" in result["note"]


def test_candidate_sections_only_cite_curated_kb_sections():
    # Whatever the matcher suggests, the citation guard must never have to
    # strip it — the KB and the matcher may not drift apart.
    for clause in (
        "No refunds. Sold as seen. All sales final. The customer must prove the defect. "
        "We exclude all liability for death or personal injury."
    ,):
        for section in classify_clause_guidance(clause)["candidate_sections"]:
            assert section in STATUTORY_STANDARDS


# ---------------------------------------------------------------------------
# lookup_remedy_tier — boundary cases the existing suite doesn't pin yet.
# ---------------------------------------------------------------------------

def test_day_zero_is_tier_0():
    result = lookup_remedy_tier("2026-07-01", evaluation_date="2026-07-01")
    assert result["applicable_tier"] == "TIER_0"
    assert result["days_since_delivery"] == 0


def test_plain_six_month_boundary():
    on_mark = lookup_remedy_tier("2026-01-15", evaluation_date="2026-07-15")
    after_mark = lookup_remedy_tier("2026-01-15", evaluation_date="2026-07-16")
    assert on_mark["burden_of_proof"] == "trader"
    assert after_mark["burden_of_proof"] == "consumer"


def test_tier_2_after_six_months_burden_and_deduction():
    result = lookup_remedy_tier(
        "2025-11-01", repair_or_replacement_attempted=True, evaluation_date="2026-07-01"
    )
    assert result["applicable_tier"] == "TIER_2"
    assert result["burden_of_proof"] == "consumer"
    assert "deduction for use may apply" in result["notes"]


def test_malformed_date_raises_value_error():
    with pytest.raises(ValueError):
        lookup_remedy_tier("01/06/2026", evaluation_date="2026-07-01")


def test_remedy_tool_never_invents_sections():
    # Every statutory_basis the tool can emit must exist in the curated KB.
    for kwargs in (
        {"evaluation_date": "2026-07-01"},
        {"evaluation_date": "2026-09-01"},
        {"repair_or_replacement_attempted": True, "evaluation_date": "2026-07-01"},
    ):
        result = lookup_remedy_tier("2026-06-25", **kwargs)
        for section in result["statutory_basis"]:
            assert section in STATUTORY_STANDARDS
