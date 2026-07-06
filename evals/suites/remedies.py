"""Remedies reconciliation eval: does the model pick a legally-available
primary_remedy that honours the user's desired_outcome where the Act allows
it, and never grants something the tier forbids? Tool-truth (tier, available
set, burden) is derived from lookup_remedy_tier itself. See EVALS.md §3.3.
"""

from __future__ import annotations

from datetime import date, timedelta

from fairclaim.backend.mcp_server.server import STATUTORY_STANDARDS, lookup_remedy_tier
from evals.harness import contains, load_dataset, norm, run_staged


def _iso_days_ago(days: int) -> str:
    return (date.today() - timedelta(days=days)).isoformat()


def _simple_surfaces_obstacle(simple, barriers: list[str]) -> bool:
    """A weak/barriered claim's plain-English summary should name the obstacle,
    not read as a formality. The remedies agent used to have this stapled on by
    a template; now the model writes it, so we check the concept is present
    against whichever barrier the tool returned (see _assess_claim_strength in
    backend/mcp_server/server.py)."""
    text = norm(simple)
    btext = " ".join(barriers).lower()
    ok = True
    if "proof of purchase" in btext:
        ok = ok and any(k in text for k in ("proof", "prove", "bought it", "buy it"))
    if "six months" in btext:
        ok = ok and any(
            k in text
            for k in (
                "six month", "prove", "proof", "show the fault", "at the start",
                "from the start", "at delivery", "evidence", "burden", "uphill",
            )
        )
    if "six years" in btext:
        ok = ok and any(k in text for k in ("six years", "out of time", "time limit", "too long"))
    return ok


