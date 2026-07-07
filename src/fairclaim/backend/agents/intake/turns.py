"""Deterministic interview progress: the intake turn state machine.

Values inferred from the user's free text are never final. capture_prior_fields
(before the model runs) binds the user's latest answer wherever it is
unambiguous; finalize_turn (after) merges known fields, asks or confirms the
first owed component, and completes the interview only when every required
field was directly answered or explicitly confirmed via a confirm_card.
"""

from __future__ import annotations

from fairclaim.backend.agents.intake.components import (
    BARE_REJECTIONS,
    BARE_YES_NO,
    BOOLEAN_CHOICE_FIELDS,
    CONFIRM_CARD_KEYS,
    CONFIRM_PROMPTS,
    EXPLICIT_UI_FIELDS,
    FALLBACK_COMPONENTS,
    FALLBACK_COMPONENTS_BY_FIELD,
    NO_CONFIRM_FIELDS,
    OUTCOME_OPTIONS,
    UNAMBIGUOUS_TYPES,
    VALID_FIELDS,
    canonical_component,
    confirm_component,
    display_bool,
    display_value,
    extract_choice_value,
    extract_terms_source,
)
from fairclaim.backend.dates import extract_delivery_date

# Invocation-scoped snapshot restored after output_key replaces intake_turn.
PRIOR_FIELDS_KEY = "temp:intake_prior_fields"

# Previous component lets finalization detect accidental re-asks.
PREV_COMPONENT_KEY = "temp:intake_prev_component"

# Interview-long set of fields directly answered or explicitly confirmed.
CONFIRMED_FIELDS_KEY = "intake_confirmed_fields"

BUSINESS_BUYER_SCOPE_GATE_FAILURE = (
    "This tool covers Consumer Rights Act 2015 claims where an individual bought goods "
    "mainly for personal use, outside their trade, business, craft or profession. "
    "Because this purchase was for a business, the CRA consumer remedy ladder does "
    "not apply. Business purchases may still have rights under the contract or laws "
    "such as the Sale of Goods Act 1979, but the contract terms can matter much more. "
    "Consider small-business legal advice or a solicitor."
)


def apply_business_buyer_scope_gate(turn: dict) -> dict:
    turn["is_complete"] = False
    turn["scope_gate_failure"] = BUSINESS_BUYER_SCOPE_GATE_FAILURE
    turn["next_component"] = None
    return turn


def _latest_user_text(callback_context) -> str:
    content = callback_context.user_content
    return "".join(part.text or "" for part in (content.parts if content else [])).strip()


def _normalize_purchase_date(callback_context, fields: dict, confirmed: set) -> None:
    field = "purchase_or_delivery_date"
    current = fields.get(field)
    latest_text = _latest_user_text(callback_context)
    if field not in confirmed:
        from_story = extract_delivery_date(latest_text, allow_contextless=False)
        if from_story:
            fields[field] = from_story
            return
        prior_fields = callback_context.state.get(PRIOR_FIELDS_KEY) or {}
        if latest_text and not prior_fields.get(field):
            # If deterministic extraction found no date in this turn, do not
            # accept a model-invented legal deadline fact.
            fields[field] = None
            confirmed.discard(field)
            return
    if current:
        parsed = extract_delivery_date(str(current), allow_contextless=True)
        if parsed:
            fields[field] = parsed
            return
        fields[field] = None
        confirmed.discard(field)


def _apply_confirm_answer(component: dict, answer: str, fields: dict, confirmed: set) -> None:
    """Deterministic handling of a confirm_card answer: accept (echoed
    inferred_value or a "yes...") keeps the stored value, a bare rejection
    drops it for a direct re-ask, and anything else binds as the correction.
    """
    field = component["field"]
    normalized = answer.strip().lower()
    accepted = normalized == str(component.get("inferred_value") or "").strip().lower()

    if field in BOOLEAN_CHOICE_FIELDS:
        # The UI renders boolean confirm cards as the direct yes/no question,
        # so a bare yes/no answers that question directly — never the
        # accept/flip protocol, whatever inferred_value the model wrote.
        direct = BARE_YES_NO.get(normalized)
        if direct is not None:
            fields[field] = direct
            confirmed.add(field)
            return
        baseline = fields.get(field)
        if not isinstance(baseline, bool):
            baseline = display_bool(component.get("inferred_value"))
        # A qualified "no, ..." disagrees with the stated inference — flip it.
        if accepted:
            if baseline is not None:
                fields[field] = baseline
        elif normalized.startswith("no"):
            fields[field] = not baseline if baseline is not None else False
        elif normalized.startswith("yes"):
            fields[field] = True
        confirmed.add(field)
        return
    if accepted or normalized.startswith("yes"):
        # Accepted -- never bind the agreement text itself as the value.
        confirmed.add(field)
        return
    if normalized in BARE_REJECTIONS:
        fields[field] = None
        confirmed.discard(field)
        return
    if field == "desired_outcome":
        # Bind only a recognisable enum option; anything else is re-collected
        # via the explicit choice_card rather than guessed at.
        option = normalized.replace(" ", "_")
        if option in OUTCOME_OPTIONS:
            fields[field] = option
            confirmed.add(field)
        else:
            fields[field] = None
            confirmed.discard(field)
        return
    if field == "purchase_or_delivery_date":
        parsed = extract_delivery_date(answer, allow_contextless=True)
        if parsed:
            fields[field] = parsed
            confirmed.add(field)
        else:
            fields[field] = None
            confirmed.discard(field)
        return
    fields[field] = answer
    confirmed.add(field)


