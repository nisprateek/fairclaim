"""Email agent guards + curated drafting brief.

The email agent writes the letters itself; we do not rewrite its prose. Two
narrow, non-prose guards survive the model boundary and are tested here:
  * the advice disclaimer (a fixed, known string) is dropped from any body —
    the dashboard shows it to the user beside the letter, so it must never sit
    inside a letter to the seller;
  * the `remedy` id (a structured field) is normalised back to the public
    EmailDraft contract.

Everything else — no false "proof enclosed" claim, no premature Section 75 /
court threats on a weak claim, evidential caveats, T&C rebuttals, the s.30
guarantee discipline — is steered up front by the case posture in
`_case_brief`, which the model then writes in its own words. Those tests
assert the curated context is correct; the model's actual compliance is a
statistical gate in evals/suites/email_drafts.py.
"""

from types import SimpleNamespace

from fairclaim.backend.agents.email_agent import (
    BODY_FIELDS,
    _case_brief,
    _normalize_and_strip_drafts,
    _strip_disclaimer,
    build_instruction,
)
from fairclaim.backend.mcp_server.server import DISCLAIMER
from fairclaim.backend.schemas import EmailDraft


def _ctx(state: dict) -> SimpleNamespace:
    return SimpleNamespace(state=state)


def _draft(polite: str, firm: str, formal: str) -> dict:
    return {
        "remedy": "full_refund",
        "polite_body": polite,
        "firm_body": firm,
        "formal_body": formal,
    }


def _raw_draft(remedy: str, body: str = "Refund please.") -> dict:
    return {
        "remedy": remedy,
        "subject": "Faulty goods",
        "polite_body": body,
        "firm_body": body,
        "formal_body": body,
    }


# ---------------------------------------------------------------------------
# Disclaimer hygiene (fixed known string, drop-only)
# ---------------------------------------------------------------------------

def test_appended_disclaimer_is_stripped_from_every_tone():
    with_disclaimer = f"Refund please.\n\n{DISCLAIMER}"
    state = {"email_drafts": [_draft(with_disclaimer, with_disclaimer, with_disclaimer)]}
    _strip_disclaimer(_ctx(state))
    for field in BODY_FIELDS:
        assert state["email_drafts"][0][field] == "Refund please."


def test_reworded_disclaimer_paragraph_is_stripped():
    reworded = (
        "Refund please.\n\n"
        "Please note: this is general information about the Consumer Rights Act 2015 "
        "and not advice from a solicitor."
    )
    state = {"email_drafts": [_draft(reworded, reworded, reworded)]}
    _strip_disclaimer(_ctx(state))
    for field in BODY_FIELDS:
        assert state["email_drafts"][0][field] == "Refund please."


def test_clean_bodies_are_left_untouched():
    state = {
        "email_drafts": [
            _draft(
                "Hi, refund please.",
                "Refund under s.22 of the Consumer Rights Act 2015.",
                "Final notice.\n\nI will escalate to the small claims court.",
            )
        ]
    }
    _strip_disclaimer(_ctx(state))
    draft = state["email_drafts"][0]
    assert draft["polite_body"] == "Hi, refund please."
    assert draft["firm_body"] == "Refund under s.22 of the Consumer Rights Act 2015."
    assert draft["formal_body"] == "Final notice.\n\nI will escalate to the small claims court."


def test_only_the_bodies_carrying_it_are_amended():
    state = {
        "email_drafts": [
            _draft("Hi, refund please.", f"Refund under s.22.\n\n{DISCLAIMER}", "Final notice."),
            _draft(f"Hi, repair please.\n\n{DISCLAIMER}", "Repair under s.23.", "Final notice."),
        ]
    }
    _strip_disclaimer(_ctx(state))
    for draft in state["email_drafts"]:
        for field in BODY_FIELDS:
            assert "not a substitute" not in draft[field].lower()
    assert state["email_drafts"][0]["firm_body"] == "Refund under s.22."
    assert state["email_drafts"][1]["polite_body"] == "Hi, repair please."


def test_no_drafts_is_a_noop():
    state = {}
    _strip_disclaimer(_ctx(state))
    assert state == {}


# ---------------------------------------------------------------------------
# Remedy-id normalisation (structured field)
# ---------------------------------------------------------------------------

def test_remedy_alias_is_normalized_before_public_contract_validation():
    state = {
        "remedy_result": {"primary_remedy": "full_refund", "alternatives": ["repair"]},
        "email_drafts": [_raw_draft("final_refund", f"Refund please.\n\n{DISCLAIMER}")],
    }
    _normalize_and_strip_drafts(_ctx(state))
    draft = state["email_drafts"][0]

    assert draft["remedy"] == "full_refund"
    assert draft["polite_body"] == "Refund please."
    EmailDraft.model_validate(draft)


