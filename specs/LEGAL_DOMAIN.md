# Legal Domain Specification

This project covers a narrow legal domain: faulty goods bought by an individual consumer from a trader, under the Consumer Rights Act 2015.

The system provides general information only. It must not present output as legal advice, a court prediction, or a solicitor's opinion.

## Curated CRA 2015 Sections

The legal KB should include plain-English summaries for these sections:

- `s.9`: satisfactory quality.
- `s.10`: fitness for particular purpose.
- `s.11`: goods matching description.
- `s.13`: goods matching a sample.
- `s.14`: goods matching a model seen or examined.
- `s.15`: installation by trader or under trader responsibility.
- `s.19`: consumer remedies and six-month presumption.
- `s.20`: refund mechanics.
- `s.22`: short-term right to reject.
- `s.23`: right to repair or replacement.
- `s.24`: price reduction or final right to reject.
- `s.28`: delivery timing.
- `s.29`: passing of risk.
- `s.30`: guarantees given without extra charge.
- `s.31`: exclusion or restriction of statutory goods rights.
- `s.62`: fairness test.
- `s.65`: death or personal injury negligence exclusion.
- `s.68`: transparency requirement.

Agents may cite only sections in the curated KB.

## Mandatory Disclaimer

Every user-facing result must include:

```text
This tool provides general information about your rights under the Consumer Rights Act 2015 and is not a substitute for advice from a qualified solicitor. Whether a contract term is ultimately "unfair" is a decision for a court. For tailored advice contact Citizens Advice (consumer helpline) or a solicitor.
```

The disclaimer is shown to the user, not embedded in seller-facing email bodies.

## Remedy Ladder

The remedy ladder is deterministic and must be implemented in code.

Inputs:

- `purchase_or_delivery_date`: ISO date the goods were received.
- `repair_or_replacement_attempted`: whether one repair/replacement has already been attempted and the goods still do not conform.
- `is_motor_vehicle`: optional, affects deduction for use.
- `has_proof_of_purchase`: whether the user has any evidence they bought from this trader.
- `evaluation_date`: optional test override. Live cases use UK current date.

### Tier 0: Short-Term Window

Condition:

- `days_since_delivery <= 30`
- no prior repair/replacement is needed

Available remedies:

- `full_refund`
- `repair`
- `replacement`

Statutory basis:

- `s.20`
- `s.22`
- `s.23`

Burden:

- For short-term rejection, consumer must show the fault.
- If choosing repair/replacement, the six-month presumption may assist.

Notes:

- Full refund should have no deduction for use.
- An agreed repair/replacement can pause the 30-day clock; note this in legal explanation if relevant.

### Tier 1: Repair Or Replacement

Condition:

- More than 30 days since delivery.
- No failed repair/replacement attempt yet.

Available remedies:

- `repair`
- `replacement`

Statutory basis:

- `s.23`

Burden:

- Trader if within six calendar months.
- Consumer if after six calendar months.

Notes:

- Trader must do it free, within a reasonable time, and without significant inconvenience.
- Trader may refuse a chosen option if impossible or disproportionate compared with the alternative.

### Tier 2: Price Reduction Or Final Rejection

Condition:

- One repair/replacement has already been attempted and goods still do not conform, or repair/replacement was impossible or unreasonable.

Available remedies:

- `price_reduction`
- `final_reject_refund`

Statutory basis:

- `s.24`

Burden:

- Trader if within six calendar months.
- Consumer if after six calendar months.

Notes:

- A deduction for use may apply after six months.
- Motor vehicles may allow deduction for use even within six months.

## Claim Strength

`lookup_remedy_tier` must return both entitlement and practical strength.

Start with `strong`, then reduce for each barrier:

- No proof of purchase: reduce by one level.
- More than six months since delivery: reduce by one level.
- More than six years since delivery: cap at `weak` and flag limitation risk; mention Scotland may differ.

Strength labels:

- `strong`: no known practical barrier.
- `moderate`: one material barrier.
- `weak`: multiple barriers or possible limitation issue.

Practical barriers must be written in plain English and included in `RemedyResult`.

## Proof Of Purchase

Do not say "receipt required". The product should explain:

- A receipt is not legally the only proof.
- Bank/card statement, order confirmation, dispatch email, or account history may help.
- Without any proof, the user may struggle to make the seller act.

## T&C Clause Labels

### BLACKLISTED

Use where a term is not binding because it excludes or restricts statutory rights, or tries to exclude death/personal injury negligence liability.

Common triggers:

- "No refunds" for faulty goods.
- "No returns" for faulty goods.
- "All sales final".
- "Sold as seen" used to defeat faulty-goods rights.
- "Goods are not guaranteed to be fit".
- "Customer must prove fault in all cases" where it reverses the six-month presumption.
- "We exclude all liability for death or personal injury caused by negligence".
- "Your only remedy is the manufacturer's warranty" where it replaces statutory rights.

Usually cite:

- `s.31`
- `s.65`
- `s.19` where proof burden is misstated

### POTENTIALLY_UNFAIR

Use where a term may be unfair under the fairness test or grey-list style reasoning, but a court would decide.

Examples:

- One-sided right for trader to change essential terms.
- Disproportionate cancellation fees.
- Hidden or unclear charges.
- Very short complaint windows that undermine statutory remedies.
- Broad discretion for trader to decide whether goods are faulty.
- Terms requiring manufacturer-only handling without preserving seller liability.

Usually cite:

- `s.62`
- `s.68`

### COMPLIANT

Use where a clause is neutral or restates rights without materially reducing them.

Examples:

- Reasonable return logistics that do not remove statutory rights.
- Warranty terms that say statutory rights are unaffected.
- Customer service contact information.
- Timeframes that apply to change-of-mind returns only and clearly preserve faulty-goods rights.

## Guarantees And Warranties

If a free guarantee is in play:

- Treat it as additional to statutory rights, not a replacement.
- Cite `s.30` only if it was given without extra charge.

If a paid extended warranty or service plan is in play:

- Do not cite `s.30` unless facts show it is a free guarantee.
- The letter can mention it as a separate route, but statutory rights remain against the seller.

## Out-Of-Scope Gate Text

For business purchases, use a message with this meaning:

```text
This tool covers Consumer Rights Act 2015 claims where an individual bought goods mainly for personal use, outside their trade, business, craft or profession. Because this purchase was for a business, the CRA consumer remedy ladder does not apply. Business purchases may still have rights under the contract or laws such as the Sale of Goods Act 1979, but contract terms can matter much more. Consider small-business legal advice or a solicitor.
```
