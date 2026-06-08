"""Integration tests for §13.3 dataset CRUD + mine endpoints (US-045).

Requires real PostgreSQL. Tests full request path including RBAC
enforcement, CRUD operations, soft-delete, pagination, and mining trigger.

Run with: pytest tests/integration/test_dataset_endpoints.py -v -m integration
"""

import os

import pytest
from httpx import ASGITransport, AsyncClient


def _postgres_available() -> bool:
    """Check if PostgreSQL is reachable."""
    db_url = os.environ.get("POI_DATABASE_URL", "")
    if not db_url:
        return False
    try:
        import psycopg2

        conn = psycopg2.connect(db_url)
        conn.close()
        return True
    except Exception:
        return False


requires_postgres = pytest.mark.skipif(
    not _postgres_available(),
    reason="PostgreSQL not available (set POI_DATABASE_URL)",
)

ADMIN_HEADERS = {"X-User-Role": "admin"}
EDITOR_HEADERS = {"X-User-Role": "editor"}
VIEWER_HEADERS = {"X-User-Role": "viewer"}


@pytest.fixture
async def client():
    """Async test client with lifespan for full-stack testing."""
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def cleanup_entries():
    """Track created entry IDs for cleanup after tests."""
    created_ids = []
    yield created_ids
    # Cleanup: hard-delete test entries from DB
    if created_ids:
        from sqlalchemy import delete

        from app.models.database import async_session_factory
        from app.models.golden_dataset import GoldenDataset

        async with async_session_factory() as session:
            await session.execute(
                delete(GoldenDataset).where(GoldenDataset.id.in_(created_ids))
            )
            await session.commit()


async def _create_entry(client, agent_code="mra", source="manual", suffix=""):
    """Helper to create a test dataset entry."""
    resp = await client.post(
        f"/v1/datasets/{agent_code}",
        json={
            "prompt_name": f"zorven-wf1-{agent_code}-test{suffix}",
            "agent_code": agent_code,
            "input_context": {"context_brand_name": "IntegrationTest"},
            "expected_output": f"Test output {suffix}",
            "source": source,
            "metadata_extra": {"industry": "Tech", "test": True},
        },
        headers=ADMIN_HEADERS,
    )
    return resp


