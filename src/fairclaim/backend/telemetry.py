"""Eval-only LLM usage telemetry.

The live app intentionally exposes no admin dashboard. Evals attach these
callbacks to the agent tree so reports can include model calls, token usage,
and estimated cost.
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections import OrderedDict, deque
from typing import Any

from google.adk.agents import BaseAgent, LlmAgent

DEFAULT_PRICING: dict[str, dict[str, float]] = {
    "gemini-3.1-flash-lite": {"input": 0.25, "output": 1.50},
    "gemini-3.5-flash": {"input": 1.50, "output": 9.00},
}


def load_pricing() -> dict[str, dict[str, float]]:
    raw = os.environ.get("FAIRCLAIMAI_PRICING_JSON")
    if not raw:
        return dict(DEFAULT_PRICING)
    try:
        table = dict(DEFAULT_PRICING)
        table.update(json.loads(raw))
        return table
    except (json.JSONDecodeError, TypeError):
        return dict(DEFAULT_PRICING)


def estimate_cost_usd(model: str, prompt_tokens: int, output_tokens: int, pricing=None) -> float:
    """Estimate one model call from a per-million-token price table."""
    table = pricing if pricing is not None else load_pricing()
    rates = table.get(model)
    if rates is None:
        rates = next(
            (known_rates for known, known_rates in table.items() if model and model.startswith(known)),
            None,
        )
    if rates is None:
        return 0.0
    return (prompt_tokens * rates["input"] + output_tokens * rates["output"]) / 1_000_000


class TelemetryStore:
    def __init__(self, max_calls: int = 1000, max_traces: int = 100):
        self._lock = threading.Lock()
        self.started_at = time.time()
        self.pricing = load_pricing()
        self.model_calls: deque[dict] = deque(maxlen=max_calls)
        self.tool_calls: deque[dict] = deque(maxlen=max_calls)
        self.guardrail_events: deque[dict] = deque(maxlen=200)
        self.traces: OrderedDict[str, dict] = OrderedDict()
        self._max_traces = max_traces
        self._open: dict[tuple, list[float]] = {}

    def _trace(self, invocation_id: str, session_id: str | None) -> dict:
        trace = self.traces.get(invocation_id)
        if trace is None:
            trace = {
                "invocation_id": invocation_id,
                "session_id": session_id,
                "started": time.time(),
                "ended": None,
                "spans": [],
            }
            self.traces[invocation_id] = trace
            while len(self.traces) > self._max_traces:
                self.traces.popitem(last=False)
        return trace

    def begin_agent_span(self, invocation_id: str, session_id: str | None, agent: str) -> None:
        with self._lock:
            trace = self._trace(invocation_id, session_id)
            trace["spans"].append(
                {
                    "agent": agent,
                    "started": time.time(),
                    "ended": None,
                    "ms": None,
                    "model_calls": 0,
                    "tool_calls": 0,
                    "tokens": 0,
                    "cost_usd": 0.0,
                }
            )

    def end_agent_span(self, invocation_id: str, agent: str) -> None:
        with self._lock:
            trace = self.traces.get(invocation_id)
            if not trace:
                return
            now = time.time()
            for span in reversed(trace["spans"]):
                if span["agent"] == agent and span["ended"] is None:
                    span["ended"] = now
                    span["ms"] = round((now - span["started"]) * 1000, 1)
                    break
            trace["ended"] = now

    def _attach_to_span(
        self,
        invocation_id: str,
        agent: str,
        *,
        tokens: int = 0,
        cost: float = 0.0,
        model_calls: int = 0,
        tool_calls: int = 0,
    ) -> None:
        trace = self.traces.get(invocation_id)
        if not trace:
            return
        for span in reversed(trace["spans"]):
            if span["agent"] == agent:
                span["tokens"] += tokens
                span["cost_usd"] = round(span["cost_usd"] + cost, 8)
                span["model_calls"] += model_calls
                span["tool_calls"] += tool_calls
                return

    def model_call_started(self, invocation_id: str, agent: str) -> None:
        with self._lock:
            self._open.setdefault((invocation_id, agent, "model"), []).append(time.perf_counter())

    def model_call_finished(
        self,
        invocation_id: str,
        session_id: str | None,
        agent: str,
        model: str,
        usage: Any,
        error: str | None = None,
    ) -> None:
        with self._lock:
            starts = self._open.get((invocation_id, agent, "model"))
            duration_ms = round((time.perf_counter() - starts.pop()) * 1000, 1) if starts else None
            prompt = int(getattr(usage, "prompt_token_count", 0) or 0)
            candidates = int(getattr(usage, "candidates_token_count", 0) or 0)
            thoughts = int(getattr(usage, "thoughts_token_count", 0) or 0)
            total = int(getattr(usage, "total_token_count", 0) or (prompt + candidates + thoughts))
            cost = estimate_cost_usd(model, prompt, candidates + thoughts, self.pricing)
            self.model_calls.append(
                {
                    "ts": time.time(),
                    "invocation_id": invocation_id,
                    "session_id": session_id,
                    "agent": agent,
                    "model": model,
                    "ms": duration_ms,
                    "prompt_tokens": prompt,
                    "output_tokens": candidates,
                    "thoughts_tokens": thoughts,
                    "total_tokens": total,
                    "cost_usd": round(cost, 8),
                    "error": error,
                }
            )
            self._attach_to_span(invocation_id, agent, tokens=total, cost=cost, model_calls=1)

    def tool_call_started(self, invocation_id: str, agent: str, tool: str) -> None:
        with self._lock:
            self._open.setdefault((invocation_id, agent, "tool", tool), []).append(time.perf_counter())

    def tool_call_finished(self, invocation_id: str, agent: str, tool: str, args_preview: str) -> None:
        with self._lock:
            starts = self._open.get((invocation_id, agent, "tool", tool))
            duration_ms = round((time.perf_counter() - starts.pop()) * 1000, 1) if starts else None
            self.tool_calls.append(
                {
                    "ts": time.time(),
                    "invocation_id": invocation_id,
                    "agent": agent,
                    "tool": tool,
                    "ms": duration_ms,
                    "args": args_preview,
                }
            )
            self._attach_to_span(invocation_id, agent, tool_calls=1)

    def record_guardrail(self, invocation_id: str, agent: str, kind: str, detail: str) -> None:
        with self._lock:
            self.guardrail_events.append(
                {"ts": time.time(), "invocation_id": invocation_id, "agent": agent, "kind": kind, "detail": detail}
            )

    def snapshot(self) -> dict:
        with self._lock:
            model_calls = list(self.model_calls)
            tool_calls = list(self.tool_calls)
            guardrails = list(self.guardrail_events)
            traces = [dict(t) for t in self.traces.values()]

        agents: dict[str, dict] = {}
        models: dict[str, dict] = {}
        for call in model_calls:
            for key, table in ((call["agent"], agents), (call["model"], models)):
                bucket = table.setdefault(
                    key,
                    {
                        "model_calls": 0,
                        "errors": 0,
                        "prompt_tokens": 0,
                        "output_tokens": 0,
                        "thoughts_tokens": 0,
                        "total_tokens": 0,
                        "cost_usd": 0.0,
                    },
                )
                bucket["model_calls"] += 1
                bucket["prompt_tokens"] += call["prompt_tokens"]
                bucket["output_tokens"] += call["output_tokens"]
                bucket["thoughts_tokens"] += call["thoughts_tokens"]
                bucket["total_tokens"] += call["total_tokens"]
                bucket["cost_usd"] = round(bucket["cost_usd"] + call["cost_usd"], 8)
                if call["error"]:
                    bucket["errors"] += 1
        for call in tool_calls:
            agents.setdefault(call["agent"], {"model_calls": 0, "tool_calls": 0})
            agents[call["agent"]]["tool_calls"] = agents[call["agent"]].get("tool_calls", 0) + 1

        trace_summaries = []
        for trace in reversed(traces):
            duration = (trace["ended"] - trace["started"]) * 1000 if trace["ended"] else None
            trace_summaries.append(
                {
                    "invocation_id": trace["invocation_id"],
                    "session_id": trace["session_id"],
                    "started": trace["started"],
                    "ms": round(duration, 1) if duration is not None else None,
                    "agents": [s["agent"] for s in trace["spans"]],
                    "tokens": sum(s["tokens"] for s in trace["spans"]),
                    "cost_usd": round(sum(s["cost_usd"] for s in trace["spans"]), 8),
                }
            )

        return {
            "uptime_s": round(time.time() - self.started_at, 1),
            "totals": {
                "model_calls": len(model_calls),
                "model_errors": sum(1 for c in model_calls if c["error"]),
                "tool_calls": len(tool_calls),
                "prompt_tokens": sum(c["prompt_tokens"] for c in model_calls),
                "output_tokens": sum(c["output_tokens"] for c in model_calls),
                "thoughts_tokens": sum(c["thoughts_tokens"] for c in model_calls),
                "total_tokens": sum(c["total_tokens"] for c in model_calls),
                "est_cost_usd": round(sum(c["cost_usd"] for c in model_calls), 6),
                "guardrail_events": len(guardrails),
                "invocations": len(traces),
            },
            "agents": agents,
            "models": models,
            "traces": trace_summaries[:20],
            "guardrails": list(reversed(guardrails))[:50],
            "recent_model_calls": list(reversed(model_calls))[:50],
            "recent_tool_calls": list(reversed(tool_calls))[:50],
            "pricing_per_1m_tokens": self.pricing,
        }

_CITATION_STRIP_MARKER = "[Note: citation(s)"
_GUARDED_OUTPUTS = {
    "tc_analysis_agent": ("tc_analysis_result", "clauses"),
    "remedies_agent": ("remedy_result", None),
}
_instrumented_ids: set[int] = set()


def _walk(agent: BaseAgent):
    yield agent
    for sub in agent.sub_agents or []:
        yield from _walk(sub)


def _as_list(callback) -> list:
    if callback is None:
        return []
    return list(callback) if isinstance(callback, list) else [callback]


def _sniff_guardrails(store: TelemetryStore, agent_name: str, callback_context) -> None:
    spec = _GUARDED_OUTPUTS.get(agent_name)
    if not spec:
        return
    state_key, list_field = spec
    result = callback_context.state.get(state_key)
    if not result:
        return
    items = result.get(list_field, []) if list_field else [result]
    strips = sum(1 for item in items if _CITATION_STRIP_MARKER in (item.get("legal_explanation") or ""))
    if strips:
        store.record_guardrail(
            callback_context.invocation_id,
            agent_name,
            "citation_strip",
            f"{strips} uncurated citation note(s) in {state_key}",
        )
    if agent_name == "tc_analysis_agent":
        flags = callback_context.state.get("temp:injection_flags")
        if flags:
            store.record_guardrail(callback_context.invocation_id, agent_name, "injection_prescan", ", ".join(flags))


def _session_id(callback_context) -> str | None:
    session = getattr(callback_context, "session", None)
    return getattr(session, "id", None)


def _instrument_agent(agent: BaseAgent, store: TelemetryStore) -> None:
    name = agent.name

    def span_start(callback_context=None, **_):
        store.begin_agent_span(callback_context.invocation_id, _session_id(callback_context), name)
        return None

    def span_end(callback_context=None, **_):
        _sniff_guardrails(store, name, callback_context)
        store.end_agent_span(callback_context.invocation_id, name)
        return None

    agent.before_agent_callback = [span_start] + _as_list(agent.before_agent_callback)
    agent.after_agent_callback = _as_list(agent.after_agent_callback) + [span_end]

    if not isinstance(agent, LlmAgent):
        return
    declared_model = str(agent.model)

    def model_start(callback_context=None, llm_request=None, **_):
        store.model_call_started(callback_context.invocation_id, name)
        return None

    def model_end(callback_context=None, llm_response=None, **_):
        model = getattr(llm_response, "model_version", None) or declared_model
        error = getattr(llm_response, "error_message", None)
        store.model_call_finished(
            callback_context.invocation_id,
            _session_id(callback_context),
            name,
            model,
            getattr(llm_response, "usage_metadata", None),
            error=error,
        )
        return None

    def tool_start(tool=None, args=None, tool_context=None, **_):
        store.tool_call_started(tool_context.invocation_id, name, tool.name)
        return None

    def tool_end(tool=None, args=None, tool_context=None, tool_response=None, **_):
        preview = ", ".join(sorted((args or {}).keys()))[:120]
        store.tool_call_finished(tool_context.invocation_id, name, tool.name, preview)
        return None

    agent.before_model_callback = [model_start] + _as_list(agent.before_model_callback)
    agent.after_model_callback = _as_list(agent.after_model_callback) + [model_end]
    agent.before_tool_callback = [tool_start] + _as_list(agent.before_tool_callback)
    agent.after_tool_callback = _as_list(agent.after_tool_callback) + [tool_end]


def instrument_agent_tree(root: BaseAgent, store: TelemetryStore) -> None:
    """Attach telemetry callbacks once to every agent under `root`."""
    for agent in _walk(root):
        if id(agent) in _instrumented_ids:
            continue
        _instrumented_ids.add(id(agent))
        _instrument_agent(agent, store)