def capture_prior_fields(callback_context) -> None:
    """Before the model runs: stash collected_fields as they stood at the
    start of this turn, with the just-given answer already merged in
    wherever it's unambiguous (text_input, date_picker, choice_card where
    extract_choice_value can resolve it, and confirm_card accepts and
    corrections) — see finalize_turn. Also records the field the user just
    answered as user-confirmed: everything else in collected_fields is mere
    inference that finalize_turn still owes a confirm_card for.
    """
    turn = callback_context.state.get("intake_turn")
    if not turn or turn.get("is_complete") or turn.get("scope_gate_failure"):
        return
    confirmed = set(callback_context.state.get(CONFIRMED_FIELDS_KEY) or [])
    fields = dict(turn.get("collected_fields") or {})
    component = turn.get("next_component") or {}
    answer = _latest_user_text(callback_context)
    # The terms UI arrives through stateDelta, outside the conversational
    # transcript. Direct text handling below is only for tests.
    if callback_context.state.get("terms_opted_out"):
        fields["terms_source"] = "none"
        confirmed.add("terms_source")
    elif callback_context.state.get("terms_clean"):
        fields["terms_source"] = "pasted"
        confirmed.add("terms_source")
    if answer and component.get("field") in VALID_FIELDS:
        field = component["field"]
        if field == "terms_source":
            source = extract_terms_source(answer)
            if source:
                fields[field] = source
                confirmed.add(field)
        elif component.get("type") in UNAMBIGUOUS_TYPES:
            if field == "purchase_or_delivery_date":
                value = extract_delivery_date(answer, allow_contextless=True)
                if value:
                    fields[field] = value
                    confirmed.add(field)
                else:
                    fields[field] = None
                    confirmed.discard(field)
            else:
                fields[field] = answer
                confirmed.add(field)
        elif component.get("type") == "choice_card":
            value = extract_choice_value(component, answer)
            if value is not None:
                fields[field] = value
            # Direct answers do not need a later confirm_card.
            confirmed.add(field)
        elif component.get("type") == "confirm_card":
            _apply_confirm_answer(component, answer, fields, confirmed)
        callback_context.state[PREV_COMPONENT_KEY] = component
    callback_context.state[CONFIRMED_FIELDS_KEY] = sorted(confirmed)
    callback_context.state[PRIOR_FIELDS_KEY] = fields
    # Hint for the model's `{{intake_turn?}}`; finalization remains authoritative.
    turn["collected_fields"] = fields
    callback_context.state["intake_turn"] = turn


def _emit_component(callback_context, turn: dict, component: dict) -> None:
    turn["next_component"] = canonical_component(component)
    turn["is_complete"] = False
    callback_context.state["intake_turn"] = turn


def _stripped(component: dict | None) -> dict:
    """Component minus null-valued keys, for re-emit comparison: the model's
    schema-parsed output carries every optional UiComponent key as None,
    while deterministic fallback components only carry the keys they use.
    Confirm cards also drop keys they don't render, so a stale `options`
    echo from an earlier component never reads as a new question."""
    stripped = {k: v for k, v in (component or {}).items() if v is not None}
    if stripped.get("type") == "confirm_card":
        return {k: v for k, v in stripped.items() if k in CONFIRM_CARD_KEYS}
    return stripped


def _sweep_owes_earlier_field(fields: dict, confirmed: set, target_field: str) -> bool:
    """True when the sweep below still owes a question or confirmation for a
    field ordered before `target_field` in FALLBACK_COMPONENTS."""
    for field, _ in FALLBACK_COMPONENTS:
        if field == target_field:
            return False
        if field in EXPLICIT_UI_FIELDS and field not in confirmed:
            return True
        if fields.get(field) is None:
            return True
        if field not in confirmed and field not in NO_CONFIRM_FIELDS:
            return True
    return False


