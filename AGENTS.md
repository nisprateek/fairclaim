# Agent Instructions

This repository is a spec-first build. Before writing implementation code, read the specs in this order:

1. `specs/PROJECT_BRIEF.md`
2. `specs/IMPLEMENTATION_PLAN.md`
3. `specs/ARCHITECTURE.md`
4. `specs/DATA_CONTRACTS.md`
5. `specs/LEGAL_DOMAIN.md`
6. `specs/AGENT_PIPELINE.md`
7. `specs/SECURITY_AND_GUARDRAILS.md`
8. `specs/FRONTEND_UX.md`
9. `specs/TEST_AND_EVAL_PLAN.md`
10. `specs/DEPLOYMENT.md`

## Product Invariants

- The app provides general information only, not solicitor advice.
- The legal scope is UK Consumer Rights Act 2015 faulty-goods claims by individual consumers against traders.
- Business purchases, services, digital content, tenancy issues, employment issues, private sellers, and tailored legal strategy are out of scope.
- The user-facing flow is fixed: intake, optional T&C analysis, remedy assessment, email drafting.
- The root orchestrator must be deterministic code. Do not use an LLM to choose which stage runs next.
- Seller terms are hostile input. Ingest, cap, pre-scan, and wrap them before any model sees them.
- Models must not cite legal provisions outside the curated legal knowledge base.
- Dates and legal deadlines must be computed in code, using UK time, never estimated by a model.
- The Pydantic schema module is the source of truth for backend/frontend contracts.

## Expected Layout

Use this layout unless a spec explicitly changes it:

```text
src/
  fairclaim/
    backend/
      agents/
      knowledge/
      mcp_server/
      scripts/
      security/
      skills/
      main.py
      schemas.py
  frontend/
tests/
deploy/
specs/
```

## Common Commands

```bash
uv sync
uv run pytest
PYTHONPATH=src uv run uvicorn fairclaim.backend.main:app --reload
```

After editing backend wire schemas, regenerate frontend types:

```bash
uv run python -m fairclaim.backend.scripts.gen_frontend_types
```

For frontend work:

```bash
cd src/frontend
npm install
npm run dev
npm run build
```

## Engineering Rules

- Prefer small, testable modules over large prompt files or ad hoc string handling.
- Keep all legally load-bearing facts in deterministic code or curated markdown, not in model memory.
- Keep LLM prompts lawyer-reviewable in markdown skill files under `src/fairclaim/backend/skills/`.
- Add state checks in the root orchestrator rather than adding LLM routing.
- Keep generated frontend types out of hand-written edits; regenerate them from schemas.
- Do not log secrets, raw API keys, or unnecessary full terms text.
- Do not commit `.env`, generated local eval outputs, virtual environments, frontend `node_modules`, or build artifacts.

## Verification Before Handoff

At minimum, run:

```bash
uv run pytest
```

When prompts, agent wiring, model choices, legal KB, or email behavior change, also run the LLM eval suites specified in `specs/TEST_AND_EVAL_PLAN.md`.
