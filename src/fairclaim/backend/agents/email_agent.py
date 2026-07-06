"""Email drafting agent — one draft per available remedy, each at three
sternness levels (polite / firm / formal) for the dashboard's tone slider.

Design: the model writes each letter itself from a curated, case-specific
drafting brief (see `_case_brief`). We do NOT stitch templated sentences onto
its output — that produced duplicated closings and a stapled-on register,
because the de-dup relied on brittle phrase matching against prose the model
had already worded differently. The case posture is instead handed to the
model as up-front guidance, and it integrates each point once, in its own
voice.

Two narrow, non-prose guards survive the model boundary, because they enforce
hard contracts without rewriting sentences:
  * `remedy` is normalised back to the public EmailDraft id (a structured
    field, not prose) — a near-miss like "final_refund" is corrected instead
    of failing the whole ADK run with a 500.
  * A leaked advice disclaimer (a fixed, known string) is dropped from any
    body — the app shows that disclaimer to the user beside the letter.
"""

from __future__ import annotations

import json
import re
from typing import get_args

from google.adk.agents import LlmAgent
from google.adk.agents.readonly_context import ReadonlyContext
from google.genai.types import ThinkingLevel
from pydantic import BaseModel

from fairclaim.backend.llm_config import CAPABLE_MODEL, thinking
from fairclaim.backend.mcp_client import CRA_TOOLSET
from fairclaim.backend.schemas import EmailDraft

# Email bodies go to the seller; the user-facing disclaimer is shown elsewhere.
_DISCLAIMER_FINGERPRINTS = (
    "not a substitute for advice from a qualified solicitor",
    "not advice from a solicitor",
    "general information about the consumer rights act",
)

# Dashboard tone slider order, politest first.
BODY_FIELDS = ("polite_body", "firm_body", "formal_body")

_EMAIL_REMEDY_ORDER = list(get_args(EmailDraft.model_fields["remedy"].annotation))
_EMAIL_REMEDIES = set(_EMAIL_REMEDY_ORDER)
_REMEDY_ALIASES = {
    "refund": ("full_refund", "final_reject_refund"),
    "money_back": ("full_refund", "final_reject_refund"),
    "full_refund": ("full_refund",),
    "final_refund": ("full_refund", "final_reject_refund"),
    "final_reject": ("final_reject_refund",),
    "final_rejection": ("final_reject_refund",),
    "final_right_to_reject": ("final_reject_refund",),
    "reject_refund": ("final_reject_refund",),
    "partial_refund": ("price_reduction",),
    "price_reduction": ("price_reduction",),
    "repair": ("repair",),
    "replacement": ("replacement",),
}


class RawEmailDraft(EmailDraft):
    """LLM-facing email draft shape.

    Inherits every EmailDraft field — including the body-field descriptions
    that steer the model — but widens `remedy` to a plain string so a
    near-miss id can be corrected in the callback instead of failing the
    whole ADK run with a 500.
    """

    remedy: str


# ---------------------------------------------------------------------------
# State helpers
# ---------------------------------------------------------------------------

def _as_dict(draft) -> dict:
    if isinstance(draft, dict):
        return draft
    if isinstance(draft, BaseModel):
        return draft.model_dump()
    return dict(draft)


def _as_state_dict(value) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, BaseModel):
        return value.model_dump()
    return {}


def _state_value(value, key: str):
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)


def _expected_remedies(state) -> list[str]:
    result = state.get("remedy_result") or {}
    candidates = [_state_value(result, "primary_remedy")]
    candidates.extend(_state_value(result, "alternatives") or [])
    expected = list(dict.fromkeys(c for c in candidates if c in _EMAIL_REMEDIES))
    return expected or _EMAIL_REMEDY_ORDER


# ---------------------------------------------------------------------------
# Remedy-id normalisation (structured field, not prose)
# ---------------------------------------------------------------------------

def _remedy_key(value) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")


def _normalize_remedy(value, expected: list[str]) -> str:
    normalized = _remedy_key(value)
    if normalized in expected:
        return normalized
    # Every alias maps to canonical remedy ids, so prefer one the case actually
    # offers, else fall back to the alias's first (most likely) meaning.
    aliases = _REMEDY_ALIASES.get(normalized, ())
    for candidate in aliases:
        if candidate in expected:
            return candidate
    return aliases[0] if aliases else expected[0]


