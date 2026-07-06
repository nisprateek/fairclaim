"""End-to-end eval: scripted personas driven through the real orchestrator.

The checklist scores the final SessionStateContract after intake, optional
T&C analysis, remedies, and email drafting.
"""

from __future__ import annotations

from datetime import date, timedelta

from evals.harness import contains, load_dataset, run_conversation


def _tier_for(days_ago: int, attempted: bool) -> str:
    from fairclaim.backend.mcp_server.server import lookup_remedy_tier

    delivery = (date.today() - timedelta(days=days_ago)).isoformat()
    return lookup_remedy_tier(delivery, repair_or_replacement_attempted=attempted)["applicable_tier"]


def _materialize(persona: dict) -> tuple[dict, str]:
    delivery = (date.today() - timedelta(days=persona["days_ago"])).isoformat()
    persona = dict(persona)
    persona["story"] = persona["story"].replace("{date}", delivery)
    persona["answers"] = {k: str(v).replace("{date}", delivery) for k, v in persona["answers"].items()}
    return persona, delivery


def _done(state: dict) -> bool:
    # Run the whole pipeline to completion, not just intake.
    if "email_drafts" in state:
        return True
    turn = state.get("intake_turn") or {}
    return bool(turn.get("scope_gate_failure"))


async def run(reps: int = 1, use_judge: bool = True) -> dict:
    dataset = load_dataset("e2e_personas.json")
    cases = []

    for rep in range(reps):
        for raw in dataset["personas"]:
            # One persona's crash must not zero the whole suite. Retry once —
            # the usual cause is a rare invalid-model-output blip in one
            # specialist that a fresh roll clears — then record a hard failure.
            try:
                cases.append(await _score_persona(raw, rep))
            except Exception as first:  # noqa: BLE001
                try:
                    cases.append(await _score_persona(raw, rep))
                except Exception as second:  # noqa: BLE001
                    cases.append(
                        {
                            "id": f"{raw['id']}#r{rep}",
                            "checks": {"pipeline_ran": False},
                            "pass_fraction": 0.0,
                            "all_pass": False,
                            "error": f"{type(second).__name__}: {second}"[:300],
                            "turns": None,
                            "tier": None,
                            "primary_remedy": None,
                        }
                    )

    n = len(cases)
    all_checks = [(k, v) for c in cases for k, v in c["checks"].items()]
    metrics = {
        "persona_full_pass_rate": round(sum(c["all_pass"] for c in cases) / n, 3),
        "check_pass_rate": round(sum(v for _, v in all_checks) / len(all_checks), 3),
        "pipeline_completion_rate": round(sum(c["checks"].get("intake_completes", False) for c in cases) / n, 3),
        "errored_personas": sum(1 for c in cases if "error" in c),
    }
    gates = [
        {
            "name": "every persona reaches drafted emails",
            "ok": metrics["pipeline_completion_rate"] == 1.0,
            "detail": f"rate {metrics['pipeline_completion_rate']}",
        },
        {
            "name": "checklist pass rate >= 0.9",
            "ok": metrics["check_pass_rate"] >= 0.9,
            "detail": f"rate {metrics['check_pass_rate']}",
        },
        {
            "name": "no personas errored out",
            "ok": metrics["errored_personas"] == 0,
            "detail": f"{metrics['errored_personas']} errored",
        },
    ]
    return {"suite": "e2e", "cases": cases, "metrics": metrics, "gates": gates}


async def _score_persona(raw: dict, rep: int) -> dict:
    from fairclaim.backend.agents.orchestrator import NO_TERMS_STUB, orchestrator_agent

    persona, _delivery = _materialize(raw)
    checklist = persona["checklist"]
    attempted = persona["answers"].get("has_repair_or_replacement_been_attempted", "No").lower().startswith("yes")

    result = await run_conversation(
        orchestrator_agent,
        persona,
        initial_state=persona.get("initial_state"),
        max_turns=40,
        done=_done,
    )
    state = result["state"]
    tc = state.get("tc_analysis_result") or {}
    remedy = state.get("remedy_result") or {}
    emails = state.get("email_drafts") or []
    checks = {}

    checks["intake_completes"] = "email_drafts" in state
    if checklist.get("injection_flagged"):
        checks["injection_flagged"] = bool(tc.get("injection_flagged"))
    if "min_blacklisted_clauses" in checklist:
        blacklisted = sum(1 for c in tc.get("clauses") or [] if c.get("label") == "BLACKLISTED")
        checks["min_blacklisted_clauses"] = blacklisted >= checklist["min_blacklisted_clauses"]
    if checklist.get("tc_analysis_is_no_terms_stub"):
        checks["tc_analysis_is_no_terms_stub"] = tc.get("clauses") == [] and tc == NO_TERMS_STUB
    if checklist.get("expected_tier") == "from_days_ago":
        checks["expected_tier"] = remedy.get("applicable_tier") == _tier_for(persona["days_ago"], attempted)
    if "primary_remedy_any" in checklist:
        checks["primary_remedy"] = remedy.get("primary_remedy") in checklist["primary_remedy_any"]
    if checklist.get("email_per_remedy"):
        wanted = {remedy.get("primary_remedy"), *(remedy.get("alternatives") or [])} - {None}
        checks["email_per_remedy"] = bool(emails) and {e.get("remedy") for e in emails} == wanted
    if checklist.get("disclaimer_on_outputs"):
        checks["disclaimer_on_outputs"] = (
            bool(tc.get("disclaimer"))
            and bool(remedy.get("disclaimer"))
            and all(
                contains(e.get(field), "consumer rights act 2015")
                for e in emails
                for field in ("firm_body", "formal_body")
            )
        )
    return {
        "id": f"{persona['id']}#r{rep}",
        "checks": checks,
        "pass_fraction": round(sum(checks.values()) / len(checks), 3),
        "all_pass": all(checks.values()),
        "turns": result["turns"],
        "tier": remedy.get("applicable_tier"),
        "primary_remedy": remedy.get("primary_remedy"),
    }
