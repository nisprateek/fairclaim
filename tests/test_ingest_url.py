"""URL ingestion: SSRF guard, content-type allowlist, size cap, and redirect
re-check — all offline via httpx.MockTransport (no real network or DNS).
"""

import httpx
import pytest

from fairclaim.backend.security import ingest
from fairclaim.backend.security.ingest import MAX_BYTES, IngestError, _is_blocked_address, ingest_url


# ---------------------------------------------------------------------------
# _is_blocked_address — IP literals resolve without network, so these run
# offline. Every class the guard names must actually be caught.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "host",
    [
        "localhost",
        "metadata.google.internal",  # cloud metadata endpoint
        "127.0.0.1",  # loopback
        "10.0.0.8",  # RFC 1918 private
        "172.16.5.5",  # RFC 1918 private
        "192.168.1.1",  # RFC 1918 private
        "169.254.169.254",  # link-local (AWS/GCP metadata IP)
        "0.0.0.0",  # unspecified
        "::1",  # IPv6 loopback
        "definitely-not-a-real-host.invalid",  # unresolvable -> refuse
    ],
)
def test_private_and_unresolvable_hosts_are_blocked(host):
    assert _is_blocked_address(host) is True


def test_public_ip_literal_is_not_blocked():
    assert _is_blocked_address("8.8.8.8") is False


# ---------------------------------------------------------------------------
# URL validation before any request is made.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("url", ["ftp://example.com/terms", "file:///etc/passwd", "javascript:alert(1)"])
def test_non_http_schemes_rejected(url):
    with pytest.raises(IngestError, match="scheme"):
        ingest_url(url)


def test_url_without_hostname_rejected():
    with pytest.raises(IngestError, match="hostname"):
        ingest_url("http://")


def test_blocked_host_rejected_before_fetch():
    with pytest.raises(IngestError, match="private/local"):
        ingest_url("http://127.0.0.1/terms")


# ---------------------------------------------------------------------------
# Fetch behaviour, with the network mocked out. `client_with` swaps the
# module's httpx.Client for one pinned to a MockTransport, and the DNS guard
# is replaced by an explicit blocklist so tests never resolve real names.
# ---------------------------------------------------------------------------

def _mock_network(monkeypatch, handler, blocked_hosts=frozenset()):
    transport = httpx.MockTransport(handler)
    real_client = httpx.Client

    def client_with(**kwargs):
        return real_client(transport=transport, **kwargs)

    monkeypatch.setattr(ingest.httpx, "Client", client_with)
    monkeypatch.setattr(ingest, "_is_blocked_address", lambda host: host in blocked_hosts)


def test_html_fetch_returns_decoded_text(monkeypatch):
    def handler(request):
        return httpx.Response(200, text="No refunds on sale items.", headers={"content-type": "text/html; charset=utf-8"})

    _mock_network(monkeypatch, handler)
    assert ingest_url("https://example.com/terms") == "No refunds on sale items."


def test_unsupported_content_type_rejected(monkeypatch):
    def handler(request):
        return httpx.Response(200, json={"terms": "nope"}, headers={"content-type": "application/json"})

    _mock_network(monkeypatch, handler)
    with pytest.raises(IngestError, match="content-type"):
        ingest_url("https://example.com/terms.json")


def test_oversized_response_rejected_mid_stream(monkeypatch):
    def handler(request):
        return httpx.Response(200, content=b"x" * (MAX_BYTES + 1), headers={"content-type": "text/plain"})

    _mock_network(monkeypatch, handler)
    with pytest.raises(IngestError, match="size cap"):
        ingest_url("https://example.com/huge")


def test_redirect_to_private_address_rejected(monkeypatch):
    # The initial hostname passes, but the redirect target must be re-checked
    # against the *resolved* final address — a redirect is the classic SSRF
    # bypass of a pre-fetch hostname check.
    def handler(request):
        if request.url.host == "example.com":
            return httpx.Response(302, headers={"location": "http://127.0.0.1/latest/meta-data"})
        return httpx.Response(200, text="secret", headers={"content-type": "text/plain"})

    _mock_network(monkeypatch, handler, blocked_hosts={"127.0.0.1"})
    with pytest.raises(IngestError, match="Redirected"):
        ingest_url("https://example.com/terms")


def test_http_error_status_becomes_ingest_error(monkeypatch):
    def handler(request):
        return httpx.Response(403)

    _mock_network(monkeypatch, handler)
    with pytest.raises(IngestError, match="403"):
        ingest_url("https://example.com/terms")


def test_timeout_becomes_ingest_error(monkeypatch):
    def handler(request):
        raise httpx.ConnectTimeout("too slow")

    _mock_network(monkeypatch, handler)
    with pytest.raises(IngestError, match="too long"):
        ingest_url("https://example.com/terms")


def test_connection_error_becomes_ingest_error(monkeypatch):
    def handler(request):
        raise httpx.ConnectError("refused")

    _mock_network(monkeypatch, handler)
    with pytest.raises(IngestError, match="Couldn't reach"):
        ingest_url("https://example.com/terms")