def test_final_refund_alias_prefers_final_reject_when_that_is_the_available_remedy():
    state = {
        "remedy_result": {
            "primary_remedy": "final_reject_refund",
            "alternatives": ["price_reduction"],
        },
        "email_drafts": [_raw_draft("final_refund")],
    }
    _normalize_and_strip_drafts(_ctx(state))

    assert state["email_drafts"][0]["remedy"] == "final_reject_refund"
    EmailDraft.model_validate(state["email_drafts"][0])


# ---------------------------------------------------------------------------
# Curated drafting brief — the case posture handed to the model up front
# ---------------------------------------------------------------------------

_NO_PROOF_WEAK = {
    "fields": {
        "seller_name": "TechBarn",
        "product": "laptop",
        "purchase_or_delivery_date": "2022-06-16",
        "grievance": "randomly shuts down",
        "has_proof_of_purchase": False,
    },
    "result": {
        "primary_remedy": "repair",
        "alternatives": ["replacement"],
        "claim_strength": "weak",
        "burden_of_proof": "consumer",
        "practical_barriers": [
            "You've said you have no proof of purchase.",
            "More than six months have passed since delivery.",
        ],
    },
    "tc": {"clauses": []},
}


def test_no_proof_weak_case_brief_forbids_false_proof_and_card_escalation():
    brief = _case_brief(_NO_PROOF_WEAK["fields"], _NO_PROOF_WEAK["result"], _NO_PROOF_WEAK["tc"]).lower()
    # Never claim proof was provided; only that it is being located.
    assert "never say or imply" in brief
    assert "locating alternative proof of purchase" in brief
    # Weak claim → no premature card/court threats, ask what evidence is needed.
    assert "do not threaten section 75" in brief
    assert "what evidence they need" in brief
    assert "inspect the item" in brief
    # Post-six-month evidential burden is disclosed, without overstating.
    assert "more than six months have passed" in brief
    assert "do not state as established fact that the fault is inherent" in brief


def test_strong_case_with_blacklisted_clause_allows_conditional_escalation_and_rebuts():
    fields = {
        "seller_name": "TechBarn Ltd",
        "product": "Lenovo ThinkPad",
        "purchase_or_delivery_date": "2026-06-20",
        "grievance": "dead pixels",
        "has_proof_of_purchase": True,
    }
    result = {"primary_remedy": "full_refund", "alternatives": ["repair"], "burden_of_proof": "consumer"}
    tc = {
        "clauses": [
            {
                "clause_text": "All sales are final and no refunds will be given.",
                "label": "BLACKLISTED",
                "statutory_basis": ["s.31"],
            }
        ]
    }
    brief = _case_brief(fields, result, tc).lower()
    # Strong + proof → conditional escalation is permitted.
    assert "conditional next steps" in brief
    assert "do not threaten section 75" not in brief
    # The specific problem clause is quoted for rebuttal with its basis.
    assert "all sales are final and no refunds will be given" in brief
    assert "s.31" in brief
    assert "cannot be relied on to exclude or restrict" in brief


def test_brief_stays_silent_on_guarantee_when_none_is_in_play():
    fields = {"product": "kettle", "grievance": "leaks", "has_proof_of_purchase": True}
    brief = _case_brief(fields, {"primary_remedy": "repair"}, {"clauses": []}).lower()
    assert "none is in play — say nothing about one" in brief
    assert "separate, additional route" not in brief


def test_brief_raises_guarantee_route_with_s30_free_vs_paid_discipline():
    fields = {
        "product": "dishwasher",
        "grievance": "It came with a 2-year manufacturer's guarantee that is still in date.",
        "has_proof_of_purchase": True,
    }
    brief = _case_brief(fields, {"primary_remedy": "repair"}, {"clauses": []}).lower()
    assert "separate, additional route" in brief
    # The s.30 free/paid discipline is spelled out, not decided for the model.
    assert "cite s.30 only if it was given free" in brief
    assert "do not cite s.30" in brief


def test_build_instruction_embeds_verbatim_facts_and_case_posture():
    state = {
        "temp:case_fields": _NO_PROOF_WEAK["fields"],
        "remedy_result": _NO_PROOF_WEAK["result"],
        "tc_analysis_result": _NO_PROOF_WEAK["tc"],
    }
    instruction = build_instruction(_ctx(state))
    # Verbatim facts are present for exact-name/date accuracy.
    assert "laptop" in instruction
    assert "2022-06-16" in instruction
    # The required remedies are enumerated deterministically (coverage contract).
    assert "Return EXACTLY 2 draft(s)" in instruction
    assert "repair, replacement" in instruction
    # The curated posture and the tone/output rules are both assembled in.
    assert "CASE POSTURE" in instruction
    assert "NEVER say or imply" in instruction
    assert "polite_body" in instruction
    # Per-tone length targets and letter craft replaced the flat ~200-word cap.
    assert "120–180 words" in instruction
    assert "300–400 words" in instruction
    assert "salutation" in instruction
