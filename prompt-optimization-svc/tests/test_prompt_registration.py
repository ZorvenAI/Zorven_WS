"""Tests for POST /v1/prompts registration endpoint (US-006).

Updated for US-043 RBAC enforcement — all requests include X-User-Role header.
"""

import pytest
from httpx import ASGITransport, AsyncClient

ADMIN_HEADERS = {"X-User-Role": "admin"}


@pytest.fixture
async def client():
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestPromptRegistration:
    async def test_register_valid_prompt(self, client):
        resp = await client.post(
            "/v1/prompts",
            json={"name": "zorven-wf1-mra-landscape", "template": "Test"},
            headers=ADMIN_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "zorven-wf1-mra-landscape"

    async def test_register_system_prompt(self, client):
        resp = await client.post(
            "/v1/prompts",
            json={"name": "zorven-wf2-bpa-system", "template": "System"},
            headers=ADMIN_HEADERS,
        )
        assert resp.status_code == 200

    async def test_register_planner_prompt(self, client):
        resp = await client.post(
            "/v1/prompts",
            json={"name": "zorven-wf3-coa-planner", "template": "Planner"},
            headers=ADMIN_HEADERS,
        )
        assert resp.status_code == 200

    async def test_register_variant_prompt(self, client):
        resp = await client.post(
            "/v1/prompts",
            json={"name": "zorven-wf3-cga-creative-v2", "template": "Variant"},
            headers=ADMIN_HEADERS,
        )
        assert resp.status_code == 200

    async def test_register_with_metadata(self, client):
        resp = await client.post(
            "/v1/prompts",
            json={
                "name": "zorven-wf1-mra-landscape",
                "template": "T",
                "metadata": {"model_target": "claude-sonnet-4"},
            },
            headers=ADMIN_HEADERS,
        )
        assert resp.status_code == 200

    async def test_invalid_name_returns_400(self, client):
        resp = await client.post(
            "/v1/prompts",
            json={"name": "bad-name", "template": "T"},
            headers=ADMIN_HEADERS,
        )
        assert resp.status_code == 400
        assert "errors" in resp.json()

    async def test_invalid_name_corrective_message(self, client):
        resp = await client.post(
            "/v1/prompts",
            json={"name": "wf1-mra-landscape", "template": "T"},
            headers=ADMIN_HEADERS,
        )
        assert resp.status_code == 400

    async def test_wrong_workflow_agent_returns_400(self, client):
        resp = await client.post(
            "/v1/prompts",
            json={"name": "zorven-wf1-bpa-positioning", "template": "T"},
            headers=ADMIN_HEADERS,
        )
        assert resp.status_code == 400

    async def test_missing_template_returns_400(self, client):
        resp = await client.post(
            "/v1/prompts",
            json={"name": "zorven-wf1-mra-landscape"},
            headers=ADMIN_HEADERS,
        )
        assert resp.status_code == 400
