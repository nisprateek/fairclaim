"""Eval CLI: runs one or more suites in a single event loop and writes a
JSON + Markdown report under evals/results/.

    uv run python -m evals.run --suites all --reps 1
    uv run python -m evals.run --suites tc,security --no-judge
    uv run python -m evals.run --list

Suites share one asyncio loop (the MCP stdio toolset binds its sessions to
the running loop; a fresh asyncio.run() per suite would strand subprocess
sessions). Eval-only telemetry callbacks collect model cost and token totals.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import traceback
from pathlib import Path

from evals.harness import RESULTS_DIR, load_env, now_stamp, telemetry_store, usage_totals
from evals.suites import SUITES


def _fmt(value) -> str:
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def _render_markdown(report: dict) -> str:
    lines = [
        f"# Eval report — {report['stamp']}",
        "",
        f"- Models: fast=`{report['models']['fast']}` capable=`{report['models']['capable']}` "
        f"judge=`{report['models']['judge']}`",
        f"- Reps: {report['reps']} · judge: {report['use_judge']} · wall: {report['wall_s']}s",
        f"- Estimated cost: **${report['usage']['est_cost_usd']:.4f}** "
        f"over {report['usage']['model_calls']} model calls, {report['usage']['total_tokens']:,} tokens",
        "",
        f"**Overall gate status: {'PASS ✅' if report['all_gates_pass'] else 'FAIL ❌'}**",
        "",
    ]
    for suite in report["suites"]:
        name = suite["suite"]
        if "error" in suite:
            lines += [f"## {name} — ERRORED", "", f"```\n{suite['error']}\n```", ""]
            continue
        gate_line = " · ".join(
            f"{'✅' if g['ok'] else '❌'} {g['name']} ({g['detail']})" for g in suite["gates"]
        )
        lines += [
            f"## {name} — {'PASS' if all(g['ok'] for g in suite['gates']) else 'FAIL'}",
            "",
            "| metric | value |",
            "| --- | --- |",
        ]
        lines += [f"| {k} | {_fmt(v)} |" for k, v in suite["metrics"].items()]
        lines += ["", f"Gates: {gate_line}" if gate_line else "", ""]
    lines += ["---", "", "_Costs are estimates; see EVALS.md. All data in-memory._"]
    return "\n".join(lines)


async def _run_suites(names: list[str], reps: int, use_judge: bool) -> dict:
    from fairclaim.backend.llm_config import CAPABLE_MODEL, FAST_MODEL

    try:
        from evals.judge import judge_model

        judge_name = judge_model()
    except Exception:  # noqa: BLE001
        judge_name = "n/a"

    telemetry_store()  # instrument before the first model call
    started = time.time()
    results = []
    for name in names:
        suite_started = time.time()
        print(f"▶ running suite: {name} …", flush=True)
        try:
            result = await SUITES[name](reps=reps, use_judge=use_judge)
        except Exception:  # noqa: BLE001 — one suite failing shouldn't sink the rest
            result = {"suite": name, "error": traceback.format_exc(), "gates": [], "metrics": {}}
        result["wall_s"] = round(time.time() - suite_started, 1)
        gates_ok = all(g["ok"] for g in result.get("gates", [])) and "error" not in result
        print(
            f"  {'✅' if gates_ok else '❌'} {name} "
            f"({result['wall_s']}s) — { {k: _fmt(v) for k, v in result.get('metrics', {}).items()} }",
            flush=True,
        )
        results.append(result)

    return {
        "stamp": now_stamp(),
        "reps": reps,
        "use_judge": use_judge,
        "wall_s": round(time.time() - started, 1),
        "models": {"fast": FAST_MODEL, "capable": CAPABLE_MODEL, "judge": judge_name},
        "usage": usage_totals(),
        "suites": results,
        "all_gates_pass": all(
            "error" not in s and all(g["ok"] for g in s.get("gates", [])) for s in results
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Consumer Rights Agent eval suites.")
    parser.add_argument("--suites", default="all", help="comma-separated suite names, or 'all'")
    parser.add_argument("--reps", type=int, default=1, help="repetitions per case (report mean + worst)")
    parser.add_argument("--no-judge", action="store_true", help="skip LLM-as-judge scoring (cheaper)")
    parser.add_argument("--list", action="store_true", help="list suites and exit")
    args = parser.parse_args(argv)

    if args.list:
        print("suites:", ", ".join(SUITES))
        return 0

    load_env()
    if not (__import__("os").environ.get("GEMINI_API_KEY") or __import__("os").environ.get("GOOGLE_API_KEY")):
        print("ERROR: no GEMINI_API_KEY/GOOGLE_API_KEY in env or .env — evals need a live model.", file=sys.stderr)
        return 2

    names = list(SUITES) if args.suites == "all" else [s.strip() for s in args.suites.split(",") if s.strip()]
    unknown = [n for n in names if n not in SUITES]
    if unknown:
        print(f"ERROR: unknown suite(s): {unknown}. Known: {list(SUITES)}", file=sys.stderr)
        return 2

    report = asyncio.run(_run_suites(names, args.reps, not args.no_judge))

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = report["stamp"]
    json_path = RESULTS_DIR / f"eval-{stamp}.json"
    md_path = RESULTS_DIR / f"eval-{stamp}.md"
    json_path.write_text(json.dumps(report, indent=2, default=str))
    md_path.write_text(_render_markdown(report))

    print("\n" + "=" * 70)
    print(_render_markdown(report))
    print("=" * 70)
    print(f"\nWrote {json_path}\n      {md_path}")
    return 0 if report["all_gates_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
