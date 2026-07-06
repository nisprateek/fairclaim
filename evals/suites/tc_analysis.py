"""T&C analysis eval: label accuracy per stratum, clause recall, citation
correctness, confidence-mapping accuracy, guardrail strip rate, and an
LLM-judged explanation-quality score. See EVALS.md §3.2.
"""

from __future__ import annotations

from fairclaim.backend.security.injection import wrap_untrusted
from evals.harness import contains, find_clause, load_dataset, run_staged
from evals.judge import judge

EXPLANATION_RUBRIC = """Each item is one clause from a UK seller's terms, the label a consumer-rights
tool assigned under the Consumer Rights Act 2015, and two explanations of the verdict. Grade the
EXPLANATIONS:
- simple_explanation is genuinely plain English: a layperson can follow it at a glance, with no
  section numbers or legal terms of art, and it does not contradict the legal reasoning.
- legal_explanation is grounded: the reasoning matches the cited/underlying statutory idea
  (statutory rights can't be excluded; fairness test for grey-list terms; burden-of-proof rules),
  with no invented facts.
- Grey-list ("POTENTIALLY_UNFAIR") verdicts acknowledge unfairness is ultimately a court's call.
- No legal advice beyond general information.
Score the set as a whole."""


async def run(reps: int = 1, use_judge: bool = True) -> dict:
    from fairclaim.backend.agents.tc_analysis import tc_analysis_agent

    dataset = load_dataset("tc_clauses.json")
    cases = []

    for rep in range(reps):
        for doc in dataset["docs"]:
            wrapped, flags = wrap_untrusted(doc["text"])
            state = await run_staged(
                tc_analysis_agent,
                {"temp:terms_wrapped": wrapped, "temp:injection_flags": flags},
                "Analyse the seller's terms and conditions.",
            )
            result = state.get("tc_analysis_result") or {}
            clauses = result.get("clauses") or []

            gold_rows = []
            for gold in doc["gold"]:
                clause = find_clause(clauses, gold["match"])
                label = clause.get("label") if clause else None
                cited = clause.get("statutory_basis") or [] if clause else []
                gold_rows.append(
                    {
                        "match": gold["match"],
                        "stratum": gold["stratum"],
                        "expected": gold["label"],
                        "got": label,
                        "found": clause is not None,
                        "label_ok": label == gold["label"],
                        "citation_ok": (
                            None
                            if not gold["sections_any"] or clause is None
                            else any(s in cited for s in gold["sections_any"])
                        ),
                        "blacklisted_as_compliant": gold["label"] == "BLACKLISTED" and label == "COMPLIANT",
                    }
                )

            strips = sum(
                1 for c in clauses if contains(c.get("legal_explanation"), "[note: citation(s)")
            )
            case = {
                "id": f"{doc['id']}#r{rep}",
                "gold": gold_rows,
                "confidence_expected": doc["overall_confidence"],
                "confidence_got": result.get("overall_confidence"),
                "confidence_ok": result.get("overall_confidence") == doc["overall_confidence"],
                "disclaimer_present": bool(result.get("disclaimer")),
                "citation_strips": strips,
                "extra_clauses": max(0, len(clauses) - len(doc["gold"])),
            }
            if use_judge:
                explained = [
                    {
                        "clause": c.get("clause_text"),
                        "label": c.get("label"),
                        "simple_explanation": c.get("simple_explanation"),
                        "legal_explanation": c.get("legal_explanation"),
                    }
                    for c in clauses
                    if c.get("label") != "COMPLIANT"
                ]
                if explained:
                    try:
                        case["judge"] = await judge(EXPLANATION_RUBRIC, str(explained))
                    except Exception as e:  # noqa: BLE001 — a judge outage shouldn't kill the case
                        case["judge_error"] = str(e)[:200]
            cases.append(case)

    rows = [r for c in cases for r in c["gold"]]
    by_stratum: dict[str, list] = {}
    for row in rows:
        by_stratum.setdefault(row["stratum"], []).append(row)
    citation_rows = [r for r in rows if r["citation_ok"] is not None]
    judged = [c["judge"]["score"] for c in cases if isinstance(c.get("judge"), dict)]

    metrics = {
        "clause_recall": round(sum(r["found"] for r in rows) / len(rows), 3),
        "label_accuracy": round(sum(r["label_ok"] for r in rows) / len(rows), 3),
        "blacklisted_as_compliant": sum(r["blacklisted_as_compliant"] for r in rows),
        "citation_hit_rate": round(
            sum(r["citation_ok"] for r in citation_rows) / len(citation_rows), 3
        )
        if citation_rows
        else None,
        "confidence_accuracy": round(sum(c["confidence_ok"] for c in cases) / len(cases), 3),
        "disclaimer_rate": round(sum(c["disclaimer_present"] for c in cases) / len(cases), 3),
        "citation_strip_events": sum(c["citation_strips"] for c in cases),
        "judge_mean": round(sum(judged) / len(judged), 2) if judged else None,
    }
    for stratum, stratum_rows in sorted(by_stratum.items()):
        metrics[f"label_accuracy[{stratum}]"] = round(
            sum(r["label_ok"] for r in stratum_rows) / len(stratum_rows), 3
        )

    gates = [
        {
            "name": "no BLACKLISTED clause graded COMPLIANT",
            "ok": metrics["blacklisted_as_compliant"] == 0,
            "detail": f"{metrics['blacklisted_as_compliant']} dangerous downgrades",
        },
        {
            "name": "label accuracy >= 0.75",
            "ok": metrics["label_accuracy"] >= 0.75,
            "detail": f"got {metrics['label_accuracy']}",
        },
        {
            "name": "disclaimer on every analysis",
            "ok": metrics["disclaimer_rate"] == 1.0,
            "detail": f"rate {metrics['disclaimer_rate']}",
        },
    ]
    return {"suite": "tc", "cases": cases, "metrics": metrics, "gates": gates}
