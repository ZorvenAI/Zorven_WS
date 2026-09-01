"""M-02 · OIA erasure endpoint tests — real Redis."""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from app.cache.redis_manager import TenantKeys


@pytest.fixture
def client(app_with_live_redis):
    with TestClient(app_with_live_redis) as c:
        yield c


@pytest.fixture
def service_token(app_with_live_redis):
    return app_with_live_redis.state.settings.SERVICE_TOKEN


@pytest.mark.integration
class TestErasureDeletesKeys:
    def test_erasure_deletes_session_keys(self, client, service_token):
        tenant_id = "erasure-test-tenant"
        session_id = "sess-001"
        keys = TenantKeys(tenant_id)

        import redis as sync_redis

        r = sync_redis.Redis.from_url("redis://localhost:6379/2")
        r.set(keys.session(session_id), "data")
        r.set(keys.session_summary(session_id), "summary")
        r.set(keys.transcript(session_id), "transcript")

        resp = client.request(
            "DELETE",
            "/v1/admin/erasure",
            json={
                "tenant_id": tenant_id,
                "session_ids": [session_id],
            },
            headers={"X-Service-Token": service_token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 3

        assert r.exists(keys.session(session_id)) == 0
        assert r.exists(keys.session_summary(session_id)) == 0
        assert r.exists(keys.transcript(session_id)) == 0
        r.close()

    def test_erasure_scan_catches_unlisted_keys(self, client, service_token):
        tenant_id = "erasure-scan-tenant"
        session_id = "sess-scan-001"
        extra_key = f"oia:v1:{tenant_id}:custom:{session_id}:extra"

        import redis as sync_redis

        r = sync_redis.Redis.from_url("redis://localhost:6379/2")
        r.set(extra_key, "custom-data")

        resp = client.request(
            "DELETE",
            "/v1/admin/erasure",
            json={
                "tenant_id": tenant_id,
                "session_ids": [session_id],
            },
            headers={"X-Service-Token": service_token},
        )
        assert resp.status_code == 200
        assert r.exists(extra_key) == 0
        r.close()


class TestErasureAuth:
    def test_erasure_rejects_missing_token(self, client):
        resp = client.request(
            "DELETE",
            "/v1/admin/erasure",
            json={
                "tenant_id": "t",
                "session_ids": ["s"],
            },
        )
        assert resp.status_code == 401

    def test_erasure_rejects_wrong_token(self, client):
        resp = client.request(
            "DELETE",
            "/v1/admin/erasure",
            json={
                "tenant_id": "t",
                "session_ids": ["s"],
            },
            headers={"X-Service-Token": "wrong-token"},
        )
        assert resp.status_code == 401
