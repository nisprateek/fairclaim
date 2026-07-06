"""Inferred-field confirmation: intake never treats a model inference as
final — every required field must be directly asked or explicitly confirmed
before the interview may complete (backend/agents/intake/turns.py)."""

from datetime import date
from types import SimpleNamespace

import pytest

from fairclaim.backend.agents.intake import (
    BUSINESS_BUYER_SCOPE_GATE_FAILURE,
    CONFIRMED_FIELDS_KEY,
    capture_prior_fields,
    extract_choice_value,
    finalize_turn,
)
from fairclaim.backend.dates import MIN_DELIVERY_DATE_ISO, extract_delivery_date


def _ctx(state: dict, answer: str = "") -> SimpleNamespace:
    content = SimpleNamespace(parts=[SimpleNamespace(text=answer)]) if answer else None
    return SimpleNamespace(state=state, user_content=content)


def _turn(fields: dict, **overrides) -> dict:
    return {
        "is_complete": overrides.get("is_complete", False),
        "scope_gate_failure": overrides.get("scope_gate_failure"),
        "next_component": overrides.get("next_component"),
        "collected_fields": fields,
    }


# "I bought Rolex submariner from Watches of Switzerland and it's broken" —
# every field the model can infer from that story, plus the rest filled in.
ALL_FIELDS = {
    "is_individual": True,
    "seller_name": "Watches of Switzerland",
    "product": "Rolex Submariner",
    "purchase_or_delivery_date": "2026-06-20",
    "terms_source": "none",
    "grievance": "The watch stopped working after a week.",
    "desired_outcome": "refund",
    "has_repair_or_replacement_been_attempted": False,
    "has_proof_of_purchase": True,
}


def test_inferred_fields_block_completion_and_get_confirm_cards():
    # Model filled everything by inference and even claimed completion —
    # the sweep must veto it and confirm the buyer scope gate first.
    state = {"intake_turn": _turn(dict(ALL_FIELDS), is_complete=True)}
    finalize_turn(_ctx(state))
    turn = state["intake_turn"]
    assert turn["is_complete"] is False
    component = turn["next_component"]
    assert component["type"] == "confirm_card"
    assert component["field"] == "is_individual"
    assert component["inferred_value"] == "Yes"


def test_all_fields_confirmed_completes_the_interview():
    state = {
        "intake_turn": _turn(dict(ALL_FIELDS)),
        CONFIRMED_FIELDS_KEY: sorted(ALL_FIELDS),
    }
    finalize_turn(_ctx(state))
    assert state["intake_turn"]["is_complete"] is True
    assert state["intake_turn"]["next_component"] is None


def test_model_inferred_terms_source_still_gets_terms_card():
    state = {
        "intake_turn": _turn(dict(ALL_FIELDS), is_complete=True),
        CONFIRMED_FIELDS_KEY: sorted(f for f in ALL_FIELDS if f != "terms_source"),
    }
    finalize_turn(_ctx(state))
    turn = state["intake_turn"]
    assert turn["is_complete"] is False
    assert turn["next_component"]["field"] == "terms_source"


def test_premature_model_terms_card_defers_to_owed_confirms():
    # The model jumped straight to the terms step while inferred fields still
    # owe confirm cards. Terms must stay the interview's final question — the
    # frontend runs the analysis pipeline off the terms answer — so the sweep
    # confirms the earlier fields first and re-emits the terms card last.
    state = {
        "intake_turn": _turn(
            dict(ALL_FIELDS, terms_source=None),
            next_component={
                "type": "file_upload",
                "field": "terms_source",
                "prompt": "Finally, do you have the seller's terms and conditions?",
            },
        ),
        CONFIRMED_FIELDS_KEY: ["is_individual"],
    }
    finalize_turn(_ctx(state))
    turn = state["intake_turn"]
    assert turn["is_complete"] is False
    component = turn["next_component"]
    assert (component["type"], component["field"]) == ("confirm_card", "product")


