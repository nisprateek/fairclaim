"""Email drafting eval: deterministic checklist per draft (deadline, no
advice disclaimer inside any tone body — it is user-facing info shown next
to the letter, not letter text — escalation ladder on the formal body only,
polite body free of threats/citations, verbatim case facts, no hallucinated
contacts, one draft per remedy) + an LLM-judged tone/factuality score.
See EVALS.md §3.4.
"""

from __future__ import annotations

import re
from datetime import date

from evals.harness import contains, load_dataset, norm, run_staged
from evals.judge import judge


def _date_forms(iso: str) -> list[str]:
    """ISO date plus the human forms an email is likely to use, so the
    'received date is stated' check doesn't fail just because the model wrote
    '20 June 2026' instead of '2026-06-20'."""
    forms = [iso]
    try:
        d = date.fromisoformat(iso)
    except ValueError:
        return forms
    month = d.strftime("%B")
    forms += [
        f"{d.day} {month} {d.year}",
        f"{d.day}{_ordinal(d.day)} {month} {d.year}",
        f"{month} {d.day}, {d.year}",
        d.strftime("%d/%m/%Y"),
        d.strftime("%-d/%-m/%Y"),
    ]
    return forms


def _ordinal(n: int) -> str:
    if 11 <= n % 100 <= 13:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")

TONE_RUBRIC = """This is a consumer's complaint email to a UK seller about faulty goods. Grade it:
- Firm but civil — asserts rights, not abusive or threatening.
- States product, the fault, and the date the goods were received.
- Cites the relevant Consumer Rights Act 2015 remedy accurately for what it demands.
- Invents no facts: no order numbers, prices, or contact details that were not provided.
Score the email overall."""

_EMAIL_OR_URL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+|https?://\S+")

# Escalation language that must NOT appear in the polite first-contact body —
# the whole point of the tone slider is that level one reads like a friendly
# customer, not a softened legal letter.
_POLITE_FORBIDDEN = ["small claims", "trading standards", "legal action", "14 day"]
_SECTION_CITE = re.compile(r"\bs\.\s*\d")

BODY_FIELDS = ("polite_body", "firm_body", "formal_body")  # mirrors email_agent.BODY_FIELDS