def finalize_turn(callback_context) -> None:
    """Merge prior fields and enforce deterministic interview progress.

    The model can omit or repeat next_component, drop older fields, or mark
    completion too early. This callback keeps known fields, asks or confirms
    the first owed component, and completes only after all required fields are
    filled and user-confirmed.
    """
    turn = callback_context.state.get("intake_turn")
    if not turn:
        return

    prior_fields = callback_context.state.get(PRIOR_FIELDS_KEY)
    if prior_fields and not turn.get("scope_gate_failure"):
        confirmed = set(callback_context.state.get(CONFIRMED_FIELDS_KEY) or [])
        prev_component = callback_context.state.get(PREV_COMPONENT_KEY) or {}
        protected_fields = set(confirmed)
        if prev_component.get("field") in VALID_FIELDS:
            # The callback already bound the user's latest answer before the
            # model ran. Do not let a stale model echo restore the old value.
            protected_fields.add(prev_component["field"])

        new_fields = turn.get("collected_fields") or {}
        merged = dict(prior_fields)
        for key, value in new_fields.items():
            if value is None:
                continue
            if key in protected_fields and key in prior_fields:
                continue
            merged[key] = value
        turn["collected_fields"] = merged
        callback_context.state["intake_turn"] = turn

    if turn.get("scope_gate_failure"):
        return

    fields = turn.get("collected_fields") or {}
    confirmed = set(callback_context.state.get(CONFIRMED_FIELDS_KEY) or [])
    _normalize_purchase_date(callback_context, fields, confirmed)
    turn["collected_fields"] = fields
    callback_context.state[CONFIRMED_FIELDS_KEY] = sorted(confirmed)
    callback_context.state["intake_turn"] = turn
    prev_component = callback_context.state.get(PREV_COMPONENT_KEY) or {}
    next_component = turn.get("next_component")
    target_field = next_component.get("field") if next_component else None

    if fields.get("is_individual") is False and "is_individual" in confirmed:
        callback_context.state["intake_turn"] = apply_business_buyer_scope_gate(turn)
        return

    # If the user rejected or failed validation for the just-answered field,
    # re-ask that exact field before returning to the normal sweep order.
    if (
        prev_component.get("field") in FALLBACK_COMPONENTS_BY_FIELD
        and fields.get(prev_component["field"]) is None
    ):
        field = prev_component["field"]
        _emit_component(callback_context, turn, {"field": field, **FALLBACK_COMPONENTS_BY_FIELD[field]})
        return

    # The terms card triggers the analysis pipeline when answered, so the
    # frontend relies on it being the interview's final question. A model
    # that jumps to terms early is overruled: the sweep below asks and
    # confirms everything else first, then emits the terms card last.
    if (
        next_component
        and target_field in EXPLICIT_UI_FIELDS
        and _sweep_owes_earlier_field(fields, confirmed, target_field)
    ):
        next_component = None
        target_field = None

    # Keep the model's component only when it is still a valid owed question.
    if next_component and target_field in VALID_FIELDS:
        if fields.get(target_field) is None:
            _emit_component(callback_context, turn, next_component)
            return
        if _stripped(next_component) != _stripped(prev_component):
            if target_field == prev_component.get("field"):
                _emit_component(callback_context, turn, next_component)
                return
            if (
                next_component.get("type") == "confirm_card"
                and target_field not in confirmed
                and target_field not in NO_CONFIRM_FIELDS
            ):
                # The accept button submits inferred_value.
                if not next_component.get("inferred_value"):
                    next_component["inferred_value"] = display_value(fields[target_field])
                _emit_component(callback_context, turn, next_component)
                return

    # Ask the first missing field, or confirm the first unconfirmed inference.
    for field, component in FALLBACK_COMPONENTS:
        value = fields.get(field)
        if field in EXPLICIT_UI_FIELDS and field not in confirmed:
            _emit_component(callback_context, turn, {"field": field, **component})
            return
        if value is None:
            _emit_component(callback_context, turn, {"field": field, **component})
            return
        if field not in confirmed and field not in NO_CONFIRM_FIELDS:
            _emit_component(callback_context, turn, confirm_component(field, value))
            return
    # Every required field is filled and user-confirmed.
    turn["next_component"] = None
    turn["is_complete"] = True
    callback_context.state["intake_turn"] = turn
