"""Tests for API routes — endpoint contracts and error handling."""

from typing import Any

from httpx import AsyncClient


class TestHealthEndpoint:
    """GET /health tests."""

    async def test_health_returns_200(self, async_client: AsyncClient) -> None:
        response = await async_client.get("/health")
        assert response.status_code == 200

    async def test_health_response_shape(self, async_client: AsyncClient) -> None:
        response = await async_client.get("/health")
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "trend-cultural-insights-agent"
        assert data["version"] == "1.0.0"

    async def test_health_no_auth_required(self, async_client: AsyncClient) -> None:
        """Health endpoint does not require X-Service-Token."""
        response = await async_client.get("/health")
        assert response.status_code == 200


class TestExecuteEndpoint:
    """POST /v1/execute tests."""

    async def test_execute_requires_auth(self, async_client: AsyncClient) -> None:
        """Execute endpoint returns 422 when X-Service-Token header is missing."""
        response = await async_client.post(
            "/v1/execute",
            json={"input_prompt": "test"},
        )
        assert response.status_code == 422

    async def test_execute_rejects_bad_token(self, async_client: AsyncClient) -> None:
        """Execute endpoint returns 403 with invalid service token."""
        response = await async_client.post(
            "/v1/execute",
            json={"input_prompt": "test"},
            headers={"X-Service-Token": "bad-token"},
        )
        assert response.status_code == 403

    async def test_execute_requires_tenant(
        self,
        async_client: AsyncClient,
    ) -> None:
        """Execute without X-Tenant-ID uses default 'default' tenant (not 400).

        The route defines X-Tenant-ID with a default value of 'default',
        so omitting it still succeeds.
        """
        response = await async_client.post(
            "/v1/execute",
            json={"input_prompt": "test"},
            headers={"X-Service-Token": "dev-service-token"},
        )
        # Should succeed with default tenant, not error
        assert response.status_code == 200

    async def test_execute_success(
        self,
        async_client: AsyncClient,
        service_token_headers: dict[str, str],
        valid_execute_payload: dict[str, Any],
    ) -> None:
        """Execute with valid payload returns 200."""
        response = await async_client.post(
            "/v1/execute",
            json=valid_execute_payload,
            headers=service_token_headers,
        )
        assert response.status_code == 200
        data = response.json()
        # Should have standard response fields (from analyzer or stub)
        assert isinstance(data, dict)

    async def test_execute_with_upstream_outputs(
        self,
        async_client: AsyncClient,
        service_token_headers: dict[str, str],
        valid_payload_with_upstream_outputs: dict[str, Any],
    ) -> None:
        """Execute with MRA+CIA+APA previous_outputs."""
        response = await async_client.post(
            "/v1/execute",
            json=valid_payload_with_upstream_outputs,
            headers=service_token_headers,
        )
        assert response.status_code == 200

    async def test_execute_empty_prompt(
        self,
        async_client: AsyncClient,
        service_token_headers: dict[str, str],
    ) -> None:
        """Execute with empty prompt still returns 200 (stub or guardrail)."""
        response = await async_client.post(
            "/v1/execute",
            json={"input_prompt": ""},
            headers=service_token_headers,
        )
        assert response.status_code == 200


class TestTrendsAlias:
    """POST /v1/trends tests — alias for /v1/execute."""

    async def test_trends_returns_200(
        self,
        async_client: AsyncClient,
        service_token_headers: dict[str, str],
        valid_execute_payload: dict[str, Any],
    ) -> None:
        """Trends alias endpoint returns 200 with valid auth."""
        response = await async_client.post(
            "/v1/trends",
            json=valid_execute_payload,
            headers=service_token_headers,
        )
        assert response.status_code == 200

    async def test_trends_same_shape_as_execute(
        self,
        async_client: AsyncClient,
        service_token_headers: dict[str, str],
        valid_execute_payload: dict[str, Any],
    ) -> None:
        """Trends alias returns same response shape as execute."""
        execute_response = await async_client.post(
            "/v1/execute",
            json=valid_execute_payload,
            headers=service_token_headers,
        )
        trends_response = await async_client.post(
            "/v1/trends",
            json=valid_execute_payload,
            headers=service_token_headers,
        )
        execute_data = execute_response.json()
        trends_data = trends_response.json()
        assert set(execute_data.keys()) == set(trends_data.keys())

    async def test_trends_requires_auth(self, async_client: AsyncClient) -> None:
        """Trends endpoint also requires X-Service-Token."""
        response = await async_client.post(
            "/v1/trends",
            json={"input_prompt": "test"},
        )
        assert response.status_code == 422