def test_model_terms_card_stands_once_everything_else_is_confirmed():
    prompt = "Do you have Watches of Switzerland's terms and conditions to paste?"
    state = {
        "intake_turn": _turn(
            dict(ALL_FIELDS, terms_source=None),
            next_component={"type": "file_upload", "field": "terms_source", "prompt": prompt},
        ),
        CONFIRMED_FIELDS_KEY: sorted(f for f in ALL_FIELDS if f != "terms_source"),
    }
    finalize_turn(_ctx(state))
    turn = state["intake_turn"]
    assert turn["is_complete"] is False
    assert turn["next_component"]["field"] == "terms_source"
    assert turn["next_component"]["prompt"] == prompt


def test_confirm_card_drops_stale_options_echoed_from_previous_component():
    state = {
        "intake_turn": _turn(
            dict(ALL_FIELDS),
            next_component={
                "type": "confirm_card",
                "field": "grievance",
                "prompt": "So the watch stopped working after a week — is that right?",
                "options": ["I have them and can paste them", "I don't have them"],
            },
        )
    }
    finalize_turn(_ctx(state))
    component = state["intake_turn"]["next_component"]
    assert component["field"] == "grievance"
    assert "options" not in component


def test_direct_answer_marks_field_confirmed():
    state = {
        "intake_turn": _turn(
            {},
            next_component={"type": "text_input", "field": "product", "prompt": "What did you buy?"},
        )
    }
    capture_prior_fields(_ctx(state, answer="Rolex Submariner"))
    assert state["intake_turn"]["collected_fields"]["product"] == "Rolex Submariner"
    assert "product" in state[CONFIRMED_FIELDS_KEY]


def test_confirm_card_accept_confirms_without_rebinding():
    # The frontend's accept button echoes inferred_value verbatim.
    component = {
        "type": "confirm_card",
        "field": "seller_name",
        "prompt": 'And you bought it from "Watches of Switzerland" — is that right?',
        "inferred_value": "Watches of Switzerland",
    }
    state = {"intake_turn": _turn({"seller_name": "Watches of Switzerland"}, next_component=component)}
    capture_prior_fields(_ctx(state, answer="Watches of Switzerland"))
    assert state["intake_turn"]["collected_fields"]["seller_name"] == "Watches of Switzerland"
    assert "seller_name" in state[CONFIRMED_FIELDS_KEY]


def test_confirm_card_correction_binds_verbatim():
    component = {
        "type": "confirm_card",
        "field": "seller_name",
        "prompt": 'And you bought it from "Watches of Switzerland" — is that right?',
        "inferred_value": "Watches of Switzerland",
    }
    state = {"intake_turn": _turn({"seller_name": "Watches of Switzerland"}, next_component=component)}
    capture_prior_fields(_ctx(state, answer="Goldsmiths"))
    assert state["intake_turn"]["collected_fields"]["seller_name"] == "Goldsmiths"
    assert "seller_name" in state[CONFIRMED_FIELDS_KEY]


def test_confirm_card_bare_rejection_reasks_directly():
    component = {
        "type": "confirm_card",
        "field": "product",
        "prompt": 'Just to confirm — the item you bought is "Rolex Submariner". Is that right?',
        "inferred_value": "Rolex Submariner",
    }
    state = {"intake_turn": _turn({"product": "Rolex Submariner"}, next_component=component)}
    capture_prior_fields(_ctx(state, answer="No"))
    assert state["intake_turn"]["collected_fields"]["product"] is None
    assert "product" not in state[CONFIRMED_FIELDS_KEY]

    # The model produced nothing usable this turn — the sweep re-asks the
    # rejected field as a direct question.
    state["intake_turn"]["next_component"] = None
    finalize_turn(_ctx(state))
    assert state["intake_turn"]["next_component"]["type"] == "text_input"
    assert state["intake_turn"]["next_component"]["field"] == "product"


