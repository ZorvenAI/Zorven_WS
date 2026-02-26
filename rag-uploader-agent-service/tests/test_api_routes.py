"""Tests for API routes."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.api import routes
from app.api.schemas import ExecuteResponse
from app.main import app


class TestHealthEndpoint:
    """Tests for GET /health."""

    async def test_health_returns_ok(self):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["version"] == "0.1.0"


class TestExecuteEndpoint:
    """Tests for POST /v1/execute."""

    async def test_execute_stub_when_no_executor(self):
        # Ensure executor is None (stub mode)
        original = routes.executor
        routes.executor = None
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    "/v1/execute",
                    json={
                        "input_prompt": "Save to knowledge base",
                        "input_context": {},
                        "tenant_context": {},
                        "config": {},
                        "previous_outputs": {},
                    },
                    headers={"X-Tenant-ID": "test"},
                )
            assert response.status_code == 200
            data = response.json()
            assert "not fully initialized" in data["findings"][0]
        finally:
            routes.executor = original

    async def test_execute_missing_prompt_422(self):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/v1/execute",
                json={},  # Missing required input_prompt
            )
        assert response.status_code == 422
