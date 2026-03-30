"""Tests for CAA API routes."""

import pytest


class TestHealthEndpoint:
    """Test /health endpoint."""

    async def test_health_returns_ok(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    async def test_health_includes_service_name(self, client):
        resp = await client.get("/health")
        data = resp.json()
        assert data["service"] == "campaign-architecture-agent"


class TestExecuteEndpoint:
    """Test /v1/execute endpoint."""

    async def test_execute_requires_auth(self, client, sample_execute_request):
        resp = await client.post("/v1/execute", json=sample_execute_request)
        assert resp.status_code == 401

    async def test_execute_missing_token_401(self, client, sample_execute_request):
        resp = await client.post(
            "/v1/execute",
            json=sample_execute_request,
            headers={"X-Service-Token": ""},
        )
        assert resp.status_code == 401

    async def test_execute_wrong_token_401(self, client, sample_execute_request):
        resp = await client.post(
            "/v1/execute",
            json=sample_execute_request,
            headers={"X-Service-Token": "wrong-token"},
        )
        assert resp.status_code == 401

    async def test_execute_returns_stub_response(
        self, client, sample_execute_request, auth_headers
    ):
        """When executor is not initialised, stub response is returned."""
        resp = await client.post(
            "/v1/execute",
            json=sample_execute_request,
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["blueprint"] == {}
        assert data["funnel_map"] == {}
        assert data["confidence_score"] == 0.0
        assert data["meta_api_compatible"] is False
        assert "query" in data

    async def test_execute_empty_prompt_422(self, client, auth_headers):
        payload = {}
        resp = await client.post(
            "/v1/execute",
            json=payload,
            headers=auth_headers,
        )
        # Empty payload is valid because all fields have defaults
        assert resp.status_code == 200


class TestCampaignBlueprintAlias:
    """Test /v1/campaign-blueprint alias endpoint."""

    async def test_campaign_blueprint_alias_works(
        self, client, sample_execute_request, auth_headers
    ):
        resp = await client.post(
            "/v1/campaign-blueprint",
            json=sample_execute_request,
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "query" in data
        assert "blueprint" in data
