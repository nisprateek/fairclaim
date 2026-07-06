"""Shared machinery for the eval suites: .env loading, instrumented agent
runs through the real ADK Runner, staged single-agent execution (mirroring
how the orchestrator feeds each specialist), and multi-turn intake driving.

Everything here runs inside ONE asyncio event loop per process (see
evals/run.py) — the shared MCP stdio toolset binds its sessions to the loop,
so per-case asyncio.run() calls would leak subprocess sessions.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from pathlib import Path
from typing import Any

from google.adk.agents import BaseAgent
from google.adk.events import Event, EventActions
from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.adk.utils.context_utils import Aclosing
from google.genai import types

SRC_DIR = Path(__file__).resolve().parent.parent
DATASETS_DIR = Path(__file__).resolve().parent / "datasets"
RESULTS_DIR = Path(__file__).resolve().parent / "results"

_RETRYABLE = re.compile(r"429|RESOURCE_EXHAUSTED|UNAVAILABLE|503|overloaded|quota", re.I)


def load_env() -> None:
    """Load .env into os.environ (setdefault — real env wins), the same
    file ADK's own agent loader reads for the REST path."""
    env_path = SRC_DIR / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load_dataset(name: str) -> Any:
    return json.loads((DATASETS_DIR / name).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Eval telemetry: model callbacks capture exact tokens and estimated cost.
# ---------------------------------------------------------------------------

_store = None


def telemetry_store():
    global _store
    if _store is None:
        from fairclaim.backend.agents.orchestrator import orchestrator_agent
        from fairclaim.backend.telemetry import TelemetryStore, instrument_agent_tree

        _store = TelemetryStore(max_calls=10_000, max_traces=1000)
        instrument_agent_tree(orchestrator_agent, _store)
    return _store


def usage_totals() -> dict:
    snapshot = telemetry_store().snapshot()
    return {
        "model_calls": snapshot["totals"]["model_calls"],
        "total_tokens": snapshot["totals"]["total_tokens"],
        "est_cost_usd": snapshot["totals"]["est_cost_usd"],
    }


# ---------------------------------------------------------------------------
# Runners
# ---------------------------------------------------------------------------

class StagedRunner(BaseAgent):
    """Root agent that stages a state delta (the way the orchestrator stages
    `temp:` inputs) and then runs one target agent. `target` is a plain
    attribute, not a sub_agent, because the real agents already belong to the
    orchestrator and an agent can only have one parent."""

    staged: dict = {}
    target: Any = None

    async def _run_async_impl(self, ctx):
        yield Event(author=self.name, actions=EventActions(state_delta=dict(self.staged)))
        async with Aclosing(self.target.run_async(ctx)) as agen:
            async for event in agen:
                yield event


async def _drive_turn(runner: Runner, service, session_id: str, text: str) -> dict:
    message = types.Content(role="user", parts=[types.Part(text=text)])
    async for _event in runner.run_async(user_id="eval", session_id=session_id, new_message=message):
        pass
    session = await service.get_session(app_name=runner.app_name, user_id="eval", session_id=session_id)
    return dict(session.state)


async def with_retry(coro_factory, attempts: int = 3):
    """Retry transient model-quota/availability errors with a linear backoff;
    anything else propagates immediately."""
    for attempt in range(1, attempts + 1):
        try:
            return await coro_factory()
        except Exception as e:  # noqa: BLE001 — classify then re-raise
            if attempt == attempts or not _RETRYABLE.search(str(e)):
                raise
            await asyncio.sleep(10 * attempt)


async def run_staged(target: BaseAgent, staged: dict, message: str = "Proceed.") -> dict:
    """Run one specialist agent with its inputs staged exactly the way the
    orchestrator would stage them; returns the final session state."""
    telemetry_store()  # ensure instrumentation before any model call
    root = StagedRunner(name="eval_staged_runner", staged=staged, target=target)
    service = InMemorySessionService()
    runner = Runner(app_name="evals", agent=root, session_service=service)
    session = await service.create_session(app_name="evals", user_id="eval")

    async def _once():
        return await _drive_turn(runner, service, session.id, message)

    return await with_retry(_once)


class ConversationResult(dict):
    """Final session state plus how the interview went."""


async def run_conversation(
    root_agent: BaseAgent,
    persona: dict,
    *,
    initial_state: dict | None = None,
    max_turns: int = 30,
    done: Any = None,
) -> ConversationResult:
    """Drive a scripted persona through a multi-turn interview.

    The persona supplies `story` (turn 1) and `answers` (field -> reply for
    direct questions). Confirm cards are accepted by echoing inferred_value —
    exactly what the frontend's accept button submits — unless
    `corrections[field]` supplies a one-shot correction. `done(state)` stops
    the loop (default: intake turn complete or scope-gated).
    """
    telemetry_store()
    service = InMemorySessionService()
    runner = Runner(app_name="evals", agent=root_agent, session_service=service)
    session = await service.create_session(app_name="evals", user_id="eval", state=dict(initial_state or {}))

    if done is None:
        def done(state):  # noqa: ANN001
            turn = state.get("intake_turn") or {}
            return turn.get("is_complete") or turn.get("scope_gate_failure")

    answers: dict = dict(persona.get("answers") or {})
    corrections: dict = dict(persona.get("corrections") or {})
    transcript: list[dict] = []
    reply = persona["story"]
    state: dict = {}
    stall = 0
    last_component_key = None

    for turn_index in range(1, max_turns + 1):
        async def _once(text=reply):
            return await _drive_turn(runner, service, session.id, text)

        state = await with_retry(_once)
        turn = state.get("intake_turn") or {}
        component = turn.get("next_component")
        transcript.append({"sent": reply, "component": component})
        if done(state):
            return ConversationResult(
                state=state, turns=turn_index, transcript=transcript, stalled=False
            )
        if not component:
            break
        key = (component.get("type"), component.get("field"), component.get("prompt"))
        stall = stall + 1 if key == last_component_key else 0
        last_component_key = key
        if stall >= 3:
            break  # identical question three times — abort, don't hang the suite
        reply = _answer_for(component, answers, corrections)

    return ConversationResult(state=state, turns=len(transcript), transcript=transcript, stalled=True)


def _answer_for(component: dict, answers: dict, corrections: dict) -> str:
    field = component.get("field") or ""
    if component.get("type") == "confirm_card":
        if field in corrections:
            return str(corrections.pop(field))  # one-shot correction, then accept next time
        return str(component.get("inferred_value") or "Yes")
    if field in answers:
        return str(answers[field])
    return "I'm not sure."


# ---------------------------------------------------------------------------
# Small scoring helpers shared by suites
# ---------------------------------------------------------------------------

def norm(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def contains(haystack: Any, needle: str) -> bool:
    return norm(needle) in norm(haystack)


def find_clause(clauses: list[dict], match: str) -> dict | None:
    """Find the model clause whose text contains `match` (normalized)."""
    for clause in clauses or []:
        if contains(clause.get("clause_text"), match):
            return clause
    return None


def now_stamp() -> str:
    return time.strftime("%Y%m%d-%H%M%S")
