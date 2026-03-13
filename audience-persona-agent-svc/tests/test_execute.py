"""Tests for the execute and personas endpoints."""

import pytest


class TestExecuteEndpoint:
    async def test_execute_requires_auth(self, client):
        """Execute endpoint returns 422 without service token."""
        response = await client.post("/v1/execute", json={})
        assert response.status_code == 422

    async def test_execute_rejects_bad_token(self, client):
        """Execute endpoint returns 403 with invalid token."""
        response = await client.post(
            "/v1/execute",
            json={"input_prompt": "test"},
            headers={"X-Service-Token": "bad-token"},
        )
        assert response.status_code == 403

    async def test_execute_returns_response(
        self, client, service_token_headers, valid_execute_payload
    ):
        """Execute endpoint returns a response with valid auth."""
        response = await client.post(
            "/v1/execute",
            json=valid_execute_payload,
            headers=service_token_headers,
        )
        assert response.status_code == 200
        data = response.json()
        # Should have standard response fields
        assert "query" in data or "findings" in data

    async def test_execute_with_empty_prompt(self, client, service_token_headers):
        """Execute with empty prompt still returns 200 (stub or guardrail)."""
        response = await client.post(
            "/v1/execute",
            json={"input_prompt": ""},
            headers=service_token_headers,
        )
        assert response.status_code == 200


class TestPersonasEndpoint:
    async def test_personas_requires_auth(self, client):
        """Personas endpoint requires service token."""
        response = await client.post("/v1/personas", json={})
        assert response.status_code == 422

    async def test_personas_returns_response(
        self, client, service_token_headers, valid_execute_payload
    ):
        """Personas endpoint returns a response."""
        response = await client.post(
            "/v1/personas",
            json=valid_execute_payload,
            headers=service_token_headers,
        )
        assert response.status_code == 200


class TestExecuteWithUpstreamOutputs:
    async def test_execute_with_mra_cia_outputs(
        self, client, service_token_headers, valid_payload_with_mra_outputs
    ):
        """Execute with MRA+CIA previous_outputs."""
        response = await client.post(
            "/v1/execute",
            json=valid_payload_with_mra_outputs,
            headers=service_token_headers,
        )
        assert response.status_code == 200
