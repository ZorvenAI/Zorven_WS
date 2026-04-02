"""Tests for API routes."""

import pytest

from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def auth_headers():
    return {"X-Service-Token": "dev-service-token"}


class TestHealthEndpoint:
    async def test_health(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["service"] == "ad-publishing-agent"


class TestExecuteEndpoint:
    async def test_execute_requires_auth(self, client):
        resp = await client.post("/v1/execute", json={})
        assert resp.status_code == 422  # Missing X-Service-Token

    async def test_execute_invalid_token(self, client):
        resp = await client.post(
            "/v1/execute",
            json={"input_prompt": "test"},
            headers={"X-Service-Token": "wrong-token"},
        )
        assert resp.status_code == 403

    async def test_execute_stub_response(self, client, auth_headers):
        """When executor is not initialized, returns stub."""
        resp = await client.post(
            "/v1/execute",
            json={"input_prompt": "publish ads"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "awaiting_approval"
        assert data["approval_request_id"] == "stub-approval-id"


class TestApproveEndpoint:
    async def test_approve_requires_auth(self, client):
        resp = await client.post("/v1/approve", json={})
        assert resp.status_code == 422

    async def test_approve_not_initialized(self, client, auth_headers):
        resp = await client.post(
            "/v1/approve",
            json={
                "approval_request_id": "test-id",
                "decision": "approve_all",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "error"


class TestApprovalListEndpoints:
    async def test_list_approvals_not_initialized(self, client, auth_headers):
        resp = await client.get(
            "/v1/approvals/tenant-1",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_get_approval_not_initialized(self, client, auth_headers):
        resp = await client.get(
            "/v1/approvals/tenant-1/request-1",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "error" in data
