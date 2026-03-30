"""Tests for BSA API routes."""

import pytest


class TestHealthEndpoint:
    """Test /health endpoint."""

    async def test_health_returns_ok(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["service"] == "brand-story-agent"


class TestExecuteEndpoint:
    """Test /v1/execute endpoint."""

    async def test_execute_requires_auth(self, client, valid_execute_payload):
        resp = await client.post("/v1/execute", json=valid_execute_payload)
        assert resp.status_code == 422  # Missing X-Service-Token

    async def test_execute_rejects_invalid_token(self, client, valid_execute_payload):
        resp = await client.post(
            "/v1/execute",
            json=valid_execute_payload,
            headers={"X-Service-Token": "wrong-token"},
        )
        assert resp.status_code == 403

    async def test_execute_accepts_valid_token(
        self, client, valid_execute_payload, service_token_headers
    ):
        resp = await client.post(
            "/v1/execute",
            json=valid_execute_payload,
            headers=service_token_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "query" in data or "findings" in data

    async def test_execute_stub_response_when_no_executor(
        self, client, valid_execute_payload, service_token_headers
    ):
        """When executor is not initialised, stub response is returned."""
        resp = await client.post(
            "/v1/execute",
            json=valid_execute_payload,
            headers=service_token_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        # Stub returns empty origin_story, pitches, etc.
        assert data["origin_story"] == {}
        assert data["pitches"] == {}
        assert data["confidence_score"] == 0.0

    async def test_execute_with_empty_prompt(self, client, service_token_headers):
        payload = {"input_prompt": ""}
        resp = await client.post(
            "/v1/execute",
            json=payload,
            headers=service_token_headers,
        )
        assert resp.status_code == 200

    async def test_execute_with_full_context(
        self, client, valid_payload_with_context, service_token_headers
    ):
        resp = await client.post(
            "/v1/execute",
            json=valid_payload_with_context,
            headers=service_token_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "query" in data


class TestStoryEndpoint:
    """Test /v1/story alias endpoint."""

    async def test_story_requires_auth(self, client, valid_execute_payload):
        resp = await client.post("/v1/story", json=valid_execute_payload)
        assert resp.status_code == 422

    async def test_story_accepts_valid_token(
        self, client, valid_execute_payload, service_token_headers
    ):
        resp = await client.post(
            "/v1/story",
            json=valid_execute_payload,
            headers=service_token_headers,
        )
        assert resp.status_code == 200
