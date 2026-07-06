"""FastAPI entry point for the consumer-rights app.

Run locally with:  uv run uvicorn fairclaim.backend.main:app --reload

The backend exposes ADK REST/session routes and `/ingest/terms`. When
`src/frontend/dist` exists, the same process serves the built React app.
"""

from pathlib import Path

from fastapi import Form, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles
from google.adk.cli.fast_api import get_fast_api_app

from fairclaim.backend.security.ingest import IngestError, ingest_file, ingest_pasted_text, ingest_url

BACKEND_DIR = Path(__file__).resolve().parent
SRC_DIR = BACKEND_DIR.parents[1]
AGENTS_DIR = BACKEND_DIR / "agents_root"
FRONTEND_DIST = SRC_DIR / "frontend" / "dist"

app = get_fast_api_app(
    agents_dir=str(AGENTS_DIR),
    web=False,
    a2a=False,
    # Allow Vite's fallback dev ports without opening CORS beyond localhost.
    allow_origins=[r"regex:^https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$"],
)


@app.post("/ingest/terms")
async def ingest_terms(
    method: str = Form(...),
    text: str | None = Form(None),
    url: str | None = Form(None),
    file: UploadFile | None = None,
):
    """Extract clean T&C text before it reaches a model.

    The production UI currently uses pasted terms only. URL/file methods are
    retained as hardened backend helpers for future UI expansion. Kept as a
    plain REST endpoint (not a model tool) so ingestion -- and its SSRF guard,
    size caps, and content-type checks -- always runs before untrusted content
    reaches an LLM.
    """
    try:
        if method == "pasted":
            return {"text": ingest_pasted_text(text or "")}
        if method == "url":
            return {"text": ingest_url(url or "")}
        if method == "upload":
            if file is None:
                raise HTTPException(400, "No file provided.")
            data = await file.read()
            return {"text": ingest_file(file.filename or "upload", data)}
        raise HTTPException(400, f"Unknown method {method!r} (expected pasted|url|upload).")
    except IngestError as e:
        raise HTTPException(400, str(e)) from e


if FRONTEND_DIST.exists():
    # Registered last so API routes win over the SPA catch-all.
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")