# ---------------------------------------------------------------------------
# Disclaimer hygiene (fixed known string, drop-only)
# ---------------------------------------------------------------------------

def _strip_disclaimer(callback_context) -> None:
    drafts = callback_context.state.get("email_drafts")
    if not drafts:
        return
    changed = False
    for draft in drafts:
        for field in BODY_FIELDS:
            body = draft.get(field) or ""
            kept = [
                paragraph
                for paragraph in body.split("\n\n")
                if not any(mark in paragraph.lower() for mark in _DISCLAIMER_FINGERPRINTS)
            ]
            cleaned = "\n\n".join(kept).rstrip()
            if cleaned != body:
                draft[field] = cleaned
                changed = True
    if changed:
        callback_context.state["email_drafts"] = drafts


def _normalize_and_strip_drafts(callback_context) -> None:
    drafts = callback_context.state.get("email_drafts")
    if not drafts:
        return
    expected = _expected_remedies(callback_context.state)
    normalized = []
    for raw_draft in drafts:
        draft = _as_dict(raw_draft)
        draft["remedy"] = _normalize_remedy(draft.get("remedy"), expected)
        normalized.append(EmailDraft.model_validate(draft).model_dump())
    callback_context.state["email_drafts"] = normalized
    _strip_disclaimer(callback_context)


# ---------------------------------------------------------------------------
# Curated drafting brief — the case posture handed to the model up front.
# Each entry is guidance keyed to THIS case, applied once by the model in its
# own words. Nothing here is stapled onto the model's output afterwards.
# ---------------------------------------------------------------------------

def _barriers_text(result: dict) -> str:
    return " ".join(result.get("practical_barriers") or []).lower()


