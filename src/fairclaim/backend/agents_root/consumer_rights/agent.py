"""ADK agent-discovery entry point — the one app the frontend talks to for
the whole case lifecycle (intake through to drafted emails). See
backend/agents/orchestrator.py for why intake and analysis, previously two
separate apps/sessions, are now one deterministic root agent sharing a
single session.
"""

from fairclaim.backend.agents.orchestrator import orchestrator_agent as root_agent

__all__ = ["root_agent"]
