---
name: cra-remedies
description: |
  Turns the deterministic tier computed by the lookup_remedy_tier tool into
  the final CRA 2015 remedy recommendation, reconciled with what the
  consumer wants. Use when intake is complete on an in-scope goods case and
  you must decide what the consumer can demand: full refund, repair,
  replacement, price reduction or final rejection. Do NOT use for intake or
  scope questions (cra-intake-checklist) or for classifying T&C clauses
  (cra-unfair-terms).
version: 1.0.0
metadata:
  status: Reviewed by a qualified UK solicitor
  sources: src/fairclaim/backend/knowledge/CRA_2015_KB.md §2-3 (ss.9-24)
---

# CRA Remedies (Tiered Decision Logic)

## When to use
- Intake is complete and in scope, and the case needs its user-facing remedy
  recommendation.

## When NOT to use
- Intake or scope questions — that is cra-intake-checklist.
- Clause-by-clause T&C classification — that is cra-unfair-terms.

## Workflow

### 1. Is there a breach at all?
Goods must meet: satisfactory quality (s.9), fitness for particular purpose
(s.10), as described (s.11), match a sample (s.13), match a model (s.14),
correct installation (s.15). A failure of any one is a breach. These
standards **cannot** be excluded by any T&C term (s.31).

### 2. Call the tool — never compute tiers yourself
Call `lookup_remedy_tier(purchase_or_delivery_date,
repair_or_replacement_attempted, has_proof_of_purchase=...)`. It returns the
tier, available remedies, statutory basis, burden of proof, conditions, and a
**claim-strength assessment** (`claim_strength` + `practical_barriers`)
**deterministically** — the 30-day and 6-month boundaries are legal
deadlines, and how provable the claim is is not the model's judgment to make.
Always pass `has_proof_of_purchase` when the case fact is known.

### 3. Reconcile with desired_outcome to pick `primary_remedy`
The tool returns a **set** of legally available remedies for the tier, not a
single answer — you choose the `primary_remedy` field:
- If the user's `desired_outcome` is legally available in the tool's
  `available_remedies`, make that the primary remedy. (Within 30 days that
  set includes repair and replacement — a Tier 0 user who wants a repair can
  have one; the full refund is simply the strongest option, so mention it.)
- If not (e.g. a Tier 2 case only offers price reduction / final reject),
  pick the closest legally available option as primary and **explain the
  mismatch plainly** — do not imply they can have something the Act doesn't
  currently give them at this tier.
- List every other tool-provided option under `alternatives`.
- Report `burden_of_proof` exactly as the tool returned it — it already
  accounts for the fact that the six-month presumption does **not** cover
  the short-term right to reject.

### 3a. Carry the claim-strength assessment through — never oversell a weak claim
The tier is what the Act lets the consumer **demand**; `claim_strength` and
`practical_barriers` are how hard that demand is to make **stick**. A valid
tier can still be a weak claim (e.g. more than six months on with no proof of
purchase). Copy both fields through verbatim:
- Set `claim_strength` to the tool's value exactly — do not upgrade or
  downgrade it from your own reading of the facts.
- Set `practical_barriers` to the tool's list exactly (empty list if none).
- When `claim_strength` is `weak` or `moderate`, the `simple_explanation`
  must name the biggest obstacle honestly and up front, not bury it — the
  consumer should never come away thinking the remedy is a formality when it
  isn't. When it is `strong` and there are no barriers, do not manufacture
  doubt.

### 4. Explain the remedy twice — once for the consumer, once for review
The output carries two explanations of the same conclusion:
- `simple_explanation` — 1-3 sentences a layperson reads at a glance: what
  they are entitled to and why, in everyday words. No section numbers, no
  legal terms of art.
- `legal_explanation` — the tool's conditions and notes (verbatim or lightly
  paraphrased), the statutory basis cited inline, the burden-of-proof
  position, any reconciliation caveat from step 3, and the substance of any
  `practical_barriers` from step 3a.

### 5. Attach the disclaimer
Always call `get_disclaimer` and attach its text verbatim as `disclaimer`.

## Examples
- Tier 0 case, user wants a repair: repair is in the tool's available set,
  so `primary_remedy` is `repair`, with `full_refund` listed under
  `alternatives` and mentioned as the strongest option.
- Tier 2 case, user wants a full refund: a full refund is not in the set, so
  the closest available option (`final_reject_refund` — a refund that may
  carry a deduction for use) becomes primary, and the mismatch is explained
  plainly.
- Tier 1 case over six months old with no proof of purchase, user wants a
  refund: the 30-day refund window has long closed, so `primary_remedy` is
  `repair` (closest available), `claim_strength` is `weak`, and
  `practical_barriers` carries the proof-of-purchase and post-6-month
  evidential-burden notes. `simple_explanation` leads with the honest
  obstacle: *"You can ask for a free repair or replacement, but two things
  make this an uphill claim — after six months it's on you to prove the fault
  was there from the start, and without any proof you bought it from this
  seller they may not act at all."*
- `simple_explanation` register: *"Because the fault showed up within 30
  days of delivery, you can hand the goods back and ask for all your money
  back — the shop's 'no refunds' sign doesn't change that."*

## Output format (must match `RemedyResult` exactly)
```json
{
  "applicable_tier": "TIER_0 | TIER_1 | TIER_2",
  "primary_remedy": "full_refund | repair | replacement | price_reduction | final_reject_refund",
  "statutory_basis": ["s.20", "s.22"],
  "simple_explanation": "plain-English summary per workflow step 4",
  "legal_explanation": "statutory reasoning per workflow step 4",
  "burden_of_proof": "trader | consumer",
  "claim_strength": "strong | moderate | weak (the tool's value, verbatim)",
  "practical_barriers": ["the tool's practical_barriers, verbatim; [] if none"],
  "alternatives": ["..."],
  "disclaimer": "the get_disclaimer text, attached verbatim"
}
```

## Anti-patterns to avoid
- Never estimate the 30-day or 6-month boundaries yourself — they are legal
  deadlines the tool computes, not judgment calls.
- Never imply the consumer can have a remedy the Act doesn't currently give
  them at this tier.
- Never state a remedy as guaranteed — it is what the Act entitles the
  consumer to demand, not a promise of the outcome of any dispute.
- Never present a `weak` or `moderate` claim as a formality, and never
  override the tool's `claim_strength` with your own optimism — surface the
  `practical_barriers` plainly instead.
