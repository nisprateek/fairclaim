"""MCP server exposing the CRA 2015 knowledge base as typed tools.

Deterministic legal facts (dates, tiers, citations) live here so the
reasoning agents ground their output in code, not model guesswork. Manual
check: `uv run python -m fairclaim.backend.mcp_server.server` (waits on stdio, as
ADK's McpToolset expects — Ctrl-C to exit).

Source of truth for all text returned here: backend/knowledge/CRA_2015_KB.md
— keep this file in sync with that KB if either changes.
"""

from __future__ import annotations

import re
from datetime import date

from mcp.server.fastmcp import FastMCP

from fairclaim.backend.dates import add_months, today_uk

mcp = FastMCP("cra-2015-kb")

DISCLAIMER = (
    "This tool provides general information about your rights under the Consumer "
    "Rights Act 2015 and is not a substitute for advice from a qualified solicitor. "
    "Whether a contract term is ultimately \"unfair\" is a decision for a court. "
    "For tailored advice contact Citizens Advice (consumer helpline) or a solicitor."
)

STATUTORY_STANDARDS: dict[str, str] = {
    "s.9": "Satisfactory quality — goods must meet the standard a reasonable person would regard as satisfactory, considering price, description and circumstances (fitness for common purposes, appearance/finish, freedom from minor defects, safety, durability).",
    "s.10": "Fit for particular purpose — if the consumer made known a particular purpose, the goods must be fit for it.",
    "s.11": "As described — goods must match any description given (listing, packaging, labelling).",
    "s.13": "Match a sample — if bought by reference to a sample, the bulk must match the sample.",
    "s.14": "Match a model seen/examined — goods must match a model the consumer saw or examined, except for differences brought to attention.",
    "s.15": "Installation — if the trader installs the goods (or it is done under their responsibility) and installation is incorrect, the goods do not conform.",
    "s.19": "Burden of proof timeline — within 6 months of delivery, non-conformity is presumed to have existed at delivery and the trader must prove otherwise; after 6 months, the consumer must prove the fault existed at delivery.",
    "s.20": "Refund mechanics — refund via the same payment method, no fee, within 14 days of the trader agreeing the consumer is entitled to a refund.",
    "s.22": "Short-term right to reject — within 30 days of ownership/delivery, reject for a full refund with no deduction for use; the clock pauses during an agreed repair/replacement.",
    "s.23": "Right to repair or replacement — the consumer chooses repair or replacement, free, within a reasonable time, without significant inconvenience; the trader may refuse only if impossible or disproportionately costly compared to the alternative.",
    "s.24": "Price reduction or final right to reject — unlocked after one failed repair/replacement attempt; refund may be reduced to reflect use except within the first 6 months (motor vehicles excepted).",
    "s.28": "Delivery — unless otherwise agreed, the trader must deliver the goods without undue delay and within 30 days; if a delivery deadline was essential and missed, the consumer may treat the contract as at an end and get a refund.",
    "s.29": "Passing of risk — the goods remain at the trader's risk until they come into the physical possession of the consumer (or a carrier the consumer arranged); damage in transit is the trader's problem, not the consumer's.",
    "s.30": "Goods under guarantee — a guarantee given without extra charge (a free manufacturer's or retailer's undertaking to repair, replace or refund) is legally binding in its own right and takes effect as a contractual obligation on the terms set out in the guarantee and its advertising. It is in addition to the consumer's statutory rights, not a replacement, so an expired or narrower guarantee does not remove those rights. It must be transparent: in plain, intelligible language; stating that the consumer has statutory rights that are unaffected by the guarantee; giving the essentials for making a claim, the guarantor's name and address, the duration and territorial scope; written in English where the goods are offered in the UK; and made available in writing and in a form accessible to the consumer, on request. A paid extended warranty bought separately is NOT a s.30 guarantee, though it may still bind as an ordinary contract.",
    "s.31": "Exclusion of liability — a term that excludes or restricts the statutory goods rights (ss.9-16) or the delivery/risk rules (ss.28-29) is not binding on the consumer.",
    "s.62": "Fairness test — a term is unfair if, contrary to good faith, it causes a significant imbalance in the parties' rights and obligations to the detriment of the consumer.",
    "s.65": "A term excluding or restricting liability for death or personal injury from negligence is not binding.",
    "s.68": "Transparency — contract terms must be in plain, intelligible language.",
}

_BLACKLIST_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("no_refunds", re.compile(r"no\s+refunds?\b", re.I)),
    ("sold_as_seen", re.compile(r"sold\s+as\s+seen", re.I)),
    ("all_sales_final", re.compile(r"all\s+sales?\s+(are\s+)?final", re.I)),
    ("not_guaranteed_fit", re.compile(r"not\s+guaranteed\s+to\s+be\s+fit", re.I)),
    ("no_returns", re.compile(r"no\s+returns?\b", re.I)),
    ("consumer_must_prove", re.compile(r"(consumer|buyer|customer)\s+(must|shall)\s+prove", re.I)),
    ("excludes_death_injury_liability", re.compile(r"exclud\w*\s+(all\s+)?liability.*(death|personal injury)", re.I)),
]


