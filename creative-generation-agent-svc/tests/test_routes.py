"""Tests for CGA API routes."""

import pytest

from app.api.schemas import TenantContext


class TestHealthEndpoint:
    """Test /health endpoint."""

    async def test_health_returns_ok(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["service"] == "creative-generation-agent"

    async def test_health_no_auth_required(self, client):
        """Health endpoint must not require X-Service-Token."""
        resp = await client.get("/health")
        assert resp.status_code == 200


class TestExecuteEndpoint:
    """Test /v1/execute endpoint."""

    async def test_execute_requires_auth(self, client, valid_execute_payload):
        resp = await client.post("/v1/execute", json=valid_execute_payload)
        assert resp.status_code == 422  # Missing X-Service-Token

    async def test_execute_returns_stub_when_no_executor(
        self, client, valid_execute_payload, service_token_headers
    ):
        """When app.state.executor is None, a stub with creative_package={} is returned."""
        # In test mode the lifespan doesn't run so executor is not set
        resp = await client.post(
            "/v1/execute",
            json=valid_execute_payload,
            headers=service_token_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["creative_package"] == {}
        assert data["confidence_score"] == 0.0
        assert data["ad_set_packages"] == []
        assert data["total_images_generated"] == 0

    async def test_execute_with_empty_prompt(self, client, service_token_headers):
        payload = {"input_prompt": ""}
        resp = await client.post(
            "/v1/execute",
            json=payload,
            headers=service_token_headers,
        )
        assert resp.status_code == 200

    async def test_execute_accepts_dict_tenant_context(
        self, client, valid_execute_payload, service_token_headers
    ):
        """tenant_context can be a plain dict."""
        assert isinstance(valid_execute_payload["tenant_context"], dict)
        resp = await client.post(
            "/v1/execute",
            json=valid_execute_payload,
            headers=service_token_headers,
        )
        assert resp.status_code == 200

    async def test_execute_accepts_pydantic_tenant_context(
        self, client, service_token_headers
    ):
        """tenant_context can be serialised from a TenantContext model."""
        tc = TenantContext(
            tenant_id="t-pydantic",
            company_name="PydanticCo",
            user_role="ADMIN",
        )
        payload = {
            "input_prompt": "Generate creatives",
            "tenant_context": tc.model_dump(),
        }
        resp = await client.post(
            "/v1/execute",
            json=payload,
            headers=service_token_headers,
        )
        assert resp.status_code == 200


class TestCreativeAliasEndpoint:
    """Test /v1/creative alias endpoint."""

    async def test_creative_alias_requires_auth(self, client, valid_execute_payload):
        resp = await client.post("/v1/creative", json=valid_execute_payload)
        assert resp.status_code == 422

    async def test_creative_alias_returns_stub_when_no_executor(
        self, client, valid_execute_payload, service_token_headers
    ):
        resp = await client.post(
            "/v1/creative",
            json=valid_execute_payload,
            headers=service_token_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["creative_package"] == {}
        assert data["confidence_score"] == 0.0
