"""Integration test: contract compatibility with pipeline-orchestrator-svc.

Verifies that the ExternalWrapper payload from the orchestrator is
accepted and that the response matches what ManagerNode and
BrandEquityDashboard expect.
"""

from typing import Any

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration


class TestOrchestratorContract:
    """Verify exact contract compatibility."""

    async def test_external_wrapper_payload_accepted(
        self,
        app_with_redis: AsyncClient,
    ) -> None:
        """Send the exact payload that ExternalWrapper constructs."""
        payload = {
            "input_prompt": "Analyze brand positioning for Acme Corp",
            "input_context": {"company_id": 42},
            "tenant_context": {
                "tenant_id": "1",
                "gcs_raw_bucket": "brand-automator/1/",
                "gcs_processed_bucket": "brand-automator-curated/1/",
                "rag_data_store_id": "ds-123",
            },
            "config": {"focus": "market_trends,competitors"},
            "previous_outputs": {},
        }
        resp = await app_with_redis.post(
            "/v1/execute",
            json=payload,
            headers={"X-Tenant-ID": "1"},
        )
        assert resp.status_code == 200

    async def test_response_storable_in_node_outputs(
        self,
        app_with_redis: AsyncClient,
        valid_execute_payload: dict[str, Any],
        tenant_headers: dict[str, str],
    ) -> None:
        """Response must be a valid JSON dict for node_outputs[node_id]."""
        resp = await app_with_redis.post(
            "/v1/execute",
            json=valid_execute_payload,
            headers=tenant_headers,
        )
        data = resp.json()
        assert isinstance(data, dict)

    async def test_response_has_findings_for_manager_node(
        self,
        app_with_redis: AsyncClient,
        valid_execute_payload: dict[str, Any],
        tenant_headers: dict[str, str],
    ) -> None:
        """ManagerNode aggregates 'findings' and 'recommendations' arrays."""
        resp = await app_with_redis.post(
            "/v1/execute",
            json=valid_execute_payload,
            headers=tenant_headers,
        )
        data = resp.json()
        assert "findings" in data
        assert "recommendations" in data
        assert isinstance(data["findings"], list)
        assert isinstance(data["recommendations"], list)

    async def test_response_has_sources_for_dashboard(
        self,
        app_with_redis: AsyncClient,
        valid_execute_payload: dict[str, Any],
        tenant_headers: dict[str, str],
    ) -> None:
        """BrandEquityDashboard renders sources with {type, title, url}."""
        resp = await app_with_redis.post(
            "/v1/execute",
            json=valid_execute_payload,
            headers=tenant_headers,
        )
        data = resp.json()
        for source in data["sources"]:
            assert "type" in source
            assert "title" in source
            assert "url" in source

    async def test_iso_brand_equity_focus(
        self,
        app_with_redis: AsyncClient,
        tenant_headers: dict[str, str],
    ) -> None:
        """iso-brand-equity manifest: royalty_rates,market_trends,brand_rankings."""
        payload = {
            "input_prompt": "ISO brand equity valuation",
            "config": {"focus": "royalty_rates,market_trends,brand_rankings"},
        }
        resp = await app_with_redis.post(
            "/v1/execute", json=payload, headers=tenant_headers
        )
        assert resp.status_code == 200
        query = resp.json()["query"]
        assert "royalty_rates" in query
        assert "market_trends" in query
        assert "brand_rankings" in query

    async def test_brand_analysis_focus(
        self,
        app_with_redis: AsyncClient,
        tenant_headers: dict[str, str],
    ) -> None:
        """brand-analysis manifest: market_trends,competitors."""
        payload = {
            "input_prompt": "Brand analysis for Acme Corp",
            "config": {"focus": "market_trends,competitors"},
        }
        resp = await app_with_redis.post(
            "/v1/execute", json=payload, headers=tenant_headers
        )
        assert resp.status_code == 200
        query = resp.json()["query"]
        assert "market_trends" in query
        assert "competitors" in query

    async def test_competitor_audit_focus(
        self,
        app_with_redis: AsyncClient,
        tenant_headers: dict[str, str],
    ) -> None:
        """competitor-audit manifest: competitors,market_share."""
        payload = {
            "input_prompt": "Competitor audit for Acme Corp",
            "config": {"focus": "competitors,market_share"},
        }
        resp = await app_with_redis.post(
            "/v1/execute", json=payload, headers=tenant_headers
        )
        assert resp.status_code == 200
        query = resp.json()["query"]
        assert "competitors" in query
        assert "market_share" in query

    async def test_search_endpoint_also_works(
        self,
        app_with_redis: AsyncClient,
        valid_execute_payload: dict[str, Any],
        tenant_headers: dict[str, str],
    ) -> None:
        """Seed manifests reference /v1/search, not /v1/execute."""
        resp = await app_with_redis.post(
            "/v1/search",
            json=valid_execute_payload,
            headers=tenant_headers,
        )
        assert resp.status_code == 200
        assert "findings" in resp.json()
