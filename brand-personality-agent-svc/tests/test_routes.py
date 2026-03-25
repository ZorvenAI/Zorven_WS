"""Tests for BPV API routes."""

import pytest


class TestHealthEndpoint:
    """Test /health endpoint."""

    async def test_health_returns_ok(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["service"] == "brand-personality-agent"


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

    async def test_execute_with_empty_prompt(self, client, service_token_headers):
        payload = {"input_prompt": ""}
        resp = await client.post(
            "/v1/execute",
            json=payload,
            headers=service_token_headers,
        )
        assert resp.status_code == 200


class TestPersonalityEndpoint:
    """Test /v1/personality alias endpoint."""

    async def test_personality_requires_auth(self, client, valid_execute_payload):
        resp = await client.post("/v1/personality", json=valid_execute_payload)
        assert resp.status_code == 422

    async def test_personality_accepts_valid_token(
        self, client, valid_execute_payload, service_token_headers
    ):
        resp = await client.post(
            "/v1/personality",
            json=valid_execute_payload,
            headers=service_token_headers,
        )
        assert resp.status_code == 200