def test_confirm_card_no_flips_boolean_but_echoed_no_accepts():
    component = {
        "type": "confirm_card",
        "field": "has_repair_or_replacement_been_attempted",
        "prompt": "The seller has not yet attempted a repair or replacement — is that right?",
        "inferred_value": "No",
    }
    # Echoed inferred_value "No" is the accept button, not a rejection.
    state = {
        "intake_turn": _turn(
            {"has_repair_or_replacement_been_attempted": False}, next_component=dict(component)
        )
    }
    capture_prior_fields(_ctx(state, answer="No"))
    assert state["intake_turn"]["collected_fields"]["has_repair_or_replacement_been_attempted"] is False
    assert "has_repair_or_replacement_been_attempted" in state[CONFIRMED_FIELDS_KEY]

    # A typed "no, ..." disagrees with the stated value — flip it.
    state = {
        "intake_turn": _turn(
            {"has_repair_or_replacement_been_attempted": False}, next_component=dict(component)
        )
    }
    capture_prior_fields(_ctx(state, answer="no, they replaced it once already"))
    assert state["intake_turn"]["collected_fields"]["has_repair_or_replacement_been_attempted"] is True
    assert "has_repair_or_replacement_been_attempted" in state[CONFIRMED_FIELDS_KEY]


def test_confirm_card_boolean_correction_binds_from_inferred_value_when_field_missing():
    # A model can emit a boolean confirm_card with inferred_value but omit the
    # matching collected_fields entry. The user's "No" still needs to become
    # the stored False value; otherwise remedies treat proof as unknown.
    component = {
        "type": "confirm_card",
        "field": "has_proof_of_purchase",
        "prompt": "You have some proof of purchase — a receipt, bank statement or order confirmation — is that right?",
        "inferred_value": "Yes",
    }
    state = {"intake_turn": _turn({}, next_component=component)}

    capture_prior_fields(_ctx(state, answer="No"))

    assert state["intake_turn"]["collected_fields"]["has_proof_of_purchase"] is False
    assert "has_proof_of_purchase" in state[CONFIRMED_FIELDS_KEY]


def test_confirm_card_boolean_accept_binds_from_inferred_value_when_field_missing():
    component = {
        "type": "confirm_card",
        "field": "has_proof_of_purchase",
        "prompt": "You have some proof of purchase — a receipt, bank statement or order confirmation — is that right?",
        "inferred_value": "Yes",
    }
    state = {"intake_turn": _turn({}, next_component=component)}

    capture_prior_fields(_ctx(state, answer="Yes"))

    assert state["intake_turn"]["collected_fields"]["has_proof_of_purchase"] is True
    assert "has_proof_of_purchase" in state[CONFIRMED_FIELDS_KEY]


@pytest.mark.parametrize(
    "text, expected",
    [
        ("It arrived on 10 June 2026.", "2026-06-10"),
        ("It was delivered 2026-06-20.", "2026-06-20"),
        ("I bought it 20 days ago.", "2026-06-15"),
        ("I bought this six months ago.", "2026-01-05"),
        ("I received it two months ago.", "2026-05-05"),
        ("I got it a fortnight ago.", "2026-06-21"),
        ("I ordered it on 1 June 2026 and it arrived on 10 June 2026.", "2026-06-10"),
    ],
)
def testextract_delivery_date_from_opening_story(text, expected):
    assert extract_delivery_date(text, today=date(2026, 7, 5)) == expected


def testextract_delivery_date_handles_month_end_relative_dates():
    assert extract_delivery_date("I bought it one month ago.", today=date(2026, 3, 31)) == "2026-02-28"


@pytest.mark.parametrize(
    "text",
    [
        "It arrived on 31 February 2026.",
        "It was delivered on 1899-12-31.",
        "I received it on 10 July 2026.",
        "I got it 200 years ago.",
    ],
)
def testextract_delivery_date_rejects_invalid_out_of_bounds_and_future_dates(text):
    assert extract_delivery_date(text, today=date(2026, 7, 5)) is None