def _case_brief(fields: dict, result: dict, tc: dict) -> str:
    barriers = _barriers_text(result)
    claim_strength = result.get("claim_strength")
    weak = claim_strength == "weak" or bool(result.get("practical_barriers"))
    no_proof = fields.get("has_proof_of_purchase") is False or "proof of purchase" in barriers
    # The post-six-month evidential burden shows up as a "six months" barrier
    # from the remedies tool. burden_of_proof == "consumer" alone is NOT enough:
    # the short-term (within 30 days) rejection burden is also on the consumer,
    # so keying off burden here would falsely claim "six months have passed".
    six_month_burden = "six months" in barriers
    # No proof of purchase makes any claim hard to enforce regardless of tier,
    # so it gates escalation the same way a weak claim does.
    guarded = weak or no_proof

    lines: list[str] = []

    if weak:
        lines.append(
            f"- CLAIM STRENGTH: this is a WEAK claim ({claim_strength}). Do not write as "
            "though the seller will simply comply; assert the right but stay measured."
        )
    elif no_proof:
        lines.append(
            "- CLAIM STRENGTH: the statutory position is sound, but until the consumer can "
            "prove the purchase it is hard to enforce. Stay measured and evidence-focused."
        )
    elif claim_strength == "moderate":
        lines.append(
            "- CLAIM STRENGTH: this is a MODERATE claim. Assert the right but avoid "
            "overstatement."
        )
    else:
        lines.append("- CLAIM STRENGTH: this is a STRONG claim. You can be confident and direct.")

    if no_proof:
        lines.append(
            "- PROOF OF PURCHASE: the consumer has none yet. NEVER say or imply that a "
            "receipt, bank/card statement, or order confirmation has been provided, "
            "enclosed, or attached. In the firm and formal bodies, say once that they are "
            "locating alternative proof of purchase (a bank or card statement, or an order "
            "confirmation) and that an original receipt is not legally required."
        )
    elif fields.get("has_proof_of_purchase") is True:
        lines.append(
            "- PROOF OF PURCHASE: the consumer has it. If the seller might demand an original "
            "receipt, note once in the formal body that a bank/card statement or order "
            "confirmation is sufficient — a receipt is not legally required."
        )

    if six_month_burden:
        lines.append(
            "- EVIDENCE OF FAULT: more than six months have passed, so the burden is on the "
            "consumer. In the formal body, acknowledge once — without overstating — that "
            "they may need evidence the fault was present or inherent at delivery. Do not "
            "state as established fact that the fault is inherent; say they believe it is and "
            "are gathering evidence."
        )

    if guarded:
        lines.append(
            "- CLOSING (formal body): do NOT threaten Section 75, chargeback, the small "
            "claims court, or Money Claim Online — the claim is not yet strong enough to "
            "back them. Close by asking the seller what evidence they need and offering to "
            "let them inspect the item once it is provided. Then state that, if it is not "
            "resolved, the consumer may use the seller's formal complaints process, any ADR "
            "scheme, or take further advice."
        )
    else:
        lines.append(
            "- CLOSING (formal body): if ignored, you may set out conditional next steps — "
            "the seller's formal complaints process, any ADR scheme, and taking further "
            "advice. Mention Section 75 or chargeback only as conditional on how the consumer "
            "paid and the scheme's time limits, then the small claims court / Money Claim "
            "Online as a last resort."
        )

    problem_clauses = [
        c
        for c in (tc.get("clauses") or [])
        if isinstance(c, dict) and c.get("label") in ("BLACKLISTED", "POTENTIALLY_UNFAIR")
    ]
    if problem_clauses:
        for clause in problem_clauses:
            basis = ", ".join(clause.get("statutory_basis") or []) or "the Consumer Rights Act 2015"
            verdict = (
                "cannot be relied on to exclude or restrict your statutory goods rights"
                if clause.get("label") == "BLACKLISTED"
                else "is likely unfair and cannot fairly defeat your statutory remedy — a "
                "court would have the final say"
            )
            lines.append(
                f'- REBUT THIS TERM (firm and formal bodies): "{clause.get("clause_text")}" — '
                f"quote or paraphrase it, then state that it {verdict} ({basis})."
            )
    else:
        lines.append(
            "- SELLER TERMS: the T&C analysis found no problematic clause — do not invent a "
            "small-print issue."
        )

    lines.append(
        "- COMMON BRUSH-OFFS (formal body, only where relevant): a \"no refunds\" / \"sold as "
        "seen\" / \"all sales final\" term does not bind you for faulty goods (s.31); and "
        "\"take it up with the manufacturer\" is wrong — your contract is with the seller."
    )

    grievance = str(fields.get("grievance") or "").lower()
    tc_text = " ".join(
        str(c.get("clause_text") or "").lower() for c in (tc.get("clauses") or []) if isinstance(c, dict)
    )
    if any(word in grievance or word in tc_text for word in ("guarantee", "warranty")):
        lines.append(
            "- GUARANTEE/WARRANTY: one is mentioned. Raise it in the firm and formal bodies as "
            "a SEPARATE, ADDITIONAL route, enforceable in its own right and on top of (not a "
            "replacement for) the statutory remedy — so an expired or narrower guarantee does "
            "not remove the rights claimed here. Cite s.30 ONLY if it was given FREE with the "
            "goods (e.g. a manufacturer's guarantee included at no cost). If it is a PAID "
            "extended warranty, service plan, or protection plan bought separately, raise it "
            "as a route but do NOT cite s.30. If unsure whether it was free or paid, hedge "
            "('if this came free with the goods, it is also enforceable under s.30') rather "
            "than citing s.30 outright. This is separate from the 'take it up with the "
            "manufacturer' brush-off — the statutory claim is still against the seller."
        )
    else:
        lines.append("- GUARANTEE/WARRANTY: none is in play — say nothing about one.")

    return "\n".join(lines)


_ROLE = (
    "You are the email drafting agent for a UK consumer-rights tool (Consumer Rights Act "
    "2015, faulty goods, individual consumers). You write letters a consumer can send to "
    "the SELLER as-is."
)