def _check_draft(draft: dict, case: dict) -> dict:
    fields = case["case_fields"]
    bodies = {field: draft.get(field) or "" for field in BODY_FIELDS}
    stern_n = [norm(bodies["firm_body"]), norm(bodies["formal_body"])]
    all_text = " ".join(bodies.values())
    # Contacts present in any body must have been provided in the inputs —
    # the context-hygiene / hallucinated-email check from the whitepaper.
    provided = norm(str(fields))
    invented = [tok for tok in _EMAIL_OR_URL.findall(all_text) if norm(tok) not in provided]
    date_forms = _date_forms(fields["purchase_or_delivery_date"])
    expected_tc_terms = case.get("expected_tc_rebuttal_terms") or []
    tc_rebuttal_text = f"{bodies['firm_body']} {bodies['formal_body']}"
    formal_norm = norm(bodies["formal_body"])
    weak_evidence_case = (
        fields.get("has_proof_of_purchase") is False
        or case.get("expect_evidence_caveat")
        or case.get("remedy_result", {}).get("claim_strength") == "weak"
    )
    next_steps_ok = "complaint" in formal_norm and (
        "adr" in formal_norm
        or "further advice" in formal_norm
        or "citizens advice" in formal_norm
        or "small claims" in formal_norm
    )
    if weak_evidence_case:
        next_steps_ok = (
            next_steps_ok
            and "section 75" not in formal_norm
            and "chargeback" not in formal_norm
            and "money claim" not in formal_norm
            and "small claims" not in formal_norm
        )
    # s.30 guarantee note: the firm/formal bodies should raise the guarantee as
    # a separate, additional route when — and ONLY when — a guarantee is in play
    # (mentioned in the grievance or found in the T&Cs). expect_guarantee_note
    # drives both directions, so "stays silent otherwise" is a real check too.
    # s.30 is only for a FREE guarantee; a paid extended warranty must be raised
    # (if at all) WITHOUT the s.30 citation. forbid_s30_citation asserts that.
    forbid_s30_citation = bool(case.get("forbid_s30_citation"))
    s30_cited = contains(tc_rebuttal_text, "s.30") or contains(tc_rebuttal_text, "section 30")
    # "Raising the s.30 guarantee route" means a guarantee/warranty word FRAMED as
    # a separate, additional route — not an incidental mention. Match on
    # guarantee-route-specific phrasing so a stray "guarantee"/"warranty" token in
    # an unrelated sentence isn't miscounted as the note (the negative-control trap).
    guarantee_word = contains(tc_rebuttal_text, "guarantee") or contains(
        tc_rebuttal_text, "warranty"
    )
    guarantee_route = guarantee_word and any(
        contains(tc_rebuttal_text, phrase)
        for phrase in (
            "in its own right",
            "separately enforceable",
            "separate route",
            "additional route",
            "in addition to your statutory",
            "in addition to the statutory",
            "on top of your statutory",
            "as well as your statutory",
            "does not remove your",
            "in addition to your rights",
        )
    )
    guarantee_snippet = ""
    if guarantee_word:
        m = re.search(r"(?i)\b(guarantee|warranty)\b", tc_rebuttal_text)
        if m:
            guarantee_snippet = tc_rebuttal_text[max(0, m.start() - 40) : m.end() + 70]
    # Tri-state: True = must raise the guarantee route, False = must stay silent,
    # absent = not asserted (the paid-warranty case only tests s.30 discipline).
    egn = case.get("expect_guarantee_note")
    guarantee_note_ok = True if egn is None else (guarantee_route if egn else not guarantee_route)
    no_false_proof_ok = True
    if fields.get("has_proof_of_purchase") is False:
        no_false_proof_ok = not any(
            contains(all_text, phrase)
            for phrase in (
                "provided my bank statement",
                "provided my card statement",
                "enclosed my bank statement",
                "enclosed my card statement",
                "legally sufficient evidence",
            )
        )
    expect_evidence_caveat = bool(case.get("expect_evidence_caveat"))
    evidence_caveat_ok = (
        True
        if not expect_evidence_caveat
        else contains(bodies["formal_body"], "proof of purchase")
        and (
            contains(bodies["formal_body"], "six months")
            or contains(bodies["formal_body"], "fault was present")
            or contains(bodies["formal_body"], "inherent at delivery")
            or contains(bodies["formal_body"], "evidence may be needed")
        )
    )
    expect_conditional_card = bool(case.get("expect_conditional_card_escalation"))
    conditional_card_escalation_ok = (
        True
        if not expect_conditional_card
        else "section 75 claim or chargeback request" not in formal_norm
        and (
            ("section 75" not in formal_norm and "chargeback" not in formal_norm)
            or any(
                phrase in formal_norm
                for phrase in (
                    "only pursue payment-card",
                    "only if",
                    "if they fit how i paid",
                    "if the payment method",
                    "within the card scheme",
                    "scheme time limits",
                )
            )
        )
    )
    return {
        "remedy": draft.get("remedy"),
        "deadline_ok": draft.get("response_deadline_days") == 14
        or all("14 day" in body for body in stern_n),
        # The bodies are letters to the seller — the advice disclaimer is
        # shown to the user in the UI and must never be inside a body (the
        # code guard in email_agent.py strips it; this checks the guard).
        "no_disclaimer_ok": not any(
            contains(body, "not a substitute") or contains(body, "not advice from a solicitor")
            for body in bodies.values()
        ),
        "product_ok": all(contains(body, fields["product"]) for body in bodies.values()),
        "date_ok": all(
            any(contains(body, form) for form in date_forms) for body in bodies.values()
        ),
        "ladder_ok": next_steps_ok,
        "polite_ok": not any(term in norm(bodies["polite_body"]) for term in _POLITE_FORBIDDEN)
        and not _SECTION_CITE.search(bodies["polite_body"]),
        "tc_rebuttal_ok": not expected_tc_terms
        or all(contains(tc_rebuttal_text, term) for term in expected_tc_terms),
        "guarantee_note_ok": guarantee_note_ok,
        "guarantee_route": guarantee_route,
        "guarantee_snippet": guarantee_snippet,
        "s30_discipline_ok": (not s30_cited) if forbid_s30_citation else True,
        "no_false_proof_ok": no_false_proof_ok,
        "evidence_caveat_ok": evidence_caveat_ok,
        "conditional_card_escalation_ok": conditional_card_escalation_ok,
        "no_invented_contacts": not invented,
        "invented": invented,
    }


