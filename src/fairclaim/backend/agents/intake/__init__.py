"""Intake package: agent definition, UI component catalog, and the
deterministic turn state machine.

- agent.py       — the LlmAgent + its instruction
- components.py  — fallback question catalog and deterministic answer parsing
- turns.py       — before/after-model callbacks enforcing interview progress

Date extraction lives in backend.dates (shared with the MCP KB server).
"""

from fairclaim.backend.agents.intake.agent import INSTRUCTION, intake_agent
from fairclaim.backend.agents.intake.components import (
    CONFIRM_PROMPTS,
    FALLBACK_COMPONENTS,
    NO_CONFIRM_FIELDS,
    OUTCOME_OPTIONS,
    extract_choice_value,
)
from fairclaim.backend.agents.intake.turns import (
    BUSINESS_BUYER_SCOPE_GATE_FAILURE,
    CONFIRMED_FIELDS_KEY,
    apply_business_buyer_scope_gate,
    capture_prior_fields,
    finalize_turn,
)

__all__ = [
    "BUSINESS_BUYER_SCOPE_GATE_FAILURE",
    "CONFIRMED_FIELDS_KEY",
    "CONFIRM_PROMPTS",
    "FALLBACK_COMPONENTS",
    "INSTRUCTION",
    "NO_CONFIRM_FIELDS",
    "OUTCOME_OPTIONS",
    "apply_business_buyer_scope_gate",
    "capture_prior_fields",
    "extract_choice_value",
    "finalize_turn",
    "intake_agent",
]
