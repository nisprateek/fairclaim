from datetime import date, timedelta
from types import SimpleNamespace

from fairclaim.backend.agents.remedies import _ground_remedy_result_in_tool_truth, _hydrate_remedy_tool_args


def _tool(name: str = "lookup_remedy_tier") -> SimpleNamespace:
    return SimpleNamespace(name=name)


def _ctx(fields: dict) -> SimpleNamespace:
    return SimpleNamespace(state={"temp:case_fields": fields})


def test_remedy_tool_args_are_hydrated_from_case_fields_when_omitted():
    args = {"purchase_or_delivery_date": "2024-05-31"}
    fields = {
        "purchase_or_delivery_date": "2024-05-31",
        "has_repair_or_replacement_been_attempted": False,
        "has_proof_of_purchase": False,
        "is_motor_vehicle": False,
    }

    _hydrate_remedy_tool_args(_tool(), args, _ctx(fields))

    assert args == {
        "purchase_or_delivery_date": "2024-05-31",
        "repair_or_replacement_attempted": False,
        "has_proof_of_purchase": False,
        "is_motor_vehicle": False,
    }


def test_remedy_tool_args_keep_explicit_model_values():
    args = {
        "purchase_or_delivery_date": "2024-05-31",
        "repair_or_replacement_attempted": True,
        "has_proof_of_purchase": True,
        "is_motor_vehicle": True,
    }
    fields = {
        "purchase_or_delivery_date": "2024-05-31",
        "has_repair_or_replacement_been_attempted": False,
        "has_proof_of_purchase": False,
        "is_motor_vehicle": False,
    }

    _hydrate_remedy_tool_args(_tool(), args, _ctx(fields))

    assert args["repair_or_replacement_attempted"] is True
    assert args["has_proof_of_purchase"] is True
    assert args["is_motor_vehicle"] is True


def test_remedy_tool_args_ignore_other_tools():
    args = {}

    _hydrate_remedy_tool_args(
        _tool("get_disclaimer"),
        args,
        _ctx({"has_proof_of_purchase": False}),
    )

    assert args == {}


def test_grounding_copies_tool_truth_but_leaves_model_prose_untouched():
    """The callback grounds STRUCTURED fields from the deterministic tool
    (claim_strength, practical_barriers, tier, burden) but must not rewrite the
    model's prose — surfacing the obstacle in simple_explanation is the model's
    job (steered by the skill/instruction and checked in evals), not a stapled
    template."""
    delivery = (date.today() - timedelta(days=800)).isoformat()
    original_simple = (
        "Because you purchased the laptop over 30 days ago, you can ask "
        "TechBarn to repair or replace it free of charge."
    )
    original_legal = "You are entitled to request repair or replacement under s.23."
    state = {
        "temp:case_fields": {
            "purchase_or_delivery_date": delivery,
            "product": "laptop",
            "seller_name": "TechBarn",
            "desired_outcome": "refund",
            "has_repair_or_replacement_been_attempted": False,
            "has_proof_of_purchase": False,
        },
        "remedy_result": {
            "applicable_tier": "TIER_1",
            "primary_remedy": "repair",
            "statutory_basis": ["s.23"],
            "simple_explanation": original_simple,
            "legal_explanation": original_legal,
            "burden_of_proof": "consumer",
            "claim_strength": "moderate",
            "practical_barriers": [
                "More than six months have passed since delivery.",
            ],
            "alternatives": ["replacement"],
            "disclaimer": "General information only.",
        },
    }

    _ground_remedy_result_in_tool_truth(SimpleNamespace(state=state))
    result = state["remedy_result"]
    barriers = " ".join(result["practical_barriers"]).lower()

    # Structured tool-truth is grounded deterministically (the model can't
    # over-present a no-proof, post-six-month case).
    assert result["claim_strength"] == "weak"
    assert "proof of purchase" in barriers
    assert "six months" in barriers
    # The model's own explanations are left exactly as written — no prose surgery.
    assert result["simple_explanation"] == original_simple
    assert result["legal_explanation"] == original_legal
