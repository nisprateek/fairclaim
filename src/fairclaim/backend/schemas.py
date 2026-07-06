"""Pydantic schemas for agent outputs and frontend session state."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


CITATION_DESCRIPTION = (
    "Short section codes ONLY, e.g. ['s.9', 's.31'] — never the section's full "
    "text or description, even though get_statutory_standard returns that text."
)

# Field descriptions are passed into ADK output schemas, so they shape model
# responses as well as documenting the contract.
SIMPLE_DESCRIPTION = (
    "1-3 sentences in everyday English a layperson can read at a glance: what "
    "this means for them and what they can do. NO section numbers, NO legal "
    "terms of art (no 'statutory', 'non-binding', 'burden of proof')."
)
LEGAL_DESCRIPTION = (
    "The full legal reasoning: the statutory basis, conditions, and caveats, "
    "citing the relevant CRA 2015 sections inline."
)


class ClauseVerdict(BaseModel):
    clause_text: str
    label: Literal["BLACKLISTED", "POTENTIALLY_UNFAIR", "COMPLIANT"]
    statutory_basis: list[str] = Field(description=CITATION_DESCRIPTION)
    simple_explanation: str = Field(description=SIMPLE_DESCRIPTION)
    legal_explanation: str = Field(description=LEGAL_DESCRIPTION)
    confidence: Literal["high", "medium", "low"]


class TcAnalysisResult(BaseModel):
    clauses: list[ClauseVerdict]
    # "moderate", not "medium" — distinct from ClauseVerdict.confidence above;
    # this mirrors the KB's "overall confidence mapping" vocabulary exactly
    # (high / Moderate / low), which is what the agent is instructed against.
    overall_confidence: Literal["high", "moderate", "low"]
    injection_flagged: bool = Field(
        description="True if the ingested text contained a suspected prompt-injection attempt."
    )
    disclaimer: str


class RemedyResult(BaseModel):
    applicable_tier: Literal["TIER_0", "TIER_1", "TIER_2"]
    primary_remedy: Literal[
        "full_refund", "repair", "replacement", "price_reduction", "final_reject_refund"
    ]
    statutory_basis: list[str] = Field(description=CITATION_DESCRIPTION)
    simple_explanation: str = Field(description=SIMPLE_DESCRIPTION)
    legal_explanation: str = Field(description=LEGAL_DESCRIPTION)
    burden_of_proof: Literal["trader", "consumer"]
    # How hard the remedy is to actually obtain, distinct from whether the Act
    # grants it: copy lookup_remedy_tier's claim_strength verbatim — a valid
    # tier can still be a weak claim (no proof of purchase, post-6-month
    # evidential burden, out of time).
    claim_strength: Literal["strong", "moderate", "weak"]
    practical_barriers: list[str] = Field(
        description=(
            "Plain-English obstacles between the consumer and the remedy, copied "
            "from lookup_remedy_tier's practical_barriers (missing proof of "
            "purchase, the post-6-month evidential burden, a limitation period). "
            "Empty list if none apply."
        )
    )
    alternatives: list[str]
    disclaimer: str


class EmailDraft(BaseModel):
    """One remedy, three escalating tones — the dashboard's sternness slider
    picks which body to show. First contact should not read like a legal
    threat, so the polite body leads and the legal register ramps up."""

    remedy: Literal[
        "full_refund", "repair", "replacement", "price_reduction", "final_reject_refund"
    ]
    subject: str
    polite_body: str = Field(
        description=(
            "Friendly first contact (~120-180 words), a complete letter with "
            "salutation and sign-off: states the product, fault, and received "
            "date, asks the seller to put it right, and names the outcome "
            "wanted. Warm, everyday English — no section citations, no "
            "deadlines, no escalation threats."
        )
    )
    firm_body: str = Field(
        description=(
            "Firm but civil follow-up (~200-280 words), a complete letter with "
            "salutation and sign-off: same facts, now citing the specific "
            "CRA 2015 section(s) for the remedy demanded and setting the "
            "14-day response deadline."
        )
    )
    formal_body: str = Field(
        description=(
            "Formal final notice (~300-400 words) in the register of a letter "
            "before action, with salutation and sign-off: full statutory "
            "citations, the 14-day deadline, rebuttals to common brush-offs, "
            "evidential caveats where the claim is weak, and conditional "
            "escalation options if ignored."
        )
    )
    response_deadline_days: int = 14


class UiComponent(BaseModel):
    """One intake UI component rendered by the React app."""

    type: Literal["choice_card", "date_picker", "text_input", "file_upload", "confirm_card"]
    field: str
    prompt: str
    options: list[str] | None = None
    accept: list[str] | None = None
    inferred_value: str | None = None


class CaseFields(BaseModel):
    is_individual: bool | None = None
    seller_name: str | None = None
    product: str | None = None
    # The date the goods were RECEIVED (delivery/collection) — the s.22 clock
    # runs from the latest of ownership and delivery, not the order date.
    purchase_or_delivery_date: str | None = None
    # "none" = the user can't get the terms; the pipeline then skips the T&C
    # check (statutory rights apply regardless) instead of blocking.
    terms_source: Literal["pasted", "none"] | None = None
    grievance: str | None = None
    desired_outcome: Literal["refund", "repair", "replacement", "price_reduction"] | None = None
    has_repair_or_replacement_been_attempted: bool | None = None
    # Any proof counts (bank statement, order confirmation) — a receipt is
    # not legally required; the email cites this if a trader demands one.
    has_proof_of_purchase: bool | None = None


class IntakeTurn(BaseModel):
    is_complete: bool
    scope_gate_failure: str | None = None
    next_component: UiComponent | None = None
    collected_fields: CaseFields


class SessionStateContract(BaseModel):
    """Session keys the frontend may read.

    Backend-only state such as `temp:*`, `terms_clean`, `terms_opted_out`,
    and `intake_confirmed_fields` is intentionally excluded.
    """

    intake_turn: IntakeTurn | None = None
    tc_analysis_result: TcAnalysisResult | None = None
    remedy_result: RemedyResult | None = None
    email_drafts: list[EmailDraft] | None = None