# Outer limit for bringing a court claim over faulty goods: 6 years from
# delivery in England, Wales & NI (Limitation Act 1980 s.5); Scotland is 5
# years (Prescription and Limitation (Scotland) Act 1973). The tool does not
# know the consumer's jurisdiction, so it uses the longer (6-year) cap and
# flags the Scottish position in the barrier text.
LIMITATION_YEARS = 6


def _assess_claim_strength(
    *,
    presumption_applies: bool,
    has_proof_of_purchase: bool | None,
    time_barred: bool,
) -> tuple[str, list[str]]:
    """Deterministic 'can this consumer actually make the claim stick?' layer.

    The tier says what the Act entitles the consumer to demand; this says how
    hard it will be to get it. Two facts weaken a claim independently — the
    post-six-month evidential burden and a total absence of proof of purchase
    — and an out-of-time claim caps it outright. Returns a plain-English
    strength grade and the concrete barriers to surface to the user.
    """
    barriers: list[str] = []
    # 2 = strong, 1 = moderate, 0 = weak. Each independent obstacle drops it.
    score = 2

    if has_proof_of_purchase is False:
        score -= 1
        barriers.append(
            "You've said you have no proof of purchase. A receipt is not legally "
            "required, but before the seller has to act you'll need some evidence "
            "that you bought this from them — a bank or card statement, or an order "
            "or dispatch confirmation email. Track one of these down first."
        )

    if not presumption_applies:
        score -= 1
        barriers.append(
            "More than six months have passed since delivery, so it is now up to "
            "you to show the fault was there at the start (or was always going to "
            "develop). Be ready to back this up — for example photographs, a "
            "repairer's or independent expert's report, or evidence that others hit "
            "the same failure."
        )

    if time_barred:
        score = 0
        barriers.append(
            "This purchase was more than six years ago. A court claim over faulty "
            "goods normally has to be brought within six years of delivery (five "
            "years in Scotland), so a claim may now be out of time."
        )

    strength = ("weak", "moderate", "strong")[max(0, min(2, score))]
    return strength, barriers


@mcp.tool()
def get_disclaimer() -> str:
    """Return the mandatory CRA 2015 disclaimer to attach to every user-facing output."""
    return DISCLAIMER


@mcp.tool()
def get_statutory_standard(section: str) -> str:
    """Return the verbatim plain-language summary of a CRA 2015 section for citation grounding.

    Args:
        section: Section id, e.g. "s.9", "s.23", "s.31".
    """
    key = section.strip().lower()
    if not key.startswith("s."):
        key = f"s.{key.lstrip('s').lstrip('.')}"
    return STATUTORY_STANDARDS.get(
        key, f"Unknown section '{section}'. Verify against https://www.legislation.gov.uk/ukpga/2015/15."
    )


@mcp.tool()
def classify_clause_guidance(clause_text: str) -> dict:
    """Pattern-match a T&C clause against known CRA 2015 blacklist triggers.

    This is grounding guidance for the LLM classifier, not a final verdict —
    grey-list "potentially unfair" terms still require the fairness-test
    judgment call from the cra_unfair_terms skill.

    Args:
        clause_text: The verbatim clause to check.
    """
    matches = [name for name, pattern in _BLACKLIST_PATTERNS if pattern.search(clause_text)]
    sections = sorted(
        ({"s.31"} if any(m not in ("excludes_death_injury_liability", "consumer_must_prove") for m in matches) else set())
        | ({"s.65"} if "excludes_death_injury_liability" in matches else set())
        | ({"s.19"} if "consumer_must_prove" in matches else set())
    )
    return {
        "likely_blacklisted": bool(matches),
        "matched_patterns": matches,
        "candidate_sections": sections,
        "note": (
            "Pattern match found — very likely BLACKLISTED, confirm against the exact wording."
            if matches
            else "No blacklist pattern matched — assess against the grey-list and fairness test instead."
        ),
    }