def testextract_delivery_date_accepts_minimum_date():
    assert (
        extract_delivery_date("It was delivered on 1900-01-01.", today=date(2026, 7, 5))
        == MIN_DELIVERY_DATE_ISO
    )


def testextract_delivery_date_ignores_policy_windows_without_receipt_context():
    assert (
        extract_delivery_date(
            "Their terms say customers have 14 days to report delivery damage.",
            today=date(2026, 7, 5),
        )
        is None
    )


@pytest.mark.parametrize("answer", ["20 June 2026", "20/06/2026", "20-06-2026"])
def test_direct_date_answer_is_normalized_to_iso(answer):
    state = {
        "intake_turn": _turn(
            {},
            next_component={
                "type": "date_picker",
                "field": "purchase_or_delivery_date",
                "prompt": "When did you receive it?",
            },
        )
    }
    capture_prior_fields(_ctx(state, answer=answer))
    assert state["intake_turn"]["collected_fields"]["purchase_or_delivery_date"] == "2026-06-20"
    assert "purchase_or_delivery_date" in state[CONFIRMED_FIELDS_KEY]


@pytest.mark.parametrize("answer", ["31 February 2026", "1899-12-31", "2999-01-01", "not a date"])
def test_invalid_direct_date_answer_blocks_model_repair(answer):
    state = {
        "intake_turn": _turn(
            {},
            next_component={
                "type": "date_picker",
                "field": "purchase_or_delivery_date",
                "prompt": "When did you receive it?",
            },
        )
    }
    capture_prior_fields(_ctx(state, answer=answer))

    # Simulate the model trying to fill a plausible date after deterministic
    # validation rejected the user's answer.
    state["intake_turn"] = _turn(
        dict(ALL_FIELDS, purchase_or_delivery_date="2026-06-20"),
        is_complete=True,
    )
    finalize_turn(_ctx(state, answer=answer))
    turn = state["intake_turn"]
    assert turn["collected_fields"]["purchase_or_delivery_date"] is None
    assert turn["next_component"]["field"] == "purchase_or_delivery_date"
    assert turn["next_component"]["type"] == "date_picker"
    assert "purchase_or_delivery_date" not in state[CONFIRMED_FIELDS_KEY]


def test_story_without_date_does_not_accept_model_invented_date():
    state = {
        "intake_turn": _turn(
            dict(ALL_FIELDS, purchase_or_delivery_date="2026-06-20"),
            is_complete=True,
        ),
        CONFIRMED_FIELDS_KEY: sorted(f for f in ALL_FIELDS if f != "purchase_or_delivery_date"),
    }
    finalize_turn(_ctx(state, answer="I bought a watch from Goldsmiths and it stopped working."))
    turn = state["intake_turn"]
    assert turn["collected_fields"]["purchase_or_delivery_date"] is None
    assert turn["next_component"]["field"] == "purchase_or_delivery_date"
    assert turn["next_component"]["type"] == "date_picker"


def test_story_date_overrides_wrong_model_date_before_confirmation():
    state = {
        "intake_turn": _turn(
            dict(ALL_FIELDS, purchase_or_delivery_date="2026-06-01"),
            is_complete=True,
        ),
        CONFIRMED_FIELDS_KEY: sorted(f for f in ALL_FIELDS if f != "purchase_or_delivery_date"),
    }
    finalize_turn(
        _ctx(state, answer="I ordered it on 1 June 2026 and it arrived on 10 June 2026.")
    )
    component = state["intake_turn"]["next_component"]
    assert component["field"] == "purchase_or_delivery_date"
    assert component["inferred_value"] == "2026-06-10"
    assert state["intake_turn"]["collected_fields"]["purchase_or_delivery_date"] == "2026-06-10"


