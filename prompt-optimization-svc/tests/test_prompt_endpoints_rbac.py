"""Unit tests for RBAC enforcement on §13.1 prompt management endpoints (US-043).

Tests verify that each endpoint enforces the correct RBAC permission via
Depends(require_permission(...)). Since the api_client fixture disables
lifespan (mlflow_registry is None), endpoints that pass RBAC return 503.
The key assertion: DENY roles get 403, ALLOW/ESCALATE roles do NOT get 403.

AC-2: Auth dependencies enforce RBAC on all §13.1 endpoints.
AC-3: OpenAPI documentation includes all §13.1 endpoints.
"""

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def api_client():
    """Async test client — lifespan disabled to isolate RBAC testing."""
    from app.main import app

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# ── GET /v1/prompts (Permission.VIEW — VIEWER+) ──


class TestListPromptsRbac:
    @pytest.mark.asyncio
    async def test_viewer_allowed(self, api_client):
        resp = await api_client.get("/v1/prompts", headers={"X-User-Role": "viewer"})
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_editor_allowed(self, api_client):
        resp = await api_client.get("/v1/prompts", headers={"X-User-Role": "editor"})
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_admin_allowed(self, api_client):
        resp = await api_client.get("/v1/prompts", headers={"X-User-Role": "admin"})
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_owner_allowed(self, api_client):
        resp = await api_client.get("/v1/prompts", headers={"X-User-Role": "owner"})
        assert resp.status_code != 403


# ── GET /v1/prompts/{name} (Permission.VIEW — VIEWER+) ──


class TestGetPromptDetailRbac:
    @pytest.mark.asyncio
    async def test_viewer_allowed(self, api_client):
        resp = await api_client.get(
            "/v1/prompts/test-prompt", headers={"X-User-Role": "viewer"}
        )
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_editor_allowed(self, api_client):
        resp = await api_client.get(
            "/v1/prompts/test-prompt", headers={"X-User-Role": "editor"}
        )
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_admin_allowed(self, api_client):
        resp = await api_client.get(
            "/v1/prompts/test-prompt", headers={"X-User-Role": "admin"}
        )
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_owner_allowed(self, api_client):
        resp = await api_client.get(
            "/v1/prompts/test-prompt", headers={"X-User-Role": "owner"}
        )
        assert resp.status_code != 403


# ── GET /v1/prompts/{name}/versions/{version} (Permission.VIEW — VIEWER+) ──


class TestGetPromptVersionRbac:
    @pytest.mark.asyncio
    async def test_viewer_allowed(self, api_client):
        resp = await api_client.get(
            "/v1/prompts/test-prompt/versions/1",
            headers={"X-User-Role": "viewer"},
        )
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_editor_allowed(self, api_client):
        resp = await api_client.get(
            "/v1/prompts/test-prompt/versions/1",
            headers={"X-User-Role": "editor"},
        )
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_admin_allowed(self, api_client):
        resp = await api_client.get(
            "/v1/prompts/test-prompt/versions/1",
            headers={"X-User-Role": "admin"},
        )
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_owner_allowed(self, api_client):
        resp = await api_client.get(
            "/v1/prompts/test-prompt/versions/1",
            headers={"X-User-Role": "owner"},
        )
        assert resp.status_code != 403


# ── POST /v1/prompts (Permission.REGISTER — EDITOR+) ──


REGISTER_BODY = {
    "name": "zorven-wf1-mra-test",
    "template": "Test prompt template for {context.brand_name}",
}


