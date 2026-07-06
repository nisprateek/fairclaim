"""Citation-integrity guardrail: only curated sections survive to the user."""

from fairclaim.backend.security.guardrails import _normalize_section, _scrub, _short_label, make_citation_guard


def test_normalize_extracts_section_from_long_form_text():
    assert _normalize_section("s.9: Satisfactory quality — goods must meet...") == "s.9"
    assert _normalize_section("S. 31") == "s.31"
    assert _normalize_section("no section here") is None


def test_scrub_keeps_curated_and_drops_uncurated():
    item = {
        "statutory_basis": ["s.9", "s.28", "s.99"],
        "legal_explanation": "Base reasoning.",
    }
    _scrub(item)
    assert item["statutory_basis"] == ["s.9", "s.28"]
    assert "s.99" in item["legal_explanation"]
    assert "curated statutory set" in item["legal_explanation"]


def test_scrub_normalizes_padded_citation_without_noting():
    item = {
        "statutory_basis": ["s.22: Short-term right to reject — within 30 days..."],
        "legal_explanation": "Base reasoning.",
    }
    _scrub(item)
    assert item["statutory_basis"] == ["s.22"]
    assert "curated statutory set" not in item["legal_explanation"]


def test_scrub_never_touches_the_simple_explanation():
    # The dropped-citation note is legal detail — it must land in the legal
    # explanation, keeping the layperson-facing text jargon-free.
    item = {
        "statutory_basis": ["s.99"],
        "simple_explanation": "Plain words.",
        "legal_explanation": "Base reasoning.",
    }
    _scrub(item)
    assert item["simple_explanation"] == "Plain words."
    assert "s.99" in item["legal_explanation"]


def test_scrub_creates_legal_explanation_when_missing():
    # Defensive: a malformed result without the field still gets the note.
    item = {"statutory_basis": ["s.99"]}
    _scrub(item)
    assert item["statutory_basis"] == []
    assert "s.99" in item["legal_explanation"]


def test_short_label_truncates_long_dropped_strings():
    # A full statutory paragraph mistakenly placed in statutory_basis must
    # never be dumped verbatim into the user-facing note.
    long_text = "Some entirely uncurated statutory-sounding text " * 5
    label = _short_label(long_text)
    assert len(label) <= 25
    assert label.endswith("…")


class _Ctx:
    def __init__(self, state):
        self.state = state


def test_citation_guard_scrubs_every_clause_in_a_list_result():
    state = {
        "tc_analysis_result": {
            "clauses": [
                {"statutory_basis": ["s.9"], "legal_explanation": "ok"},
                {"statutory_basis": ["s.99"], "legal_explanation": "fabricated"},
            ]
        }
    }
    make_citation_guard("tc_analysis_result", list_field="clauses")(_Ctx(state))
    clauses = state["tc_analysis_result"]["clauses"]
    assert clauses[0]["statutory_basis"] == ["s.9"]
    assert clauses[1]["statutory_basis"] == []
    assert "curated statutory set" in clauses[1]["legal_explanation"]


def test_citation_guard_scrubs_a_flat_result():
    state = {"remedy_result": {"statutory_basis": ["s.23", "s.77"], "legal_explanation": ""}}
    make_citation_guard("remedy_result")(_Ctx(state))
    assert state["remedy_result"]["statutory_basis"] == ["s.23"]
    assert "s.77" in state["remedy_result"]["legal_explanation"]


def test_citation_guard_is_a_noop_without_a_result():
    state = {}
    make_citation_guard("tc_analysis_result", list_field="clauses")(_Ctx(state))
    assert state == {}