def test_confirmed_date_correction_survives_stale_model_echo():
    component = {
        "type": "confirm_card",
        "field": "purchase_or_delivery_date",
        "prompt": "You received the goods on 2026-06-20 — is that right?",
        "inferred_value": "2026-06-20",
    }
    state = {
        "intake_turn": _turn(
            dict(ALL_FIELDS, purchase_or_delivery_date="2026-06-20"),
            next_component=component,
        ),
        CONFIRMED_FIELDS_KEY: sorted(f for f in ALL_FIELDS if f != "purchase_or_delivery_date"),
    }
    capture_prior_fields(_ctx(state, answer="2025-01-02"))

    # Simulate the model output_key replacing intake_turn with an old value
    # from the original sample story after the deterministic callback already
    # captured the user's correction.
    state["intake_turn"] = _turn(
        dict(ALL_FIELDS, purchase_or_delivery_date="2026-06-20"),
        is_complete=True,
    )

    finalize_turn(_ctx(state, answer="2025-01-02"))
    turn = state["intake_turn"]
    assert turn["is_complete"] is True
    assert turn["collected_fields"]["purchase_or_delivery_date"] == "2025-01-02"


def test_unparseable_model_date_is_reasked_directly():
    state = {
        "intake_turn": _turn(
            dict(ALL_FIELDS, purchase_or_delivery_date="soon"),
            is_complete=True,
        ),
        CONFIRMED_FIELDS_KEY: sorted(f for f in ALL_FIELDS if f != "purchase_or_delivery_date"),
    }
    finalize_turn(_ctx(state))
    component = state["intake_turn"]["next_component"]
    assert component["type"] == "date_picker"
    assert component["field"] == "purchase_or_delivery_date"
    assert state["intake_turn"]["collected_fields"]["purchase_or_delivery_date"] is None


def test_model_text_input_for_date_is_normalized_to_date_picker():
    state = {
        "intake_turn": _turn(
            dict(ALL_FIELDS, purchase_or_delivery_date=None),
            next_component={
                "type": "text_input",
                "field": "purchase_or_delivery_date",
                "prompt": "When did the watch arrive?",
            },
        ),
        CONFIRMED_FIELDS_KEY: sorted(f for f in ALL_FIELDS if f != "purchase_or_delivery_date"),
    }
    finalize_turn(_ctx(state))
    component = state["intake_turn"]["next_component"]
    assert component["field"] == "purchase_or_delivery_date"
    assert component["type"] == "date_picker"
    assert component["prompt"] == "When did the watch arrive?"


def test_model_confirm_card_for_date_is_normalized_to_date_picker_with_value():
    state = {
        "intake_turn": _turn(
            dict(ALL_FIELDS, purchase_or_delivery_date="2026-06-20"),
            next_component={
                "type": "confirm_card",
                "field": "purchase_or_delivery_date",
                "prompt": "You received the watch on 2026-06-20 — is that right?",
                "inferred_value": "2026-06-20",
            },
        ),
        CONFIRMED_FIELDS_KEY: sorted(f for f in ALL_FIELDS if f != "purchase_or_delivery_date"),
    }
    finalize_turn(_ctx(state))
    component = state["intake_turn"]["next_component"]
    assert component["field"] == "purchase_or_delivery_date"
    assert component["type"] == "date_picker"
    assert component["inferred_value"] == "2026-06-20"
    assert component["prompt"] == "You received the watch on 2026-06-20 — is that right?"


def test_models_own_confirm_card_stands_and_gets_inferred_value():
    state = {
        "intake_turn": _turn(
            dict(ALL_FIELDS),
            next_component={
                "type": "confirm_card",
                "field": "grievance",
                "prompt": "So the watch stopped working after a week — is that right?",
            },
        )
    }
    finalize_turn(_ctx(state))
    component = state["intake_turn"]["next_component"]
    assert component["field"] == "grievance"
    assert component["inferred_value"] == ALL_FIELDS["grievance"]
    assert state["intake_turn"]["is_complete"] is False


