"""Integration test: full execute flow through the API.

Verifies that POST /v1/execute returns a valid ExecuteResponse
with all expected fields when backed by real Redis.
"""

from typing import Any

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration


class TestFullExecuteFlow:
    """End-to-end execute endpoint tests."""

    async def test_execute_returns_valid_response(
        self,
        app_with_redis: AsyncClient,
        valid_execute_payload: dict[str, Any],
        tenant_headers: dict[str, str],
    ) -> None:
        resp = await app_with_redis.post(
            "/v1/execute",
            json=valid_execute_payload,
            headers=tenant_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "query" in data
        assert "sources" in data
        assert "findings" in data
        assert "recommendations" in data
        assert "raw_context" in data

    async def test_execute_response_has_sources_with_correct_shape(
        self,
        app_with_redis: AsyncClient,
        valid_execute_payload: dict[str, Any],
        tenant_headers: dict[str, str],
    ) -> None:
        resp = await app_with_redis.post(
            "/v1/execute",
            json=valid_execute_payload,
            headers=tenant_headers,
        )
        data = resp.json()
        assert len(data["sources"]) > 0
        for source in data["sources"]:
            assert "type" in source
            assert "title" in source
            assert "url" in source

    async def test_execute_response_has_nonempty_findings(
        self,
        app_with_redis: AsyncClient,
        valid_execute_payload: dict[str, Any],
        tenant_headers: dict[str, str],
    ) -> None:
        resp = await app_with_redis.post(
            "/v1/execute",
            json=valid_execute_payload,
            headers=tenant_headers,
        )
        data = resp.json()
        assert isinstance(data["findings"], list)
        assert len(data["findings"]) > 0
        for finding in data["findings"]:
            assert isinstance(finding, str)

    async def test_execute_query_includes_focus_terms(
        self,
        app_with_redis: AsyncClient,
        valid_execute_payload: dict[str, Any],
        tenant_headers: dict[str, str],
    ) -> None:
        resp = await app_with_redis.post(
            "/v1/execute",
            json=valid_execute_payload,
            headers=tenant_headers,
        )
        data = resp.json()
        assert "market_trends" in data["query"]
        assert "competitors" in data["query"]

    async def test_execute_raw_context_is_nonempty(
        self,
        app_with_redis: AsyncClient,
        valid_execute_payload: dict[str, Any],
        tenant_headers: dict[str, str],
    ) -> None:
        resp = await app_with_redis.post(
            "/v1/execute",
            json=valid_execute_payload,
            headers=tenant_headers,
        )
        data = resp.json()
        assert isinstance(data["raw_context"], str)
        assert len(data["raw_context"]) > 0
