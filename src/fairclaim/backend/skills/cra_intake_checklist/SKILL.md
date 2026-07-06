---
name: cra-intake-checklist
description: |
  Runs the scope gate and required-field checklist for a new UK Consumer
  Rights Act 2015 goods complaint. Use when starting intake on a consumer
  case: confirming it is in scope (consumer buyer, physical goods, trader
  seller, UK purchase, actual fault) and collecting the case fields the
  analysis pipeline needs. Do NOT use for classifying T&C clauses
  (cra-unfair-terms) or for choosing a remedy (cra-remedies).
version: 1.0.0
metadata:
  status: Reviewed by a qualified UK solicitor
  sources: src/fairclaim/backend/knowledge/CRA_2015_KB.md §1 (scope gate); PROJECT_BRIEF.md §6 (required fields)
---

# CRA Intake Checklist

## When to use
- A consumer has described a new goods complaint and the case fields are not
  yet all collected and confirmed.
- Before any legal analysis runs — the scope gate below decides whether the
  rest of the pipeline may run at all.

## When NOT to use
- Classifying seller T&C clauses — that is cra-unfair-terms.
- Deciding what remedy the consumer can demand — that is cra-remedies. Never
  give legal analysis mid-interview; intake only collects and confirms facts.

## Workflow

### 1. Scope gate — confirm ALL before proceeding to analysis

| # | Gate | Fails if | On failure |
| --- | --- | --- | --- |
| 1 | Consumer, not business | Buyer is a business/sole trader acting in that capacity | Stop, explain goods bought for business are out of scope (future work) |
| 2 | Goods, not services/digital content | Purchase is a service or digital content | Stop, explain services/digital content are out of scope (future work) |
| 3 | Trader seller | Seller is a private individual (peer-to-peer) | Stop, explain private sales aren't covered by these goods rights |
| 4 | UK contract | Purchase is not under UK law / is an EU purchase | Stop, explain EU purchases are out of scope (future work) |
| 5 | An actual fault is alleged | The grievance is a change of mind, not a defect/misdescription under ss.9-15 | Stop. Explain that this tool is for faulty goods; for non-faulty change-of-mind returns there is usually no CRA 2015 right to force a refund, so any return may depend on the seller's policy or other cancellation rules outside this MVP. |

If any gate fails, do **not** proceed to T&C analysis or remedies — tell the
user plainly which limit applies and stop.

### 2. Collect every required field (see Output format below)
- Be tolerant: infer from free text first, only ask for genuine gaps.
- Ask or confirm `is_individual` before the other case facts so business
  purchases stop early instead of progressing into the consumer remedy flow.
- Always confirm inferred values back to the user before treating them as
  final — one confirm_card per inferred field, before moving on to genuine
  gaps. Intake is not complete until every required field has been either
  asked directly or explicitly confirmed.

## Output format — the collected case fields

| Field | Type | Notes |
| --- | --- | --- |
| `is_individual` | bool | Confirms scope gate 1. Ask whether the goods were bought mainly for personal use, rather than for trade, business or professional use. |
| `seller_name` | str | Identifies the trader |
| `product` | str | Confirms scope gate 2 (goods, not a service) |
| `purchase_or_delivery_date` | ISO date | The date the goods were **received** (delivery or collection) — the 30-day clock runs from the latest of ownership and delivery, so the order date is the wrong date for online purchases. Ask for "the day you received it". |
| `terms_source` | pasted / **none** | Always ask for the seller's terms through the explicit terms step; if the user doesn't have them or can't get them, set `none` — statutory rights apply regardless and the pipeline skips the T&C check rather than blocking. |
| `grievance` | str | What went wrong (the alleged breach) |
| `desired_outcome` | refund / repair / replacement / price reduction | Reconciled against what the law actually allows downstream, not taken at face value |
| `has_proof_of_purchase` | bool | Any proof counts — receipt, bank/card statement, order confirmation. Infer `true` if they mention how they paid; confirm back rather than asking as a blocking question. A missing receipt is NOT a reason to stop: note that a statement suffices. |
| `has_repair_or_replacement_been_attempted` | bool | Not in the brief's own table, but required by the remedies tool (KB §3) to distinguish Tier 1 from Tier 2 — infer `false` if the user's free text doesn't mention a prior attempt, then confirm it back rather than asking as a blocking question |

## Anti-patterns to avoid
- Never skip the scope gate to "be helpful" — an out-of-scope case must stop
  with a clear explanation, not a best-effort analysis.
- Never ask for the order date — the 30-day clock runs from the day the
  goods were received (delivery or collection).
- Never treat a missing receipt as a reason to stop — any proof counts,
  including a bank/card statement or order confirmation.
- Never treat missing T&Cs as a dead end — set `terms_source` to `none` and
  continue; statutory rights apply regardless of the small print.
- Do not ask whether the purchase was online/by phone, or whether the goods
  are a motor vehicle; those are not required fields in this MVP.
