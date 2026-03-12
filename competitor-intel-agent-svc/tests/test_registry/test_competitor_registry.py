"""Tests for CompetitorRegistry — CRUD, snapshot, change detection."""

from unittest.mock import AsyncMock

from app.registry.competitor_registry import CompetitorRegistry


class TestCompetitorRegistryCRUD:
    def setup_method(self):
        self.mock_redis = AsyncMock()
        self.registry = CompetitorRegistry(self.mock_redis)

    async def test_set_competitor(self):
        await self.registry.set_competitor(
            "t1", "acme-corp", {"name": "Acme Corp", "website": "https://acme.com"}
        )
        self.mock_redis.hset.assert_awaited_once()

    async def test_get_competitor_found(self):
        self.mock_redis.hget.return_value = '{"name": "Acme Corp"}'
        result = await self.registry.get_competitor("t1", "acme-corp")
        assert result == {"name": "Acme Corp"}

    async def test_get_competitor_not_found(self):
        self.mock_redis.hget.return_value = None
        result = await self.registry.get_competitor("t1", "missing")
        assert result is None

    async def test_get_all_competitors(self):
        self.mock_redis.hgetall.return_value = {
            "acme-corp": '{"name": "Acme Corp"}',
            "beta-inc": '{"name": "Beta Inc"}',
        }
        result = await self.registry.get_all_competitors("t1")
        assert len(result) == 2
        assert "acme-corp" in result
        assert result["acme-corp"]["name"] == "Acme Corp"

    async def test_delete_competitor(self):
        self.mock_redis.hdel.return_value = 1
        result = await self.registry.delete_competitor("t1", "acme-corp")
        assert result is True

    async def test_delete_nonexistent(self):
        self.mock_redis.hdel.return_value = 0
        result = await self.registry.delete_competitor("t1", "missing")
        assert result is False

    async def test_competitor_count(self):
        self.mock_redis.hlen.return_value = 5
        count = await self.registry.competitor_count("t1")
        assert count == 5


class TestCompetitorRegistryNoRedis:
    async def test_get_returns_none(self):
        registry = CompetitorRegistry(redis_client=None)
        result = await registry.get_competitor("t1", "acme")
        assert result is None

    async def test_set_is_noop(self):
        registry = CompetitorRegistry(redis_client=None)
        await registry.set_competitor("t1", "acme", {"name": "Acme"})

    async def test_count_returns_zero(self):
        registry = CompetitorRegistry(redis_client=None)
        count = await registry.competitor_count("t1")
        assert count == 0


class TestChangeDetection:
    def setup_method(self):
        self.mock_redis = AsyncMock()
        self.registry = CompetitorRegistry(self.mock_redis)

    async def test_new_competitor_detected(self):
        self.mock_redis.hget.return_value = None
        result = await self.registry.detect_changes(
            "t1", "acme-corp", {"name": "Acme Corp"}
        )
        assert result["status"] == "new"

    async def test_no_changes_detected(self):
        self.mock_redis.hget.return_value = (
            '{"name": "Acme Corp", "website": "https://acme.com"}'
        )
        result = await self.registry.detect_changes(
            "t1", "acme-corp",
            {"name": "Acme Corp", "website": "https://acme.com"},
        )
        assert result == {}

    async def test_changes_detected(self):
        self.mock_redis.hget.return_value = (
            '{"name": "Acme Corp", "market_position": "challenger"}'
        )
        result = await self.registry.detect_changes(
            "t1", "acme-corp",
            {"name": "Acme Corp", "market_position": "leader"},
        )
        assert result["status"] == "changed"
        assert "market_position" in result["changes"]
        assert result["changes"]["market_position"]["old"] == "challenger"
        assert result["changes"]["market_position"]["new"] == "leader"


class TestSnapshots:
    def setup_method(self):
        self.mock_redis = AsyncMock()
        self.registry = CompetitorRegistry(self.mock_redis)

    async def test_create_snapshot(self):
        await self.registry.create_snapshot(
            "t1", "acme-corp", {"name": "Acme Corp"}
        )
        self.mock_redis.set.assert_awaited_once()
        # Verify TTL is 90 days
        call_kwargs = self.mock_redis.set.call_args.kwargs
        assert call_kwargs.get("ex") == 90 * 24 * 60 * 60
