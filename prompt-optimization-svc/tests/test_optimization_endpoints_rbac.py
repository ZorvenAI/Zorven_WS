"""Unit tests for RBAC enforcement on §13.2 optimization endpoints (US-044).

Validates that each optimization endpoint correctly enforces its RBAC
permission. Lifespan is disabled (ASGITransport), so endpoints backed by
Redis/MLflow return 503/404 when RBAC passes, while endpoints that read
only from in-memory registries (optimize/agent, optimize/all) return 200.
The key assertion across all tests is:
  - DENY roles get 403
  - ALLOW/ESCALATE roles do NOT get 403
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth.rbac import Decision, Permission, Role, check_permission


@pytest.fixture
async def api_client():
    """Async test client — lifespan disabled to isolate RBAC testing."""
    from app.main import app

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# ── POST /v1/optimize/agent/{agent_code} — TRIGGER_OPTIMIZATION (ADMIN+) ──


class TestOptimizeAgent:
    @pytest.mark.asyncio
    async def test_viewer_denied(self, api_client):
        resp = await api_client.post(
            "/v1/optimize/agent/mra", headers={"X-User-Role": "viewer"}
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_editor_allowed(self, api_client):
        resp = await api_client.post(
            "/v1/optimize/agent/mra", headers={"X-User-Role": "editor"}
        )
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_admin_allowed(self, api_client):
        resp = await api_client.post(
            "/v1/optimize/agent/mra", headers={"X-User-Role": "admin"}
        )
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_owner_allowed(self, api_client):
        resp = await api_client.post(
            "/v1/optimize/agent/mra", headers={"X-User-Role": "owner"}
        )
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_invalid_agent_code_returns_404(self, api_client):
        resp = await api_client.post(
            "/v1/optimize/agent/invalid_agent",
            headers={"X-User-Role": "admin"},
        )
        assert resp.status_code == 404
        assert "Unknown agent_code" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_valid_agent_returns_response(self, api_client):
        resp = await api_client.post(
            "/v1/optimize/agent/mra", headers={"X-User-Role": "admin"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["agent_code"] == "mra"
        assert data["state"] == "QUEUED"
        assert data["prompt_count"] > 0


# ── POST /v1/optimize/group/{group_name} — TRIGGER_OPTIMIZATION (ADMIN+) ──


class TestOptimizeGroup:
    @pytest.mark.asyncio
    async def test_viewer_denied(self, api_client):
        resp = await api_client.post(
            "/v1/optimize/group/wf1-discovery-pipeline",
            headers={"X-User-Role": "viewer"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_editor_allowed(self, api_client):
        resp = await api_client.post(
            "/v1/optimize/group/wf1-discovery-pipeline",
            headers={"X-User-Role": "editor"},
        )
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_admin_allowed(self, api_client):
        resp = await api_client.post(
            "/v1/optimize/group/wf1-discovery-pipeline",
            headers={"X-User-Role": "admin"},
        )
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_owner_allowed(self, api_client):
        resp = await api_client.post(
            "/v1/optimize/group/wf1-discovery-pipeline",
            headers={"X-User-Role": "owner"},
        )
        assert resp.status_code != 403


# ── POST /v1/optimize/all — OWNER only (AC-1) ──


class TestOptimizeAll:
    @pytest.mark.asyncio
    async def test_viewer_denied(self, api_client):
        resp = await api_client.post(
            "/v1/optimize/all", headers={"X-User-Role": "viewer"}
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_editor_denied(self, api_client):
        resp = await api_client.post(
            "/v1/optimize/all", headers={"X-User-Role": "editor"}
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_denied(self, api_client):
        resp = await api_client.post(
            "/v1/optimize/all", headers={"X-User-Role": "admin"}
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_owner_allowed(self, api_client):
        resp = await api_client.post(
            "/v1/optimize/all", headers={"X-User-Role": "owner"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["groups_triggered"] > 0
        assert data["total_prompts"] > 0


# ── GET /v1/optimize/runs — VIEW (VIEWER+) ──


class TestListRuns:
    @pytest.mark.asyncio
    async def test_viewer_allowed(self, api_client):
        resp = await api_client.get(
            "/v1/optimize/runs", headers={"X-User-Role": "viewer"}
        )
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_editor_allowed(self, api_client):
        resp = await api_client.get(
            "/v1/optimize/runs", headers={"X-User-Role": "editor"}
        )
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_admin_allowed(self, api_client):
        resp = await api_client.get(
            "/v1/optimize/runs", headers={"X-User-Role": "admin"}
        )
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_owner_allowed(self, api_client):
        resp = await api_client.get(
            "/v1/optimize/runs", headers={"X-User-Role": "owner"}
        )
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_pagination_params_accepted(self, api_client):
        resp = await api_client.get(
            "/v1/optimize/runs?page=2&page_size=10",
            headers={"X-User-Role": "viewer"},
        )
        assert resp.status_code != 403


# ── GET /v1/optimize/runs/{run_id} — VIEW (VIEWER+) ──


class TestGetRunDetail:
    @pytest.mark.asyncio
    async def test_viewer_allowed(self, api_client):
        resp = await api_client.get(
            "/v1/optimize/runs/test-run-1",
            headers={"X-User-Role": "viewer"},
        )
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_editor_allowed(self, api_client):
        resp = await api_client.get(
            "/v1/optimize/runs/test-run-1",
            headers={"X-User-Role": "editor"},
        )
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_admin_allowed(self, api_client):
        resp = await api_client.get(
            "/v1/optimize/runs/test-run-1",
            headers={"X-User-Role": "admin"},
        )
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_owner_allowed(self, api_client):
        resp = await api_client.get(
            "/v1/optimize/runs/test-run-1",
            headers={"X-User-Role": "owner"},
        )
        assert resp.status_code != 403


# ── POST /v1/optimize/runs/{run_id}/approve — APPROVE (ADMIN+) ──


class TestApproveRun:
    @pytest.mark.asyncio
    async def test_viewer_denied(self, api_client):
        resp = await api_client.post(
            "/v1/optimize/runs/test-run-1/approve",
            json={"approved_by": "test-user"},
            headers={"X-User-Role": "viewer"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_editor_denied(self, api_client):
        resp = await api_client.post(
            "/v1/optimize/runs/test-run-1/approve",
            json={"approved_by": "test-user"},
            headers={"X-User-Role": "editor"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_allowed(self, api_client):
        resp = await api_client.post(
            "/v1/optimize/runs/test-run-1/approve",
            json={"approved_by": "test-user"},
            headers={"X-User-Role": "admin"},
        )
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_owner_allowed(self, api_client):
        resp = await api_client.post(
            "/v1/optimize/runs/test-run-1/approve",
            json={"approved_by": "test-user"},
            headers={"X-User-Role": "owner"},
        )
        assert resp.status_code != 403


# ── POST /v1/optimize/runs/{run_id}/reject — APPROVE (ADMIN+) ──


class TestRejectRun:
    @pytest.mark.asyncio
    async def test_viewer_denied(self, api_client):
        resp = await api_client.post(
            "/v1/optimize/runs/test-run-1/reject",
            json={"approved_by": "test-user", "reason": "Not ready"},
            headers={"X-User-Role": "viewer"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_editor_denied(self, api_client):
        resp = await api_client.post(
            "/v1/optimize/runs/test-run-1/reject",
            json={"approved_by": "test-user", "reason": "Not ready"},
            headers={"X-User-Role": "editor"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_allowed(self, api_client):
        resp = await api_client.post(
            "/v1/optimize/runs/test-run-1/reject",
            json={"approved_by": "test-user", "reason": "Not ready"},
            headers={"X-User-Role": "admin"},
        )
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_owner_allowed(self, api_client):
        resp = await api_client.post(
            "/v1/optimize/runs/test-run-1/reject",
            json={"approved_by": "test-user", "reason": "Not ready"},
            headers={"X-User-Role": "owner"},
        )
        assert resp.status_code != 403


# ── Cross-cutting tests ──


class TestOptimizationRbacCrossCutting:
    @pytest.mark.asyncio
    async def test_default_role_behaves_as_viewer(self, api_client):
        """No X-User-Role header → defaults to viewer → denied on TRIGGER."""
        resp = await api_client.post("/v1/optimize/agent/mra")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_default_role_allowed_on_view(self, api_client):
        """No X-User-Role header → defaults to viewer → allowed on VIEW."""
        resp = await api_client.get("/v1/optimize/runs/test-run-1")
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_all_section_13_2_routes_registered(self, api_client):
        """All §13.2 paths are registered in the FastAPI router."""
        from app.main import app

        registered_paths = {route.path for route in app.routes}
        expected_paths = {
            "/v1/optimize/agent/{agent_code}",
            "/v1/optimize/group/{group_name}",
            "/v1/optimize/all",
            "/v1/optimize/runs",
            "/v1/optimize/runs/{run_id}",
            "/v1/optimize/runs/{run_id}/approve",
            "/v1/optimize/runs/{run_id}/reject",
        }
        for expected in expected_paths:
            assert expected in registered_paths, f"Missing §13.2 route: {expected}"
