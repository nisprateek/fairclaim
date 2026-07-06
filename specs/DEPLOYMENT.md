# Deployment Specification

## Goal

Deploy one combined application to Google Cloud Run:

- FastAPI serves API and ADK REST.
- FastAPI also serves the built React frontend.
- One origin in production.
- `GEMINI_API_KEY` is mounted from Secret Manager.

## Required Files

The implementation includes:

```text
Dockerfile
deploy/cloudrun.sh
```

The default Cloud Run target remains the existing service:
`https://fairclaimai-698454199279.europe-west2.run.app/`.

## Environment Variables

Runtime:

```text
GEMINI_API_KEY
FAIRCLAIMAI_FAST_MODEL
FAIRCLAIMAI_CAPABLE_MODEL
FAIRCLAIMAI_JUDGE_MODEL
FAIRCLAIMAI_ENABLE_TELEMETRY
```

Deployment script inputs:

```text
PROJECT_ID       required
REGION           default europe-west2
SERVICE_NAME     default fairclaimai
SECRET_NAME      default gemini-api-key
```

## Docker Build

Recommended multi-stage behavior:

1. Node stage:
   - Workdir `src/frontend`.
   - Install dependencies.
   - Run `npm run build`.
2. Python stage:
   - Install Python 3.13 runtime.
   - Install uv.
   - Copy project.
   - Run `uv sync --frozen --no-dev`.
   - Copy frontend `dist`.
   - Set `PYTHONPATH=/app/src`.
   - Run `uv run uvicorn fairclaim.backend.main:app --host 0.0.0.0 --port ${PORT:-8080}`.

Acceptance:

- `docker build -t fairclaimai .` succeeds.
- `docker run --rm -p 8080:8080 --env-file .env fairclaimai` serves the frontend and API.

## FastAPI Static Serving

In `src/fairclaim/backend/main.py`:

- Register API routes first.
- Register frontend static mount last.
- Serve `src/frontend/dist` or copied equivalent.
- Do not enable broad CORS in production.
- Allow local Vite origins only for dev.

## Cloud Run Script Behavior

`deploy/cloudrun.sh` should:

1. `cd` to repo root.
2. Require `PROJECT_ID`.
3. Read `GEMINI_API_KEY` from `.env`.
4. Enable required APIs:
   - Cloud Run.
   - Cloud Build.
   - Artifact Registry.
   - Secret Manager.
5. Create Secret Manager secret if missing.
6. Add a new secret version on redeploy.
7. Grant deploy/runtime service account access to build and read secret.
8. Run `gcloud run deploy --source .`.
9. Set:
   - `--allow-unauthenticated`
   - `--min-instances=0`
   - `--max-instances=1`
   - `--memory=1Gi`
   - `--set-secrets="GEMINI_API_KEY=${SECRET_NAME}:latest"`
10. Print the service URL.

## Why Max Instances Is 1

The MVP may use process-local session storage. With more than one instance, a user could start a case on one instance and continue on another with missing session state.

Keep:

```text
--max-instances=1
```

until sessions move to a shared store.

## Release Gate

Before deploy:

```bash
uv run pytest
uv run python -m evals.run
cd src/frontend
npm run build
```

Deployment should not proceed if tests or evals fail.

## Operational Caveats

- Scale-to-zero cold starts may orphan process-local sessions.
- Redeploys may orphan in-flight sessions.
- Secret Manager stores API key versions; old versions should be rotated or disabled as needed.
- Logs must not print API keys or full untrusted terms text.
