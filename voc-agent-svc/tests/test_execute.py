"""Tests for /v1/execute endpoint."""

import pytest
from unittest.mock import AsyncMock, patch

from app.api import routes


@pytest.mark.asyncio
async def test_execute_requires_service_token(client):
    """POST /v1/execute without X-Service-Token header returns 422/403."""
    resp = await client.post(
        "/v1/execute",
        json={
            "input_prompt": "Analyze feedback",
            "input_context": {"company_name": "TestCorp"},
            "tenant_context": {"tenant_id": "t1", "user_role": "EDITOR"},
            "config": {},
            "previous_outputs": {},
        },
    )
    # FastAPI returns 422 when required header is missing
    assert resp.status_code in (403, 422)


@pytest.mark.asyncio
async def test_execute_valid_request(client, service_token_headers):
    """POST /v1/execute with valid token, executor=None returns stub response."""
    # Ensure executor is None (lifespan not fully initialised in test)
    original = routes.executor
    routes.executor = None
    try:
        resp = await client.post(
            "/v1/execute",
            json={
                "input_prompt": "Analyze customer feedback for SaaS product",
                "input_context": {"company_name": "TestCorp"},
                "tenant_context": {
                    "tenant_id": "test-tenant",
                    "user_role": "EDITOR",
                },
                "config": {},
                "previous_outputs": {},
            },
            headers=service_token_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["query"] == "Analyze customer feedback for SaaS product"
        assert data["confidence_score"] == 0.0
        assert "stub" in data["findings"][0].lower() or "initializing" in data["findings"][0].lower()
    finally:
        routes.executor = original


@pytest.mark.asyncio
async def test_execute_accepts_empty_previous_outputs(
    client, service_token_headers
):
    """POST /v1/execute accepts empty previous_outputs without error."""
    original = routes.executor
    routes.executor = None
    try:
        resp = await client.post(
            "/v1/execute",
            json={
                "input_prompt": "VoC analysis",
                "input_context": {},
                "tenant_context": {"tenant_id": "t1"},
                "config": {},
                "previous_outputs": {},
            },
            headers=service_token_headers,
        )
        assert resp.status_code == 200
    finally:
        routes.executor = original
