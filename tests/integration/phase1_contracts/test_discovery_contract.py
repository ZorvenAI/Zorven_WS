"""Contract tests: Orchestrator -> Discovery agent service.

Direct HTTP calls to discovery-agent-svc validating the ExecuteRequest
/ ExecuteResponse contract that ExternalWrapper depends on.
"""

import pytest

from tests.integration.conftest import (
    DISCOVERY_URL,
    make_agent_payload,
)


@pytest.mark.integration
class TestDiscoveryContract:
    """POST /v1/execute and /v1/search contract validation."""

    async def test_execute_returns_expected_schema(self, http_client, tenant_headers):
        """POST /v1/execute returns all required response fields."""
        payload = make_agent_payload(
            config={"focus": "market_trends,competitors"},
        )
        resp = await http_client.post(
            f"{DISCOVERY_URL}/v1/execute",
            json=payload,
            headers=tenant_headers,
        )
        assert resp.status_code == 200
        data = resp.json()

        # Required fields per ExecuteResponse schema
        assert "query" in data
        assert "sources" in data
        assert "findings" in data
        assert "recommendations" in data
        assert "raw_context" in data

        assert isinstance(data["query"], str)
        assert isinstance(data["sources"], list)
        assert isinstance(data["findings"], list)
        assert isinstance(data["recommendations"], list)
        assert isinstance(data["raw_context"], str)

    async def test_search_alias_accepted(self, http_client, tenant_headers):
        """POST /v1/search (seed manifest URL) returns same schema as /v1/execute."""
        payload = make_agent_payload(
            config={"focus": "market_trends,competitors"},
        )
        resp = await http_client.post(
            f"{DISCOVERY_URL}/v1/search",
            json=payload,
            headers=tenant_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "query" in data
        assert "sources" in data
        assert "findings" in data

    async def test_tenant_id_header_propagated(self, http_client):
        """X-Tenant-ID header is accepted without error."""
        payload = make_agent_payload()
        resp = await http_client.post(
            f"{DISCOVERY_URL}/v1/execute",
            json=payload,
            headers={
                "X-Tenant-ID": "tenant-42",
                "Content-Type": "application/json",
            },
        )
        assert resp.status_code == 200

    async def test_empty_config_uses_defaults(self, http_client, tenant_headers):
        """Missing config.focus still returns a valid response."""
        payload = make_agent_payload(config={})
        resp = await http_client.post(
            f"{DISCOVERY_URL}/v1/execute",
            json=payload,
            headers=tenant_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "findings" in data
        assert len(data["findings"]) > 0

    async def test_response_findings_are_strings(self, http_client, tenant_headers):
        """Each finding in the response is a plain string."""
        payload = make_agent_payload(
            config={"focus": "market_trends"},
        )
        resp = await http_client.post(
            f"{DISCOVERY_URL}/v1/execute",
            json=payload,
            headers=tenant_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        for finding in data["findings"]:
            assert isinstance(
                finding, str
            ), f"Finding is {type(finding).__name__}, expected str: {finding}"
