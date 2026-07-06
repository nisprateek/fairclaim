"""T&C ingestion helpers, all converging on one untrusted-text path.

The active production UI currently uses pasted terms only. URL fetch and
file extraction remain available as hardened backend helpers for future UI
expansion, with size caps and (for URLs) an SSRF guard.

Known limitation: the hostname-block check and the actual httpx connection
are two separate DNS resolutions (TOCTOU gap) — this blocks the overwhelming
majority of real SSRF attempts (literal localhost/private/link-local/cloud
metadata URLs) but is not a fully pinned-connection guard. A custom httpx
transport that connects to the pre-resolved IP would close that gap; noted
as a hardening follow-up, not required for the MVP demo.
"""

from __future__ import annotations

import ipaddress
import socket
from io import BytesIO
from urllib.parse import urlparse

import httpx
from docx import Document as DocxDocument
from pypdf import PdfReader

MAX_BYTES = 2_000_000  # 2 MB
ALLOWED_CONTENT_TYPES = (
    "text/html",
    "text/plain",
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
)
FETCH_TIMEOUT_SECONDS = 10.0

_BLOCKED_HOSTS = {"localhost", "metadata.google.internal"}


class IngestError(ValueError):
    """Raised when T&C content can't be safely ingested."""


def _is_blocked_address(host: str) -> bool:
    if host.lower() in _BLOCKED_HOSTS:
        return True
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return True  # can't resolve -> refuse rather than risk it
    for _family, _type, _proto, _canon, sockaddr in infos:
        ip = ipaddress.ip_address(sockaddr[0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
            return True
    return False


def ingest_pasted_text(text: str) -> str:
    if not text or not text.strip():
        raise IngestError("Pasted terms and conditions text is empty.")
    return text[:MAX_BYTES]


def ingest_url(url: str) -> str:
    """Fetch T&Cs from a live URL with an SSRF guard, timeout, and size cap."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise IngestError(f"Unsupported URL scheme: {parsed.scheme!r}")
    if not parsed.hostname:
        raise IngestError("URL has no hostname.")
    if _is_blocked_address(parsed.hostname):
        raise IngestError("This URL resolves to a private/local address and is blocked.")

    try:
        with httpx.Client(follow_redirects=True, timeout=FETCH_TIMEOUT_SECONDS) as client:
            with client.stream("GET", url) as response:
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").split(";")[0].strip()
                if content_type and content_type not in ALLOWED_CONTENT_TYPES:
                    raise IngestError(f"Unsupported content-type: {content_type!r}")
                # Re-check the *resolved* address after redirects, so a redirect
                # can't be used to bypass the initial hostname check.
                final_host = urlparse(str(response.url)).hostname
                if final_host and _is_blocked_address(final_host):
                    raise IngestError("Redirected to a private/local address; blocked.")
                chunks = []
                total = 0
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > MAX_BYTES:
                        raise IngestError(f"Response exceeded the {MAX_BYTES}-byte size cap.")
                    chunks.append(chunk)
    except httpx.HTTPStatusError as e:
        raise IngestError(
            f"That site returned an error ({e.response.status_code}) — it may be blocking "
            "automated requests. Try pasting the terms and conditions text instead."
        ) from e
    except httpx.TimeoutException as e:
        raise IngestError(f"That site took too long to respond (>{FETCH_TIMEOUT_SECONDS:.0f}s).") from e
    except httpx.RequestError as e:
        raise IngestError(f"Couldn't reach that URL: {e}") from e
    raw = b"".join(chunks)
    if content_type == "application/pdf":
        return _extract_pdf(raw)
    if content_type.endswith("wordprocessingml.document"):
        return _extract_docx(raw)
    return raw.decode("utf-8", errors="replace")


def ingest_file(filename: str, data: bytes) -> str:
    if len(data) > MAX_BYTES:
        raise IngestError(f"Uploaded file exceeds the {MAX_BYTES}-byte size cap.")
    lower = filename.lower()
    if lower.endswith(".pdf"):
        return _extract_pdf(data)
    if lower.endswith(".docx"):
        return _extract_docx(data)
    if lower.endswith(".txt"):
        return data.decode("utf-8", errors="replace")
    raise IngestError(f"Unsupported file type: {filename!r} (use .pdf, .docx, or .txt).")


def _extract_pdf(data: bytes) -> str:
    reader = PdfReader(BytesIO(data))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _extract_docx(data: bytes) -> str:
    doc = DocxDocument(BytesIO(data))
    return "\n".join(p.text for p in doc.paragraphs)
