"""Tests for API routes and response shapes."""

import pytest


class TestHealthEndpoint:
    """Verify /health endpoint."""

    async def test_health_returns_200(self, client):
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data


class TestISOCalcEndpoint:
    """Verify POST /v1/iso-calc endpoint."""

    async def test_iso_calc_returns_valuation(
        self, client, valid_iso_calc_payload, tenant_headers
    ):
        response = await client.post(
            "/v1/iso-calc",
            json=valid_iso_calc_payload,
            headers=tenant_headers,
        )
        assert response.status_code == 200
        data = response.json()

        # Must include findings + recommendations for ManagerNode
        assert "findings" in data
        assert "recommendations" in data
        assert len(data["findings"]) > 0
        assert len(data["recommendations"]) > 0

        # Valuation-specific fields
        assert data["methodology"] == "royalty_relief"
        assert data["analysis_type"] == "iso_valuation"
        assert data["valuation"] is not None
        assert data["valuation"]["brand_value_npv"] > 0
        assert data["bsi"] is not None

    async def test_iso_calc_default_method(self, client, tenant_headers):
        """POST /v1/iso-calc without method in config defaults to royalty_relief."""
        payload = {
            "input_prompt": "Calculate brand value",
            "config": {},
        }
        response = await client.post(
            "/v1/iso-calc",
            json=payload,
            headers=tenant_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["methodology"] == "royalty_relief"

    async def test_iso_calc_no_tenant_header_uses_default(self, client):
        """Missing X-Tenant-ID header should use default."""
        payload = {
            "input_prompt": "Calculate brand value",
            "config": {"method": "royalty_relief"},
        }
        response = await client.post("/v1/iso-calc", json=payload)
        assert response.status_code == 200


class TestAnalyzeEndpoint:
    """Verify POST /v1/analyze endpoint."""

    async def test_analyze_returns_gap_analysis(
        self, client, valid_gap_analysis_payload, tenant_headers
    ):
        response = await client.post(
            "/v1/analyze",
            json=valid_gap_analysis_payload,
            headers=tenant_headers,
        )
        assert response.status_code == 200
        data = response.json()

        assert "findings" in data
        assert "recommendations" in data
        assert len(data["findings"]) > 0
        assert data["analysis_type"] == "competitive_gap"
        assert data["gap_analysis"] is not None

    async def test_analyze_default_type(self, client, tenant_headers):
        """POST /v1/analyze without analysis_type defaults to competitive_gap."""
        payload = {
            "input_prompt": "Analyze gaps",
            "config": {},
            "previous_outputs": {
                "research": {"findings": ["Market is growing"]}
            },
        }
        response = await client.post(
            "/v1/analyze",
            json=payload,
            headers=tenant_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["analysis_type"] == "competitive_gap"


class TestExecuteEndpoint:
    """Verify POST /v1/execute endpoint."""

    async def test_execute_iso_routing(
        self, client, valid_iso_calc_payload, tenant_headers
    ):
        """Execute with method=royalty_relief routes to ISO valuation."""
        response = await client.post(
            "/v1/execute",
            json=valid_iso_calc_payload,
            headers=tenant_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["analysis_type"] == "iso_valuation"

    async def test_execute_gap_routing(
        self, client, valid_gap_analysis_payload, tenant_headers
    ):
        """Execute with analysis_type=competitive_gap routes to gap analysis."""
        response = await client.post(
            "/v1/execute",
            json=valid_gap_analysis_payload,
            headers=tenant_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["analysis_type"] == "competitive_gap"

    async def test_execute_general_fallback(self, client, tenant_headers):
        """Execute with no specific config → general analysis."""
        payload = {
            "input_prompt": "Analyze the market trends",
            "previous_outputs": {
                "web": {"findings": ["Revenue growth 10%"]}
            },
        }
        response = await client.post(
            "/v1/execute",
            json=payload,
            headers=tenant_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["analysis_type"] == "general"


class TestResponseShape:
    """Verify response always includes ManagerNode-required fields."""

    async def test_response_always_has_findings(self, client, tenant_headers):
        """All endpoints must return findings list."""
        for endpoint in ["/v1/execute", "/v1/iso-calc", "/v1/analyze"]:
            payload = {
                "input_prompt": "Test",
                "previous_outputs": {
                    "n": {"findings": ["test finding"]}
                },
            }
            response = await client.post(
                endpoint, json=payload, headers=tenant_headers
            )
            data = response.json()
            assert isinstance(data["findings"], list), (
                f"{endpoint} did not return findings as list"
            )

    async def test_response_always_has_recommendations(
        self, client, tenant_headers
    ):
        """All endpoints must return recommendations list."""
        for endpoint in ["/v1/execute", "/v1/iso-calc", "/v1/analyze"]:
            payload = {
                "input_prompt": "Test",
                "previous_outputs": {
                    "n": {"findings": ["test finding"]}
                },
            }
            response = await client.post(
                endpoint, json=payload, headers=tenant_headers
            )
            data = response.json()
            assert isinstance(data["recommendations"], list), (
                f"{endpoint} did not return recommendations as list"
            )