def test_verbatim_reemit_of_answered_question_is_recomputed():
    # The user just answered the product question, but the model re-emitted
    # the identical component (with schema-parsed None keys) — the sweep
    # must move on to the buyer scope gate instead of re-asking in a loop.
    asked = {"type": "text_input", "field": "product", "prompt": "What did you buy?"}
    state = {"intake_turn": _turn({}, next_component=dict(asked))}
    capture_prior_fields(_ctx(state, answer="Rolex Submariner"))

    state["intake_turn"] = _turn(
        {"product": "Rolex Submariner"},
        next_component={**asked, "options": None, "accept": None, "inferred_value": None},
    )
    finalize_turn(_ctx(state))
    component = state["intake_turn"]["next_component"]
    assert component["field"] != "product"
    assert (component["type"], component["field"]) == ("choice_card", "is_individual")


@pytest.mark.parametrize(
    "answer, expected",
    [
        ("Yes", True),
        ("Yes, mainly personal", True),
        ("no", False),
        ("No, mainly business", False),
        ("maybe?", None),  # ambiguous -> falls through to the model
    ],
)
def test_boolean_choice_answers_bind_deterministically(answer, expected):
    component = {
        "type": "choice_card",
        "field": "is_individual",
        "options": ["Yes, mainly personal", "No, mainly business"],
    }
    assert extract_choice_value(component, answer) is expected


def test_direct_business_buyer_answer_scope_gates():
    component = {
        "type": "choice_card",
        "field": "is_individual",
        "options": ["Yes, mainly personal", "No, mainly business"],
    }
    state = {"intake_turn": _turn({}, next_component=component)}

    capture_prior_fields(_ctx(state, answer="No, mainly business"))
    finalize_turn(_ctx(state))

    turn = state["intake_turn"]
    assert turn["is_complete"] is False
    assert turn["next_component"] is None
    assert turn["scope_gate_failure"] == BUSINESS_BUYER_SCOPE_GATE_FAILURE
    assert turn["collected_fields"]["is_individual"] is False


def test_confirmed_business_buyer_inference_scope_gates():
    component = {
        "type": "confirm_card",
        "field": "is_individual",
        "prompt": "You bought this mainly for trade, business or professional use — is that right?",
        "inferred_value": "No",
    }
    state = {"intake_turn": _turn({"is_individual": False}, next_component=component)}

    capture_prior_fields(_ctx(state, answer="No"))
    finalize_turn(_ctx(state))

    turn = state["intake_turn"]
    assert turn["scope_gate_failure"] == BUSINESS_BUYER_SCOPE_GATE_FAILURE
    assert turn["next_component"] is None
    assert turn["is_complete"] is False


def test_unconfirmed_business_buyer_inference_is_confirmed_before_scope_gate():
    state = {
        "intake_turn": _turn(dict(ALL_FIELDS, is_individual=False), is_complete=True),
        CONFIRMED_FIELDS_KEY: sorted(
            field for field in ALL_FIELDS if field not in {"is_individual", "terms_source"}
        ),
    }

    finalize_turn(_ctx(state))

    turn = state["intake_turn"]
    component = turn["next_component"]
    assert turn["scope_gate_failure"] is None
    assert turn["is_complete"] is False
    assert component["type"] == "confirm_card"
    assert component["field"] == "is_individual"
    assert component["inferred_value"] == "No"


def test_non_boolean_choice_binds_only_an_exact_option_match():
    component = {
        "type": "choice_card",
        "field": "desired_outcome",
        "options": ["refund", "repair", "replacement", "price_reduction"],
    }
    assert extract_choice_value(component, "  Refund ") == "refund"
    assert extract_choice_value(component, "my money back") is None


