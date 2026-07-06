"""LLM-as-judge: a 0-5 scored verdict against a fixed rubric.

Judge hygiene (see EVALS.md): the judge runs on the dedicated
gemini-3.1-pro-preview judge model by default, sees only the rubric and the
output being graded (never the agent's system prompt), and returns a
structured verdict at temperature 0 so scores are as repeatable as the API
allows.
"""

from __future__ import annotations

import os

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from evals.harness import with_retry

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client()
    return _client


def judge_model() -> str:
    from fairclaim.backend.llm_config import JUDGE_MODEL

    return os.environ.get("FAIRCLAIMAI_JUDGE_MODEL", JUDGE_MODEL)


class JudgeVerdict(BaseModel):
    score: int = Field(ge=0, le=5, description="0 = fails the rubric entirely, 5 = fully meets it.")
    rationale: str = Field(description="One or two sentences citing the specific rubric points won/lost.")


PROMPT_TEMPLATE = """You are a strict evaluation judge. Grade the OUTPUT below against the RUBRIC.
Score 0-5: 5 = meets every rubric point, 3 = meets most with real gaps, 0 = fails the rubric.
Judge only what is written — do not give credit for what the author probably intended.

RUBRIC:
{rubric}

OUTPUT TO GRADE:
{payload}
"""


async def judge(rubric: str, payload: str) -> dict:
    """Returns {"score": int, "rationale": str}."""

    async def _once():
        response = await _get_client().aio.models.generate_content(
            model=judge_model(),
            contents=PROMPT_TEMPLATE.format(rubric=rubric.strip(), payload=payload.strip()[:24_000]),
            config=types.GenerateContentConfig(
                temperature=0,
                response_mime_type="application/json",
                response_schema=JudgeVerdict,
            ),
        )
        verdict: JudgeVerdict = response.parsed
        return {"score": verdict.score, "rationale": verdict.rationale}

    return await with_retry(_once)
