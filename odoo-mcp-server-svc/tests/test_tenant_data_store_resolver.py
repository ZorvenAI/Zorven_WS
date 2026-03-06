"""Tests for TenantDataStoreResolver — tenant → Vertex AI data store lookup."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.rag.tenant_resolver import CACHE_KEY_PREFIX, TenantDataStoreResolver


@pytest.fixture
def mock_redis() -> AsyncMock:
    """Mock RedisManager."""
    redis = AsyncMock()
    redis.get.return_value = None
    redis.set.return_value = None
    return redis


@pytest.fixture
def resolver(mock_redis: AsyncMock) -> TenantDataStoreResolver:
    """Resolver with mock Redis and no DB pool."""
    return TenantDataStoreResolver(
        database_url="",
        redis_manager=mock_redis,
        default_data_store_id="default-store",
    )


# ── Constructor ──


class TestInit:
    def test_defaults(self) -> None:
        r = TenantDataStoreResolver(database_url="")
        assert r.database_url == ""
        assert r.redis_manager is None
        assert r._pool is None

    def test_custom_default_store(self) -> None:
        r = TenantDataStoreResolver(
            database_url="",
            default_data_store_id="my-store",
        )
        assert r.default_data_store_id == "my-store"


# ── resolve_data_store_id ──


class TestResolveDataStoreId:
    async def test_returns_cached_value(
        self,
        resolver: TenantDataStoreResolver,
        mock_redis: AsyncMock,
    ) -> None:
        """Returns cached data store ID from Redis."""
        mock_redis.get.return_value = "cached-store"

        result = await resolver.resolve_data_store_id("1")

        assert result == "cached-store"
        mock_redis.get.assert_awaited_once_with(f"{CACHE_KEY_PREFIX}:1")

    async def test_falls_back_to_default_when_no_db(
        self,
        resolver: TenantDataStoreResolver,
    ) -> None:
        """Returns default when no DB pool and no cache."""
        result = await resolver.resolve_data_store_id("1")

        assert result == "default-store"

    async def test_caches_db_result(
        self,
        mock_redis: AsyncMock,
    ) -> None:
        """Caches DB lookup result in Redis."""
        resolver = TenantDataStoreResolver(
            database_url="postgresql://test",
            redis_manager=mock_redis,
            default_data_store_id="default-store",
        )

        # Mock the DB pool
        mock_pool = AsyncMock()
        mock_pool.fetchrow.return_value = {"vertex_ai_data_store_id": "tenant-store-1"}
        resolver._pool = mock_pool

        result = await resolver.resolve_data_store_id("42")

        assert result == "tenant-store-1"
        mock_redis.set.assert_awaited_once()

    async def test_returns_default_for_non_numeric_tenant(
        self,
        resolver: TenantDataStoreResolver,
    ) -> None:
        """Returns default for non-numeric tenant_id."""
        resolver._pool = AsyncMock()

        result = await resolver.resolve_data_store_id("not-a-number")

        assert result == "default-store"

    async def test_returns_default_when_db_returns_none(
        self,
        mock_redis: AsyncMock,
    ) -> None:
        """Returns default when DB has no data store ID for tenant."""
        resolver = TenantDataStoreResolver(
            database_url="postgresql://test",
            redis_manager=mock_redis,
            default_data_store_id="default-store",
        )
        mock_pool = AsyncMock()
        mock_pool.fetchrow.return_value = None
        resolver._pool = mock_pool

        result = await resolver.resolve_data_store_id("999")

        assert result == "default-store"

    async def test_returns_default_when_db_field_is_empty(
        self,
        mock_redis: AsyncMock,
    ) -> None:
        """Returns default when vertex_ai_data_store_id is empty."""
        resolver = TenantDataStoreResolver(
            database_url="postgresql://test",
            redis_manager=mock_redis,
            default_data_store_id="default-store",
        )
        mock_pool = AsyncMock()
        mock_pool.fetchrow.return_value = {"vertex_ai_data_store_id": ""}
        resolver._pool = mock_pool

        result = await resolver.resolve_data_store_id("1")

        assert result == "default-store"

    async def test_handles_db_exception_gracefully(
        self,
        mock_redis: AsyncMock,
    ) -> None:
        """Falls back to default when DB query raises."""
        resolver = TenantDataStoreResolver(
            database_url="postgresql://test",
            redis_manager=mock_redis,
            default_data_store_id="default-store",
        )
        mock_pool = AsyncMock()
        mock_pool.fetchrow.side_effect = Exception("Connection lost")
        resolver._pool = mock_pool

        result = await resolver.resolve_data_store_id("1")

        assert result == "default-store"

    async def test_handles_redis_get_exception(self) -> None:
        """Falls back gracefully when Redis read fails."""
        broken_redis = AsyncMock()
        broken_redis.get.side_effect = Exception("Redis down")
        broken_redis.set.return_value = None

        resolver = TenantDataStoreResolver(
            database_url="",
            redis_manager=broken_redis,
            default_data_store_id="default-store",
        )

        result = await resolver.resolve_data_store_id("1")

        assert result == "default-store"

    async def test_handles_redis_set_exception(
        self,
        mock_redis: AsyncMock,
    ) -> None:
        """Does not fail when Redis cache write fails."""
        mock_redis.set.side_effect = Exception("Redis write failed")

        resolver = TenantDataStoreResolver(
            database_url="postgresql://test",
            redis_manager=mock_redis,
            default_data_store_id="default-store",
        )
        mock_pool = AsyncMock()
        mock_pool.fetchrow.return_value = {"vertex_ai_data_store_id": "tenant-store"}
        resolver._pool = mock_pool

        # Should not raise
        result = await resolver.resolve_data_store_id("1")
        assert result == "tenant-store"


# ── init / close ──


class TestLifecycle:
    async def test_init_without_database_url(self) -> None:
        """init() is a no-op when DATABASE_URL is empty."""
        resolver = TenantDataStoreResolver(database_url="")
        await resolver.init()
        assert resolver._pool is None

    async def test_close_without_pool(self) -> None:
        """close() is safe when _pool is None."""
        resolver = TenantDataStoreResolver(database_url="")
        await resolver.close()  # Should not raise

    async def test_close_with_pool(self) -> None:
        """close() calls pool.close()."""
        resolver = TenantDataStoreResolver(database_url="")
        mock_pool = AsyncMock()
        resolver._pool = mock_pool

        await resolver.close()

        mock_pool.close.assert_awaited_once()
        assert resolver._pool is None
