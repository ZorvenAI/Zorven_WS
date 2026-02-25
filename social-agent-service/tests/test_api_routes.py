"""Tests for FastAPI route handlers."""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient


class TestHealthEndpoint:
    async def test_health_returns_ok(self, client: AsyncClient):
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["version"] == "0.1.0"


class TestExecuteEndpoint:
    async def test_execute_returns_200(
        self,
        client: AsyncClient,
        valid_execute_payload: dict[str, Any],
        tenant_headers: dict[str, str],
    ):
        resp = await client.post(
            "/v1/execute",
            json=valid_execute_payload,
            headers=tenant_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "findings" in data
        assert "adapted_posts" in data

    async def test_execute_missing_prompt_returns_422(
        self,
        client: AsyncClient,
        tenant_headers: dict[str, str],
    ):
        resp = await client.post(
            "/v1/execute",
            json={"config": {}},
            headers=tenant_headers,
        )
        assert resp.status_code == 422
