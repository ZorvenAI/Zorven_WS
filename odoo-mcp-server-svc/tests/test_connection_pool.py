"""Tests for TenantConnectionPool — maximise coverage of
app/services/connection_pool.py.

Covers:
  - get_client: create, cache, changed params eviction, max pool eviction
  - release_client: existing and non-existing tenant
  - close_all
  - get_pool_stats
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.connection_pool import TenantConnectionPool


@pytest.fixture
def pool() -> TenantConnectionPool:
    """Return a fresh connection pool with small limits for testing."""
    return TenantConnectionPool(default_pool_size=2, max_pool_size=5)


def _patch_authenticate():
    """Patch OdooRPCClient.authenticate so it sets uid without I/O."""
    return patch(
        "app.services.connection_pool.OdooRPCClient.authenticate",
        new_callable=AsyncMock,
        side_effect=lambda self=None: None,
    )


# ── get_client ─────────────────────────────────────────────────────


class TestGetClient:
    async def test_get_client_creates_new_client(self, pool):
        """First call for a tenant creates and returns a client."""
        with _patch_authenticate() as mock_auth:
            client = await pool.get_client(
                "t1",
                "http://odoo:8069",
                "db1",
                "admin",
                "pass",
            )

        assert client is not None
        assert client.db == "db1"
        mock_auth.assert_awaited_once()

    async def test_get_client_returns_cached(self, pool):
        """Second call with same tenant reuses the cached client."""
        with _patch_authenticate() as mock_auth:
            first = await pool.get_client(
                "t1",
                "http://odoo:8069",
                "db1",
                "admin",
                "pass",
            )
            second = await pool.get_client(
                "t1",
                "http://odoo:8069",
                "db1",
                "admin",
                "pass",
            )

        assert first is second
        # authenticate called only once — second call hits cache
        assert mock_auth.await_count == 1

    async def test_get_client_evicts_stale_on_url_change(self, pool):
        """When the URL changes for a tenant, the stale entry is evicted
        and a new client is created."""
        with _patch_authenticate() as mock_auth:
            first = await pool.get_client(
                "t1",
                "http://odoo:8069",
                "db1",
                "admin",
                "pass",
            )
            second = await pool.get_client(
                "t1",
                "http://odoo:9069",  # changed URL
                "db1",
                "admin",
                "pass",
            )

        assert first is not second
        assert second.url == "http://odoo:9069"
        # Two authenticate calls: original + new after eviction
        assert mock_auth.await_count == 2

    async def test_get_client_evicts_stale_on_db_change(self, pool):
        """When the database changes, the stale entry is evicted."""
        with _patch_authenticate() as mock_auth:
            first = await pool.get_client(
                "t1",
                "http://odoo:8069",
                "db1",
                "admin",
                "pass",
            )
            second = await pool.get_client(
                "t1",
                "http://odoo:8069",
                "db2",  # changed DB
                "admin",
                "pass",
            )

        assert first is not second
        assert second.db == "db2"
        assert mock_auth.await_count == 2

    async def test_get_client_evicts_stale_on_username_change(self, pool):
        """When the username changes, the stale entry is evicted."""
        with _patch_authenticate() as mock_auth:
            first = await pool.get_client(
                "t1",
                "http://odoo:8069",
                "db1",
                "admin",
                "pass",
            )
            second = await pool.get_client(
                "t1",
                "http://odoo:8069",
                "db1",
                "other_user",  # changed username
                "pass",
            )

        assert first is not second
        assert second.username == "other_user"
        assert mock_auth.await_count == 2

    async def test_get_client_evicts_oldest_at_max_pool_size(self):
        """When the pool is at max capacity, the oldest entry is evicted
        to make room for a new tenant."""
        # Create pool with max_pool_size=2 for easy testing
        pool = TenantConnectionPool(default_pool_size=1, max_pool_size=2)

        with _patch_authenticate():
            await pool.get_client("t1", "http://odoo:8069", "db1", "admin", "pass")
            await pool.get_client("t2", "http://odoo:8069", "db2", "admin", "pass")

            # Pool is now at max (2). Adding t3 should evict t1.
            client_t3 = await pool.get_client(
                "t3", "http://odoo:8069", "db3", "admin", "pass"
            )

        stats = pool.get_pool_stats()
        assert "t1" not in stats  # evicted
        assert "t2" in stats
        assert "t3" in stats
        assert client_t3.db == "db3"


# ── release_client ─────────────────────────────────────────────────


class TestReleaseClient:
    async def test_release_existing_tenant(self, pool):
        """release_client() removes the tenant from the pool."""
        with _patch_authenticate():
            await pool.get_client("t1", "http://odoo:8069", "db1", "admin", "pass")

        assert "t1" in pool.get_pool_stats()

        await pool.release_client("t1")

        assert "t1" not in pool.get_pool_stats()

    async def test_release_nonexisting_tenant(self, pool):
        """release_client() is a no-op for a tenant not in the pool."""
        # Should not raise
        await pool.release_client("nonexistent")
        assert pool.get_pool_stats() == {}


# ── close_all ──────────────────────────────────────────────────────


class TestCloseAll:
    async def test_close_all_clears_pool(self, pool):
        """close_all() empties the pool entirely."""
        with _patch_authenticate():
            await pool.get_client("t1", "http://odoo:8069", "db1", "admin", "pass")
            await pool.get_client("t2", "http://odoo:8069", "db2", "admin", "pass")

        assert len(pool.get_pool_stats()) == 2

        await pool.close_all()

        assert pool.get_pool_stats() == {}

    async def test_close_all_on_empty_pool(self, pool):
        """close_all() on an empty pool does not raise."""
        await pool.close_all()
        assert pool.get_pool_stats() == {}


# ── get_pool_stats ─────────────────────────────────────────────────


class TestPoolStats:
    async def test_pool_stats_reports_tenants(self, pool):
        """get_pool_stats() returns an entry per cached tenant."""
        with _patch_authenticate():
            await pool.get_client("t1", "http://odoo:8069", "db1", "admin", "pass")
            await pool.get_client("t2", "http://odoo:8069", "db2", "admin", "pass")

        stats = pool.get_pool_stats()
        assert stats == {"t1": 1, "t2": 1}

    def test_pool_stats_empty(self, pool):
        """get_pool_stats() returns empty dict on a fresh pool."""
        assert pool.get_pool_stats() == {}


# ── Multi-Tenant ───────────────────────────────────────────────────


class TestMultiTenant:
    async def test_different_tenants_get_different_clients(self, pool):
        """Each tenant_id maps to a distinct client instance."""
        with _patch_authenticate():
            client_a = await pool.get_client(
                "t-alpha",
                "http://odoo:8069",
                "db_alpha",
                "admin",
                "pass",
            )
            client_b = await pool.get_client(
                "t-beta",
                "http://odoo:8069",
                "db_beta",
                "admin",
                "pass",
            )

        assert client_a is not client_b
        assert client_a.db == "db_alpha"
        assert client_b.db == "db_beta"
