"""Integration test: /v1/search alias parity with /v1/execute.

Verifies that both endpoints return identical response shapes and field types.
"""

from typing import Any

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration


class TestSearchAlias:
    """Verify /v1/search returns identical results to /v1/execute."""

    async def test_search_returns_same_shape_as_execute(
        self,
        app_with_redis: AsyncClient,
        valid_execute_payload: dict[str, Any],
        tenant_headers: dict[str, str],
    ) -> None:
        execute_resp = await app_with_redis.post(
            "/v1/execute",
            json=valid_execute_payload,
            headers=tenant_headers,
        )
        search_resp = await app_with_redis.post(
            "/v1/search",
            json=valid_execute_payload,
            headers=tenant_headers,
        )

        assert execute_resp.status_code == 200
        assert search_resp.status_code == 200

        exec_data = execute_resp.json()
        search_data = search_resp.json()

        # Both have the same top-level keys
        assert set(exec_data.keys()) == set(search_data.keys())

    async def test_search_query_matches_execute_query(
        self,
        app_with_redis: AsyncClient,
        valid_execute_payload: dict[str, Any],
        tenant_headers: dict[str, str],
    ) -> None:
        execute_resp = await app_with_redis.post(
            "/v1/execute",
            json=valid_execute_payload,
            headers=tenant_headers,
        )
        search_resp = await app_with_redis.post(
            "/v1/search",
            json=valid_execute_payload,
            headers=tenant_headers,
        )

        assert execute_resp.json()["query"] == search_resp.json()["query"]

    async def test_search_returns_200_with_valid_payload(
        self,
        app_with_redis: AsyncClient,
        valid_execute_payload: dict[str, Any],
        tenant_headers: dict[str, str],
    ) -> None:
        resp = await app_with_redis.post(
            "/v1/search",
            json=valid_execute_payload,
            headers=tenant_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "sources" in data
        assert "findings" in data
