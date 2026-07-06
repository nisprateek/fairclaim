"""Cross-module contract drift tests: the enums, field lists, and generated
types that multiple modules (or the frontend) must agree on. Each of these
would fail silently at runtime if edited in one place only — pin them here
so drift fails CI instead.
"""

import re
import typing

from fairclaim.backend.agents.intake import (
    CONFIRM_PROMPTS,
    FALLBACK_COMPONENTS,
    NO_CONFIRM_FIELDS,
    OUTCOME_OPTIONS,
)
from fairclaim.backend.agents.orchestrator import NO_TERMS_STUB
from fairclaim.backend.mcp_server.server import lookup_remedy_tier
from fairclaim.backend.schemas import (
    CaseFields,
    EmailDraft,
    RemedyResult,
    SessionStateContract,
    TcAnalysisResult,
)
from fairclaim.backend.scripts.gen_frontend_types import MODELS, OUT_PATH, _render_model
from fairclaim.backend.skills.loader import SKILLS_DIR, load_skill, split_frontmatter


def _literal_args(model, field: str) -> set:
    annotation = model.model_fields[field].annotation
    # Unwrap Optional[Literal[...]] if needed.
    if typing.get_origin(annotation) in (typing.Union, __import__("types").UnionType):
        annotation = next(a for a in typing.get_args(annotation) if a is not type(None))
    return set(typing.get_args(annotation))


# ---------------------------------------------------------------------------
# Intake fallback sweep <-> CaseFields
# ---------------------------------------------------------------------------

def test_fallback_sweep_covers_every_case_field_exactly_once():
    sweep_fields = [field for field, _ in FALLBACK_COMPONENTS]
    assert len(sweep_fields) == len(set(sweep_fields)), "duplicate field in sweep"
    # Every case field must be reachable by the deterministic sweep or intake
    # can dead-end on it.
    assert set(sweep_fields) == set(CaseFields.model_fields)


def test_confirm_prompts_cover_every_confirmable_field():
    confirmable = {field for field, _ in FALLBACK_COMPONENTS} - NO_CONFIRM_FIELDS
    assert set(CONFIRM_PROMPTS) == confirmable


def test_outcome_options_match_case_fields_literal():
    assert OUTCOME_OPTIONS == _literal_args(CaseFields, "desired_outcome")


def test_desired_outcome_fallback_options_are_the_literal_values():
    component = dict(FALLBACK_COMPONENTS)["desired_outcome"]
    assert set(component["options"]) == _literal_args(CaseFields, "desired_outcome")


# ---------------------------------------------------------------------------
# Remedy enums: schema <-> deterministic tool <-> email agent
# ---------------------------------------------------------------------------

def test_email_remedy_enum_matches_remedy_result_enum():
    assert _literal_args(EmailDraft, "remedy") == _literal_args(RemedyResult, "primary_remedy")


def test_email_body_fields_exist_on_the_schema():
    # The disclaimer guard (and the dashboard's tone slider) walk these keys —
    # a rename in EmailDraft must show up here, not as a silently skipped body.
    from fairclaim.backend.agents.email_agent import BODY_FIELDS

    assert set(BODY_FIELDS) <= set(EmailDraft.model_fields)


def test_remedy_tool_output_fits_the_remedy_result_schema():
    tiers = _literal_args(RemedyResult, "applicable_tier")
    remedies = _literal_args(RemedyResult, "primary_remedy")
    for kwargs in (
        {"evaluation_date": "2026-07-01"},  # TIER_0
        {"evaluation_date": "2026-09-01"},  # TIER_1
        {"repair_or_replacement_attempted": True, "evaluation_date": "2026-07-01"},  # TIER_2
    ):
        result = lookup_remedy_tier("2026-06-25", **kwargs)
        assert result["applicable_tier"] in tiers
        assert set(result["available_remedies"]) <= remedies
        assert result["burden_of_proof"] in _literal_args(RemedyResult, "burden_of_proof")
        assert result["claim_strength"] in _literal_args(RemedyResult, "claim_strength")
        assert isinstance(result["practical_barriers"], list)


def test_no_terms_stub_validates_against_the_schema():
    parsed = TcAnalysisResult.model_validate(NO_TERMS_STUB)
    assert parsed.clauses == []
    assert parsed.injection_flagged is False


