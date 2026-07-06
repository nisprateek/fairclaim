"""Deterministic root agent for the case flow.

The root is a `BaseAgent` because routing is state-machine work, not model
judgment: finish intake, stage the case facts, then run T&C analysis,
remedies, and email drafting from the first missing output onward.
"""

from collections.abc import AsyncGenerator

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.adk.utils.context_utils import Aclosing

from fairclaim.backend.agents.email_agent import email_agent
from fairclaim.backend.agents.intake import apply_business_buyer_scope_gate, intake_agent
from fairclaim.backend.agents.remedies import remedies_agent
from fairclaim.backend.agents.tc_analysis import tc_analysis_agent
from fairclaim.backend.mcp_server.server import DISCLAIMER
from fairclaim.backend.schemas import TcAnalysisResult
from fairclaim.backend.security.injection import wrap_untrusted

# Persisted when the user has no terms, so downstream agents can still run.
NO_TERMS_STUB = TcAnalysisResult(
    clauses=[],
    overall_confidence="low",
    injection_flagged=False,
    disclaimer=DISCLAIMER,
).model_dump()


class OrchestratorAgent(BaseAgent):
    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        intake_step, tc_step, remedies_step, email_step = self.sub_agents
        state = ctx.session.state

        turn = state.get("intake_turn") or {}
        if not turn.get("is_complete"):
            async for event in self._run(intake_step, ctx):
                yield event
            turn = state.get("intake_turn") or {}

        fields = turn.get("collected_fields") or {}
        if turn.get("is_complete") and fields.get("is_individual") is False:
            yield Event(
                author=self.name,
                actions=EventActions(
                    state_delta={"intake_turn": apply_business_buyer_scope_gate(dict(turn))}
                ),
            )
            return

        if not turn.get("is_complete") or "email_drafts" in state:
            return

        fields = turn["collected_fields"]
        # Trust the explicit UI opt-out even if the model left terms_source
        # stale. The normalized field is persisted for the frontend.
        normalize_terms_source = (
            state.get("terms_opted_out") and fields.get("terms_source") != "none"
        )
        if normalize_terms_source:
            fields["terms_source"] = "none"
        terms_skipped = fields.get("terms_source") == "none"
        terms_clean = state.get("terms_clean")
        if not terms_skipped and not terms_clean:
            # The frontend will keep the terms card visible and retry with
            # terms_clean or terms_opted_out in the next stateDelta.
            return

        delta: dict = {"temp:case_fields": fields}
        if normalize_terms_source:
            delta["intake_turn"] = turn
        if terms_skipped:
            delta["tc_analysis_result"] = NO_TERMS_STUB
        else:
            wrapped, flags = wrap_untrusted(terms_clean)
            delta["temp:terms_wrapped"] = wrapped
            delta["temp:injection_flags"] = flags
        yield Event(author=self.name, actions=EventActions(state_delta=delta))

        if not terms_skipped and "tc_analysis_result" not in state:
            async for event in self._run(tc_step, ctx):
                yield event
        if "remedy_result" not in state:
            async for event in self._run(remedies_step, ctx):
                yield event
        # Email instructions template {remedy_result}; skip if the remedies
        # model produced invalid output and let the next turn retry remedies.
        if "remedy_result" in state:
            async for event in self._run(email_step, ctx):
                yield event

    @staticmethod
    async def _run(step: BaseAgent, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        async with Aclosing(step.run_async(ctx)) as agen:
            async for event in agen:
                yield event


orchestrator_agent = OrchestratorAgent(
    name="orchestrator_agent",
    description=(
        "Routes a consumer-rights case from intake through to a drafted "
        "complaint email: intake, T&C analysis when terms exist, remedies, "
        "then email drafting."
    ),
    sub_agents=[intake_agent, tc_analysis_agent, remedies_agent, email_agent],
)
