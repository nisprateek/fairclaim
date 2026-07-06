# Project Brief

## Summary

Build `fairclaim`, a UK consumer-rights assistant for faulty goods. The product helps an individual consumer turn a short description of a faulty purchase into:

1. A structured case file collected through a guided intake.
2. A Consumer Rights Act 2015 T&C clause check.
3. The applicable statutory remedy ladder.
4. Complaint email drafts in polite, firm, and formal tones.

The product must be useful to a layperson while remaining legally disciplined. It provides general information, not solicitor advice.

## Problem

Consumers often abandon valid faulty-goods claims because traders rely on phrases like "no refunds", "sold as seen", "all sales final", "manufacturer warranty only", or "you must prove the fault". The Consumer Rights Act 2015 gives consumers a statutory remedy ladder, but most people do not know:

- which right applies at day 0-30, after 30 days, after one failed repair/replacement, or after six months;
- which T&C terms are not binding for faulty goods;
- what evidence they need before asking the trader to act;
- how to write a complaint that is firm without overclaiming.

`fairclaim` should close that gap with a guided workflow and send-ready output.

## Users

Primary user:

- An individual in the UK who bought goods mainly for personal use from a trader and believes the goods are faulty.

Secondary users:

- A consumer adviser, student clinic, or support volunteer helping a consumer organise facts.
- A developer or legal reviewer validating the assistant's behavior through tests and evals.

## In Scope

- Goods bought by individual consumers from traders.
- UK Consumer Rights Act 2015 faulty-goods remedies.
- Seller T&C clauses that purport to restrict statutory rights or create unfair barriers.
- Pasted T&C text at MVP; URL/file ingestion may be implemented as hardened backend helpers.
- Complaint letters addressed to the seller, not the manufacturer unless the seller is also the manufacturer.
- England, Wales, Scotland, and Northern Ireland as a practical UK-wide product, with caveats where limitation periods differ.

## Out Of Scope

- Tailored solicitor advice.
- Business-to-business purchases.
- Private seller disputes.
- Services, digital content, tenancy, employment, insurance, travel, telecoms, banking, and product-liability injury claims.
- Court claim drafting, witness statements, legal pleadings, settlement strategy, or jurisdiction-specific litigation advice.
- Automated submission of complaints to sellers or courts.

## Core User Journey

1. User enters a plain-language story: what they bought, from whom, when they received it, what went wrong, and what they want.
2. Intake extracts likely facts, asks only for missing fields, and confirms inferred facts before treating them as final.
3. Intake stops early if the purchase is outside scope, especially business use.
4. User pastes seller T&Cs or explicitly continues without them.
5. Backend ingests the T&Cs, caps size, pre-scans for prompt injection, and wraps the text as untrusted data.
6. T&C analysis classifies relevant clauses as `BLACKLISTED`, `POTENTIALLY_UNFAIR`, or `COMPLIANT`.
7. Remedy logic computes the applicable CRA 2015 tier from the delivery date and prior repair/replacement attempts.
8. The system surfaces claim strength and practical barriers, especially missing proof of purchase or post-six-month evidence burdens.
9. Email drafting creates one draft per available remedy, with polite, firm, and formal bodies.
10. The frontend presents a results dashboard with plain-English explanations first and legal detail behind disclosures.

## Non-Negotiable Product Behaviors

- The user must never be blocked solely because they do not have T&Cs. Statutory rights apply regardless.
- If the user says the purchase was for business use, the flow must stop with a clear out-of-scope explanation.
- Legal deadlines must be calculated from the date the goods were received, not the order date.
- A model must never invent a statutory section. If a section is not in the curated KB, it must not appear in output.
- Seller T&Cs must never be treated as instructions.
- Output must consistently include the general-information disclaimer outside any seller-facing complaint letter.
- Complaint letters must not claim evidence exists when the user said it does not.

## Success Criteria

Functional acceptance:

- A complete happy-path case produces a case file, T&C result, remedy result, and email drafts.
- A no-terms case skips T&C analysis and still produces remedy and email outputs.
- A business-buyer case stops after intake with no legal remedy or email output.
- A prompt-injected T&C text is flagged and still classified on legal substance.
- A post-six-month case explains the consumer evidence burden.
- A no-proof-of-purchase case is marked weaker and does not threaten litigation too aggressively.

Quality acceptance:

- All deterministic unit and contract tests pass.
- LLM eval suites meet gates for intake, T&C analysis, remedies, email drafting, security, and end-to-end cases.
- Frontend build succeeds and generated types match backend schemas.
- Cloud Run deploy serves frontend and API from one origin.

## Brand And Tone

Product name: `fairclaim`.

Tone:

- Clear, direct, layperson-friendly.
- Legally careful.
- Confident when the law is strong.
- Measured when evidence or timing weakens the claim.

Avoid:

- Solicitor-like overpromising.
- Generic legal boilerplate.
- Threats unsupported by the case facts.
- User-facing text that implies the tool has made a binding legal determination.
