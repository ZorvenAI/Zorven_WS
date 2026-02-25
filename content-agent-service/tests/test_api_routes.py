"""Tests for API routes — health and execute endpoints."""

from typing import Any


class TestHealthEndpoint:
    """Health check endpoint tests."""

    async def test_health_endpoint(self, client) -> None:
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["version"] == "0.1.0"


class TestExecuteEndpoint:
    """POST /v1/execute endpoint tests."""

    async def test_execute_returns_blog(
        self, client, valid_execute_payload: dict[str, Any], tenant_headers
    ) -> None:
        response = await client.post(
            "/v1/execute",
            json=valid_execute_payload,
            headers=tenant_headers,
        )
        assert response.status_code == 200
        data = response.json()
        # Should have blog content (stub or real)
        assert "blog_content" in data
        assert isinstance(data["blog_content"], str)
        assert len(data["blog_content"]) > 0

    async def test_execute_with_missing_prompt_returns_422(
        self, client, tenant_headers
    ) -> None:
        response = await client.post(
            "/v1/execute",
            json={"config": {}},  # Missing required input_prompt
            headers=tenant_headers,
        )
        assert response.status_code == 422
