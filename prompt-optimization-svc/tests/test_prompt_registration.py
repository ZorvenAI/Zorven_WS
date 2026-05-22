"""Tests for POST /v1/prompts registration endpoint."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def client():
    """Async test client for the FastAPI app."""
    with patch("app.cache.redis_manager.aioredis") as mock_aioredis:
        mock_redis = AsyncMock()
        mock_redis.ping.return_value = True
        mock_redis.aclose.return_value = None
        mock_aioredis.from_url.return_value = mock_redis

        from app.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


class TestPromptRegistration:
    """Test POST /v1/prompts endpoint."""

    async def test_register_valid_prompt(self, client):
        resp = await client.post(
            "/v1/prompts",
            json={
                "name": "zorven-wf1-mra-landscape",
                "template": "You are a market researcher...",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "zorven-wf1-mra-landscape"
        assert data["status"] == "registered"

    async def test_register_system_prompt(self, client):
        """AC-3: System prompts accepted."""
        resp = await client.post(
            "/v1/prompts",
            json={
                "name": "zorven-wf2-bpa-system",
                "template": "System prompt template",
            },
        )
        assert resp.status_code == 200

    async def test_register_planner_prompt(self, client):
        """AC-4: Planner prompts accepted."""
        resp = await client.post(
            "/v1/prompts",
            json={
                "name": "zorven-wf3-coa-planner",
                "template": "Planner prompt template",
            },
        )
        assert resp.status_code == 200

    async def test_register_variant_prompt(self, client):
        """AC-2: Variant suffix accepted."""
        resp = await client.post(
            "/v1/prompts",
            json={
                "name": "zorven-wf3-cga-creative-v2",
                "template": "Variant template",
            },
        )
        assert resp.status_code == 200

    async def test_register_with_metadata(self, client):
        resp = await client.post(
            "/v1/prompts",
            json={
                "name": "zorven-wf1-mra-landscape",
                "template": "Template",
                "metadata": {"model_target": "claude-sonnet-4"},
            },
        )
        assert resp.status_code == 200

    async def test_invalid_name_returns_400(self, client):
        """AC-5: Invalid names rejected with 400 and corrective message."""
        resp = await client.post(
            "/v1/prompts",
            json={
                "name": "bad-name",
                "template": "Template",
            },
        )
        assert resp.status_code == 400
        data = resp.json()
        assert "errors" in data
        assert any("name" in e["field"] for e in data["errors"])

    async def test_invalid_name_corrective_message(self, client):
        """AC-5: Response includes corrective guidance."""
        resp = await client.post(
            "/v1/prompts",
            json={
                "name": "wf1-mra-landscape",
                "template": "Template",
            },
        )
        assert resp.status_code == 400
        data = resp.json()
        error_msg = data["errors"][0]["message"]
        assert "zorven-wf" in error_msg.lower() or "format" in error_msg.lower()

    async def test_wrong_workflow_agent_returns_400(self, client):
        resp = await client.post(
            "/v1/prompts",
            json={
                "name": "zorven-wf1-bpa-positioning",
                "template": "Template",
            },
        )
        assert resp.status_code == 400

    async def test_missing_template_returns_400(self, client):
        resp = await client.post(
            "/v1/prompts",
            json={"name": "zorven-wf1-mra-landscape"},
        )
        assert resp.status_code == 400
