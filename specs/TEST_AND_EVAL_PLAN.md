# Test And Eval Plan

## Philosophy

This product depends on both deterministic legal logic and model-written language. Use two gates:

- Pytest for deterministic behavior and contracts.
- LLM eval suites for behavior that cannot be fully pinned with unit tests.

No prompt, model, legal KB, or agent-wiring change should land without running the relevant evals.

## Pytest Coverage

### Contracts

File: `tests/test_contracts.py`

Assertions:

- All Pydantic schemas validate representative valid examples.
- Enum values match frontend expectations.
- `SessionStateContract` contains only public keys.
- Generated frontend schema output is deterministic.

### Dates And Remedy Tier

Files:

- `tests/test_remedy_tier.py`
- `tests/test_mcp_kb.py`

Assertions:

- Day 30 is Tier 0.
- Day 31 is Tier 1 unless repair/replacement attempted.
- Six calendar months boundary is calculated with month arithmetic.
- Month-end dates clamp correctly.
- Future delivery date raises error.
- Repair/replacement attempted unlocks Tier 2.
- Motor vehicle deduction note differs where applicable.
- No proof of purchase reduces claim strength and adds a practical barrier.
- Post-six-month cases put burden on consumer and add evidence barrier.
- Over six years adds limitation barrier.

### Ingestion

Files:

- `tests/test_ingest.py`
- `tests/test_ingest_url.py`
- `tests/test_api_ingest.py`

Assertions:

- Empty pasted text rejected.
- Valid pasted text accepted.
- Size caps enforced.
- Unsupported upload extensions rejected.
- PDF/DOCX/TXT extraction works on sample files.
- URL ingestion blocks localhost/private/link-local/metadata hosts.
- Redirect to blocked host is rejected.
- Unsupported content type rejected.
- API endpoint returns 400 with useful detail on ingestion error.

### Prompt Injection

File: `tests/test_injection.py`

Assertions:

- Each injection pattern is detected.
- Clean terms are not flagged.
- Wrapped text includes open/close delimiters.
- Security notice appears when flags exist.
- Injection guard ORs `temp:injection_flags` into `tc_analysis_result.injection_flagged`.

### Citation Guard

File: `tests/test_guardrails.py`

Assertions:

- Curated citations are kept and normalized.
- Long-form citations are normalized to short codes.
- Uncurated citations are removed.
- Dropped citation note is appended to legal explanation.
- Guard handles both single result and list-of-clauses result.

### Intake

File: `tests/test_intake_confirmation.py`

Assertions:

- Opening story may prefill fields but unconfirmed fields are confirmed.
- Direct text/date/choice answers bind deterministically.
- Boolean confirm yes/no works.
- Bare rejection re-asks field.
- Correction replaces inferred value.
- Invalid date re-asks date field.
- Business buyer scope gate stops the flow.
- Terms opt-out and terms-clean state set `terms_source`.

### Orchestrator

File: `tests/test_orchestrator.py`

Assertions:

- Incomplete intake runs only intake.
- Complete intake with no terms waits.
- Terms opt-out emits no-terms stub.
- Terms provided are wrapped and pre-scan flags stored.
- Stage gates prevent duplicate T&C/remedy/email reruns.
- Existing final output makes orchestrator stop.

### Remedies Agent

File: `tests/test_remedies_agent.py`

Assertions:

- Tool args are hydrated from state.
- Missing proof-of-purchase cannot be omitted silently.
- Structured remedy result is grounded in tool truth.
- Invalid primary remedy is replaced with available remedy.
- Alternatives are filtered to available remedies.

### Email Guard

File: `tests/test_email_guard.py`

Assertions:

- Remedy aliases normalize to expected IDs.
- Draft count matches expected remedies.
- Disclaimer paragraph is stripped from bodies.
- `[Your name]` is allowed; other placeholders are rejected in evals.

## LLM Eval Suites

Place eval code under:

```text
evals/
  run.py
  harness.py
  judge.py
  suites/
  datasets/
  results/
```

### Intake Suite

Dataset:

- Opening stories with varied phrasing.
- Missing fields.
- Ambiguous dates.
- Business-buyer cases.
- No-proof cases.

Checks:

- Required fields converge.
- Inferences are confirmed.
- Scope gate fires where appropriate.
- No invented delivery date.

### T&C Analysis Suite

Dataset:

- No refunds.
- Sold as seen.
- All sales final.
- Manufacturer-only warranty.
- Short complaint windows.
- Hidden fees.
- Compliant statutory-rights-preserved clause.
- Prompt-injected terms.

Checks:

- Correct label.
- Correct curated citations.
- Useful simple and legal explanations.
- Injection flag where expected.

### Remedies Suite

Dataset:

- Day 10 refund request.
- Day 31 repair request.
- Five-month replacement request.
- Seven-month claim with evidence burden.
- Failed repair leading to Tier 2.
- No proof of purchase.
- Old purchase near limitation.

Checks:

- Tier and remedy match deterministic tool.
- Explanation leads with biggest barrier when claim is weak/moderate.
- No overconfident claim when proof is missing.

### Email Drafts Suite

Dataset:

- Strong refund case.
- Weak no-proof case.
- Post-six-month case.
- Problematic T&C clause rebuttal.
- Warranty/guarantee scenario.

Checks:

- One draft per remedy.
- All three tones present.
- Polite body has no citations or threats.
- Firm body includes 14-day deadline and citations.
- Formal body includes caveats and conditional escalation only if justified.
- No invented facts.
- Disclaimer excluded.

### Security Suite

Dataset:

- Injection corpus.
- Terms with system prompt probes.
- Terms with zero-width/control chars.
- Legal-citation bait.

Checks:

- Injection surfaced.
- Legal classification remains based on clause substance.
- Uncurated citations absent.

### End-To-End Suite

Dataset:

- Complete happy path with terms.
- No-terms path.
- Business-buyer path.
- Weak evidence path.
- Failed repair path.

Checks:

- Final state contains expected public keys.
- UI-relevant fields are populated.
- Disclaimer appears in user-facing result.
- Email is coherent and case-specific.

## Gate Policy

Before merging normal code:

```bash
uv run pytest
```

Before merging changes to prompts, model choices, legal KB, guardrails, or agent routing:

```bash
uv run pytest
uv run python -m evals.run
```

Before deployment:

```bash
uv run pytest
uv run python -m evals.run
cd src/frontend && npm run build
```

Eval result artifacts should be written to `evals/results/` and ignored by git except for `.gitkeep`.
