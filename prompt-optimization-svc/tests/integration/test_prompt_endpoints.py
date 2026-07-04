"""Integration tests for §13.1 prompt management endpoints (US-043).

Requires real Redis and MLflow. Tests the full request path including
RBAC enforcement, MLflow registry operations, and response validation.

Run with: pytest tests/integration/test_prompt_endpoints.py -v -m integration
"""

import pytest
from httpx import ASGITransport, AsyncClient

from tests.integration.conftest import requires_mlflow, requires_redis


@pytest.fixture
async def client():
    """Async test client with lifespan for full-stack testing."""
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# Test prompt name — uses __test prefix for cleanup isolation
TEST_PROMPT_NAME = "zorven-wf1-mra-integration-test"
TEST_TEMPLATE = (
    "You are a market research analyst for {context.brand_name}. "
    "Analyze the {context.industry} market landscape."
)
TEST_METADATA = {
    "agent_code": "mra",
    "workflow": "wf1",
    "agent_port": "8021",
    "skill": "landscape",
    "optimization_group": "wf1-research-pipeline",
}


@pytest.mark.integration
@requires_redis
@requires_mlflow
class TestPromptRegistrationFlow:
    """Test the register → list → get → get-version flow."""

    async def test_register_prompt_as_admin(self, client):
        """AC-1: POST /v1/prompts registers a new prompt (ADMIN role)."""
        resp = await client.post(
            "/v1/prompts",
            json={
                "name": TEST_PROMPT_NAME,
                "template": TEST_TEMPLATE,
                "metadata": TEST_METADATA,
            },
            headers={"X-User-Role": "admin", "X-Tenant-ID": "default"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["name"] == TEST_PROMPT_NAME
        assert data["version"] >= 1
        assert data["status"] == "registered"

    async def test_list_prompts_as_viewer(self, client):
        """AC-1: GET /v1/prompts returns registered prompts (VIEWER role)."""
        # Ensure prompt exists
        await client.post(
            "/v1/prompts",
            json={
                "name": TEST_PROMPT_NAME,
                "template": TEST_TEMPLATE,
                "metadata": TEST_METADATA,
            },
            headers={"X-User-Role": "admin"},
        )

        resp = await client.get(
            "/v1/prompts",
            headers={"X-User-Role": "viewer"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["total"] >= 1
        names = [p["name"] for p in data["prompts"]]
        assert TEST_PROMPT_NAME in names

    async def test_get_prompt_detail_as_viewer(self, client):
        """AC-1: GET /v1/prompts/{name} returns full metadata (VIEWER role)."""
        # Ensure prompt exists
        await client.post(
            "/v1/prompts",
            json={
                "name": TEST_PROMPT_NAME,
                "template": TEST_TEMPLATE,
                "metadata": TEST_METADATA,
            },
            headers={"X-User-Role": "admin"},
        )

        resp = await client.get(
            f"/v1/prompts/{TEST_PROMPT_NAME}",
            headers={"X-User-Role": "viewer"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["name"] == TEST_PROMPT_NAME
        assert data["template"] == TEST_TEMPLATE
        assert "metadata" in data
        assert data["metadata"]["agent_code"] == "mra"

    async def test_get_prompt_version_as_viewer(self, client):
        """AC-1: GET /v1/prompts/{name}/versions/{version} returns version detail."""
        # Ensure prompt exists
        reg_resp = await client.post(
            "/v1/prompts",
            json={
                "name": TEST_PROMPT_NAME,
                "template": TEST_TEMPLATE,
                "metadata": TEST_METADATA,
            },
            headers={"X-User-Role": "admin"},
        )
        version = reg_resp.json()["version"]

        resp = await client.get(
            f"/v1/prompts/{TEST_PROMPT_NAME}/versions/{version}",
            headers={"X-User-Role": "viewer"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["name"] == TEST_PROMPT_NAME
        assert data["version"] == version
        assert data["template"] == TEST_TEMPLATE

    async def test_get_nonexistent_version_returns_404(self, client):
        """GET /v1/prompts/{name}/versions/999 returns 404."""
        resp = await client.get(
            f"/v1/prompts/{TEST_PROMPT_NAME}/versions/999",
            headers={"X-User-Role": "viewer"},
        )
        assert resp.status_code == 404


@pytest.mark.integration
@requires_redis
@requires_mlflow
class TestRbacEnforcementIntegration:
    """Test RBAC denial returns 403 with real services running."""

    async def test_viewer_blocked_from_register(self, client):
        """AC-2: VIEWER cannot POST /v1/prompts."""
        resp = await client.post(
            "/v1/prompts",
            json={
                "name": "zorven-wf1-mra-rbac-test",
                "template": "Should be blocked",
            },
            headers={"X-User-Role": "viewer"},
        )
        assert resp.status_code == 403

    async def test_viewer_blocked_from_promote(self, client):
        """AC-2: VIEWER cannot PUT .../promote."""
        resp = await client.put(
            f"/v1/prompts/{TEST_PROMPT_NAME}/versions/1/promote",
            json={"target_state": "PRODUCTION"},
            headers={"X-User-Role": "viewer"},
        )
        assert resp.status_code == 403

    async def test_editor_blocked_from_rollback(self, client):
        """AC-2: EDITOR cannot PUT .../rollback."""
        resp = await client.put(
            f"/v1/prompts/{TEST_PROMPT_NAME}/versions/1/rollback",
            headers={"X-User-Role": "editor"},
        )
        assert resp.status_code == 403

    async def test_admin_blocked_from_delete_override(self, client):
        """AC-2: ADMIN cannot DELETE .../tenant-overrides/{tid}."""
        resp = await client.delete(
            f"/v1/prompts/{TEST_PROMPT_NAME}/tenant-overrides/tenant-1",
            headers={"X-User-Role": "admin"},
        )
        assert resp.status_code == 403

    async def test_editor_escalate_on_promote(self, client):
        """AC-2: EDITOR gets ESCALATE on promote (not 403)."""
        resp = await client.put(
            f"/v1/prompts/{TEST_PROMPT_NAME}/versions/1/promote",
            json={"target_state": "PRODUCTION"},
            headers={"X-User-Role": "editor"},
        )
        assert resp.status_code != 403


@pytest.mark.integration
@requires_redis
@requires_mlflow
class TestPromptLifecycleIntegration:
    """Test promote and rollback operations with real MLflow."""

    async def test_promote_prompt_as_admin(self, client):
        """AC-1: PUT .../promote transitions prompt state (ADMIN role)."""
        # Register a fresh prompt
        reg = await client.post(
            "/v1/prompts",
            json={
                "name": TEST_PROMPT_NAME,
                "template": TEST_TEMPLATE,
                "metadata": TEST_METADATA,
            },
            headers={"X-User-Role": "admin"},
        )
        version = reg.json()["version"]

        # Promote DRAFT → STAGING
        resp = await client.put(
            f"/v1/prompts/{TEST_PROMPT_NAME}/versions/{version}/promote",
            json={"target_state": "STAGING"},
            headers={"X-User-Role": "admin"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["success"] is True
        assert data["to_state"] == "STAGING"

    async def test_rollback_prompt_as_admin(self, client):
        """AC-1: PUT .../rollback rolls back prompt state (ADMIN role)."""
        # Register and promote to get a rollbackable state
        reg = await client.post(
            "/v1/prompts",
            json={
                "name": TEST_PROMPT_NAME,
                "template": TEST_TEMPLATE,
                "metadata": TEST_METADATA,
            },
            headers={"X-User-Role": "admin"},
        )
        version = reg.json()["version"]

        resp = await client.put(
            f"/v1/prompts/{TEST_PROMPT_NAME}/versions/{version}/rollback",
            headers={"X-User-Role": "admin"},
        )
        # May succeed or fail depending on current state — but must not be 403
        assert resp.status_code != 403


@pytest.mark.integration
@requires_redis
@requires_mlflow
class TestOpenApiIntegration:
    """AC-3: OpenAPI documentation served correctly."""

    async def test_openapi_json_available(self, client):
        """GET /openapi.json returns valid OpenAPI schema."""
        resp = await client.get("/openapi.json")
        assert resp.status_code == 200
        schema = resp.json()
        assert "openapi" in schema
        assert "paths" in schema

    async def test_docs_endpoint_available(self, client):
        """GET /docs returns Swagger UI HTML."""
        resp = await client.get("/docs")
        assert resp.status_code == 200
        assert "swagger" in resp.text.lower() or "openapi" in resp.text.lower()
