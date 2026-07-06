---
name: cra-unfair-terms
description: |
  Classifies each clause of a seller's terms and conditions against the CRA
  2015 blacklist (automatically non-binding, s.31/s.65) and the Schedule 2
  grey list with the s.62 fairness test (potentially unfair). Use when
  analysing pasted seller T&Cs on a goods complaint.
  Do NOT use for intake or scope questions (cra-intake-checklist) or for
  choosing the consumer's remedy (cra-remedies).
version: 1.0.0
metadata:
  status: Reviewed by a qualified UK solicitor
  sources: src/fairclaim/backend/knowledge/CRA_2015_KB.md §4-5 (Part 2, Schedule 2); §3/§4.3/§7 (s.30 guarantees)
---

# CRA Unfair & Non-Binding Terms (T&C Analysis)

## When to use
- Seller T&Cs have been ingested and every clause bearing on the consumer's
  statutory rights or remedies needs a classification.

## When NOT to use
- Choosing the consumer's remedy — that is cra-remedies.
- Intake or scope questions — that is cra-intake-checklist.

## Workflow
Classify each clause into one of two problem categories or COMPLIANT. The
two problem categories are legally distinct — **do not conflate them**.

### 1. BLACKLISTED — automatically non-binding, no fairness test needed
A term is BLACKLISTED (not a fairness judgment call — it simply does not bind
the consumer) if it:
- Excludes/restricts the statutory goods rights in ss.9-16 (s.31). Examples:
  "no refunds on faulty goods", "sold as seen" applied to a hidden fault,
  "all sales final", "goods not guaranteed to be fit for purpose".
- Excludes/restricts liability for death or personal injury from negligence (s.65).
- Shifts onto the consumer a burden of proof the law places on the trader
  (e.g. requiring the consumer to prove a fault existed at delivery within
  the first 6 months, contrary to s.19).

Use `classify_clause_guidance` as a first-pass pattern hint, but the final
label is your judgment against the three rules above, not the tool's alone.

### 2. POTENTIALLY_UNFAIR — the grey list + fairness test, needs judgment
Not automatically void. Assessed under the s.62 fairness test: **contrary to
good faith, does it cause a significant imbalance in the parties' rights and
obligations to the detriment of the consumer?** Core price/subject-matter
terms are exempt only if transparent and prominent (s.64).

Common Schedule 2 grey-list patterns for goods retail:
- Excludes/limits the trader's liability for non-performance.
- Excludes/limits the consumer's legal rights if the trader breaches.
- Trader's obligations subject to the trader's sole discretion/whim.
- Trader may retain prepayments on consumer cancellation without a matching
  right the other way.
- Disproportionate cancellation compensation required of the consumer.
- Trader may unilaterally alter terms or the goods' characteristics without a
  valid contractual reason.
- Trader has sole discretion to decide if goods conform / to interpret a term.
- Disputes forced to non-statutory arbitration.
- Auto-renewal with an unreasonably early opt-out deadline.

State the concern plainly and **always note that "unfair" is ultimately a
court's decision, not a settled fact** — never assert a grey-list term is
definitely void.

### 3. COMPLIANT
Restates statutory rights, sets reasonable/transparent delivery or core-price
terms. No concern to flag.

A **guarantee or warranty** clause (manufacturer's or retailer's) is COMPLIANT
**only when it genuinely adds** a right without cutting down the statutory ones.
When it does, note in its `legal_explanation` that the guarantee is separately
enforceable under **s.30** and is *in addition to*, not a replacement for, the
statutory rights — the signal the email agent uses to raise the guarantee as a
second route. Do **not** treat "guarantee/warranty" as an automatic COMPLIANT:
a clause making the guarantee the consumer's **sole or exclusive remedy**,
**ending their rights once the guarantee expires**, or otherwise excluding or
restricting the ss.9-16 rights is **BLACKLISTED (s.31)** — the guarantee framing
does not save it. Only a guarantee given free with the goods engages s.30; a
separately purchased paid warranty does not (judge the clause on its substance,
not its label).

### 4. Explain each clause twice — once for the consumer, once for review
Every clause verdict carries two explanations of the same conclusion:
- `simple_explanation` — 1-3 sentences a layperson reads at a glance: what
  the clause means for them, in everyday words. No section numbers, no legal
  terms of art. Example: *"The shop can't refuse to help with a faulty item
  just because of this rule — the law overrides it."*
- `legal_explanation` — the statutory reasoning with sections cited inline
  (blacklist rule engaged, or the fairness-test concern). For
  POTENTIALLY_UNFAIR clauses this is where the "ultimately a court's
  decision" caveat lives; the simple explanation can say "a court would have
  the final say" in plain words.

## Output format
Each clause verdict carries `label`, `statutory_basis`, both explanations,
and a per-clause `confidence`; the overall result carries
`overall_confidence`. Note the two confidence fields use different scales.

Per-clause `confidence` (high | medium | low) — how settled THAT verdict is:
- **high** — a clean rule match: a clear blacklist hit, or boilerplate that
  plainly restates statutory rights.
- **medium** — the call needed judgment (most grey-list/fairness-test
  verdicts).
- **low** — the clause is ambiguous or its effect depends on context the
  terms don't show.

`overall_confidence` (high | moderate | low) — the KB's overall mapping:
- **high** — at least one BLACKLISTED clause found.
- **moderate** — one or more POTENTIALLY_UNFAIR clauses, no BLACKLISTED term.
- **low** — nothing problematic found; statutory rights still apply
  regardless.

## Anti-patterns to avoid
- Never conflate the categories: BLACKLISTED is not a fairness judgment
  call, and a grey-list term is never automatically void.
- Never assert a grey-list term is definitely unfair or void — "unfair" is
  ultimately a court's decision; say so.
- Never treat `classify_clause_guidance`'s pattern hint as the verdict — the
  final label is your judgment against the rules above.
