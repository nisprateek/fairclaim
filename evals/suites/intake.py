"""Intake eval: multi-turn field-extraction accuracy, completion honesty,
turn efficiency, and scope-gate recall. Drives the real intake agent (with
its deterministic backstops) through scripted personas. See EVALS.md §3.1.
"""

from __future__ import annotations

from evals.harness import load_dataset, norm, run_conversation

_ANY_PROVIDED = {"pasted"}


def _field_ok(expected, got) -> bool:
    if isinstance(expected, dict) and "contains" in expected:
        return norm(expected["contains"]) in norm(got)
    if expected == "any_provided":
        return got in _ANY_PROVIDED
    return expected == got


async def run(reps: int = 1, use_judge: bool = True) -> dict:
    from fairclaim.backend.agents.orchestrator import intake_agent

    dataset = load_dataset("intake_personas.json")
    cases = []

    for rep in range(reps):
        for persona in dataset["personas"]:
            gold = persona["gold"]
            result = await run_conversation(
                intake_agent, persona, max_turns=gold.get("max_turns", 30) + 6
            )
            state = result["state"]
            turn = state.get("intake_turn") or {}

            if gold.get("expect_scope_gate"):
                explanation = turn.get("scope_gate_failure") or ""
                triggered = bool(explanation)
                mentions = gold.get("scope_gate_failure_mentions_any", [])
                explains = any(norm(m) in norm(explanation) for m in mentions) if mentions else triggered
                cases.append(
                    {
                        "id": f"{persona['id']}#r{rep}",
                        "kind": "scope_gate",
                        "gate_triggered": triggered,
                        "gate_not_completed": not turn.get("is_complete"),
                        "explanation_ok": triggered and explains,
                        "turns": result["turns"],
                    }
                )
                continue

            fields = turn.get("collected_fields") or {}
            field_rows = {
                name: {"expected": expected, "got": fields.get(name), "ok": _field_ok(expected, fields.get(name))}
                for name, expected in gold["fields"].items()
            }
            accuracy = sum(r["ok"] for r in field_rows.values()) / len(field_rows)
            within_turns = result["turns"] <= gold.get("max_turns", 30)
            cases.append(
                {
                    "id": f"{persona['id']}#r{rep}",
                    "kind": "collect",
                    "completed": bool(turn.get("is_complete")),
                    "completion_ok": bool(turn.get("is_complete")) == gold["expect_complete"],
                    "stalled": result["stalled"],
                    "field_accuracy": round(accuracy, 3),
                    "all_fields_ok": accuracy == 1.0,
                    "turns": result["turns"],
                    "within_turn_budget": within_turns,
                    "fields": field_rows,
                }
            )

    collect = [c for c in cases if c["kind"] == "collect"]
    gates_cases = [c for c in cases if c["kind"] == "scope_gate"]
    metrics = {}
    if collect:
        field_accs = [c["field_accuracy"] for c in collect]
        metrics.update(
            {
                "field_accuracy_mean": round(sum(field_accs) / len(field_accs), 3),
                "completion_accuracy": round(sum(c["completion_ok"] for c in collect) / len(collect), 3),
                "stall_rate": round(sum(c["stalled"] for c in collect) / len(collect), 3),
                "turn_budget_rate": round(sum(c["within_turn_budget"] for c in collect) / len(collect), 3),
            }
        )
    if gates_cases:
        metrics.update(
            {
                "scope_gate_recall": round(
                    sum(c["gate_triggered"] and c["gate_not_completed"] for c in gates_cases) / len(gates_cases), 3
                ),
                "scope_gate_explanation_rate": round(
                    sum(c["explanation_ok"] for c in gates_cases) / len(gates_cases), 3
                ),
            }
        )

    gates = []
    if collect:
        gates.append(
            {
                "name": "intake field accuracy >= 0.9",
                "ok": metrics["field_accuracy_mean"] >= 0.9,
                "detail": f"mean {metrics['field_accuracy_mean']}",
            }
        )
        gates.append(
            {"name": "no stalled interviews", "ok": metrics["stall_rate"] == 0.0, "detail": f"rate {metrics['stall_rate']}"}
        )
    if gates_cases:
        gates.append(
            {
                "name": "scope-gate recall == 1.0",
                "ok": metrics["scope_gate_recall"] == 1.0,
                "detail": f"recall {metrics['scope_gate_recall']}",
            }
        )
    return {"suite": "intake", "cases": cases, "metrics": metrics, "gates": gates}
