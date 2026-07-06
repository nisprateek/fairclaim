"""/ingest/terms endpoint, over the real app (backend.main).

The ingestion endpoint is deliberately a plain REST route so its guards run
before any content reaches a model — so exercise it exactly the way the
frontend does, over HTTP, including the error mapping (IngestError -> 400,
never a 500).
"""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    from fairclaim.backend.main import app

    with TestClient(app) as test_client:
        yield test_client


def test_pasted_terms_round_trip(client):
    response = client.post("/ingest/terms", data={"method": "pasted", "text": "No refunds."})
    assert response.status_code == 200
    assert response.json() == {"text": "No refunds."}


def test_empty_paste_is_a_400_not_a_500(client):
    response = client.post("/ingest/terms", data={"method": "pasted", "text": "   "})
    assert response.status_code == 400
    assert "empty" in response.json()["detail"]


def test_unknown_method_is_a_400(client):
    response = client.post("/ingest/terms", data={"method": "carrier_pigeon"})
    assert response.status_code == 400
    assert "carrier_pigeon" in response.json()["detail"]


def test_txt_upload_round_trip(client):
    response = client.post(
        "/ingest/terms",
        data={"method": "upload"},
        files={"file": ("terms.txt", b"All sales are final.", "text/plain")},
    )
    assert response.status_code == 200
    assert response.json() == {"text": "All sales are final."}


def test_upload_without_file_is_a_400(client):
    response = client.post("/ingest/terms", data={"method": "upload"})
    assert response.status_code == 400
    assert "No file" in response.json()["detail"]


def test_unsupported_upload_extension_is_a_400(client):
    response = client.post(
        "/ingest/terms",
        data={"method": "upload"},
        files={"file": ("terms.exe", b"MZ...", "application/octet-stream")},
    )
    assert response.status_code == 400
    assert "Unsupported file type" in response.json()["detail"]


def test_url_method_rejects_bad_scheme_without_network(client):
    response = client.post("/ingest/terms", data={"method": "url", "url": "ftp://example.com/terms"})
    assert response.status_code == 400
    assert "scheme" in response.json()["detail"]


def test_url_method_blocks_private_addresses(client):
    response = client.post(
        "/ingest/terms", data={"method": "url", "url": "http://169.254.169.254/latest/meta-data"}
    )
    assert response.status_code == 400
    assert "blocked" in response.json()["detail"]


def test_admin_routes_are_not_registered():
    from fairclaim.backend.main import app

    paths = {getattr(route, "path", "") for route in app.routes}
    assert not any(path.startswith("/admin") for path in paths)
