"""Remedies agent — applies the CRA 2015 tiered remedy logic (ss.19-24) to
the user's facts, reconciled against their desired outcome.
"""

from google.adk.agents import LlmAgent
from google.genai.types import ThinkingLevel

from fairclaim.backend.llm_config import FAST_MODEL, thinking
from fairclaim.backend.mcp_client import CRA_TOOLSET
from fairclaim.backend.mcp_server.server import lookup_remedy_tier
from fairclaim.backend.schemas import RemedyResult
from fairclaim.backend.security.guardrails import make_citation_guard
from fairclaim.backend.skills.loader import load_skill

_REMEDY_TOOL_NAME = "lookup_remedy_tier"
_citation_guard = make_citation_guard("remedy_result")


def _hydrate_remedy_tool_args(tool, args: dict, tool_context) -> None:
    """Force deterministic case facts into the tier tool call.

    The model is instructed to pass these values, but `has_proof_of_purchase`
    is an optional MCP argument for compatibility. If the model omits it, a
    weak no-proof case can be over-presented. Mutating `args` here lets ADK
    call the tool normally with the complete intake facts.
    """
    if getattr(tool, "name", "") != _REMEDY_TOOL_NAME:
        return None

    fields = tool_context.state.get("temp:case_fields") or {}
    mappings = {
        "purchase_or_delivery_date": "purchase_or_delivery_date",
        "has_repair_or_replacement_been_attempted": "repair_or_replacement_attempted",
        "has_proof_of_purchase": "has_proof_of_purchase",
        "is_motor_vehicle": "is_motor_vehicle",
    }
    for field_key, arg_key in mappings.items():
        if arg_key not in args or args[arg_key] is None:
            value = fields.get(field_key)
            if value is not None:
                args[arg_key] = value
    return None


def _bool_field(fields: dict, key: str, default: bool = False) -> bool:
    value = fields.get(key)
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower().startswith("yes")


def _ground_remedy_result_in_tool_truth(callback_context) -> None:
    """Copy deterministic tool truth into the model's public RemedyResult.

    Grounds the STRUCTURED fields only — tier, burden, claim_strength,
    practical_barriers, available remedies, statutory basis — so provability
    never depends on whether the model remembered to copy every barrier. The
    prose (`simple_explanation`, `legal_explanation`) is left exactly as the
    model wrote it: the model has the tool's claim_strength and barriers during
    generation and is instructed to lead with the obstacle, so we no longer
    overwrite its explanation with a templated one (that read as boilerplate and
    could drift from the model's own wording).
    """

    result = callback_context.state.get("remedy_result")
    fields = callback_context.state.get("temp:case_fields") or {}
    if not result or not fields.get("purchase_or_delivery_date"):
        return None

    truth = lookup_remedy_tier(
        fields["purchase_or_delivery_date"],
        repair_or_replacement_attempted=_bool_field(
            fields, "has_repair_or_replacement_been_attempted"
        ),
        is_motor_vehicle=_bool_field(fields, "is_motor_vehicle"),
        has_proof_of_purchase=fields.get("has_proof_of_purchase"),
    )

    result["applicable_tier"] = truth["applicable_tier"]
    result["burden_of_proof"] = truth["burden_of_proof"]
    result["claim_strength"] = truth["claim_strength"]
    result["practical_barriers"] = truth["practical_barriers"]
    result["statutory_basis"] = list(
        dict.fromkeys((result.get("statutory_basis") or []) + truth["statutory_basis"])
    )

    if result.get("primary_remedy") not in truth["available_remedies"]:
        result["primary_remedy"] = truth["available_remedies"][0]
    result["alternatives"] = [
        remedy
        for remedy in result.get("alternatives", [])
        if remedy in truth["available_remedies"] and remedy != result.get("primary_remedy")
    ]
    if not result["alternatives"]:
        result["alternatives"] = [
            remedy
            for remedy in truth["available_remedies"]
            if remedy != result.get("primary_remedy")
        ]

    callback_context.state["remedy_result"] = result
    return None


def _ground_and_guard_remedy_result(callback_context):
    _ground_remedy_result_in_tool_truth(callback_context)
    return _citation_guard(callback_context)


INSTRUCTION = f"""
You are the remedies agent for a UK consumer-rights tool (Consumer Rights Act
2015, goods only, individual consumers only).

Follow this skill exactly:

---
{load_skill("cra_remedies")}
---

The consumer's case facts (as a Python dict — read purchase_or_delivery_date,
has_repair_or_replacement_been_attempted, desired_outcome, and
has_proof_of_purchase from it):

{{temp:case_fields}}

Call `lookup_remedy_tier(purchase_or_delivery_date,
repair_or_replacement_attempted, has_proof_of_purchase=...)` to get the
deterministic tier, available remedies, and the claim-strength assessment —
never estimate the 30-day or 6-month boundaries, nor judge how strong the
claim is, yourself. Then reconcile with desired_outcome per the skill to
choose `primary_remedy`, carry the tool's `claim_strength` and
`practical_barriers` through, and call `get_disclaimer` to attach the
disclaimer field.

When `claim_strength` is `weak` or `moderate`, or `practical_barriers` is
non-empty, `simple_explanation` MUST lead with the biggest obstacle in plain
words — no proof of purchase, or the post-six-month burden to show the fault
was there at delivery — before naming the remedy. Never present the remedy as a
formality when the tool flags a barrier. When `claim_strength` is `strong` with
no barriers, do not manufacture doubt.
"""

remedies_agent = LlmAgent(
    name="remedies_agent",
    model=FAST_MODEL,
    description="Applies the CRA 2015 tiered remedy logic to the consumer's facts.",
    instruction=INSTRUCTION,
    # This agent's job is fully defined by {temp:case_fields} above, set
    # fresh by the orchestrator right before this runs — it must not also
    # see the unrelated intake Q&A that precedes it in the shared session.
    include_contents="none",
    tools=[CRA_TOOLSET],
    # The tier is computed by the tool; the model reconciles it with the
    # user's desired outcome and writes the explanation.
    generate_content_config=thinking(ThinkingLevel.MEDIUM),
    before_tool_callback=_hydrate_remedy_tool_args,
    after_agent_callback=_ground_and_guard_remedy_result,
    output_schema=RemedyResult,
    output_key="remedy_result",
)
