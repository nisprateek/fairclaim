"""Eval telemetry: cost math, aggregation, and agent callback wiring."""

import asyncio
from types import SimpleNamespace

import pytest
from google.adk.agents import BaseAgent
from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.adk.utils.context_utils import Aclosing
from google.genai import types

from fairclaim.backend.telemetry import TelemetryStore, estimate_cost_usd, instrument_agent_tree

PRICING = {"gemini-3.5-flash": {"input": 0.30, "output": 2.50}}


def _usage(prompt=1000, output=500, thoughts=200):
    return SimpleNamespace(
        prompt_token_count=prompt,
        candidates_token_count=output,
        thoughts_token_count=thoughts,
        total_token_count=prompt + output + thoughts,
    )


def test_cost_math_per_million_tokens():
    cost = estimate_cost_usd("gemini-3.5-flash", 1_000_000, 1_000_000, PRICING)
    assert cost == pytest.approx(0.30 + 2.50)


def test_versioned_model_ids_match_by_prefix():
    assert estimate_cost_usd("gemini-3.5-flash-001", 1_000_000, 0, PRICING) == pytest.approx(0.30)


def test_unknown_model_costs_zero_not_invented():
    assert estimate_cost_usd("mystery-model", 1_000_000, 1_000_000, PRICING) == 0.0


def test_model_call_records_tokens_latency_and_cost():
    store = TelemetryStore()
    store.pricing = PRICING
    store.begin_agent_span("inv1", "sess1", "tc_analysis_agent")
    store.model_call_started("inv1", "tc_analysis_agent")
    store.model_call_finished("inv1", "sess1", "tc_analysis_agent", "gemini-3.5-flash", _usage())
    store.end_agent_span("inv1", "tc_analysis_agent")

    (call,) = store.model_calls
    assert call["prompt_tokens"] == 1000
    assert call["output_tokens"] == 500
    assert call["thoughts_tokens"] == 200
    assert call["ms"] is not None and call["ms"] >= 0
    assert call["cost_usd"] == pytest.approx((1000 * 0.30 + 700 * 2.50) / 1e6)

    snapshot = store.snapshot()
    assert snapshot["totals"]["model_calls"] == 1
    assert snapshot["totals"]["total_tokens"] == 1700
    assert snapshot["agents"]["tc_analysis_agent"]["model_calls"] == 1
    assert snapshot["models"]["gemini-3.5-flash"]["total_tokens"] == 1700
    (trace,) = snapshot["traces"]
    assert trace["agents"] == ["tc_analysis_agent"]
    assert trace["tokens"] == 1700


def test_missing_usage_metadata_records_zeros():
    store = TelemetryStore()
    store.model_call_started("inv1", "a")
    store.model_call_finished("inv1", None, "a", "gemini-3.5-flash", None, error="quota")
    (call,) = store.model_calls
    assert call["total_tokens"] == 0
    assert call["error"] == "quota"
    assert store.snapshot()["totals"]["model_errors"] == 1


def test_guardrail_sniffing_reports_citation_strips_and_injection_flags():
    from fairclaim.backend.telemetry import _sniff_guardrails

    store = TelemetryStore()
    state = {
        "tc_analysis_result": {
            "clauses": [
                {"legal_explanation": "fine"},
                {"legal_explanation": "x [Note: citation(s) s.99 removed - ...]"},
            ]
        },
        "temp:injection_flags": ["role_override"],
    }
    _sniff_guardrails(store, "tc_analysis_agent", SimpleNamespace(state=state, invocation_id="inv1"))
    assert {event["kind"] for event in store.guardrail_events} == {
        "citation_strip",
        "injection_prescan",
    }


class ChildAgent(BaseAgent):
    async def _run_async_impl(self, ctx):
        return
        yield  # pragma: no cover


class ParentAgent(BaseAgent):
    async def _run_async_impl(self, ctx):
        for sub in self.sub_agents:
            async with Aclosing(sub.run_async(ctx)) as agen:
                async for event in agen:
                    yield event


def test_instrumentation_traces_agent_spans_in_run_order():
    root = ParentAgent(name="parent", sub_agents=[ChildAgent(name="child_a"), ChildAgent(name="child_b")])
    store = TelemetryStore()
    instrument_agent_tree(root, store)

    async def _run():
        service = InMemorySessionService()
        runner = Runner(app_name="t", agent=root, session_service=service)
        session = await service.create_session(app_name="t", user_id="u")
        message = types.Content(role="user", parts=[types.Part(text="hi")])
        async for _ in runner.run_async(user_id="u", session_id=session.id, new_message=message):
            pass

    asyncio.run(_run())
    (trace,) = store.snapshot()["traces"]
    assert trace["agents"] == ["parent", "child_a", "child_b"]


def test_instrumentation_is_idempotent_and_preserves_existing_callbacks():
    calls = []
    existing = lambda callback_context=None, **_: calls.append("existing") or None  # noqa: E731
    agent = ChildAgent(name="solo", after_agent_callback=existing)
    store = TelemetryStore()
    instrument_agent_tree(agent, store)
    instrument_agent_tree(agent, store)
    callbacks = agent.after_agent_callback
    assert callbacks[0] is existing
    assert len(callbacks) == 2