def test_confirm_card_outcome_correction_binds_only_known_options():
    component = {
        "type": "confirm_card",
        "field": "desired_outcome",
        "prompt": "The outcome you want is a refund — is that right?",
        "inferred_value": "refund",
    }
    # A recognisable correction ("price reduction") binds as the enum value.
    state = {"intake_turn": _turn({"desired_outcome": "refund"}, next_component=dict(component))}
    capture_prior_fields(_ctx(state, answer="price reduction"))
    assert state["intake_turn"]["collected_fields"]["desired_outcome"] == "price_reduction"
    assert "desired_outcome" in state[CONFIRMED_FIELDS_KEY]

    # An unrecognisable one drops the value for an explicit re-ask.
    state = {"intake_turn": _turn({"desired_outcome": "refund"}, next_component=dict(component))}
    capture_prior_fields(_ctx(state, answer="I want compensation for my time"))
    assert state["intake_turn"]["collected_fields"]["desired_outcome"] is None
    assert "desired_outcome" not in state[CONFIRMED_FIELDS_KEY]


def test_terms_opted_out_forces_terms_source_none_in_capture():
    state = {
        "terms_opted_out": True,
        "intake_turn": _turn(
            {"terms_source": None},
            next_component={"type": "text_input", "field": "product", "prompt": "What did you buy?"},
        ),
    }
    capture_prior_fields(_ctx(state, answer="Rolex Submariner"))
    assert state["intake_turn"]["collected_fields"]["terms_source"] == "none"
    assert "terms_source" in state[CONFIRMED_FIELDS_KEY]


def test_terms_clean_marks_pasted_terms_confirmed_in_capture():
    state = {
        "terms_clean": "No refunds.",
        "intake_turn": _turn(
            {"terms_source": None},
            next_component={"type": "text_input", "field": "product", "prompt": "What did you buy?"},
        ),
    }
    capture_prior_fields(_ctx(state, answer="Rolex Submariner"))
    assert state["intake_turn"]["collected_fields"]["terms_source"] == "pasted"
    assert "terms_source" in state[CONFIRMED_FIELDS_KEY]


def test_scope_gate_failure_passes_through_untouched():
    # A gated turn must not get a synthesized component or a field merge —
    # the explanation is the final answer for that interview.
    state = {
        "intake_turn": _turn({}, scope_gate_failure="This tool covers goods, not services."),
    }
    finalize_turn(_ctx(state))
    assert state["intake_turn"]["next_component"] is None
    assert state["intake_turn"]["is_complete"] is False


def test_hallucinated_field_name_is_recomputed():
    # The model asked about "terms_text" — not a CaseFields field. The sweep
    # must replace it, or the frontend strands the user on a bare text box.
    state = {
        "intake_turn": _turn(
            dict(ALL_FIELDS, product=None),
            next_component={"type": "text_input", "field": "terms_text", "prompt": "Paste the terms"},
        ),
        CONFIRMED_FIELDS_KEY: sorted(field for field in ALL_FIELDS if field != "product"),
    }
    finalize_turn(_ctx(state))
    component = state["intake_turn"]["next_component"]
    assert (component["type"], component["field"]) == ("text_input", "product")


def test_sweep_interleaves_confirms_and_asks_in_interview_order():
    state = {"intake_turn": _turn({"product": "Rolex Submariner"})}
    finalize_turn(_ctx(state))
    first = state["intake_turn"]["next_component"]
    assert (first["type"], first["field"]) == ("choice_card", "is_individual")

    # Once the scope gate is answered, the next step is confirming the
    # inferred product before asking for the remaining missing facts.
    state["intake_turn"]["collected_fields"]["is_individual"] = True
    state[CONFIRMED_FIELDS_KEY] = ["is_individual"]
    finalize_turn(_ctx(state))
    second = state["intake_turn"]["next_component"]
    assert (second["type"], second["field"]) == ("confirm_card", "product")

    state[CONFIRMED_FIELDS_KEY] = ["is_individual", "product"]
    finalize_turn(_ctx(state))
    third = state["intake_turn"]["next_component"]
    assert (third["type"], third["field"]) == ("text_input", "seller_name")
