"""Tests for API routes — endpoint contracts and error handling."""

from typing import Any

from httpx import AsyncClient


class TestHealthEndpoint:
    """GET /health tests."""

    async def test_health_returns_200(self, client: AsyncClient) -> None:
        response = await client.get("/health")
        assert response.status_code == 200

    async def test_health_response_shape(self, client: AsyncClient) -> None:
        response = await client.get("/health")
        data = response.json()
        assert data["status"] == "ok"
        assert data["version"] == "0.1.0"


class TestExecuteEndpoint:
    """POST /v1/execute tests."""

    async def test_execute_returns_200(
        self,
        client: AsyncClient,
        valid_execute_payload: dict[str, Any],
        tenant_headers: dict[str, str],
    ) -> None:
        response = await client.post(
            "/v1/execute",
            json=valid_execute_payload,
            headers=tenant_headers,
        )
        assert response.status_code == 200

    async def test_execute_response_shape(
        self,
        client: AsyncClient,
        valid_execute_payload: dict[str, Any],
        tenant_headers: dict[str, str],
    ) -> None:
        response = await client.post(
            "/v1/execute",
            json=valid_execute_payload,
            headers=tenant_headers,
        )
        data = response.json()
        assert "query" in data
        assert "sources" in data
        assert "findings" in data
        assert "recommendations" in data
        assert "raw_context" in data
        assert isinstance(data["sources"], list)
        assert isinstance(data["findings"], list)
        assert isinstance(data["recommendations"], list)

    async def test_execute_builds_query_from_prompt_and_focus(
        self,
        client: AsyncClient,
        valid_execute_payload: dict[str, Any],
        tenant_headers: dict[str, str],
    ) -> None:
        response = await client.post(
            "/v1/execute",
            json=valid_execute_payload,
            headers=tenant_headers,
        )
        data = response.json()
        assert "Analyze brand positioning" in data["query"]
        assert "market_trends" in data["query"]
        assert "competitors" in data["query"]

    async def test_execute_sources_have_correct_shape(
        self,
        client: AsyncClient,
        valid_execute_payload: dict[str, Any],
        tenant_headers: dict[str, str],
    ) -> None:
        response = await client.post(
            "/v1/execute",
            json=valid_execute_payload,
            headers=tenant_headers,
        )
        data = response.json()
        for source in data["sources"]:
            assert "type" in source
            assert "title" in source
            assert "url" in source

    async def test_execute_empty_body_returns_422(
        self, client: AsyncClient
    ) -> None:
        response = await client.post("/v1/execute", content=b"")
        assert response.status_code == 422

    async def test_execute_missing_input_prompt_returns_422(
        self,
        client: AsyncClient,
        tenant_headers: dict[str, str],
    ) -> None:
        response = await client.post(
            "/v1/execute",
            json={"config": {"focus": "test"}},
            headers=tenant_headers,
        )
        assert response.status_code == 422

    async def test_execute_without_tenant_header_uses_default(
        self,
        client: AsyncClient,
        valid_execute_payload: dict[str, Any],
    ) -> None:
        response = await client.post(
            "/v1/execute",
            json=valid_execute_payload,
        )
        # Should still work with default tenant
        assert response.status_code == 200

    async def test_execute_minimal_payload(
        self, client: AsyncClient
    ) -> None:
        response = await client.post(
            "/v1/execute",
            json={"input_prompt": "test query"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "test query" in data["query"]


class TestSearchAlias:
    """POST /v1/search tests — alias for /v1/execute."""

    async def test_search_returns_200(
        self,
        client: AsyncClient,
        valid_execute_payload: dict[str, Any],
        tenant_headers: dict[str, str],
    ) -> None:
        response = await client.post(
            "/v1/search",
            json=valid_execute_payload,
            headers=tenant_headers,
        )
        assert response.status_code == 200

    async def test_search_returns_same_shape_as_execute(
        self,
        client: AsyncClient,
        valid_execute_payload: dict[str, Any],
        tenant_headers: dict[str, str],
    ) -> None:
        execute_response = await client.post(
            "/v1/execute",
            json=valid_execute_payload,
            headers=tenant_headers,
        )
        search_response = await client.post(
            "/v1/search",
            json=valid_execute_payload,
            headers=tenant_headers,
        )
        execute_data = execute_response.json()
        search_data = search_response.json()
        assert set(execute_data.keys()) == set(search_data.keys())
        assert execute_data["query"] == search_data["query"]


class TestSeedManifestFocusValues:
    """Verify all three config.focus values from seed manifests work."""

    async def test_iso_brand_equity_focus(
        self, client: AsyncClient
    ) -> None:
        response = await client.post(
            "/v1/search",
            json={
                "input_prompt": "Brand equity valuation",
                "config": {
                    "focus": "royalty_rates,market_trends,brand_rankings"
                },
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "royalty_rates" in data["query"]
        assert "market_trends" in data["query"]
        assert "brand_rankings" in data["query"]

    async def test_brand_analysis_focus(
        self, client: AsyncClient
    ) -> None:
        response = await client.post(
            "/v1/search",
            json={
                "input_prompt": "Brand positioning analysis",
                "config": {"focus": "market_trends,competitors"},
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "market_trends" in data["query"]
        assert "competitors" in data["query"]

    async def test_competitor_audit_focus(
        self, client: AsyncClient
    ) -> None:
        response = await client.post(
            "/v1/search",
            json={
                "input_prompt": "Competitor audit",
                "config": {"focus": "competitors,market_share"},
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "competitors" in data["query"]
        assert "market_share" in data["query"]
