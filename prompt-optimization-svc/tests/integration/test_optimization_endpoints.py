"""Integration tests for §13.2 optimization endpoints (US-044).

Requires real Redis and MLflow. Tests the full request path including
RBAC enforcement, pagination, GEPA trace fields, and response validation.

Run with: pytest tests/integration/test_optimization_endpoints.py -v -m integration
"""

import json

import pytest
from httpx import ASGITransport, AsyncClient

from tests.integration.conftest import requires_redis


@pytest.fixture
async def client():
    """Async test client with lifespan for full-stack testing."""
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def seeded_run(client):
    """Seed a fake optimization run into Redis for testing GET endpoints."""
    from app.cache.prompt_cache import PromptCacheManager
    from app.core.config import settings

    run_id = "integration-test-run-001"
    cache = PromptCacheManager(redis_url=settings.PROMPT_CACHE_REDIS_URL)
    r = await cache.connect()
    try:
        key = f"prompt:optimization:progress:{run_id}"
        await r.hset(
            key,
            mapping={
                "state": "PENDING_APPROVAL",
                "prompt_name": "zorven-wf1-mra-landscape",
                "agent_code": "mra",
                "score_before": "0.65",
                "score_after": "0.78",
                "improvement": "0.13",
                "cost_usd": "1.25",
                "gepa_traces": json.dumps(
                    [{"iteration": 1, "score": 0.78, "strategy": "rephrase"}]
                ),
                "reflection_prompts": json.dumps(
                    ["Improve clarity of market analysis instructions"]
                ),
                "updated_at": "2026-06-08T12:00:00Z",
            },
        )
        yield run_id
        # Cleanup
        await r.delete(key)
    finally:
        await cache.close()


@pytest.mark.integration
class TestOptimizationEndpointsIntegration:
    @requires_redis
    @pytest.mark.asyncio
    async def test_trigger_agent_optimization_as_admin(self, client):
        """Admin can trigger single-agent optimization."""
        resp = await client.post(
            "/v1/optimize/agent/mra",
            headers={"X-User-Role": "admin"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["agent_code"] == "mra"
        assert data["state"] == "QUEUED"
        assert data["prompt_count"] > 0

    @requires_redis
    @pytest.mark.asyncio
    async def test_trigger_group_optimization_as_admin(self, client):
        """Admin can trigger group optimization."""
        resp = await client.post(
            "/v1/optimize/group/wf1-discovery-pipeline",
            headers={"X-User-Role": "admin"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["group_name"] == "wf1-discovery-pipeline"
        assert data["prompt_count"] > 0

    @requires_redis
    @pytest.mark.asyncio
    async def test_trigger_platform_optimization_as_owner(self, client):
        """Owner can trigger platform-wide optimization (AC-1)."""
        resp = await client.post(
            "/v1/optimize/all",
            headers={"X-User-Role": "owner"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["groups_triggered"] > 0
        assert data["total_prompts"] > 0
        assert len(data["runs"]) > 0

    @requires_redis
    @pytest.mark.asyncio
    async def test_list_runs_as_viewer_with_pagination(self, client, seeded_run):
        """Viewer can list runs with pagination fields (AC-2)."""
        resp = await client.get(
            "/v1/optimize/runs?page=1&page_size=10",
            headers={"X-User-Role": "viewer"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "runs" in data
        assert "total" in data
        assert data["page"] == 1
        assert data["page_size"] == 10

    @requires_redis
    @pytest.mark.asyncio
    async def test_get_run_detail_with_gepa_traces(self, client, seeded_run):
        """Viewer can get run detail with GEPA traces and reflection prompts (AC-3)."""
        resp = await client.get(
            f"/v1/optimize/runs/{seeded_run}",
            headers={"X-User-Role": "viewer"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["run_id"] == seeded_run
        assert data["state"] == "PENDING_APPROVAL"
        assert data["prompt_name"] == "zorven-wf1-mra-landscape"
        # AC-2: metrics and cost
        assert data["score_before"] == 0.65
        assert data["score_after"] == 0.78
        assert data["improvement"] == 0.13
        assert data["cost_usd"] == 1.25
        # AC-3: GEPA traces
        assert len(data["gepa_traces"]) == 1
        assert data["gepa_traces"][0]["strategy"] == "rephrase"
        assert len(data["reflection_prompts"]) == 1

    @requires_redis
    @pytest.mark.asyncio
    async def test_viewer_blocked_from_optimize_agent(self, client):
        """Viewer cannot trigger agent optimization."""
        resp = await client.post(
            "/v1/optimize/agent/mra",
            headers={"X-User-Role": "viewer"},
        )
        assert resp.status_code == 403

    @requires_redis
    @pytest.mark.asyncio
    async def test_admin_blocked_from_optimize_all(self, client):
        """Admin cannot trigger platform-wide optimization (AC-1: OWNER-only)."""
        resp = await client.post(
            "/v1/optimize/all",
            headers={"X-User-Role": "admin"},
        )
        assert resp.status_code == 403

    @requires_redis
    @pytest.mark.asyncio
    async def test_viewer_blocked_from_approve(self, client, seeded_run):
        """Viewer cannot approve optimization runs."""
        resp = await client.post(
            f"/v1/optimize/runs/{seeded_run}/approve",
            json={"approved_by": "test-viewer"},
            headers={"X-User-Role": "viewer"},
        )
        assert resp.status_code == 403

    @requires_redis
    @pytest.mark.asyncio
    async def test_editor_blocked_from_reject(self, client, seeded_run):
        """Editor cannot reject optimization runs."""
        resp = await client.post(
            f"/v1/optimize/runs/{seeded_run}/reject",
            json={"approved_by": "test-editor", "reason": "Testing"},
            headers={"X-User-Role": "editor"},
        )
        assert resp.status_code == 403