# ---------------------------------------------------------------------------
# Frontend wire contract
# ---------------------------------------------------------------------------

def test_session_state_contract_keys_are_stable():
    # The frontend reads exactly these keys — renaming/removing one is a
    # breaking wire change and must be deliberate.
    assert set(SessionStateContract.model_fields) == {
        "intake_turn",
        "tc_analysis_result",
        "remedy_result",
        "email_drafts",
    }


def test_every_contract_model_renders_to_typescript():
    # Catches an annotation gen_frontend_types can't map (e.g. a dict field)
    # at test time instead of at regeneration time.
    for model in MODELS:
        rendered = _render_model(model)
        assert rendered.startswith(f"export interface {model.__name__} {{")


def test_generated_frontend_types_are_not_stale():
    # The checked-in schemas.ts must match what gen_frontend_types would emit
    # today; if this fails, run: uv run python -m fairclaim.backend.scripts.gen_frontend_types
    generated_body = "\n\n".join(_render_model(model) for model in MODELS)
    checked_in = OUT_PATH.read_text()
    assert generated_body in checked_in


# ---------------------------------------------------------------------------
# Skills: agent instructions are built from these files (Agent Skills format,
# one dir per skill anchored by SKILL.md); an empty or missing skill silently
# degrades the agent's behaviour, and a malformed one must fail CI, not prod.
# ---------------------------------------------------------------------------

SKILL_NAMES = ("cra_intake_checklist", "cra_unfair_terms", "cra_remedies")

# Mirrors ADK's inject_session_state: a {name} pattern in an instruction is
# resolved against session state, and a valid-looking name that isn't a state
# key raises KeyError at runtime.
_ADK_PLACEHOLDER = re.compile(r"{+[^{}]*}+")


def _is_adk_state_placeholder(inner: str) -> bool:
    name = inner.strip().removesuffix("?")
    if name.startswith("artifact."):
        return True
    parts = name.split(":")
    if len(parts) == 1:
        return parts[0].isidentifier()
    if len(parts) == 2:
        return parts[0] in ("app", "user", "temp") and parts[1].isidentifier()
    return False


def test_all_agent_skills_load_and_are_substantial():
    for name in SKILL_NAMES:
        content = load_skill(name)
        assert len(content) > 200, name


def test_skill_frontmatter_lints():
    # Agent Skills format: kebab-case name matching the snake_case dir, and a
    # description (the routing layer, <=1024 chars) that states what the
    # skill does, when to use it, and when NOT to use it.
    for name in SKILL_NAMES:
        text = (SKILLS_DIR / name / "SKILL.md").read_text(encoding="utf-8")
        frontmatter, _ = split_frontmatter(text)
        assert frontmatter, name
        lines = frontmatter.splitlines()
        assert lines[0] == f"name: {name.replace('_', '-')}", name
        assert "description: |" in lines, name
        desc_lines = []
        for line in lines[lines.index("description: |") + 1 :]:
            if not line.startswith("  "):
                break
            desc_lines.append(line.strip())
        description = " ".join(desc_lines)
        assert 0 < len(description) <= 1024, name
        assert "Use when" in description, name
        assert "Do NOT use" in description, name


def test_skill_bodies_follow_the_standard_sections():
    for name in SKILL_NAMES:
        body = load_skill(name)
        for heading in (
            "## When to use",
            "## When NOT to use",
            "## Workflow",
            "## Output format",
            "## Anti-patterns to avoid",
        ):
            assert heading in body, (name, heading)


def test_skill_bodies_contain_no_adk_state_placeholders():
    # Skill bodies are spliced verbatim into LlmAgent instructions, which ADK
    # post-processes for {state_key} placeholders. A lawyer adding e.g.
    # "{seller_name}" as an example placeholder in the markdown would crash
    # the agent's turn with a KeyError — catch it here instead. Non-name
    # brace content (like the JSON schema block) is left alone by ADK.
    for name in SKILL_NAMES:
        for match in _ADK_PLACEHOLDER.finditer(load_skill(name)):
            inner = match.group().lstrip("{").rstrip("}")
            assert not _is_adk_state_placeholder(inner), (name, match.group())