async def run(reps: int = 1, use_judge: bool = True) -> dict:
    from fairclaim.backend.agents.remedies import remedies_agent

    dataset = load_dataset("remedy_cases.json")
    base = dataset["base_fields"]
    cases = []

    for rep in range(reps):
        for spec in dataset["cases"]:
            delivery = _iso_days_ago(spec["days_ago"])
            # Tool-truth, computed the same way the agent's tool will.
            truth = lookup_remedy_tier(
                delivery,
                repair_or_replacement_attempted=spec["attempted"],
                is_motor_vehicle=spec["motor"],
                has_proof_of_purchase=spec.get("proof", base.get("has_proof_of_purchase")),
            )
            fields = {
                **base,
                "purchase_or_delivery_date": delivery,
                "desired_outcome": spec["desired"],
                "has_repair_or_replacement_been_attempted": spec["attempted"],
                "is_motor_vehicle": spec["motor"],
                "has_proof_of_purchase": spec.get("proof", base.get("has_proof_of_purchase")),
            }
            state = await run_staged(remedies_agent, {"temp:case_fields": fields})
            result = state.get("remedy_result") or {}

            primary = result.get("primary_remedy")
            alternatives = result.get("alternatives") or []
            basis = result.get("statutory_basis") or []
            available = set(truth["available_remedies"])

            # Citation integrity is "every cited section exists in the curated
            # KB", NOT "cited exactly this tool call's list": the agent
            # legitimately also cites the breach section (s.9) and the
            # burden-of-proof section (s.19), which lookup_remedy_tier doesn't
            # enumerate. The tool's own remedy sections should still appear.
            case = {
                "id": f"{spec['id']}#r{rep}",
                "expected_tier": truth["applicable_tier"],
                "got_tier": result.get("applicable_tier"),
                "tier_ok": result.get("applicable_tier") == truth["applicable_tier"],
                "primary": primary,
                "basis": basis,
                "primary_ok": primary in spec["primary_any"],
                "primary_forbidden": primary in spec.get("primary_never", []),
                "alts_within_available": all(a in available for a in alternatives),
                "basis_all_curated": all(s in STATUTORY_STANDARDS for s in basis),
                "basis_includes_tier_section": bool(set(basis) & set(truth["statutory_basis"])),
                "burden_ok": result.get("burden_of_proof") == truth["burden_of_proof"],
                "claim_strength_ok": result.get("claim_strength") == truth["claim_strength"],
                "barriers_ok": result.get("practical_barriers") == truth["practical_barriers"],
                "disclaimer_present": bool(result.get("disclaimer")),
                # When the tool flags a barrier, the model — not a template — must
                # surface it in the plain-English summary.
                "has_barriers": bool(truth["practical_barriers"]),
                "simple_grounds_ok": _simple_surfaces_obstacle(
                    result.get("simple_explanation"), truth["practical_barriers"]
                ),
            }
            if spec.get("legal_must_mention"):
                case["notes_ok"] = contains(
                    result.get("legal_explanation"), spec["legal_must_mention"]
                )
            if spec.get("expect_claim_strength"):
                case["expected_claim_strength_ok"] = (
                    result.get("claim_strength") == spec["expect_claim_strength"]
                )
            if spec.get("barrier_must_mention"):
                case["barrier_must_mention_ok"] = contains(
                    " ".join(result.get("practical_barriers") or []),
                    spec["barrier_must_mention"],
                )
            cases.append(case)

    n = len(cases)
    notes_cases = [c for c in cases if "notes_ok" in c]
    barrier_cases = [c for c in cases if c["has_barriers"]]
    metrics = {
        "tier_accuracy": round(sum(c["tier_ok"] for c in cases) / n, 3),
        "primary_accuracy": round(sum(c["primary_ok"] for c in cases) / n, 3),
        "forbidden_remedy_granted": sum(c["primary_forbidden"] for c in cases),
        "alternatives_valid_rate": round(sum(c["alts_within_available"] for c in cases) / n, 3),
        "basis_curated_rate": round(sum(c["basis_all_curated"] for c in cases) / n, 3),
        "basis_includes_tier_section_rate": round(sum(c["basis_includes_tier_section"] for c in cases) / n, 3),
        "burden_accuracy": round(sum(c["burden_ok"] for c in cases) / n, 3),
        "claim_strength_accuracy": round(sum(c["claim_strength_ok"] for c in cases) / n, 3),
        "barriers_accuracy": round(sum(c["barriers_ok"] for c in cases) / n, 3),
        "disclaimer_rate": round(sum(c["disclaimer_present"] for c in cases) / n, 3),
        "motor_note_rate": round(sum(c["notes_ok"] for c in notes_cases) / len(notes_cases), 3)
        if notes_cases
        else None,
        "simple_grounds_obstacle_rate": round(
            sum(c["simple_grounds_ok"] for c in barrier_cases) / len(barrier_cases), 3
        )
        if barrier_cases
        else None,
    }
    gates = [
        {
            "name": "never grant a tier-forbidden remedy",
            "ok": metrics["forbidden_remedy_granted"] == 0,
            "detail": f"{metrics['forbidden_remedy_granted']} forbidden grants",
        },
        {
            "name": "primary_remedy accuracy >= 0.9",
            "ok": metrics["primary_accuracy"] >= 0.9,
            "detail": f"got {metrics['primary_accuracy']}",
        },
        {
            "name": "every cited section is in the curated KB",
            "ok": metrics["basis_curated_rate"] == 1.0,
            "detail": f"rate {metrics['basis_curated_rate']}",
        },
        {
            "name": "cites the tier's remedy section",
            "ok": metrics["basis_includes_tier_section_rate"] >= 0.9,
            "detail": f"rate {metrics['basis_includes_tier_section_rate']}",
        },
        {
            "name": "claim-strength barriers match deterministic tool",
            "ok": metrics["claim_strength_accuracy"] == 1.0 and metrics["barriers_accuracy"] == 1.0,
            "detail": (
                f"strength {metrics['claim_strength_accuracy']} barriers "
                f"{metrics['barriers_accuracy']}"
            ),
        },
        {
            "name": "weak/barriered claims surface the obstacle in plain English",
            "ok": metrics["simple_grounds_obstacle_rate"] is None
            or metrics["simple_grounds_obstacle_rate"] >= 0.9,
            "detail": f"rate {metrics['simple_grounds_obstacle_rate']}",
        },
    ]
    return {"suite": "remedies", "cases": cases, "metrics": metrics, "gates": gates}