async def run(reps: int = 1, use_judge: bool = True) -> dict:
    from fairclaim.backend.agents.email_agent import email_agent

    dataset = load_dataset("email_cases.json")
    cases = []

    for rep in range(reps):
        for spec in dataset["cases"]:
            state = await run_staged(
                email_agent,
                {
                    "temp:case_fields": spec["case_fields"],
                    "remedy_result": spec["remedy_result"],
                    "tc_analysis_result": spec["tc_analysis_result"],
                },
                "Draft the complaint emails.",
            )
            drafts = state.get("email_drafts") or []
            checks = [_check_draft(d, spec) for d in drafts]
            got_remedies = {d.get("remedy") for d in drafts}
            case = {
                "id": f"{spec['id']}#r{rep}",
                "draft_count": len(drafts),
                "remedy_coverage_ok": got_remedies == set(spec["expected_remedies"]),
                "expected_remedies": spec["expected_remedies"],
                "got_remedies": sorted(r for r in got_remedies if r),
                "checks": checks,
                "all_checks_pass": bool(checks) and all(
                    all(v for k, v in c.items() if k.endswith("_ok") or k == "no_invented_contacts")
                    for c in checks
                ),
            }
            if use_judge and drafts:
                # The firm body is the register the old single-body rubric
                # described (assertive, cited, civil) — judge that one.
                try:
                    case["judge"] = await judge(TONE_RUBRIC, drafts[0].get("firm_body") or "")
                except Exception as e:  # noqa: BLE001
                    case["judge_error"] = str(e)[:200]
            cases.append(case)

    all_checks = [c for case in cases for c in case["checks"]]

    def rate(key):
        return round(sum(c[key] for c in all_checks) / len(all_checks), 3) if all_checks else None

    judged = [c["judge"]["score"] for c in cases if isinstance(c.get("judge"), dict)]
    metrics = {
        "remedy_coverage_rate": round(sum(c["remedy_coverage_ok"] for c in cases) / len(cases), 3),
        "deadline_rate": rate("deadline_ok"),
        "no_disclaimer_in_body_rate": rate("no_disclaimer_ok"),
        "product_named_rate": rate("product_ok"),
        "date_named_rate": rate("date_ok"),
        "escalation_ladder_rate": rate("ladder_ok"),
        "polite_body_unthreatening_rate": rate("polite_ok"),
        "tc_rebuttal_rate": rate("tc_rebuttal_ok"),
        "guarantee_note_rate": rate("guarantee_note_ok"),
        "s30_discipline_rate": rate("s30_discipline_ok"),
        "no_false_proof_rate": rate("no_false_proof_ok"),
        "evidence_caveat_rate": rate("evidence_caveat_ok"),
        "conditional_card_escalation_rate": rate("conditional_card_escalation_ok"),
        "no_invented_contacts_rate": rate("no_invented_contacts"),
        "judge_mean": round(sum(judged) / len(judged), 2) if judged else None,
    }
    gates = [
        {
            "name": "polite body free of citations and threats",
            "ok": metrics["polite_body_unthreatening_rate"] == 1.0,
            "detail": f"rate {metrics['polite_body_unthreatening_rate']}",
        },
        {
            "name": "one draft per available remedy",
            "ok": metrics["remedy_coverage_rate"] == 1.0,
            "detail": f"rate {metrics['remedy_coverage_rate']}",
        },
        {
            "name": "no advice disclaimer inside any letter body",
            "ok": metrics["no_disclaimer_in_body_rate"] == 1.0,
            "detail": f"rate {metrics['no_disclaimer_in_body_rate']}",
        },
        {
            "name": "no hallucinated contact details",
            "ok": metrics["no_invented_contacts_rate"] == 1.0,
            "detail": f"rate {metrics['no_invented_contacts_rate']}",
        },
        {
            "name": "problematic T&C clauses are used in firm/formal rebuttals",
            "ok": metrics["tc_rebuttal_rate"] == 1.0,
            "detail": f"rate {metrics['tc_rebuttal_rate']}",
        },
        {
            "name": "s.30 guarantee note present iff a guarantee is in play",
            "ok": metrics["guarantee_note_rate"] == 1.0,
            "detail": f"rate {metrics['guarantee_note_rate']}",
        },
        {
            "name": "s.30 not cited for a paid/uncertain warranty",
            "ok": metrics["s30_discipline_rate"] == 1.0,
            "detail": f"rate {metrics['s30_discipline_rate']}",
        },
        {
            "name": "no invented proof of purchase",
            "ok": metrics["no_false_proof_rate"] == 1.0,
            "detail": f"rate {metrics['no_false_proof_rate']}",
        },
        {
            "name": "weak evidence cases disclose evidential caveats",
            "ok": metrics["evidence_caveat_rate"] == 1.0,
            "detail": f"rate {metrics['evidence_caveat_rate']}",
        },
        {
            "name": "card escalation is conditional when payment facts are unknown",
            "ok": metrics["conditional_card_escalation_rate"] == 1.0,
            "detail": f"rate {metrics['conditional_card_escalation_rate']}",
        },
    ]
    return {"suite": "email", "cases": cases, "metrics": metrics, "gates": gates}