@mcp.tool()
def lookup_remedy_tier(
    purchase_or_delivery_date: str,
    repair_or_replacement_attempted: bool = False,
    is_motor_vehicle: bool = False,
    has_proof_of_purchase: bool | None = None,
    evaluation_date: str | None = None,
) -> dict:
    """Deterministically compute the applicable CRA 2015 remedy tier (ss.19-24).

    Never estimate "today" or the 30-day/6-month boundaries yourself — they
    are legal deadlines. Leave evaluation_date unset for a live case.

    Burden-of-proof note: the s.19(14) six-month presumption (trader must
    prove the goods conformed at delivery) applies to repair/replacement
    (s.23) and price-reduction/final-rejection (s.24) claims. It does NOT
    apply to the short-term right to reject (s.22) — for that route the
    consumer must show the fault, even within 30 days.

    The tier says what the Act entitles the consumer to *demand*. The returned
    `claim_strength` and `practical_barriers` say how hard it will be to make
    that demand stick — a >6-month case with no proof of purchase is a valid
    Tier 1 claim on paper but a weak one in practice, and the tool must say so
    rather than assert a confident entitlement.

    Args:
        purchase_or_delivery_date: ISO date "YYYY-MM-DD" the consumer
            received the goods (delivery/collection — not the order date).
        repair_or_replacement_attempted: Whether one repair/replacement has
            already been attempted and the goods still do not conform
            (unlocks Tier 2).
        is_motor_vehicle: Whether the goods are a motor vehicle (affects the
            deduction-for-use rule under s.24(8)-(11)).
        has_proof_of_purchase: Whether the consumer has any proof they bought
            the goods from this trader (receipt, bank/card statement, order
            confirmation). False materially weakens the claim in practice;
            None means it was not established and is left out of the scoring.
        evaluation_date: Optional ISO date to evaluate the case as of, for
            testing or historical cases. Defaults to today in UK time
            (Europe/London — the deadlines are UK legal deadlines).
    """
    purchase = date.fromisoformat(purchase_or_delivery_date)
    today = date.fromisoformat(evaluation_date) if evaluation_date else today_uk()
    days_since = (today - purchase).days
    if days_since < 0:
        raise ValueError("purchase_or_delivery_date is in the future.")
    within_30_days = days_since <= 30
    six_month_mark = add_months(purchase, 6)
    presumption_applies = today <= six_month_mark  # s.19(14) — see docstring for scope
    time_barred = today > add_months(purchase, LIMITATION_YEARS * 12)
    claim_strength, practical_barriers = _assess_claim_strength(
        presumption_applies=presumption_applies,
        has_proof_of_purchase=has_proof_of_purchase,
        time_barred=time_barred,
    )

    if repair_or_replacement_attempted:
        tier = "TIER_2"
        available_remedies = ["price_reduction", "final_reject_refund"]
        statutory_basis = ["s.24"]
        burden_of_proof = "trader" if presumption_applies else "consumer"
        conditions = (
            "One repair or replacement has already been attempted and the goods still "
            "do not conform (or the attempt was not reasonable/timely). Choose a price "
            "reduction (keep the goods) or reject the goods for a refund."
        )
        notes = (
            "A reasonable deduction for use may apply at any time for motor vehicles."
            if is_motor_vehicle
            else (
                "No deduction for use in the first 6 months from delivery."
                if presumption_applies
                else "A deduction for use may apply since more than 6 months have passed."
            )
        )
    elif within_30_days:
        tier = "TIER_0"
        # Within 30 days the consumer may reject for a full refund (s.22) OR
        # choose repair/replacement (s.23) — s.23 is not gated on the 30 days
        # having passed.
        available_remedies = ["full_refund", "repair", "replacement"]
        statutory_basis = ["s.20", "s.22", "s.23"]
        # s.19(14) presumption does not cover the s.22 short-term reject.
        burden_of_proof = "consumer"
        conditions = (
            "Within 30 days of delivery — reject for a full refund with no deduction "
            "for use, or choose a free repair or replacement instead."
        )
        notes = (
            "For the short-term rejection itself the consumer must show the goods were "
            "faulty at delivery — the six-month presumption does not apply to this "
            "route. Choosing repair or replacement (s.23) instead engages that "
            "presumption AND pauses the 30-day clock; on return of the goods the "
            "consumer has the remainder of the 30 days or 7 days, whichever is longer, "
            "to inspect and still reject."
        )
    else:
        tier = "TIER_1"
        available_remedies = ["repair", "replacement"]
        statutory_basis = ["s.23"]
        burden_of_proof = "trader" if presumption_applies else "consumer"
        conditions = (
            "More than 30 days since delivery — the trader must repair or replace free, "
            "within a reasonable time, without significant inconvenience."
        )
        notes = (
            "If repair/replacement fails, is impossible, or is not done reasonably, tier "
            "2 (price reduction or final right to reject) becomes available."
        )

    return {
        "applicable_tier": tier,
        "available_remedies": available_remedies,
        "statutory_basis": statutory_basis,
        "conditions": conditions,
        "burden_of_proof": burden_of_proof,
        "days_since_delivery": days_since,
        "notes": notes,
        "claim_strength": claim_strength,
        "practical_barriers": practical_barriers,
    }


if __name__ == "__main__":
    mcp.run()
