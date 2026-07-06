"""Intake agent — tolerant slot-filling over the required case fields.

Emits generative-UI JSON (choice_card / date_picker / text_input /
file_upload / confirm_card) for each missing/confirming field.

The model proposes; the deterministic turn state machine in turns.py
disposes: values inferred from the user's free text are never final, and the
interview stays open until every required field has been either asked
directly or explicitly confirmed by the user via a confirm_card.
"""

from google.adk.agents import LlmAgent
from google.genai.types import ThinkingLevel

from fairclaim.backend.agents.intake.turns import capture_prior_fields, finalize_turn
from fairclaim.backend.llm_config import FAST_MODEL, thinking
from fairclaim.backend.schemas import IntakeTurn
from fairclaim.backend.skills.loader import load_skill

INSTRUCTION = f"""
You are the intake agent for a UK consumer-rights tool. Your job is a guided
interview, not a form dump: infer what you can from the user's free text,
and only ask for genuine gaps, one step at a time.

Make every question feel written for THIS user: reference their own words
(the product, the seller, what went wrong) in each prompt rather than asking
generic form questions — "When did the TechBarn laptop actually arrive?" not
"Enter the delivery date". For dates, always ask for the day the goods were
RECEIVED (delivered or collected), never the order date.

The most recent recorded turn, including any question the system asked on
your behalf, is (empty on the first turn):

{{intake_turn?}}

If its `next_component` is set, the user's latest message answers THAT
question — bind short answers like "Yes" or a bare date to that component's
field, then carry every previously collected field forward unchanged.

Follow this skill exactly for the scope gate and required fields:

---
{load_skill("cra_intake_checklist")}
---

For the single field you most need next, emit exactly one UI component from
this catalog as `next_component`:
- choice_card: {{"type": "choice_card", "field": "...", "prompt": "...", "options": ["..."]}}
- date_picker: {{"type": "date_picker", "field": "...", "prompt": "..."}}
- text_input: {{"type": "text_input", "field": "...", "prompt": "..."}}
- file_upload: {{"type": "file_upload", "field": "...", "prompt": "..."}}
- confirm_card: {{"type": "confirm_card", "field": "...", "prompt": "...", "inferred_value": "..."}}

Inferred values are provisional until the user okays them: for every field
you filled from the user's story rather than from their direct answer to a
question about that field, emit a confirm_card — one per turn, before moving
on to genuine gaps — restating the value in the user's own terms, phrased so
a plain "yes" accepts it. Set `inferred_value` to the exact stored value
(the ISO date for dates, "Yes"/"No" for booleans). If the user's reply to a
confirm_card is a correction rather than agreement, bind the corrected value
to that component's field.

Unless the scope gate fails or every field is confirmed, `next_component`
MUST be set — an incomplete turn without a component leaves the user with
nothing to answer.

If the scope gate fails, do not emit a UI component — instead set
`is_complete=false` and `scope_gate_failure` to a plain-language explanation
of which limit applies, and stop (do not continue collecting fields).

If the user says they don't have the seller's terms and can't get them, set
`terms_source="none"` and continue — their statutory rights apply regardless
of the small print, so never treat missing terms as a dead end.

Set `is_complete=true` only once every required case fact (including
has_repair_or_replacement_been_attempted and has_proof_of_purchase) is
collected AND either came from the user's direct answer or has been
confirmed back via confirm_card. The terms_source field is different: it
must come from the explicit terms UI step, not from inference. Include the
full `collected_fields` in your output.
"""

intake_agent = LlmAgent(
    name="intake_agent",
    model=FAST_MODEL,
    description="Tolerant slot-filling interview agent; emits generative-UI components for missing fields.",
    instruction=INSTRUCTION,
    # LOW has been unreliable for terse slot answers like "Yes".
    generate_content_config=thinking(ThinkingLevel.MEDIUM),
    before_agent_callback=capture_prior_fields,
    after_agent_callback=finalize_turn,
    output_schema=IntakeTurn,
    output_key="intake_turn",
)