@pytest.mark.integration
class TestDatasetCRUDIntegration:
    @requires_postgres
    @pytest.mark.asyncio
    async def test_create_returns_201(self, client, cleanup_entries):
        """Editor can create a dataset entry with 201 status."""
        resp = await _create_entry(client, suffix="-create201")
        assert resp.status_code == 201
        data = resp.json()
        cleanup_entries.append(data["id"])
        assert data["agent_code"] == "mra"
        assert data["source"] == "manual"
        assert data["active"] is True

    @requires_postgres
    @pytest.mark.asyncio
    async def test_create_and_list(self, client, cleanup_entries):
        """Created entry appears in GET list."""
        resp = await _create_entry(client, suffix="-createlist")
        assert resp.status_code == 201
        entry_id = resp.json()["id"]
        cleanup_entries.append(entry_id)

        list_resp = await client.get("/v1/datasets/mra", headers=ADMIN_HEADERS)
        assert list_resp.status_code == 200
        data = list_resp.json()
        assert data["total"] > 0
        ids = [item["id"] for item in data["items"]]
        assert entry_id in ids

    @requires_postgres
    @pytest.mark.asyncio
    async def test_list_with_pagination(self, client, cleanup_entries):
        """Pagination returns correct page metadata (AC-3)."""
        # Create 3 entries
        for i in range(3):
            resp = await _create_entry(client, suffix=f"-page{i}")
            assert resp.status_code == 201
            cleanup_entries.append(resp.json()["id"])

        resp = await client.get(
            "/v1/datasets/mra?page=1&page_size=2",
            headers=ADMIN_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["page"] == 1
        assert data["page_size"] == 2
        assert len(data["items"]) <= 2
        assert data["total"] >= 3

    @requires_postgres
    @pytest.mark.asyncio
    async def test_list_filter_by_source(self, client, cleanup_entries):
        """Filter by source returns only matching entries (AC-3)."""
        resp1 = await _create_entry(client, source="manual", suffix="-filt-m")
        resp2 = await _create_entry(client, source="synthetic", suffix="-filt-s")
        cleanup_entries.extend([resp1.json()["id"], resp2.json()["id"]])

        resp = await client.get(
            "/v1/datasets/mra?source=synthetic",
            headers=ADMIN_HEADERS,
        )
        assert resp.status_code == 200
        sources = {item["source"] for item in resp.json()["items"]}
        assert sources <= {"synthetic"}

    @requires_postgres
    @pytest.mark.asyncio
    async def test_update_entry(self, client, cleanup_entries):
        """Editor can update a dataset entry."""
        resp = await _create_entry(client, suffix="-update")
        entry_id = resp.json()["id"]
        cleanup_entries.append(entry_id)

        update_resp = await client.put(
            f"/v1/datasets/mra/{entry_id}",
            json={"expected_output": "Updated output"},
            headers=EDITOR_HEADERS,
        )
        assert update_resp.status_code == 200
        assert update_resp.json()["expected_output"] == "Updated output"

    @requires_postgres
    @pytest.mark.asyncio
    async def test_soft_delete(self, client, cleanup_entries):
        """AC-1: DELETE sets active=false, entry disappears from GET list."""
        resp = await _create_entry(client, suffix="-softdel")
        entry_id = resp.json()["id"]
        cleanup_entries.append(entry_id)

        # Delete
        del_resp = await client.delete(
            f"/v1/datasets/mra/{entry_id}", headers=ADMIN_HEADERS
        )
        assert del_resp.status_code == 200
        assert "deactivated" in del_resp.json()["detail"]

        # Verify not in list
        list_resp = await client.get("/v1/datasets/mra", headers=ADMIN_HEADERS)
        ids = [item["id"] for item in list_resp.json()["items"]]
        assert entry_id not in ids

    @requires_postgres
    @pytest.mark.asyncio
    async def test_delete_nonexistent_returns_404(self, client):
        """DELETE on non-existent ID returns 404."""
        resp = await client.delete("/v1/datasets/mra/999999", headers=ADMIN_HEADERS)
        assert resp.status_code == 404

    @requires_postgres
    @pytest.mark.asyncio
    async def test_update_nonexistent_returns_404(self, client):
        """PUT on non-existent ID returns 404."""
        resp = await client.put(
            "/v1/datasets/mra/999999",
            json={"expected_output": "Updated"},
            headers=EDITOR_HEADERS,
        )
        assert resp.status_code == 404

    @requires_postgres
    @pytest.mark.asyncio
    async def test_unknown_agent_returns_404(self, client):
        """Unknown agent_code returns 404."""
        resp = await client.get("/v1/datasets/unknown_agent", headers=ADMIN_HEADERS)
        assert resp.status_code == 404

    @requires_postgres
    @pytest.mark.asyncio
    async def test_viewer_blocked_from_create(self, client):
        """Viewer cannot create dataset entries."""
        resp = await client.post(
            "/v1/datasets/mra",
            json={
                "prompt_name": "zorven-wf1-mra-test",
                "agent_code": "mra",
                "input_context": {"context_brand_name": "Test"},
                "expected_output": "Test",
            },
            headers=VIEWER_HEADERS,
        )
        assert resp.status_code == 403

    @requires_postgres
    @pytest.mark.asyncio
    async def test_editor_blocked_from_delete(self, client, cleanup_entries):
        """Editor cannot delete dataset entries (MODIFY_CONFIG is ADMIN+)."""
        resp = await _create_entry(client, suffix="-edblock")
        entry_id = resp.json()["id"]
        cleanup_entries.append(entry_id)

        del_resp = await client.delete(
            f"/v1/datasets/mra/{entry_id}", headers=EDITOR_HEADERS
        )
        assert del_resp.status_code == 403


@pytest.mark.integration
class TestMineTriggerIntegration:
    @requires_postgres
    @pytest.mark.asyncio
    async def test_mine_unknown_agent_returns_404(self, client):
        """POST /mine for unknown agent returns 404."""
        resp = await client.post(
            "/v1/datasets/unknown_agent/mine", headers=ADMIN_HEADERS
        )
        assert resp.status_code == 404
