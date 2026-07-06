"""Central model configuration for the agent graph.

Use the fast tier for structured intake and deterministic-tool reconciliation.
Use the capable tier for T&C clause classification and email drafting, where
the model's legal judgment and letter craft matter most.
"""

import os

from google.genai import types

FAST_MODEL = os.environ.get("FAIRCLAIMAI_FAST_MODEL", "gemini-3.1-flash-lite")
CAPABLE_MODEL = os.environ.get("FAIRCLAIMAI_CAPABLE_MODEL", "gemini-3.5-flash")
JUDGE_MODEL = os.environ.get("FAIRCLAIMAI_JUDGE_MODEL", "gemini-3.1-pro-preview")


def thinking(level: types.ThinkingLevel) -> types.GenerateContentConfig:
    """GenerateContentConfig pinning a Gemini 3.x thinking level for an agent."""
    return types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(thinking_level=level)
    )
