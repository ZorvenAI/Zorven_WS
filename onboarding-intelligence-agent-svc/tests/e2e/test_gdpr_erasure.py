"""N-01 AC-1 · GDPR erasure cascade across all artefact types.

Exercises ``DELETE /v1/admin/erasure`` against real Redis, seeding all
nine session-scoped key types and verifying complete deletion.
"""

from __future__ import annotations

import pytest
import redis as sync_redis
from starlette.testclient import TestClient

from app.cache.redis_manager import TenantKeys
from tests.conftest import REDIS_URL

pytestmark = pytest.mark.e2e


@pytest.fixture
def client(app_with_live_redis):
    with TestClient(app_with_live_redis) as c:
        yield c


@pytest.fixture
def service_token(app_with_live_redis):
    return app_with_live_redis.state.settings.SERVICE_TOKEN


def _seed_all_nine(r: sync_redis.Redis, keys: TenantKeys, sid: str) -> list[str]:
    """Seed all nine session-scoped key types and return the keys."""
    key_list = [
        keys.session(sid),
        keys.session_summary(sid),
        keys.transcript(sid),
        keys.questions(sid),
        keys.coverage(sid),
        keys.live_frames(sid),
        keys.unmapped(sid),
        keys.live_seq(sid),
        keys.outbox(sid),
    ]
    for k in key_list:
        r.set(k, "test-data")
    return key_list


class TestErasureAllKeyTypes:
    def test_erasure_deletes_all_nine_key_types(self, client, service_token):
        """Every session-scoped key type is deleted by the erasure endpoint."""
        tenant_id = "erasure-e2e-nine"
        sid = "sess-nine-001"
        keys = TenantKeys(tenant_id)

        r = sync_redis.Redis.from_url(REDIS_URL)
        key_list = _seed_all_nine(r, keys, sid)

        resp = client.request(
            "DELETE",
            "/v1/admin/erasure",
            json={"tenant_id": tenant_id, "session_ids": [sid]},
            headers={"X-Service-Token": service_token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 9

        for k in key_list:
            assert r.exists(k) == 0, f"key should be deleted: {k}"
        r.close()

    def test_non_session_keys_survive_erasure(self, client, service_token):
        """Ratelimit and config keys must not be deleted by session erasure."""
        tenant_id = "erasure-e2e-survive"
        sid = "sess-survive-001"
        keys = TenantKeys(tenant_id)

        r = sync_redis.Redis.from_url(REDIS_URL)
        _seed_all_nine(r, keys, sid)

        rl_key = keys.ratelimit("user-1")
        cfg_key = keys.config()
        r.set(rl_key, "5")
        r.set(cfg_key, "cfg")

        resp = client.request(
            "DELETE",
            "/v1/admin/erasure",
            json={"tenant_id": tenant_id, "session_ids": [sid]},
            headers={"X-Service-Token": service_token},
        )
        assert resp.status_code == 200

        assert r.exists(rl_key) == 1, "ratelimit key should survive"
        assert r.exists(cfg_key) == 1, "config key should survive"
        r.close()

    def test_erasure_is_tenant_isolated(self, client, service_token):
        """Erasing tenant A's data must not touch tenant B's keys."""
        sid = "sess-iso-001"
        keys_a = TenantKeys("erasure-e2e-iso-a")
        keys_b = TenantKeys("erasure-e2e-iso-b")

        r = sync_redis.Redis.from_url(REDIS_URL)
        _seed_all_nine(r, keys_a, sid)
        _seed_all_nine(r, keys_b, sid)

        resp = client.request(
            "DELETE",
            "/v1/admin/erasure",
            json={"tenant_id": "erasure-e2e-iso-a", "session_ids": [sid]},
            headers={"X-Service-Token": service_token},
        )
        assert resp.status_code == 200

        assert r.exists(keys_a.session(sid)) == 0
        assert r.exists(keys_b.session(sid)) == 1, "tenant B data must survive"
        assert r.exists(keys_b.transcript(sid)) == 1
        r.close()

    def test_scan_fallback_catches_custom_keys(self, client, service_token):
        """SCAN catches keys not in the explicit nine-key list."""
        tenant_id = "erasure-e2e-scan"
        sid = "sess-scan-001"
        extra_key = f"oia:v1:{tenant_id}:custom_type:{sid}:extra"

        r = sync_redis.Redis.from_url(REDIS_URL)
        r.set(extra_key, "custom-data")

        resp = client.request(
            "DELETE",
            "/v1/admin/erasure",
            json={"tenant_id": tenant_id, "session_ids": [sid]},
            headers={"X-Service-Token": service_token},
        )
        assert resp.status_code == 200
        assert r.exists(extra_key) == 0, "SCAN should catch custom-format keys"
        r.close()
