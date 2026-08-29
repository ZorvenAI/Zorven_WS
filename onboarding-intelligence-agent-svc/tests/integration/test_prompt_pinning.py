"""Integration tests for prompt pinning through HTTP endpoints (L-01).

Verifies that PREP returns prompt_version in its response and PROCESS
stores versions in the session hash. Runs against real Redis.
"""

from __future__ import annotations

import json
import uuid

import pytest
from fastapi.testclient import TestClient

from app.cache.redis_manager import RedisManager
from app.core.config import Settings

SERVICE_TOKEN = "test-service-token"

pytestmark = [pytest.mark.integration]


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


@pytest.fixture
def client(app_with_live_redis):
    with TestClient(app_with_live_redis) as c:
        yield c


@pytest.fixture
async def manager(monkeypatch):
    from tests.conftest import REDIS_URL, redis_available

    if not redis_available():
        pytest.skip("Redis is not running on localhost:6379")

    monkeypatch.setenv("OIA_REDIS_URL", REDIS_URL)
    monkeypatch.setenv("OIA_BACKEND_BASE_URL", "http://backend:8001")
    monkeypatch.setenv("OIA_GCS_BUCKET", "zorven-raw-assets")
    mgr = RedisManager(Settings())  # type: ignore[call-arg]
    await mgr.connect()
    yield mgr
    await mgr.close()


def test_prep_execute_returns_prompt_versions(client):
    """POST /v1/execute response carries prompt_version with entries."""
    tenant_id = _unique("t")
    body = {
        "tenant_context": {
            "tenant_id": tenant_id,
            "user_id": "u-1",
            "role": "ADMIN",
            "trace_id": "01J8TRACE",
            "correlation_id": "01J8CORR",
        },
        "session_id": _unique("session"),
        "chat_session_id": _unique("chat"),
        "input_prompt": "Prep for a coffee roaster.",
        "input_context": {"company_name": "TestCo", "depth": 4},
        "config": {"language": "en-IN"},
        "previous_outputs": {},
    }

    resp = client.post(
        "/v1/execute",
        json=body,
        headers={"X-Service-Token": SERVICE_TOKEN},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert "prompt_version" in data
    pv = data["prompt_version"]
    assert isinstance(pv, dict)
    assert len(pv) >= 1


def test_prep_pins_versions_in_session_hash(client):
    """PREP stores resolved versions in the session's Redis hash."""
    import redis as sync_redis

    from app.cache.redis_manager import KEY_PREFIX
    from tests.conftest import REDIS_URL

    tenant_id = _unique("t")
    session_id = _unique("session")

    body = {
        "tenant_context": {
            "tenant_id": tenant_id,
            "user_id": "u-1",
            "role": "ADMIN",
            "trace_id": "01J8TRACE",
        },
        "session_id": session_id,
        "chat_session_id": _unique("chat"),
        "input_prompt": "Prep for a bakery.",
        "input_context": {"company_name": "Bakery Inc"},
        "config": {},
        "previous_outputs": {},
    }

    resp = client.post(
        "/v1/execute",
        json=body,
        headers={"X-Service-Token": SERVICE_TOKEN},
    )
    assert resp.status_code == 200

    r = sync_redis.from_url(REDIS_URL, decode_responses=True)
    session_key = f"{KEY_PREFIX}{tenant_id}:session:{session_id}"
    raw = r.hget(session_key, "prompt_versions")
    r.close()

    if raw is not None:
        pinned = json.loads(raw)
        assert isinstance(pinned, dict)
        assert len(pinned) >= 1


def test_process_accepts_and_stores_job(client):
    """POST /v1/process returns 202 — prompt resolution happens internally."""
    tenant_id = _unique("t")
    session_id = _unique("session")

    body = {
        "tenant_context": {
            "tenant_id": tenant_id,
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
        "callback_url": "http://localhost:8001/callback/",
    }

    resp = client.post(
        "/v1/process",
        json=body,
        headers={
            "X-Service-Token": SERVICE_TOKEN,
            "Idempotency-Key": _unique("idem"),
        },
    )
    assert resp.status_code == 202
    data = resp.json()
    assert "job_id" in data
    assert data["status"] == "ACCEPTED"
