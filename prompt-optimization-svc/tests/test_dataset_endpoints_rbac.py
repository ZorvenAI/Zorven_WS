"""Unit tests for RBAC enforcement on §13.3 dataset endpoints (US-045).

Validates that each dataset endpoint correctly enforces its RBAC
permission. Lifespan is disabled (ASGITransport), so DB-backed endpoints
return 500 when RBAC passes, while in-memory endpoints (stats) return 200.
The key assertion across all tests is:
  - DENY roles get 403
  - ALLOW/ESCALATE roles do NOT get 403
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


VALID_CREATE_BODY = {
    "prompt_name": "zorven-wf1-mra-system",
    "input_context": {"context_brand_name": "Test"},
    "expected_output": "Test output",
    "source": "manual",
    "metadata_extra": {"industry": "Tech"},
}

VALID_UPDATE_BODY = {"expected_output": "Updated output"}


# ── GET /v1/datasets/{agent_code} — VIEW (VIEWER+) ──


class TestListDatasets:
    @pytest.mark.asyncio
    async def test_viewer_allowed(self, api_client):
        resp = await api_client.get(
            "/v1/datasets/mra", headers={"X-User-Role": "viewer"}
        )
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_editor_allowed(self, api_client):
        resp = await api_client.get(
            "/v1/datasets/mra", headers={"X-User-Role": "editor"}
        )
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_admin_allowed(self, api_client):
        resp = await api_client.get(
            "/v1/datasets/mra", headers={"X-User-Role": "admin"}
        )
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_owner_allowed(self, api_client):
        resp = await api_client.get(
            "/v1/datasets/mra", headers={"X-User-Role": "owner"}
        )
        assert resp.status_code != 403


# ── POST /v1/datasets/{agent_code} — REGISTER (EDITOR+) ──


class TestCreateDataset:
    @pytest.mark.asyncio
    async def test_viewer_denied(self, api_client):
        resp = await api_client.post(
            "/v1/datasets/mra",
            json=VALID_CREATE_BODY,
            headers={"X-User-Role": "viewer"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_editor_allowed(self, api_client):
        resp = await api_client.post(
            "/v1/datasets/mra",
            json=VALID_CREATE_BODY,
            headers={"X-User-Role": "editor"},
        )
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_admin_allowed(self, api_client):
        resp = await api_client.post(
            "/v1/datasets/mra",
            json=VALID_CREATE_BODY,
            headers={"X-User-Role": "admin"},
        )
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_owner_allowed(self, api_client):
        resp = await api_client.post(
            "/v1/datasets/mra",
            json=VALID_CREATE_BODY,
            headers={"X-User-Role": "owner"},
        )
        assert resp.status_code != 403


# ── PUT /v1/datasets/{agent_code}/{entry_id} — REGISTER (EDITOR+) ──


class TestUpdateDataset:
    @pytest.mark.asyncio
    async def test_viewer_denied(self, api_client):
        resp = await api_client.put(
            "/v1/datasets/mra/1",
            json=VALID_UPDATE_BODY,
            headers={"X-User-Role": "viewer"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_editor_allowed(self, api_client):
        resp = await api_client.put(
            "/v1/datasets/mra/1",
            json=VALID_UPDATE_BODY,
            headers={"X-User-Role": "editor"},
        )
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_admin_allowed(self, api_client):
        resp = await api_client.put(
            "/v1/datasets/mra/1",
            json=VALID_UPDATE_BODY,
            headers={"X-User-Role": "admin"},
        )
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_owner_allowed(self, api_client):
        resp = await api_client.put(
            "/v1/datasets/mra/1",
            json=VALID_UPDATE_BODY,
            headers={"X-User-Role": "owner"},
        )
        assert resp.status_code != 403


# ── DELETE /v1/datasets/{agent_code}/{entry_id} — MODIFY_CONFIG (ADMIN+) ──


class TestDeleteDataset:
    @pytest.mark.asyncio
    async def test_viewer_denied(self, api_client):
        resp = await api_client.delete(
            "/v1/datasets/mra/1", headers={"X-User-Role": "viewer"}
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_editor_denied(self, api_client):
        resp = await api_client.delete(
            "/v1/datasets/mra/1", headers={"X-User-Role": "editor"}
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_allowed(self, api_client):
        resp = await api_client.delete(
            "/v1/datasets/mra/1", headers={"X-User-Role": "admin"}
        )
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_owner_allowed(self, api_client):
        resp = await api_client.delete(
            "/v1/datasets/mra/1", headers={"X-User-Role": "owner"}
        )
        assert resp.status_code != 403


# ── POST /v1/datasets/{agent_code}/mine — TRIGGER_OPTIMIZATION (EDITOR+) ──


class TestTriggerMining:
    @pytest.mark.asyncio
    async def test_viewer_denied(self, api_client):
        resp = await api_client.post(
            "/v1/datasets/mra/mine", headers={"X-User-Role": "viewer"}
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_editor_allowed(self, api_client):
        resp = await api_client.post(
            "/v1/datasets/mra/mine", headers={"X-User-Role": "editor"}
        )
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_admin_allowed(self, api_client):
        resp = await api_client.post(
            "/v1/datasets/mra/mine", headers={"X-User-Role": "admin"}
        )
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_owner_allowed(self, api_client):
        resp = await api_client.post(
            "/v1/datasets/mra/mine", headers={"X-User-Role": "owner"}
        )
        assert resp.status_code != 403


# ── Existing endpoints: POST /v1/datasets/seed — REGISTER (EDITOR+) ──


class TestSeedDatasets:
    @pytest.mark.asyncio
    async def test_viewer_denied(self, api_client):
        resp = await api_client.post(
            "/v1/datasets/seed", headers={"X-User-Role": "viewer"}
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_editor_allowed(self, api_client):
        resp = await api_client.post(
            "/v1/datasets/seed", headers={"X-User-Role": "editor"}
        )
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_admin_allowed(self, api_client):
        resp = await api_client.post(
            "/v1/datasets/seed", headers={"X-User-Role": "admin"}
        )
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_owner_allowed(self, api_client):
        resp = await api_client.post(
            "/v1/datasets/seed", headers={"X-User-Role": "owner"}
        )
        assert resp.status_code != 403


# ── Existing: GET /v1/datasets/stats — VIEW (VIEWER+) ──


class TestDatasetStats:
    @pytest.mark.asyncio
    async def test_viewer_allowed(self, api_client):
        resp = await api_client.get(
            "/v1/datasets/stats", headers={"X-User-Role": "viewer"}
        )
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_editor_allowed(self, api_client):
        resp = await api_client.get(
            "/v1/datasets/stats", headers={"X-User-Role": "editor"}
        )
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_admin_allowed(self, api_client):
        resp = await api_client.get(
            "/v1/datasets/stats", headers={"X-User-Role": "admin"}
        )
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_owner_allowed(self, api_client):
        resp = await api_client.get(
            "/v1/datasets/stats", headers={"X-User-Role": "owner"}
        )
        assert resp.status_code != 403


# ── Existing: POST /v1/datasets/generate — REGISTER (EDITOR+) ──


class TestGenerateDatasets:
    @pytest.mark.asyncio
    async def test_viewer_denied(self, api_client):
        resp = await api_client.post(
            "/v1/datasets/generate",
            json={"industry": "Tech"},
            headers={"X-User-Role": "viewer"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_editor_allowed(self, api_client):
        resp = await api_client.post(
            "/v1/datasets/generate",
            json={"industry": "Tech"},
            headers={"X-User-Role": "editor"},
        )
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_admin_allowed(self, api_client):
        resp = await api_client.post(
            "/v1/datasets/generate",
            json={"industry": "Tech"},
            headers={"X-User-Role": "admin"},
        )
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_owner_allowed(self, api_client):
        resp = await api_client.post(
            "/v1/datasets/generate",
            json={"industry": "Tech"},
            headers={"X-User-Role": "owner"},
        )
        assert resp.status_code != 403


# ── Existing: GET /v1/config/dataset-size — VIEW (VIEWER+) ──


class TestGetDatasetSize:
    @pytest.mark.asyncio
    async def test_viewer_allowed(self, api_client):
        resp = await api_client.get(
            "/v1/config/dataset-size", headers={"X-User-Role": "viewer"}
        )
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_editor_allowed(self, api_client):
        resp = await api_client.get(
            "/v1/config/dataset-size", headers={"X-User-Role": "editor"}
        )
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_admin_allowed(self, api_client):
        resp = await api_client.get(
            "/v1/config/dataset-size", headers={"X-User-Role": "admin"}
        )
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_owner_allowed(self, api_client):
        resp = await api_client.get(
            "/v1/config/dataset-size", headers={"X-User-Role": "owner"}
        )
        assert resp.status_code != 403


# ── Existing: PUT /v1/config/dataset-size — MODIFY_CONFIG (ADMIN+) ──


class TestSetDatasetSize:
    @pytest.mark.asyncio
    async def test_viewer_denied(self, api_client):
        resp = await api_client.put(
            "/v1/config/dataset-size",
            json={"size": 10},
            headers={"X-User-Role": "viewer"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_editor_denied(self, api_client):
        resp = await api_client.put(
            "/v1/config/dataset-size",
            json={"size": 10},
            headers={"X-User-Role": "editor"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_allowed(self, api_client):
        resp = await api_client.put(
            "/v1/config/dataset-size",
            json={"size": 10},
            headers={"X-User-Role": "admin"},
        )
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_owner_allowed(self, api_client):
        resp = await api_client.put(
            "/v1/config/dataset-size",
            json={"size": 10},
            headers={"X-User-Role": "owner"},
        )
        assert resp.status_code != 403


# ── Cross-cutting tests ──


class TestDatasetRbacCrossCutting:
    @pytest.mark.asyncio
    async def test_default_role_behaves_as_viewer(self, api_client):
        """No X-User-Role header → defaults to viewer → denied on REGISTER."""
        resp = await api_client.post("/v1/datasets/mra", json=VALID_CREATE_BODY)
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_default_role_allowed_on_view(self, api_client):
        """No X-User-Role header → defaults to viewer → allowed on VIEW."""
        resp = await api_client.get("/v1/datasets/stats")
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_unknown_agent_returns_404(self, api_client):
        """Unknown agent_code returns 404 (not 403)."""
        resp = await api_client.get(
            "/v1/datasets/unknown_agent", headers={"X-User-Role": "admin"}
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_all_section_13_3_routes_registered(self, api_client):
        """All §13.3 paths are registered in the FastAPI router."""
        from app.main import app

        registered_paths = {route.path for route in app.routes}
        expected_paths = {
            "/v1/datasets/{agent_code}",
            "/v1/datasets/{agent_code}/mine",
            "/v1/datasets/{agent_code}/{entry_id}",
        }
        for expected in expected_paths:
            assert expected in registered_paths, f"Missing §13.3 route: {expected}"
