"""Score agent outputs against the external solicitor ground-truth labels.

The ground-truth package (clause labels, remedy tier/burden reviews, judge
calibration scores) lives in a separate repo and is NOT bundled here — point
`--gt-root` at its checkout and `--annotations` at a solicitor export. This
module only reads those files; it never writes to the ground-truth repo.

Two sources can be scored against the same labels:

- `--source frozen`  — the frozen outputs the solicitor actually reviewed
  (pinned to the SHA recorded in the export provenance); reproduces the
  headline agreement numbers from the annotation session.
- `--source live`    — re-runs the CURRENT checkout's tc_analysis and
  remedies agents on the same docs/cases and scores the fresh outputs
  against the solicitor's labels. Human labels attach to the *inputs*
  (clause spans, remedy cases), so they stay valid across refactors; only
  judge calibration is inherently pinned to the reviewed outputs.

    uv run python -m evals.human_baseline --source frozen \
        --annotations ../evals/exports/annotations-2026-07-05.json
    uv run python -m evals.human_baseline --source live \
        --annotations ../evals/exports/annotations-2026-07-05.json

Requires GEMINI_API_KEY in .env for `--source live`. Runs in one asyncio
loop per process (see evals/harness.py docstring).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

from evals.harness import RESULTS_DIR, SRC_DIR, load_env, now_stamp, run_staged

SEVERITY = {"COMPLIANT": 0, "POTENTIALLY_UNFAIR": 1, "BLACKLISTED": 2}


def norm(text) -> str:
    import re

    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def find_agent_clause(clauses: list[dict], match: str) -> dict | None:
    """Same alignment rule the annotation UI used (embed_ui_data.py)."""
    m = norm(match)
    for c in clauses or []:
        ct = norm(c.get("clause_text"))
        if m in ct or (len(ct) > 25 and ct in m):
            return c
    return None


# ---------------------------------------------------------------------------
# Output sources
# ---------------------------------------------------------------------------

def frozen_outputs(gt_root: Path) -> dict[str, dict]:
    frozen = json.loads((gt_root / "data" / "frozen_outputs.json").read_text())
    return {f"{o['case_type']}:{o['case_id']}": o for o in frozen["outputs"]}


async def live_outputs(gt_root: Path, doc_ids: set[str], case_ids: set[str]) -> dict[str, dict]:
    """Re-run the real agents at HEAD on the ground-truth docs/cases."""
    from fairclaim.backend.agents.remedies import remedies_agent
    from fairclaim.backend.agents.tc_analysis import tc_analysis_agent
    from fairclaim.backend.security.injection import wrap_untrusted

    docs = json.loads((gt_root / "data" / "tc_docs.json").read_text())["docs"]
    cases = json.loads((gt_root / "data" / "remedy_cases.json").read_text())["cases"]
    out: dict[str, dict] = {}

    for doc in docs:
        if doc["id"] not in doc_ids:
            continue
        print(f"[live] tc:{doc['id']} ...", flush=True)
        wrapped, flags = wrap_untrusted(doc["text"])
        state = await run_staged(
            tc_analysis_agent,
            {"temp:terms_wrapped": wrapped, "temp:injection_flags": flags},
            "Analyse the seller's terms and conditions.",
        )
        result = state.get("tc_analysis_result") or {}
        if not result:
            raise RuntimeError(f"tc:{doc['id']} produced no tc_analysis_result")
        out[f"tc:{doc['id']}"] = {"tc_analysis_result": result}

    for case in cases:
        if case["id"] not in case_ids:
            continue
        print(f"[live] remedy:{case['id']} ...", flush=True)
        delivery = (date.today() - timedelta(days=case["days_ago"])).isoformat()
        fields = {**case["case_fields"], "purchase_or_delivery_date": delivery}
        state = await run_staged(remedies_agent, {"temp:case_fields": fields})
        result = state.get("remedy_result") or {}
        if not result:
            raise RuntimeError(f"remedy:{case['id']} produced no remedy_result")
        out[f"remedy:{case['id']}"] = {"remedy_result": result}

    return out


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score_clauses(items: list[dict], docs_by_id: dict[str, dict], outputs: dict[str, dict]) -> dict:
    rows, disagreements = [], []
    for it in items:
        doc = docs_by_id[it["doc_id"]]
        idx = int(it["id"].rsplit(":", 1)[1])
        cand = doc["gold_candidates"][idx]
        clauses = (outputs[f"tc:{doc['id']}"].get("tc_analysis_result") or {}).get("clauses") or []
        agent = find_agent_clause(clauses, cand["match"])
        agent_label = agent.get("label") if agent else None
        human_label = it["label"]
        agree = agent_label == human_label
        rows.append({
            "id": it["id"],
            "stratum": it["stratum"],
            "human": human_label,
            "agent": agent_label,
            "found": agent is not None,
            "agree": agree,
            "confidence": it.get("confidence"),
        })
        if not agree:
            direction = None
            if agent_label is not None:
                delta = SEVERITY[agent_label] - SEVERITY[human_label]
                direction = "over" if delta > 0 else "under"
            disagreements.append({**rows[-1], "direction": direction or "missed"})

    by_stratum = {}
    for s in sorted({r["stratum"] for r in rows}):
        sub = [r for r in rows if r["stratum"] == s]
        by_stratum[s] = {"n": len(sub), "agree": sum(r["agree"] for r in sub)}
    return {
        "n": len(rows),
        "agree": sum(r["agree"] for r in rows),
        "found": sum(r["found"] for r in rows),
        "by_stratum": by_stratum,
        "confusion": Counter((r["agent"], r["human"]) for r in rows),
        "disagreements": disagreements,
    }


def score_remedies(items: list[dict], outputs: dict[str, dict]) -> dict:
    rows = []
    for it in items:
        result = outputs[f"remedy:{it['case_id']}"].get("remedy_result") or {}
        rows.append({
            "case_id": it["case_id"],
            "tier_human": it["tier"], "tier_agent": result.get("applicable_tier"),
            "burden_human": it["burden"], "burden_agent": result.get("burden_of_proof"),
            "remedies_ok": it.get("remedies_ok"),
        })
    return {
        "n": len(rows),
        "tier_agree": sum(r["tier_human"] == r["tier_agent"] for r in rows),
        "burden_agree": sum(r["burden_human"] == r["burden_agent"] for r in rows),
        "rows": rows,
    }


def score_judge(items: list[dict]) -> dict:
    """Judge calibration is inherently pinned: the solicitor scored the same
    payloads the judge scored, so it is read straight from the export."""
    rows = [
        {"id": it["id"], "rubric": it["rubric_id"], "judge": it["judge_score"],
         "human": it["own_score"], "verdict": it["judge_agreement"]}
        for it in items
    ]
    return {
        "n": len(rows),
        "agreement": Counter(r["verdict"] for r in rows),
        "mean_judge": sum(r["judge"] for r in rows) / len(rows) if rows else None,
        "mean_human": sum(r["human"] for r in rows) / len(rows) if rows else None,
        "rows": rows,
    }


def score_reviews(items: list[dict]) -> dict:
    tc = [it for it in items if it["type"] == "tc_review"]
    emails = [it for it in items if it["type"] == "email_review"]
    tone_checks = [(k, v) for it in emails for k, v in (it.get("tones") or {}).items()]
    return {
        "tc_n": len(tc),
        "tc_verdict_correct": sum(bool(it["verdict_correct"]) for it in tc),
        "email_n": len(emails),
        "facts_ok": sum(it.get("facts_ok") == "yes" for it in emails),
        "demand_ok": sum(it.get("demand_ok") == "yes" for it in emails),
        "tone_ok": sum(v == "yes" for _, v in tone_checks),
        "tone_total": len(tone_checks),
    }


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def pct(a: int, n: int) -> str:
    return f"{a}/{n} ({100 * a / n:.0f}%)" if n else "n/a"


def render(source: str, sha: str, export: dict, clause: dict, remedy: dict,
           judge: dict, reviews: dict) -> str:
    prov = export.get("provenance", {})
    lines = [
        "# Human ground-truth baseline",
        "",
        f"- Scored outputs: **{source}** (src SHA `{sha[:9]}`)",
        f"- Solicitor labels: export of {export['annotator']['date']} "
        f"(annotated against SHA `{str(prov.get('src_git_sha'))[:9]}`)",
        "",
        "## Clause classification vs solicitor labels",
        "",
        f"| Metric | Value |",
        f"|---|---|",
        f"| Label agreement (overall) | {pct(clause['agree'], clause['n'])} |",
        f"| Candidate spans surfaced by agent | {pct(clause['found'], clause['n'])} |",
    ]
    for s, d in clause["by_stratum"].items():
        lines.append(f"| Agreement — {s} | {pct(d['agree'], d['n'])} |")
    lines += ["", "Disagreements (agent vs solicitor):", ""]
    for d in clause["disagreements"]:
        lines.append(f"- `{d['id']}` [{d['stratum']}] agent={d['agent']} "
                     f"human={d['human']} → {d['direction']}")
    lines += [
        "",
        "## Remedy engine vs solicitor review",
        "",
        f"| Metric | Value |",
        f"|---|---|",
        f"| Tier agreement | {pct(remedy['tier_agree'], remedy['n'])} |",
        f"| Burden-of-proof agreement | {pct(remedy['burden_agree'], remedy['n'])} |",
    ]
    mismatches = [r for r in remedy["rows"]
                  if r["tier_human"] != r["tier_agent"] or r["burden_human"] != r["burden_agent"]]
    if mismatches:
        lines += ["", "Mismatches:", ""]
        for r in mismatches:
            lines.append(f"- `{r['case_id']}` tier {r['tier_agent']} vs {r['tier_human']}; "
                         f"burden {r['burden_agent']} vs {r['burden_human']}")
    lines += [
        "",
        "## Judge calibration (pinned to reviewed outputs)",
        "",
        f"| Metric | Value |",
        f"|---|---|",
        f"| Verdicts | {dict(judge['agreement'])} |",
        f"| Mean judge score | {judge['mean_judge']:.1f} |",
        f"| Mean solicitor score | {judge['mean_human']:.1f} |",
        "",
        "## Whole-output review (pinned to reviewed outputs)",
        "",
        f"| Metric | Value |",
        f"|---|---|",
        f"| T&C doc verdicts correct | {pct(reviews['tc_verdict_correct'], reviews['tc_n'])} |",
        f"| Email facts grounded | {pct(reviews['facts_ok'], reviews['email_n'])} |",
        f"| Email demand correct | {pct(reviews['demand_ok'], reviews['email_n'])} |",
        f"| Email tone checks passed | {pct(reviews['tone_ok'], reviews['tone_total'])} |",
        "",
    ]
    return "\n".join(lines)


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--annotations", required=True, help="solicitor export JSON")
    parser.add_argument("--gt-root", default=str(SRC_DIR.parent / "evals"),
                        help="checkout of the ground-truth repo (default: ../evals)")
    parser.add_argument("--source", choices=["frozen", "live"], default="frozen")
    parser.add_argument("--out", help="write the Markdown report here "
                        "(default: evals/results/human_baseline-<stamp>-<source>.md)")
    args = parser.parse_args()

    gt_root = Path(args.gt_root)
    export = json.loads(Path(args.annotations).read_text())
    items = [i for i in export["items"] if not i.get("warmup") and i.get("status") == "done"]
    clause_items = [i for i in items if i["type"] == "clause"]
    remedy_items = [i for i in items if i["type"] == "remedy"]
    judge_items = [i for i in items if i["type"] == "judge"]

    docs = json.loads((gt_root / "data" / "tc_docs.json").read_text())["docs"]
    docs_by_id = {d["id"]: d for d in docs}

    if args.source == "frozen":
        outputs = frozen_outputs(gt_root)
        sha = export.get("provenance", {}).get("src_git_sha") or "unknown"
    else:
        load_env()
        import os
        if not os.environ.get("GEMINI_API_KEY") and not os.environ.get("GOOGLE_API_KEY"):
            sys.exit("GEMINI_API_KEY missing (expected in .env)")
        outputs = await live_outputs(
            gt_root,
            {i["doc_id"] for i in clause_items},
            {i["case_id"] for i in remedy_items},
        )
        sha = subprocess.run(["git", "-C", str(SRC_DIR), "rev-parse", "HEAD"],
                             capture_output=True, text=True).stdout.strip()

    report = render(
        args.source, sha, export,
        score_clauses(clause_items, docs_by_id, outputs),
        score_remedies(remedy_items, outputs),
        score_judge(judge_items),
        score_reviews(items),
    )
    out_path = Path(args.out) if args.out else (
        RESULTS_DIR / f"human_baseline-{now_stamp()}-{args.source}.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    print(report)
    print(f"[human_baseline] wrote {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
