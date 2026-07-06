# Frontend UX Specification

## Goal

The frontend should feel like a focused case-building workspace, not a marketing page. The first screen should let the user start describing their faulty-goods issue immediately.

## Application States

Use four high-level states:

- `start`
- `interview`
- `analysing`
- `results`

## Start Screen

Purpose:

- Capture the user's opening story.

Requirements:

- Prominent textarea.
- Primary action to start a live case.
- Short scope cues: faulty goods, UK consumer rights, general information.
- Do not require the user to know legal terminology.

Example prompt:

```text
Tell us what you bought, who sold it, when you received it, what went wrong, and what you want them to do.
```

## Interview Workspace

Layout:

- Main question card.
- Case file sidebar or stacked mobile section.
- Thought-process/activity timeline.

Question cards should render `UiComponent`:

- `choice_card`: buttons for options.
- `date_picker`: native date input with max today and min 1900-01-01.
- `text_input`: textarea.
- `confirm_card`: inferred value, accept button, correction flow.
- `file_upload`: pasted terms card for MVP.

Case file:

- Show fields already collected.
- Show progress based on known required fields.
- Highlight active field.
- Use plain labels, not schema field names.

Thought process:

- Show concise, non-technical entries:
  - user described problem,
  - pre-filled case facts,
  - asked about delivery date,
  - terms reviewed,
  - remedy ladder applied.

Do not expose private state keys.

## Terms Card

MVP:

- Pasted text box.
- Button: "Ingest terms and analyse".
- Secondary action: "I don't have the terms - continue anyway".

Behavior:

- Pasted terms go to `/ingest/terms`.
- On success, submit ADK turn with `stateDelta.terms_clean`.
- If user continues without terms, submit ADK turn with `stateDelta.terms_opted_out = true`.
- Do not send raw terms as ordinary chat transcript after ingestion.

User-facing note:

```text
Pasted terms are size-limited and wrapped as untrusted evidence before analysis.
```

## Analysing State

Show that the system is working through stages:

- reviewing terms,
- checking remedy ladder,
- drafting letters.

Avoid fake legal conclusions before results are available.

## Results Dashboard

Sections:

1. Thought process summary.
2. Best-supported remedy hero.
3. Small print check.
4. Remedy ladder.
5. Complaint letter.

### Best-Supported Remedy

Show:

- Label for `primary_remedy`.
- `remedy.simple_explanation`.
- Statutory section chips.

### Small Print Check

Show:

- Overall confidence.
- Injection warning if `tc.injection_flagged` is true.
- No-terms note if terms were not provided.
- Clause cards with:
  - verdict,
  - section chips,
  - confidence,
  - clause text,
  - simple explanation,
  - legal detail in a disclosure.

No-terms note should clearly say statutory rights apply regardless of small print.

### Remedy Ladder

Show:

- Active tier.
- Burden of proof.
- Claim strength.
- Practical barriers, if any.
- Three ladder steps:
  - short-term reject,
  - repair/replacement,
  - price reduction/final reject.

Plain-English explanation should be visible; legal detail should be collapsible.

### Complaint Letter

Controls:

- Remedy tabs if multiple drafts exist.
- Tone segmented control:
  - Polite.
  - Firm.
  - Formal.
- Copy button.

Copy behavior:

- Copy `Subject: ...` and the selected body.
- Do not copy disclaimer.

Show disclaimer outside the letter document.

## Design Direction

Tone:

- Calm, practical, trustworthy.
- Work-focused, not decorative.

Suggested palette:

- Navy: `#022a5f`
- Violet accent: `#9988ff`
- Neutral surfaces and readable text.

Use:

- Icons for actions and status.
- Compact cards for repeated items.
- Native disclosure for legal details.
- Segmented controls for tone.
- Tabs for remedy variants.

Avoid:

- Landing-page hero composition.
- In-app paragraphs explaining implementation details.
- Decorative blobs/orbs as the dominant visual language.
- Legalese in primary explanations.

## Accessibility

Requirements:

- All controls have accessible names.
- Button labels fit at mobile widths.
- Keyboard navigation works for answer cards and result controls.
- Color is not the only signal for verdicts or warnings.
- Long email bodies are readable and preserve paragraph breaks.

## Responsive Behavior

Desktop:

- Case file and question card can sit side by side.
- Results can use a two-column grid for small print and remedies.

Mobile:

- Stack panels.
- Keep primary action visible near the current card.
- Avoid horizontal scrolling.
- Letter controls should wrap cleanly.

## Frontend Data Flow

API helper should:

1. Create ADK session on first turn.
2. POST `/run`.
3. GET session state.
4. Return state to React.

Production base URL:

- Empty string, because frontend is served by same origin.

Local dev base URL:

- `VITE_API_BASE_URL=http://localhost:8000`

## Generated Types

Frontend TypeScript should import generated schema types from:

```text
src/frontend/src/generated/schemas.ts
```

Do not hand-edit generated types.