class TestRegisterPromptRbac:
    @pytest.mark.asyncio
    async def test_viewer_denied(self, api_client):
        resp = await api_client.post(
            "/v1/prompts",
            json=REGISTER_BODY,
            headers={"X-User-Role": "viewer"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_editor_allowed(self, api_client):
        resp = await api_client.post(
            "/v1/prompts",
            json=REGISTER_BODY,
            headers={"X-User-Role": "editor"},
        )
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_admin_allowed(self, api_client):
        resp = await api_client.post(
            "/v1/prompts",
            json=REGISTER_BODY,
            headers={"X-User-Role": "admin"},
        )
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_owner_allowed(self, api_client):
        resp = await api_client.post(
            "/v1/prompts",
            json=REGISTER_BODY,
            headers={"X-User-Role": "owner"},
        )
        assert resp.status_code != 403


# ── PUT /v1/prompts/{name}/versions/{version}/promote (Permission.PROMOTE — ADMIN+, EDITOR=ESCALATE) ──


PROMOTE_BODY = {"target_state": "PRODUCTION"}


class TestPromotePromptRbac:
    @pytest.mark.asyncio
    async def test_viewer_denied(self, api_client):
        resp = await api_client.put(
            "/v1/prompts/test-prompt/versions/1/promote",
            json=PROMOTE_BODY,
            headers={"X-User-Role": "viewer"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_editor_escalate_not_denied(self, api_client):
        """EDITOR gets ESCALATE (not DENY) — request passes RBAC."""
        resp = await api_client.put(
            "/v1/prompts/test-prompt/versions/1/promote",
            json=PROMOTE_BODY,
            headers={"X-User-Role": "editor"},
        )
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_admin_allowed(self, api_client):
        resp = await api_client.put(
            "/v1/prompts/test-prompt/versions/1/promote",
            json=PROMOTE_BODY,
            headers={"X-User-Role": "admin"},
        )
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_owner_allowed(self, api_client):
        resp = await api_client.put(
            "/v1/prompts/test-prompt/versions/1/promote",
            json=PROMOTE_BODY,
            headers={"X-User-Role": "owner"},
        )
        assert resp.status_code != 403


# ── PUT /v1/prompts/{name}/versions/{version}/rollback (Permission.ROLLBACK — ADMIN+) ──


class TestRollbackPromptRbac:
    @pytest.mark.asyncio
    async def test_viewer_denied(self, api_client):
        resp = await api_client.put(
            "/v1/prompts/test-prompt/versions/1/rollback",
            headers={"X-User-Role": "viewer"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_editor_denied(self, api_client):
        resp = await api_client.put(
            "/v1/prompts/test-prompt/versions/1/rollback",
            headers={"X-User-Role": "editor"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_allowed(self, api_client):
        resp = await api_client.put(
            "/v1/prompts/test-prompt/versions/1/rollback",
            headers={"X-User-Role": "admin"},
        )
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_owner_allowed(self, api_client):
        resp = await api_client.put(
            "/v1/prompts/test-prompt/versions/1/rollback",
            headers={"X-User-Role": "owner"},
        )
        assert resp.status_code != 403


# ── DELETE /v1/prompts/{name}/tenant-overrides/{tenant_id} (Permission.DELETE_OVERRIDE — OWNER only) ──


class TestDeleteTenantOverrideRbac:
    @pytest.mark.asyncio
    async def test_viewer_denied(self, api_client):
        resp = await api_client.delete(
            "/v1/prompts/test-prompt/tenant-overrides/tenant-1",
            headers={"X-User-Role": "viewer"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_editor_denied(self, api_client):
        resp = await api_client.delete(
            "/v1/prompts/test-prompt/tenant-overrides/tenant-1",
            headers={"X-User-Role": "editor"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_denied(self, api_client):
        resp = await api_client.delete(
            "/v1/prompts/test-prompt/tenant-overrides/tenant-1",
            headers={"X-User-Role": "admin"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_owner_allowed(self, api_client):
        resp = await api_client.delete(
            "/v1/prompts/test-prompt/tenant-overrides/tenant-1",
            headers={"X-User-Role": "owner"},
        )
        assert resp.status_code != 403


# ── Default role (no header) behaves as VIEWER ──


class TestDefaultRoleBehavior:
    @pytest.mark.asyncio
    async def test_no_role_header_defaults_to_viewer_on_view(self, api_client):
        """No X-User-Role header defaults to viewer — VIEW allowed."""
        resp = await api_client.get("/v1/prompts")
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_no_role_header_defaults_to_viewer_on_register(self, api_client):
        """No X-User-Role header defaults to viewer — REGISTER denied."""
        resp = await api_client.post("/v1/prompts", json=REGISTER_BODY)
        assert resp.status_code == 403


# ── AC-3: OpenAPI documentation includes all §13.1 endpoints ──


class TestOpenApiDocumentation:
    @pytest.mark.asyncio
    async def test_all_section_13_1_routes_registered(self, api_client):
        """AC-3: All §13.1 endpoints are registered in the FastAPI router."""
        from app.main import app

        registered_paths = {route.path for route in app.routes}
        expected = {
            "/v1/prompts",
            "/v1/prompts/{name}",
            "/v1/prompts/{name}/versions/{version}",
            "/v1/prompts/{name}/versions/{version}/promote",
            "/v1/prompts/{name}/versions/{version}/rollback",
            "/v1/prompts/{name}/tenant-overrides/{tenant_id}",
        }
        for path in expected:
            assert path in registered_paths, f"Missing route: {path}"

    @pytest.mark.asyncio
    async def test_docs_endpoint_returns_html(self, api_client):
        """AC-3: /docs serves Swagger UI."""
        resp = await api_client.get("/docs")
        assert resp.status_code == 200
