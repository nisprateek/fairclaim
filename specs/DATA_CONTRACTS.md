# Data Contracts

`src/fairclaim/backend/schemas.py` is the source of truth for backend outputs and frontend session state. Generate frontend types from it rather than maintaining parallel hand-written TypeScript contracts.

## Common Field Guidance

`statutory_basis`:

- List short section codes only, such as `["s.9", "s.31"]`.
- Do not place full statutory text in this field.
- Any citation outside the curated KB must be stripped by the citation guard.

`simple_explanation`:

- 1-3 sentences.
- Everyday English.
- No section numbers.
- No legal terms of art such as "statutory", "non-binding", or "burden of proof".

`legal_explanation`:

- Full legal reasoning.
- Include statutory basis and caveats.
- May mention section codes that are curated.

## ClauseVerdict

```python
class ClauseVerdict(BaseModel):
    clause_text: str
    label: Literal["BLACKLISTED", "POTENTIALLY_UNFAIR", "COMPLIANT"]
    statutory_basis: list[str]
    simple_explanation: str
    legal_explanation: str
    confidence: Literal["high", "medium", "low"]
```

Rules:

- `clause_text` must be the relevant seller wording or a faithful excerpt.
- `BLACKLISTED` means the clause excludes or restricts a right that cannot be excluded, or excludes death/personal injury negligence liability.
- `POTENTIALLY_UNFAIR` means it may fail the CRA fairness test or grey-list logic but a court would decide.
- `COMPLIANT` means no material concern was found for the clause.

## TcAnalysisResult

```python
class TcAnalysisResult(BaseModel):
    clauses: list[ClauseVerdict]
    overall_confidence: Literal["high", "moderate", "low"]
    injection_flagged: bool
    disclaimer: str
```

Rules:

- Use `moderate`, not `medium`, for overall confidence.
- `injection_flagged` is true if either deterministic pre-scan flags input or the model sees likely manipulation.
- No-terms flow uses an empty `clauses` list and low confidence.

## RemedyResult

```python
class RemedyResult(BaseModel):
    applicable_tier: Literal["TIER_0", "TIER_1", "TIER_2"]
    primary_remedy: Literal[
        "full_refund",
        "repair",
        "replacement",
        "price_reduction",
        "final_reject_refund",
    ]
    statutory_basis: list[str]
    simple_explanation: str
    legal_explanation: str
    burden_of_proof: Literal["trader", "consumer"]
    claim_strength: Literal["strong", "moderate", "weak"]
    practical_barriers: list[str]
    alternatives: list[str]
    disclaimer: str
```

Rules:

- Structured fields must be grounded in `lookup_remedy_tier`.
- `claim_strength` is practical enforceability, not whether the Act grants the remedy.
- `practical_barriers` should be empty only where no proof/timing barrier is known.
- `primary_remedy` must be one of the tool's available remedies.
- `alternatives` must contain only other available remedies.

## EmailDraft

```python
class EmailDraft(BaseModel):
    remedy: Literal[
        "full_refund",
        "repair",
        "replacement",
        "price_reduction",
        "final_reject_refund",
    ]
    subject: str
    polite_body: str
    firm_body: str
    formal_body: str
    response_deadline_days: int = 14
```

Rules:

- One draft per offered remedy: primary remedy plus alternatives.
- `polite_body`: 120-180 words, no legal citations, no deadline, no threats.
- `firm_body`: 200-280 words, cites rights, sets 14-day deadline.
- `formal_body`: 300-400 words, final-notice register, case-specific caveats, conditional escalation only when justified.
- Bodies are complete letters with salutation and sign-off.
- `[Your name]` is the only allowed placeholder.
- Do not include the disclaimer inside seller-facing bodies.

## UiComponent

```python
class UiComponent(BaseModel):
    type: Literal["choice_card", "date_picker", "text_input", "file_upload", "confirm_card"]
    field: str
    prompt: str
    options: list[str] | None = None
    accept: list[str] | None = None
    inferred_value: str | None = None
```

Rules:

- `field` must match a `CaseFields` field.
- Components must use canonical control types from the intake component catalog.
- Confirm cards carry `inferred_value`.

## CaseFields

```python
class CaseFields(BaseModel):
    is_individual: bool | None = None
    seller_name: str | None = None
    product: str | None = None
    purchase_or_delivery_date: str | None = None
    terms_source: Literal["pasted", "none"] | None = None
    grievance: str | None = None
    desired_outcome: Literal["refund", "repair", "replacement", "price_reduction"] | None = None
    has_repair_or_replacement_been_attempted: bool | None = None
    has_proof_of_purchase: bool | None = None
```

Rules:

- `purchase_or_delivery_date` is the date goods were received, delivered, or collected.
- `terms_source = "none"` means the user explicitly continued without terms.
- A receipt is not required; any proof of purchase counts.

## IntakeTurn

```python
class IntakeTurn(BaseModel):
    is_complete: bool
    scope_gate_failure: str | None = None
    next_component: UiComponent | None = None
    collected_fields: CaseFields
```

Rules:

- `is_complete` is true only after all required fields are filled and confirmed.
- `scope_gate_failure` stops the flow.
- `next_component` is null only when complete or scope-gated.

## SessionStateContract

```python
class SessionStateContract(BaseModel):
    intake_turn: IntakeTurn | None = None
    tc_analysis_result: TcAnalysisResult | None = None
    remedy_result: RemedyResult | None = None
    email_drafts: list[EmailDraft] | None = None
```

The frontend should rely only on these public keys.

## `/ingest/terms`

Request:

- `multipart/form-data`
- `method`: `pasted`, `url`, or `upload`
- `text`: required for `pasted`
- `url`: required for `url`
- `file`: required for `upload`

MVP frontend should use only `pasted`.

Success response:

```json
{
  "text": "clean extracted terms text"
}
```

Error response:

```json
{
  "detail": "human-readable reason"
}
```

## ADK `/run` StateDelta

The frontend may pass:

```json
{
  "stateDelta": {
    "terms_clean": "clean terms text"
  }
}
```

or:

```json
{
  "stateDelta": {
    "terms_opted_out": true
  }
}
```

Do not pass raw terms as normal chat text once ingestion has succeeded.
