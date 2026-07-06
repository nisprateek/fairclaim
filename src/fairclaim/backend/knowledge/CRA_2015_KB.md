# UK Consumer Rights Act 2015 — Knowledge Base (Goods)

> **Status: DRAFT — requires review by a qualified UK solicitor before production use.**
> This is a curated, machine-readable summary of the Consumer Rights Act 2015 ("CRA 2015")
> for **consumer goods** bought by an **individual** (not a business or sole trader acting in
> a business capacity) from a **UK trader**. It is **not legal advice**. Section numbers refer
> to the CRA 2015 unless stated. Current as of July 2026; verify against
> https://www.legislation.gov.uk/ukpga/2015/15 before relying on any clause.

## 0. How agents should use this file

This document is the single source of truth for the **T&C analysis agent** and the **remedies
agent**. It encodes three things:

1. The **statutory quality standards** goods must meet (used to decide if there is a breach).
2. The **tiered remedy decision logic** (used to tell the user what they can demand).
3. The **unfair / non-binding term tests** (used to flag clauses in a seller's T&Cs).

Every agent output that relies on this file **must cite the section** it used (e.g. "s.23") and
must carry the disclaimer in section 6. Do not assert a term is "illegal" — use the graded
labels in section 4.

---

## 1. Scope gate (intake must confirm before analysis)

Analysis is only valid if ALL of the following hold. If any fail, stop and explain the limit.

- **An actual fault is alleged:** the grievance must be a non-conformity under ss.9-15 (faulty,
  not as described, unfit for purpose), not a change of mind. If the user simply no longer wants
  the goods: bought **online/at distance within the last 14 days** → signpost the unconditional
  cancellation right under the **Consumer Contracts Regulations 2013** (a different, easier route
  this tool does not draft for); otherwise explain there is no statutory right to return
  non-faulty goods and any returns policy is goodwill.
- **Consumer, not business:** buyer is an individual acting wholly or mainly outside a trade,
  business, craft or profession (s.2(3)). Sole traders buying for their business are out of scope.
- **Goods, not services or digital content:** tangible movable goods (s.2(8)). Services (Part 1
  Ch.4) and digital content (Part 1 Ch.3) are **out of scope for the MVP** — flag as future work.
- **Trader seller:** sold by a person acting for purposes relating to their trade/business (s.2(2)).
  Private/peer-to-peer sales (e.g. a private individual on a marketplace) are **not** covered by
  these goods rights — flag this to the user.
- **UK contract.** EU purchases are out of scope (future work).

---

## 2. Statutory quality standards for goods (the "is there a breach?" test)

Goods must meet these implied terms. A failure of any one is a breach that unlocks the remedies
in section 3.

| Standard | Section | Plain-language test |
| --- | --- | --- |
| Satisfactory quality | s.9 | Meets the standard a reasonable person would regard as satisfactory, considering price, description and circumstances. Covers fitness for all common purposes, appearance/finish, freedom from minor defects, safety, durability. |
| Fit for particular purpose | s.10 | If the consumer made known a particular purpose, the goods must be fit for it. |
| As described | s.11 | Goods must match any description given (including online listing, packaging, labelling). |
| Match a sample | s.13 | If bought by reference to a sample, the bulk must match the sample. |
| Match a model seen/examined | s.14 | Goods must match a model the consumer saw or examined, except for differences brought to attention. |
| Installation | s.15 | If the trader installs the goods (or it is done under their responsibility) and installation is incorrect, the goods do not conform. |

**Exclusion the consumer cannot lose:** these standards **cannot be excluded or restricted** by
the trader (s.31 — see section 4.1). A "sold as seen" or "no returns" clause does **not** remove
them for faulty goods.

**Burden of proof timeline (s.19(14)-(15)):**

- **First 6 months from delivery:** any non-conformity is **presumed to have existed at delivery**;
  the **trader** must prove otherwise. Exception: **does not apply to the short-term right to
  reject (s.22)** — for that route the consumer must show the fault even within 30 days — and does
  not apply where the presumption is incompatible with the nature of the goods or of the fault
  (e.g. obvious wear, consumables).
- **After 6 months:** the **consumer** must prove the fault was present (or inherent) at delivery.

**Delivery and transit (ss.28-29):**

- **s.28:** unless otherwise agreed, delivery must be without undue delay and within **30 days**;
  if an essential deadline is missed the consumer can treat the contract as ended and be refunded.
- **s.29:** the goods stay at the **trader's risk** until the consumer physically has them —
  transit damage is the trader's problem. Terms shifting delivery risk onto the consumer are
  caught by s.31.

---

## 3. Tiered remedy decision logic (ss.19-24)

The remedies agent must walk these tiers **in order** and return the strongest tier the facts
support, plus the full ladder for context. Inputs required: `purchase_or_delivery_date`,
`fault_description`, `has_repair_or_replacement_been_attempted`, `has_proof_of_purchase`.

### Tier 0 — Short-term right to reject (s.20, s.22) — with s.23 also open

- **Window:** within **30 days** of ownership/delivery (whichever is later). Perishables may be shorter.
- **Entitlement:** reject the goods and get a **full refund** (no deduction for use in this window).
  **Repair or replacement (s.23) is also available in this window at the consumer's choice** — it
  is not gated on the 30 days having passed.
- **Burden:** the s.19(14) presumption does **not** cover the short-term reject itself — the
  consumer must show the fault. Choosing repair/replacement instead engages the presumption.
- **Note:** the 30-day clock **pauses** if the consumer agrees to a repair/replacement; on return
  of the goods the consumer has the remainder of the 30 days **or 7 days, whichever is longer**, to
  inspect and still reject (s.22(6)-(8)).

### Tier 1 — Right to repair or replacement (s.23)

- **When:** after the 30-day window, or at the consumer's choice within it.
- **Entitlement:** the consumer chooses repair **or** replacement; the trader must do it **free**,
  **within a reasonable time**, and **without significant inconvenience**.
- **Limits:** the trader can refuse the chosen option if it is **impossible** or
  **disproportionately costly** compared with the other, but must then provide the alternative.

### Tier 2 — Price reduction OR final right to reject (s.24)

Unlocked if, after **one** repair or replacement, the goods **still** do not conform, OR repair/
replacement is impossible, or was not done within a reasonable time / without significant
inconvenience.

- **Price reduction:** an appropriate amount refunded, consumer keeps the goods.
- **Final right to reject:** return the goods for a refund. The refund **may be reduced to reflect
  use**, **except** within the **first 6 months** (no deduction), save for **motor vehicles** where
  a reasonable deduction is allowed at any time (s.24(8)-(11)).

### Refund mechanics (s.20(15)-(18))

- Refund via the **same payment method** unless agreed otherwise; **no fee**; within **14 days** of
  the trader agreeing the consumer is entitled to a refund.

### Claim strength — can the consumer make the demand stick? (provability layer)

The tier says what the Act lets the consumer **demand**; it does not say how hard that demand is to
**enforce**. The `lookup_remedy_tier` tool returns a deterministic `claim_strength`
(`strong | moderate | weak`) and a list of plain-English `practical_barriers` so the remedy is never
presented as a formality when it isn't. Two facts weaken a claim independently, and one caps it:

- **No proof of purchase.** A receipt is **not** legally required, but the consumer must be able to
  show they bought the goods **from that trader** — a bank/card statement or order confirmation
  suffices (see §7). With **none at all**, the trader can simply deny the sale, so the claim is
  practically unenforceable until the consumer produces some evidence. Downgrades strength one level.
- **Past the six-month mark.** Once the s.19(14) presumption lapses the **consumer** must prove the
  fault was present or inherent at delivery — often needing photos, a repairer's or independent
  expert's report, or evidence of the same failure in others. Downgrades strength one level.
- **Past the limitation period.** A court claim for faulty goods must normally be brought within
  **6 years** of delivery in England, Wales & NI (Limitation Act 1980 s.5); **5 years** in Scotland
  (Prescription and Limitation (Scotland) Act 1973). Beyond that the claim may be **out of time** —
  strength drops to `weak` and a limitation barrier is flagged. The tool uses the 6-year cap because
  it does not know the consumer's jurisdiction.

Scoring is deterministic: start at `strong`; each of the first two obstacles drops one level
(`strong → moderate → weak`); being out of time forces `weak`. The agent copies `claim_strength` and
`practical_barriers` through verbatim and must **not** re-grade them from its own optimism.

### Remedy output schema (structured object the agent should emit)

```json
{
  "applicable_tier": "TIER_0 | TIER_1 | TIER_2",
  "primary_remedy": "full_refund | repair | replacement | price_reduction | final_reject_refund",
  "statutory_basis": ["s.20", "s.22"],
  "simple_explanation": "Plain English for the consumer, no section numbers: what they can demand and why. Leads with the biggest obstacle when the claim is weak/moderate.",
  "legal_explanation": "The statutory reasoning: conditions (e.g. within 30 days of delivery; no deduction for use) and caveats (e.g. clock pauses during repair), with sections cited inline, plus the substance of any practical_barriers.",
  "burden_of_proof": "trader (first 6 months) | consumer (after 6 months)",
  "claim_strength": "strong | moderate | weak (copied from lookup_remedy_tier, verbatim)",
  "practical_barriers": ["Plain-English obstacles copied from lookup_remedy_tier; [] if none."],
  "alternatives": ["repair", "replacement"],
  "disclaimer": "The mandatory disclaimer (get_disclaimer), attached verbatim."
}
```

### Guarantees & warranties — a separate, additional route (s.30)

A **guarantee given without extra charge** (a free manufacturer's or retailer's undertaking to
repair, replace or refund — often labelled a "warranty") is **legally binding in its own right**
under s.30: it takes effect as a contractual obligation on the terms set out in the guarantee and its
advertising. When a genuine guarantee is in play the agents must surface two things:

- It is **in addition to** the consumer's CRA rights against the retailer, **not a replacement**. An
  **expired or narrower guarantee does not remove** the statutory rights (a court claim over faulty
  goods runs up to 6 years — see the claim-strength note above).
- It is a **second, parallel route**: the consumer may claim under the guarantee (often against the
  manufacturer) as well as, or instead of, pursuing the retailer under the CRA.

**Free vs paid — s.30 applies only to a *free* guarantee.** A **paid** extended warranty, service
plan or protection plan the consumer bought separately is **not** a s.30 guarantee. It may still
bind as an ordinary contract, so it can be raised as a separate route, but **do not cite s.30** for
it. Where it is unclear whether the cover was free or paid, **hedge** ("if this was included free
with the goods, it is also enforceable under s.30") rather than asserting s.30.

**Transparency requirements (s.30).** A guarantee must be in plain, intelligible language; **state
that the consumer's statutory rights are unaffected**; give the essentials for making a claim, the
guarantor's name and address, the duration and territorial scope; be in English where the goods are
offered in the UK; and be available in writing and in a form accessible to the consumer, on request. A guarantee
clause in the seller's T&Cs that **materially** fails these can be flagged as falling short of s.30
— but a benign guarantee that merely omits boilerplate is **not** a breach of the consumer's rights;
do not over-flag.

This does **not** change the remedy tier — that is always computed against the retailer under
ss.19-24. s.30 is an *additional* lever, raised only when a guarantee is **mentioned in the
complaint** or **found in the seller's T&Cs**; never invent one the facts do not show. A guarantee
clause is **not automatically `COMPLIANT`** — see §4.3.

---

## 4. Unfair & non-binding terms (Part 2) — the "T&C analysis" logic

Two distinct categories. The agent must not conflate them.

### 4.1 Automatically NON-BINDING terms ("blacklist") — highest-confidence flags

These do not require a fairness assessment; they simply **do not bind the consumer**:

- **Excludes/restricts the statutory goods rights** (satisfactory quality, fitness, description,
  etc. in ss.9-16) → **not binding (s.31)**. Examples: "no refunds on faulty goods", "sold as seen"
  applied to a hidden fault, "all sales final", "goods not guaranteed to be fit for purpose".
- **Excludes/restricts liability for death or personal injury from negligence** → **not binding
  (s.65)**.
- **Makes the consumer bear the burden of proof** that the law places on the trader (e.g. requiring
  the consumer to prove a fault existed at delivery within the first 6 months, contrary to s.19).

→ Map to label **`BLACKLISTED`** (this is the "high success" signal in the eval rubric).

### 4.2 POTENTIALLY UNFAIR terms — the grey list (Schedule 2) + fairness test (s.62)

Grey-list terms are **not automatically void**; they are **indicative** examples a court may find
unfair, assessed under the fairness test. Flag them and explain the test.

**Fairness test (s.62(4)):** a term is unfair if, **contrary to the requirement of good faith, it
causes a significant imbalance in the parties' rights and obligations to the detriment of the
consumer.** Assessed considering the subject matter and all circumstances at the time of contract
(s.62(5)), and **transparency** (plain, intelligible language — s.68). Core price/subject-matter
terms are exempt **only if** transparent and prominent (s.64).

**Common Schedule 2 grey-list clauses relevant to consumer goods retail:**

- Excluding/limiting the trader's liability for total or partial non-performance.
- Excluding/limiting the consumer's legal rights against the trader if the trader breaches.
- Making an agreement binding on the consumer while the trader's obligations are subject to the
  trader's whim ("we may cancel at our sole discretion").
- Allowing the trader to **retain prepayments** if the consumer cancels, without an equivalent
  right for the consumer if the trader cancels.
- Requiring a consumer who cancels to pay a **disproportionately high** sum in compensation.
- Allowing the trader to **alter the terms unilaterally** without a valid reason specified in the
  contract.
- Allowing the trader to **alter the goods' characteristics** unilaterally without valid reason.
- Giving the trader sole discretion to decide whether the goods conform, or to interpret any term.
- Requiring disputes to go to **arbitration not covered by ordinary legal provisions**.
- Automatic contract renewal with an unreasonably early deadline to opt out.

→ Map to label **`POTENTIALLY_UNFAIR`**. The agent must state that fairness is ultimately for a
court and give the reason for the concern.

### 4.3 Compliant / neutral terms

Terms that restate statutory rights, set reasonable delivery windows, or are transparent core
price/subject-matter terms → label **`COMPLIANT`**.

A clause offering a **manufacturer's or retailer's guarantee/warranty** is `COMPLIANT` **only if it
genuinely adds** a right without cutting down the statutory ones. When it does, note in its
`legal_explanation` that the guarantee is separately enforceable under **s.30** and is in addition
to (not a replacement for) the statutory rights — the T&C-side signal the email agent uses to raise
the s.30 route (see §3 for free-vs-paid and the s.30 transparency requirements). But a clause that
makes the guarantee the consumer's **sole or exclusive remedy**, that **ends the consumer's rights
when the guarantee expires**, or that otherwise excludes or restricts the ss.9-16 rights is
**`BLACKLISTED` (s.31)**, not compliant — the "guarantee" framing does not save it.

---

## 5. Clause classification schema (T&C agent output)

For each clause the agent identifies:

```json
{
  "clause_text": "verbatim quote from the T&Cs",
  "label": "BLACKLISTED | POTENTIALLY_UNFAIR | COMPLIANT",
  "statutory_basis": ["s.31"],
  "simple_explanation": "What the clause means for the consumer, one or two sentences, no section numbers.",
  "legal_explanation": "The statutory reasoning with sections cited inline; for grey-list terms, notes that fairness is ultimately a court's decision.",
  "confidence": "high | medium | low"
}
```

**Overall confidence mapping (aligns with the project's eval criteria):**

- **High success:** at least one `BLACKLISTED` clause found (clear breach of s.31 / s.65).
- **Moderate:** one or more `POTENTIALLY_UNFAIR` grey-list clauses, no blacklisted term.
- **Low:** no problematic clauses identified; advise the user their statutory rights still apply
  regardless of the T&Cs.

---

## 6. Mandatory disclaimer (attach to every user-facing output)

> This tool provides general information about your rights under the Consumer Rights Act 2015 and
> is **not a substitute for advice from a qualified solicitor**. Whether a contract term is
> ultimately "unfair" is a decision for a court. For tailored advice contact **Citizens Advice**
> (consumer helpline) or a solicitor.

---

## 7. Escalation ladder (for the email agent's footer)

If the trader does not resolve the complaint, the email agent may include next steps, but they must
be conditional and evidence-aware rather than a blanket threat. In weak/no-proof cases, the letter
should ask the trader to confirm what evidence they need and whether they will inspect the goods
once the consumer provides it. Do **not** dump a full escalation ladder into those drafts.

For stronger cases, a concise next-step sentence can mention the trader's formal complaints process,
any **Alternative Dispute Resolution (ADR)** scheme the trader belongs to, and taking further advice.
Card-provider routes and court action are not generic seller-email boilerplate. Mention them only if
the facts support it and the wording remains conditional: **Section 75** (Consumer Credit Act 1974)
is for qualifying credit-card or point-of-sale credit purchases where the item cash price is over
£100 and up to £30,000, while **chargeback** is a voluntary card-scheme route with short scheme
deadlines (often around 120 days, but the applicable start date and limit depend on the scheme and
facts). A letter before claim and the **small claims court** (Money Claim Online) are last resorts
only if the evidence supports it.

Where `claim_strength` is `weak`, `practical_barriers` is non-empty, or `has_proof_of_purchase` is
false, escalation wording must lead with the evidence step. Do **not** say the consumer will pursue
card remedies or court action as a definite next step before they have proof of purchase and any
post-six-month evidence needed to show the fault was present or inherent at delivery.

**Guarantee / warranty (s.30):** if the goods came with a manufacturer's or retailer's guarantee, it
is a **separate, additional route** — legally enforceable in its own right and on top of the
statutory claim against the seller. Raise it only when a guarantee is mentioned in the complaint or
found in the seller's T&Cs; an **expired guarantee does not remove** the consumer's CRA rights.

**Proof of purchase:** a receipt is **not** legally required — a bank/card statement or order
confirmation is sufficient proof of purchase. A trader demanding "the original receipt" for a
faulty-goods remedy is overreaching. If the consumer has said they have **no** proof, the email must
not claim they have already provided a bank/card statement, receipt, or order confirmation; it can
only say they are checking for alternative proof.

---

## 8. Sources (verify these into the app)

- Consumer Rights Act 2015 (full text): https://www.legislation.gov.uk/ukpga/2015/15
- Part 1 (goods), ss.9-24: https://www.legislation.gov.uk/ukpga/2015/15/part/1
- s.19 (burden of proof): https://www.legislation.gov.uk/ukpga/2015/15/section/19
- s.23 (repair/replacement): https://www.legislation.gov.uk/ukpga/2015/15/section/23
- s.30 (goods under guarantee): https://www.legislation.gov.uk/ukpga/2015/15/section/30
- Part 2 (unfair terms) & Schedule 2 (grey list): https://www.legislation.gov.uk/ukpga/2015/15/part/2
- CMA "Unfair contract terms explained" (CMA37): https://www.gov.uk/government/publications/unfair-contract-terms-cma37
- Which? Consumer Rights Act overview: https://www.which.co.uk/consumer-rights/regulation/consumer-rights-act-aKJYx8n5KiSl
- Citizens Advice — consumer: https://www.citizensadvice.org.uk/consumer/