_TONE_AND_RULES = """Produce the drafts listed above, one per remedy id, so the user can \
switch between them in the dashboard. Copy each remedy id EXACTLY as given; do not invent \
aliases such as final_refund.

Each draft carries the SAME request at three escalating tones — a dashboard slider, \
politest first. Every body must state the product, the fault, and the date the goods were \
received. Write real letters, not fill-in-the-blank templates: integrate each CASE POSTURE \
point once, in natural prose. Never repeat the same point twice in one body, and never \
staple a summary or evidence paragraph onto the end.

LETTER CRAFT — every body is a complete, send-ready letter:
- Open with a salutation: "Dear <seller name> Customer Service Team," (or "Dear Sir or \
Madam," in the formal body). Close with a matching sign-off — "Kind regards," for polite, \
"Yours faithfully," for firm and formal — followed by [Your name] on its own line. \
[Your name] is the ONLY placeholder allowed.
- Develop the case in short paragraphs separated by blank lines: what was bought and when \
it was received, what went wrong and how it shows up in use, then what you are asking for.
- Refer to the item by the full product name given in CASE FACTS at least once in every \
body (the opening paragraph is the natural place); a short form like "the laptop" is fine \
after that.
- Sound like a real customer: concrete and specific about the fault and its impact, never \
padded. No "I hope this email finds you well", no gushing about the product, no legalese \
where plain English does the job.
- Invent nothing that was not provided: no order numbers, prices, phone numbers, postal \
addresses, or email addresses.
- Each tone must stand alone as potentially the FIRST letter the seller sees — the user \
picks one tone and sends only that. Never refer to a previous letter, an earlier request, \
or "my previous communication"; escalate through register and content, not by claiming \
prior contact.

TONES:
- polite_body (aim for 120–180 words) — warm first contact from a customer who assumes the \
seller will do the right thing. Everyday English only: no section numbers, no deadline, no \
mention of escalation or legal action. Tell the story briefly, name the outcome wanted, \
and ask them to put it right.
- firm_body (aim for 200–280 words) — firm but civil. Cite the specific CRA 2015 \
section(s) for the remedy demanded (call get_statutory_standard to check the wording), \
state the remedy as a legal entitlement rather than a favour, and set a 14-day response \
deadline. Apply the CASE POSTURE's rebuttal, evidence, and guarantee points here where \
they fit.
- formal_body (aim for 300–400 words) — a formal final notice in the register of a letter \
before action: a brief chronology of the purchase and the fault, the statutory basis set \
out in full, everything in firm_body, plus the CASE POSTURE's evidence acknowledgement \
and closing. Follow the CLOSING instruction in the posture exactly — do not dump a \
generic escalation ladder.

Never include the tool's advice disclaimer, or any note aimed at the user, inside a body — \
the app shows the disclaimer to the user beside the letter."""


def build_instruction(ctx: ReadonlyContext) -> str:
    """Assemble the email agent's instruction from curated case context.

    Runs as an ADK InstructionProvider (so ADK skips `{key}` state templating
    and we control the whole prompt). The verbatim case facts and remedy result
    give the model exact names/dates/sections; the CASE POSTURE tells it how to
    use them for this specific case.
    """
    fields = _as_state_dict(ctx.state.get("temp:case_fields") or ctx.state.get("case_fields"))
    result = _as_state_dict(ctx.state.get("remedy_result"))
    tc = _as_state_dict(ctx.state.get("tc_analysis_result"))

    # Enumerate the required remedies deterministically rather than making the
    # model dedupe primary_remedy + alternatives from the JSON itself — that is
    # what drops a draft under load. This is the one-draft-per-remedy contract.
    expected = _expected_remedies(ctx.state)
    remedies_line = (
        "Return EXACTLY "
        + str(len(expected))
        + " draft(s) — one per remedy, using these remedy ids verbatim: "
        + ", ".join(expected)
        + ". Do not merge, add, or omit any."
    )
    facts = json.dumps(
        {"case_fields": fields, "remedy_result": result}, ensure_ascii=False, indent=2
    )
    return (
        _ROLE
        + "\n\n"
        + remedies_line
        + "\n\nCASE FACTS (verbatim — use these exact names, dates, and wording):\n"
        + facts
        + "\n\nCASE POSTURE — apply every point below exactly once, in your own words, at the "
        + "right tone level:\n"
        + _case_brief(fields, result, tc)
        + "\n\n"
        + _TONE_AND_RULES
    )


email_agent = LlmAgent(
    name="email_agent",
    model=CAPABLE_MODEL,
    description="Drafts a polite/firm/formal complaint email per available remedy.",
    instruction=build_instruction,
    # Inputs above fully define this step; previous chat turns are irrelevant.
    include_contents="none",
    tools=[CRA_TOOLSET],
    # The letters ARE the product the user sends: capable tier, like T&C
    # analysis. The fast tier wrote thin, samey prose at every tone level.
    generate_content_config=thinking(ThinkingLevel.MEDIUM),
    after_agent_callback=_normalize_and_strip_drafts,
    output_schema=list[RawEmailDraft],
    output_key="email_drafts",
)
