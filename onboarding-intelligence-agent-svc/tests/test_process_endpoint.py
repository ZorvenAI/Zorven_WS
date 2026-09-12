"""J-01 — OIA process endpoint tests.

No mocks: real Redis for idempotency, real HTTP for the endpoint.
"""

import pytest
from fastapi.testclient import TestClient

SERVICE_TOKEN = "test-service-token"

pytestmark = pytest.mark.integration


def _headers(idempotency_key: str = "test-key-123") -> dict[str, str]:
    return {
        "X-Service-Token": SERVICE_TOKEN,
        "Idempotency-Key": idempotency_key,
    }


def _payload(session_id: str = "sess-1") -> dict:
    return {
        "tenant_context": {
            "tenant_id": "tenant-1",
            "user_id": "system",
            "role": "ADMIN",
            "trace_id": "test:1",
        },
        "session_id": session_id,
        "evidence_manifest": {
            "recordings": ["rec-1"],
            "media": [],
            "has_questionnaire": True,
            "has_transcript": True,
        },
        "options": {},
        "callback_url": (
            "http://localhost:8001/api/v1/onboarding"
            "/internal/sessions/1/process/callback/"
        ),
    }


@pytest.fixture
def client(app_with_live_redis):
    with TestClient(app_with_live_redis) as c:
        yield c


def test_process_returns_202_with_job_id(client):
    resp = client.post(
        "/v1/process",
        json=_payload(),
        headers=_headers("idem-202-test"),
    )
    assert resp.status_code == 202
    data = resp.json()
    assert "job_id" in data
    assert data["status"] == "ACCEPTED"
    assert data["estimated_duration_s"] > 0


def test_idempotent_request_returns_same_job(client):
    idem_key = "idem-same-test-unique"
    resp1 = client.post(
        "/v1/process",
        json=_payload("sess-idem"),
        headers=_headers(idem_key),
    )
    assert resp1.status_code == 202
    job_id_1 = resp1.json()["job_id"]

    resp2 = client.post(
        "/v1/process",
        json=_payload("sess-idem"),
        headers=_headers(idem_key),
    )
    assert resp2.status_code == 202
    assert resp2.json()["job_id"] == job_id_1


def test_missing_service_token_returns_401(client):
    resp = client.post(
        "/v1/process",
        json=_payload(),
        headers={"Idempotency-Key": "test"},
    )
    assert resp.status_code == 401


def test_missing_idempotency_key_returns_400(client):
    resp = client.post(
        "/v1/process",
        json=_payload(),
        headers={"X-Service-Token": SERVICE_TOKEN},
    )
    assert resp.status_code == 400


def test_invalid_manifest_returns_422(client):
    payload = _payload()
    payload["evidence_manifest"] = {"invalid_field": True}
    resp = client.post(
        "/v1/process",
        json=payload,
        headers=_headers("idem-422-test"),
    )
    assert resp.status_code == 422
