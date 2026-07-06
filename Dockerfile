# Build context is the fairclaim repo root. Build with:
#   docker build -t fairclaimai .
# Run with:
#   docker run -p 8080:8080 -e GEMINI_API_KEY=... fairclaimai
#
# Single container serves both the API (FastAPI/ADK) and the built frontend
# from one origin — see fairclaim.backend.main's static mount. No secrets are baked
# in; GEMINI_API_KEY is supplied at runtime (Cloud Run: via Secret Manager).

# ---- frontend build ----
FROM node:22-slim AS frontend-build
WORKDIR /app/src/frontend
COPY src/frontend/package.json src/frontend/package-lock.json ./
RUN npm ci
COPY src/frontend/ ./
RUN npm run build

# ---- backend runtime ----
FROM python:3.13-slim AS backend
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/
WORKDIR /app

# Dependencies first for layer caching — only pyproject.toml/uv.lock changing
# invalidates this layer, not every source edit.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY README.md ./
COPY src/fairclaim/ ./src/fairclaim/
RUN uv sync --frozen --no-dev
COPY --from=frontend-build /app/src/frontend/dist ./src/frontend/dist

# Cloud Run injects $PORT (default 8080); honour it rather than hardcoding.
ENV PYTHONPATH=/app/src
ENV PORT=8080
EXPOSE 8080
# --no-sync: trust the venv baked in at build time. Without it, `uv run`
# re-syncs against uv.lock on every container start — reintroducing the
# "dev" dependency group `--no-dev` was dropped for above (confirmed live:
# it reached out to PyPI for pytest's deps at boot) and making startup
# depend on network/PyPI reachability, which a deployed container shouldn't need.
CMD ["sh", "-c", "uv run --no-sync uvicorn fairclaim.backend.main:app --host 0.0.0.0 --port ${PORT}"]
