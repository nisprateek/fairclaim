"""Intake UI component catalog and deterministic answer parsing.

The fallback catalog is the source of truth for what each case field's
question looks like when the model doesn't supply one (or supplies the wrong
control type). Answer parsing lives beside it: choice cards, confirm cards,
and the terms step all bind deterministically so a terse "Yes" never depends
on model judgment.
"""

from __future__ import annotations

from fairclaim.backend.schemas import CaseFields

# Safety net: if the model omits next_component, ask the first owed field.
# The buyer scope gate comes first so out-of-scope business purchases stop
# before the user spends time confirming the rest of the case facts.
FALLBACK_COMPONENTS: list[tuple[str, dict]] = [
    (
        "is_individual",
        {
            "type": "choice_card",
            "prompt": "Did you buy this mainly for personal use, rather than for trade, business or professional use?",
            "options": ["Yes, mainly personal", "No, mainly business"],
        },
    ),
    ("product", {"type": "text_input", "prompt": "What did you buy?"}),
    ("seller_name", {"type": "text_input", "prompt": "Who sold it to you?"}),
    ("grievance", {"type": "text_input", "prompt": "What went wrong with it?"}),
    (
        "purchase_or_delivery_date",
        {"type": "date_picker", "prompt": "When did you receive the goods (delivery or collection)?"},
    ),
    (
        "desired_outcome",
        {
            "type": "choice_card",
            "prompt": "What outcome do you want?",
            "options": ["refund", "repair", "replacement", "price_reduction"],
        },
    ),
    (
        "has_repair_or_replacement_been_attempted",
        {
            "type": "choice_card",
            "prompt": "Has the seller already attempted a repair or replacement?",
            "options": ["Yes", "No"],
        },
    ),
    (
        "has_proof_of_purchase",
        {
            "type": "choice_card",
            "prompt": "Do you have any proof of purchase? A bank statement or order confirmation counts.",
            "options": ["Yes", "No"],
        },
    ),
    (
        "terms_source",
        {
            "type": "file_upload",
            "prompt": "Paste the seller's terms and conditions — or continue without them.",
        },
    ),
]
FALLBACK_COMPONENTS_BY_FIELD = dict(FALLBACK_COMPONENTS)

# Some fields have a safer native input than a generic confirm/correct card:
# accepting the displayed value is still one click, but corrections stay typed.
DIRECT_INPUT_CONFIRM_FIELDS = {"purchase_or_delivery_date"}

# Raw text/date answers bind directly to the asked field.
UNAMBIGUOUS_TYPES = {"text_input", "date_picker"}

# Boolean choice cards are Yes/No. desired_outcome uses literal enum options.
BOOLEAN_CHOICE_FIELDS = {
    "is_individual",
    "has_repair_or_replacement_been_attempted",
    "has_proof_of_purchase",
}

# The only keys a confirm card renders — models echo stale keys (e.g. the
# previous card's `options`) that must not survive into the emitted turn.
CONFIRM_CARD_KEYS = ("type", "field", "prompt", "inferred_value")

# Bare rejections drop the inferred value so the sweep re-asks directly.
BARE_REJECTIONS = {"no", "no.", "nope", "nah", "wrong", "incorrect", "not right", "that's wrong"}

# Mirrors CaseFields.desired_outcome's Literal options.
OUTCOME_OPTIONS = {"refund", "repair", "replacement", "price_reduction"}

# terms_source comes from explicit UI actions, never inference.
NO_CONFIRM_FIELDS = {"terms_source"}
EXPLICIT_UI_FIELDS = {"terms_source"}

VALID_FIELDS = set(CaseFields.model_fields.keys())

_NO_TERMS_MARKERS = (
    "don't have",
    "do not have",
    "can't get",
    "cannot get",
    "no terms",
    "without checking",
    "continue without",
)


def extract_choice_value(component: dict, answer: str):
    """Deterministic value for a choice_card answer, or None if it can't be
    determined confidently (falls through to the model's own judgment)."""
    normalized = answer.strip().lower()
    if component.get("field") in BOOLEAN_CHOICE_FIELDS:
        if normalized.startswith("yes"):
            return True
        if normalized.startswith("no"):
            return False
        return None
    for option in component.get("options") or []:
        if option.strip().lower() == normalized:
            return option
    return None


def extract_terms_source(answer: str) -> str | None:
    """Terms are a UI-mediated choice. This parser exists for direct agent
    tests; the production React flow sets terms_clean or terms_opted_out in
    stateDelta."""
    normalized = answer.strip().lower()
    if not normalized:
        return None
    if any(marker in normalized for marker in _NO_TERMS_MARKERS):
        return "none"
    if "terms" in normalized or "conditions" in normalized or "pasted" in normalized:
        return "pasted"
    return None


def yes_no(value) -> str:
    return "Yes" if value else "No"


def display_value(value) -> str:
    return yes_no(value) if isinstance(value, bool) else str(value)


def display_bool(value: str | None) -> bool | None:
    normalized = str(value or "").strip().lower()
    if normalized.startswith("yes"):
        return True
    if normalized.startswith("no"):
        return False
    return None


# Confirm inferred values in plain yes/no form before treating them as final.
CONFIRM_PROMPTS: dict = {
    "product": lambda v: f'Just to confirm — the item you bought is "{v}". Is that right?',
    "seller_name": lambda v: f'And you bought it from "{v}" — is that right?',
    "grievance": lambda v: f'I\'ve noted the problem as: "{v}". Is that right?',
    "purchase_or_delivery_date": lambda v: f"You received the goods on {v} — is that right?",
    "is_individual": lambda v: (
        "You bought this mainly for personal use, not for business or professional use — is that right?"
        if v
        else "You bought this mainly for trade, business or professional use — is that right?"
    ),
    "desired_outcome": lambda v: f"The outcome you want is a {str(v).replace('_', ' ')} — is that right?",
    "has_repair_or_replacement_been_attempted": lambda v: (
        "The seller has already attempted a repair or replacement — is that right?"
        if v
        else "The seller has not yet attempted a repair or replacement — is that right?"
    ),
    "has_proof_of_purchase": lambda v: (
        "You have some proof of purchase — a receipt, bank statement or order confirmation — is that right?"
        if v
        else "You have no proof of purchase at all — is that right?"
    ),
}


def confirm_component(field: str, value) -> dict:
    prompt_for = CONFIRM_PROMPTS.get(
        field, lambda v: f'I\'ve recorded {field.replace("_", " ")} as "{v}" — is that right?'
    )
    return {
        "type": "confirm_card",
        "field": field,
        "prompt": prompt_for(value),
        "inferred_value": display_value(value),
    }


def canonical_component(component: dict) -> dict:
    """Keep model-written prompts, but enforce the field's UI control type.

    The fallback catalog is the source of truth for direct-answer controls.
    Most confirm cards remain model/callback-shaped because they carry
    inferred_value; fields in DIRECT_INPUT_CONFIRM_FIELDS instead use their
    native control for both accepting and correcting the value.
    """
    field = component.get("field")
    if field not in FALLBACK_COMPONENTS_BY_FIELD:
        return component
    if component.get("type") == "confirm_card" and field not in DIRECT_INPUT_CONFIRM_FIELDS:
        return {k: component[k] for k in CONFIRM_CARD_KEYS if component.get(k) is not None}
    canonical = FALLBACK_COMPONENTS_BY_FIELD[field]
    normalized = {
        "field": field,
        **canonical,
        "prompt": component.get("prompt") or canonical["prompt"],
    }
    if component.get("inferred_value") is not None:
        normalized["inferred_value"] = component["inferred_value"]
    return normalized
