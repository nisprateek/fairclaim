# Implementation Plan

This plan is written for an agentic coding harness. Build in phases. Do not skip tests for earlier phases when moving to later phases.

## Target File Layout

```text
fairclaim/
  README.md
  AGENTS.md
  pyproject.toml
  uv.lock
  .envexample
  .gitignore
  .dockerignore
  .gcloudignore
  deploy/
    cloudrun.sh
  specs/
  src/
    fairclaim/
      __init__.py
      backend/
        __init__.py
        main.py
        schemas.py
        dates.py
        llm_config.py
        mcp_client.py
        telemetry.py
        agents/
          __init__.py
          orchestrator.py
          tc_analysis.py
          remedies.py
          email_agent.py
          intake/
            __init__.py
            agent.py
            components.py
            turns.py
        agents_root/
          consumer_rights/
            __init__.py
            agent.py
        knowledge/
          CRA_2015_KB.md
        mcp_server/
          __init__.py
          server.py
        scripts/
          __init__.py
          gen_frontend_types.py
        security/
          __init__.py
          guardrails.py
          ingest.py
          injection.py
        skills/
          __init__.py
          loader.py
          cra_intake_checklist/
            SKILL.md
          cra_remedies/
            SKILL.md
          cra_unfair_terms/
            SKILL.md
    frontend/
      package.json
      index.html
      vite.config.ts
      tsconfig.json
      tsconfig.app.json
      tsconfig.node.json
      public/
      src/
        App.tsx
        api.ts
        main.tsx
        types.ts
        generated/
          schemas.ts
        components/
        lib/
  tests/
  evals/
    datasets/
    suites/
    results/
```

The root scaffold may start smaller. Add files only when the phase needs them.

## Phase 1: Project Skeleton

Tasks:

- Keep Python package code under `src/fairclaim`.
- Configure `pyproject.toml` for Python 3.13 and pytest with `pythonpath = ["src"]`.
- Create empty packages for backend, agents, security, MCP, scripts, and skills.
- Create `.envexample` with `GEMINI_API_KEY`, model override variables, and telemetry toggle.

Acceptance:

- `uv sync` succeeds.
- `uv run pytest` succeeds with no tests or placeholder tests.
- Imports from `fairclaim.backend` work.

## Phase 2: Wire Schemas

Tasks:

- Implement `src/fairclaim/backend/schemas.py` exactly as specified in `DATA_CONTRACTS.md`.
- Add JSON schema export/type generation script for frontend TypeScript.
- Add contract tests validating enum values, required fields, and public session-state keys.

Acceptance:

- `uv run pytest tests/test_contracts.py` passes.
- Frontend generated schema file is deterministic when regenerated twice.

## Phase 3: Legal KB And MCP Server

Tasks:

- Write `knowledge/CRA_2015_KB.md` in lawyer-reviewable prose.
- Implement `mcp_server/server.py` with deterministic tools:
  - `get_disclaimer`
  - `get_statutory_standard`
  - `classify_clause_guidance`
  - `lookup_remedy_tier`
- Implement shared UK date helpers in `dates.py`.

Acceptance:

- Remedy tier tests pin day 30 vs day 31.
- Six-month boundary uses calendar-month arithmetic.
- Future delivery dates raise an error.
- All cited sections returned by agents must exist in `STATUTORY_STANDARDS`.

## Phase 4: Security And Ingestion

Tasks:

- Implement pasted T&C ingestion with a hard byte cap.
- Implement URL and file ingestion only if hardened with SSRF checks, content-type allowlist, timeout, and size caps.
- Implement prompt-injection scanner and wrapper.
- Implement citation guard that strips uncurated legal citations from structured output.

Acceptance:

- Empty pasted terms fail.
- Over-size inputs fail or truncate only where specified.
- Localhost, private IPs, link-local, and metadata hosts are blocked for URL ingestion.
- Injection corpus triggers `injection_flagged`.
- Uncurated citations are removed and noted in legal explanations.

## Phase 5: Intake

Tasks:

- Build the intake package with:
  - component catalog,
  - deterministic answer parsing,
  - confirmation flow,
  - date extraction,
  - business-buyer scope gate,
  - ADK `LlmAgent`.
- Intake should infer facts from the opening story but must confirm inferred facts before completion.
- Direct UI controls should bind deterministically without needing model judgment.

Acceptance:

- Intake asks missing fields in stable order.
- Yes/no choice answers bind to booleans.
- Bare rejection of inferred value re-asks the field.
- Corrected value replaces the inferred value.
- Terms source is set only by explicit UI action or deterministic parser.

## Phase 6: Deterministic Orchestration

Tasks:

- Implement root `BaseAgent` as a state machine.
- Stage order: intake, T&C analysis if terms exist, remedies, email.
- Gate every stage on state keys so failed turns resume from the first missing result.
- Persist a no-terms T&C stub when user opts out of terms.

Acceptance:

- Incomplete intake runs only intake.
- Complete intake with no terms waits for terms or explicit opt-out.
- No-terms opt-out proceeds to remedies and email.
- Existing `tc_analysis_result` prevents duplicate T&C analysis.
- Existing `email_drafts` causes the orchestrator to stop.

## Phase 7: Specialist Agents

Tasks:

- Implement T&C analysis agent with `include_contents="none"` and wrapped terms only.
- Implement remedies agent that always calls deterministic tier tool and grounds structured output in tool truth.
- Implement email agent that drafts from a curated case brief and does not post-stitch templated prose.
- Load prompt/skill markdown from `skills/`.

Acceptance:

- T&C outputs classify relevant clauses with citations only from the KB.
- Remedies output matches tool tier, burden, claim strength, and barriers.
- Email output has one draft per offered remedy.
- Each draft contains polite, firm, and formal complete letter bodies.
- Seller-facing email bodies do not include the disclaimer.

## Phase 8: FastAPI And ADK REST

Tasks:

- Build `src/fairclaim/backend/main.py` around ADK FastAPI helper.
- Expose ADK session/run routes.
- Expose `/ingest/terms`.
- Serve built frontend when `src/frontend/dist` exists.
- Keep CORS restricted to localhost dev origins.

Acceptance:

- Creating an ADK session works.
- Posting `/run` updates session state.
- Posting `/ingest/terms` returns clean text or a 400 error.
- Static frontend route does not shadow API routes.

## Phase 9: Frontend

Tasks:

- Create Vite React TypeScript app under `src/frontend`.
- Use generated schemas from backend.
- Implement start screen, interview workspace, analysis state, results dashboard, and copyable letter.
- Use ADK REST directly for production flow.

Acceptance:

- User can complete happy path from browser.
- No-terms branch works.
- Prompt-injection warning is visible when flagged.
- Tone selector changes email body.
- Copy button copies subject and body only, not disclaimer.
- `npm run build` succeeds.

## Phase 10: Tests, Evals, Deploy

Tasks:

- Add deterministic pytest coverage described in `TEST_AND_EVAL_PLAN.md`.
- Add live-model eval suites and datasets.
- Add Dockerfile and implement `deploy/cloudrun.sh`.
- Deploy only after pytest and required evals pass.

Acceptance:

- `uv run pytest` passes.
- Eval gates pass for affected suites.
- Cloud Run deploy serves the built app from one origin.
- `GEMINI_API_KEY` is mounted from Secret Manager, not baked into the image.
