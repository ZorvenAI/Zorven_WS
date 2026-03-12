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
        assert "executive_summary" in data
        assert "competitors" in data
        assert "competitor_matrix" in data
        assert "positioning_gaps" in data
        assert "positioning_map" in data
        assert "benchmarking_report" in data
        assert "sources" in data
        assert "findings" in data
        assert "recommendations" in data
        assert "raw_context" in data
        assert "confidence_score" in data
        assert "methodology_notes" in data
        assert isinstance(data["competitors"], list)
        assert isinstance(data["sources"], list)
        assert isinstance(data["findings"], list)
        assert isinstance(data["recommendations"], list)

    async def test_execute_empty_body_returns_422(self, client: AsyncClient) -> None:
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
        assert response.status_code == 200

    async def test_execute_minimal_payload(self, client: AsyncClient) -> None:
        response = await client.post(
            "/v1/execute",
            json={"input_prompt": "test competitor query"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "test competitor query" in data["query"]


class TestAnalyzeAlias:
    """POST /v1/analyze tests — alias for /v1/execute."""

    async def test_analyze_returns_200(
        self,
        client: AsyncClient,
        valid_execute_payload: dict[str, Any],
        tenant_headers: dict[str, str],
    ) -> None:
        response = await client.post(
            "/v1/analyze",
            json=valid_execute_payload,
            headers=tenant_headers,
        )
        assert response.status_code == 200

    async def test_analyze_returns_same_shape_as_execute(
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
        analyze_response = await client.post(
            "/v1/analyze",
            json=valid_execute_payload,
            headers=tenant_headers,
        )
        execute_data = execute_response.json()
        analyze_data = analyze_response.json()
        assert set(execute_data.keys()) == set(analyze_data.keys())
        assert execute_data["query"] == analyze_data["query"]
