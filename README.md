# FairClaimAI — UK Consumer Rights Agent

*Kaggle "AI Agents: Intensive Vibe Coding" capstone — Agents for Good track.*

When something you bought in the UK turns out faulty, the Consumer Rights Act 2015 is on
your side — and almost nobody knows it. "No refunds" and "sold as seen" signs are **legally
non-binding** for faulty goods. This agent turns *"my laptop keeps crashing and the shop
says all sales are final"* into a rights-backed, send-ready result:

1. **A clause-by-clause verdict** on the seller's terms — `BLACKLISTED` (non-binding,
   s.31/s.65), `POTENTIALLY_UNFAIR` (grey list, s.62), or `COMPLIANT` — each cited and reused
   as the seller-specific rebuttal in the complaint letter.
2. **The remedy the law actually gives you** — the s.22/s.23/s.24 ladder walked
   deterministically from your delivery date, with the correct burden of proof.
3. **A complaint email per available remedy** — cited, with a 14-day deadline and the
   escalation ladder (Section 75 / chargeback → ADR → Citizens Advice → small claims).

Everything carries the disclaimer: general information under the CRA 2015, not solicitor advice.

## Architecture

<img width="1047" height="647" alt="Screenshot 2026-07-07 at 00 32 01 copy" src="https://github.com/user-attachments/assets/c6c1097d-4cdc-4643-a06e-f0e0dd413a56" />


- **Deterministic orchestration.** The root agent is plain code, not an LLM router: intake
  runs until complete, then T&C analysis → remedies → email, each gated on its own output key
  so a failed turn resumes instead of redoing work. No terms? The T&C step is skipped with a
  "statutory rights apply regardless" stub.
- **Untrusted-input security.** Pasted seller terms are ingested outside the model with size
  caps, regex pre-scanned for injection, wrapped in explicit delimiters, and analysed with
  `include_contents="none"` so hostile text can't reach the conversation. A deterministic
  guard strips any statutory citation outside the curated KB.
- **T&C analysis feeds the case.** The statutory remedy comes from the CRA 2015 ladder, but
  blacklisted/unfair clauses are passed to the email agent so letters rebut the seller's
  actual small print, not generic "no refunds" language.
- **MCP server as the legal ground truth.** `src/fairclaim/backend/mcp_server/server.py`
  serves the curated CRA 2015 knowledge base as typed tools — statute summaries, blacklist
  clause patterns, and `lookup_remedy_tier`, which computes the 30-day/6-month boundaries in
  code (UK time, with an `evaluation_date` override for tests).
- **Agent skills.** The interview checklist, unfair-terms tests and remedy logic live in
  lawyer-reviewable markdown (`src/fairclaim/backend/skills/`) loaded into agent instructions.

### Models

| Tier | Model | Used by |
| --- | --- | --- |
| Fast | `gemini-3.1-flash-lite` | intake, remedies |
| Capable | `gemini-3.5-flash` | T&C clause analysis, email drafting |
| Judge | `gemini-3.1-pro-preview` | evals |

Override with `FAIRCLAIMAI_FAST_MODEL` / `FAIRCLAIMAI_CAPABLE_MODEL`
(`FAIRCLAIMAI_JUDGE_MODEL` for eval judging).

## Setup

Prereqs: Python ≥ 3.13 with [uv](https://docs.astral.sh/uv/), Node ≥ 20, a Gemini API key.

```bash
# 1. Backend (from repo root)
cp .envexample .env            # put your GEMINI_API_KEY in .env — never commit it
uv sync
PYTHONPATH=src uv run uvicorn fairclaim.backend.main:app --reload   # http://localhost:8000

# 2. Frontend
cd src/frontend
npm install
npm run dev                    # http://localhost:5173
```

The landing page's **guided demo** walks the whole experience with canned data; submitting
your own story runs the real live pipeline.

### Tests

```bash
uv run pytest
```

The suite pins the legal boundaries (day 30 vs 31, the six-month presumption and its
short-term-reject exception, month-end arithmetic), the citation guardrail, the injection
pre-scan, ingestion caps, and the T&C-to-email handoff.

### Regenerating the frontend types

`src/fairclaim/backend/schemas.py` is the wire contract. After changing it:

```bash
uv run python -m fairclaim.backend.scripts.gen_frontend_types
```

## Deploying (Docker / Cloud Run)

The whole app ships as **one container**: `Dockerfile` builds the frontend, then serves it as
static files from the same FastAPI process as the API — one origin, no CORS in production,
one Cloud Run service.

```bash
# Build and run locally first
docker build -t fairclaimai .
docker run --rm -p 8080:8080 --env-file .env fairclaimai   # http://localhost:8080

# Deploy (needs gcloud auth login, a billing-enabled GCP project, .env populated)
PROJECT_ID=your-gcp-project ./deploy/cloudrun.sh
```

The script is a thin, idempotent wrapper around `gcloud run deploy --source .` (Cloud Build
builds the image — no local Docker needed). It stores `GEMINI_API_KEY` in **Secret Manager**
(never baked into the image or printed) and caps at one instance (`--max-instances=1`),
because session state lives per container — a single instance keeps concurrent users from
silently losing an in-progress case, at the cost of a cold start after scale-to-zero. Raise
the cap only once sessions move to a shared store (e.g. `DatabaseSessionService` + Cloud
SQL). Region defaults to `europe-west2` (London); names are overridable via env vars — see
the script header.

## Caveats

- Sessions are stored on the running container/process (ADK's default), not a managed
  database: a backend restart or scale-to-zero cycle orphans in-flight interviews (the
  frontend starts a fresh session per case).
- The knowledge base covers CRA 2015 goods bought by individuals from UK traders. Services,
  digital content, EU and B2B purchases are out of scope — the intake says so instead of
  guessing. Change-of-mind cases get signposted to the CCR 2013 cooling-off where it applies.
- **Not legal advice.** For tailored advice: Citizens Advice or a solicitor.
