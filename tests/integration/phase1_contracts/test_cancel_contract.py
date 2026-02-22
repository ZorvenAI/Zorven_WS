"""Contract tests: Django -> Orchestrator cancel endpoint.

Validates the cancel flow and Redis flag setting.
"""

import redis.asyncio as aioredis
import pytest

from tests.integration.conftest import (
    ORCHESTRATOR_URL,
    REDIS_URL,
    make_job_id,
)


@pytest.mark.integration
class TestCancelContract:
    """POST /v1/jobs/{job_id}/cancel contract validation."""

    async def test_cancel_returns_200(self, http_client, service_headers):
        """Cancel endpoint returns 200 with {"status": "cancelled"}."""
        job_id = make_job_id()
        resp = await http_client.post(
            f"{ORCHESTRATOR_URL}/v1/jobs/{job_id}/cancel",
            headers=service_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "cancelled"

    async def test_cancel_sets_redis_flag(self, http_client, service_headers):
        """Cancel sets a cancel:{job_id} key in Redis."""
        job_id = make_job_id()
        resp = await http_client.post(
            f"{ORCHESTRATOR_URL}/v1/jobs/{job_id}/cancel",
            headers=service_headers,
        )
        assert resp.status_code == 200

        # Verify Redis flag (orchestrator uses DB 1)
        r = aioredis.from_url(f"{REDIS_URL}/1", decode_responses=True)
        try:
            flag = await r.get(f"cancel:{job_id}")
            assert flag is not None, f"cancel:{job_id} not found in Redis"
        finally:
            await r.aclose()

    async def test_cancel_rejects_bad_auth(self, http_client):
        """Cancel with wrong or missing auth returns 401/403."""
        job_id = make_job_id()

        # No auth header
        resp = await http_client.post(
            f"{ORCHESTRATOR_URL}/v1/jobs/{job_id}/cancel",
        )
        assert resp.status_code in (401, 403)

        # Wrong token
        resp = await http_client.post(
            f"{ORCHESTRATOR_URL}/v1/jobs/{job_id}/cancel",
            headers={"X-Service-Token": "wrong-token"},
        )
        assert resp.status_code in (401, 403)
