"""Tests for TrendRegistry — CRUD, velocity detection, score history, eviction."""

import json
from unittest.mock import AsyncMock, MagicMock

from app.registry.models import TrendRegistryEntry, TrendVelocity
from app.registry.trend_registry import TrendRegistry


def _make_entry(**overrides) -> dict:
    """Create a TrendRegistryEntry dict."""
    defaults = {
        "trend_slug": "ev-charging",
        "topic": "EV Charging Growth",
        "relevance_score": 80,
        "audience_alignment": 20,
        "competitive_landscape": 20,
        "brand_fit": 20,
        "momentum": 20,
        "recommendation": "capitalize",
        "platforms": ["twitter"],
        "first_seen": "2026-03-01T00:00:00Z",
        "last_updated": "2026-03-10T00:00:00Z",
        "scan_count": 3,
    }
    defaults.update(overrides)
    return defaults


class TestUpsertAndGet:
    """Round-trip upsert and get operations."""

    def setup_method(self) -> None:
        self.mock_redis = AsyncMock()
        self.event_emitter = AsyncMock()
        self.registry = TrendRegistry(self.mock_redis, self.event_emitter)

    async def test_upsert_new_trend(self) -> None:
        self.mock_redis.hget.return_value = None  # No existing trend
        self.mock_redis.get_tenant_config = AsyncMock(return_value="90")
        profile = _make_entry(scan_count=0)

        result = await self.registry.upsert_trend("t1", "ev-charging", profile)
        self.mock_redis.hset.assert_awaited_once()
        self.mock_redis.zadd.assert_awaited_once()
        # New trend emits velocity event with direction="new"
        assert result is not None
        assert result.direction == "new"

    async def test_upsert_existing_trend(self) -> None:
        existing = _make_entry(relevance_score=80, scan_count=3)
        self.mock_redis.hget.return_value = json.dumps(existing)
        self.mock_redis.get_tenant_config = AsyncMock(return_value="90")

        updated = _make_entry(relevance_score=82)
        result = await self.registry.upsert_trend("t1", "ev-charging", updated)
        self.mock_redis.hset.assert_awaited_once()
        # Delta is 2, below threshold (15), so no velocity event
        assert result is None

    async def test_get_trend_found(self) -> None:
        entry = _make_entry()
        self.mock_redis.hget.return_value = json.dumps(entry)
        result = await self.registry.get_trend("t1", "ev-charging")
        assert result is not None
        assert result.trend_slug == "ev-charging"
        assert result.relevance_score == 80

    async def test_get_trend_not_found(self) -> None:
        self.mock_redis.hget.return_value = None
        result = await self.registry.get_trend("t1", "nonexistent")
        assert result is None

    async def test_get_all_trends(self) -> None:
        self.mock_redis.hgetall.return_value = {
            "ev-charging": json.dumps(_make_entry(trend_slug="ev-charging")),
            "remote-work": json.dumps(
                _make_entry(trend_slug="remote-work", topic="Remote Work")
            ),
        }
        result = await self.registry.get_all_trends("t1")
        assert len(result) == 2
        assert "ev-charging" in result
        assert "remote-work" in result
        assert isinstance(result["ev-charging"], TrendRegistryEntry)

    async def test_delete_trend(self) -> None:
        self.mock_redis.hdel.return_value = 1
        result = await self.registry.delete_trend("t1", "ev-charging")
        assert result is True

    async def test_delete_nonexistent(self) -> None:
        self.mock_redis.hdel.return_value = 0
        result = await self.registry.delete_trend("t1", "nonexistent")
        assert result is False

    async def test_trend_count(self) -> None:
        self.mock_redis.hlen.return_value = 5
        count = await self.registry.trend_count("t1")
        assert count == 5

    async def test_upsert_preserves_first_seen(self) -> None:
        existing = _make_entry(
            first_seen="2026-01-15T00:00:00Z",
            scan_count=5,
        )
        self.mock_redis.hget.return_value = json.dumps(existing)
        self.mock_redis.get_tenant_config = AsyncMock(return_value="90")

        updated = _make_entry(relevance_score=82)
        await self.registry.upsert_trend("t1", "ev-charging", updated)
        # Verify hset was called with correct data
        call_args = self.mock_redis.hset.call_args
        stored = json.loads(call_args[0][2])
        assert stored["first_seen"] == "2026-01-15T00:00:00Z"
        assert stored["scan_count"] == 6  # Incremented

    async def test_upsert_error_returns_none(self) -> None:
        """When hset fails, the outer try/except catches and returns None."""
        self.mock_redis.hget.return_value = None
        self.mock_redis.hset.side_effect = Exception("Redis down")
        self.mock_redis.get_tenant_config = AsyncMock(return_value="90")
        result = await self.registry.upsert_trend(
            "t1", "ev-charging", _make_entry()
        )
        assert result is None


class TestVelocityDetection:
    """Score change triggers velocity event when delta >= 15."""

    def setup_method(self) -> None:
        self.mock_redis = AsyncMock()
        self.event_emitter = AsyncMock()
        self.registry = TrendRegistry(self.mock_redis, self.event_emitter)

    async def test_rising_velocity_detected(self) -> None:
        existing = _make_entry(relevance_score=60)
        self.mock_redis.hget.return_value = json.dumps(existing)
        self.mock_redis.get_tenant_config = AsyncMock(return_value="90")

        updated = _make_entry(relevance_score=80)  # Delta = +20
        result = await self.registry.upsert_trend("t1", "ev-charging", updated)
        assert result is not None
        assert result.direction == "rising"
        assert result.delta == 20
        assert result.old_score == 60
        assert result.new_score == 80

    async def test_falling_velocity_detected(self) -> None:
        existing = _make_entry(relevance_score=80)
        self.mock_redis.hget.return_value = json.dumps(existing)
        self.mock_redis.get_tenant_config = AsyncMock(return_value="90")

        updated = _make_entry(relevance_score=60)  # Delta = -20
        result = await self.registry.upsert_trend("t1", "ev-charging", updated)
        assert result is not None
        assert result.direction == "falling"
        assert result.delta == -20

    async def test_small_change_no_velocity(self) -> None:
        existing = _make_entry(relevance_score=80)
        self.mock_redis.hget.return_value = json.dumps(existing)
        self.mock_redis.get_tenant_config = AsyncMock(return_value="90")

        updated = _make_entry(relevance_score=85)  # Delta = 5 (below 15)
        result = await self.registry.upsert_trend("t1", "ev-charging", updated)
        assert result is None

    async def test_new_trend_velocity(self) -> None:
        self.mock_redis.hget.return_value = None
        self.mock_redis.get_tenant_config = AsyncMock(return_value="90")

        profile = _make_entry(relevance_score=75)
        result = await self.registry.upsert_trend("t1", "new-trend", profile)
        assert result is not None
        assert result.direction == "new"
        assert result.delta == 75
        assert result.old_score == 0

    async def test_velocity_event_emitted(self) -> None:
        existing = _make_entry(relevance_score=50)
        self.mock_redis.hget.return_value = json.dumps(existing)
        self.mock_redis.get_tenant_config = AsyncMock(return_value="90")

        updated = _make_entry(relevance_score=70)  # Delta = +20
        await self.registry.upsert_trend("t1", "ev-charging", updated)
        self.event_emitter.emit.assert_awaited_once()


class TestStaticVelocityDetection:
    """Test the static _detect_velocity_change method directly."""

    def test_new_entry(self) -> None:
        entry = TrendRegistryEntry(relevance_score=75)
        result = TrendRegistry._detect_velocity_change(None, entry, "test")
        assert result is not None
        assert result.direction == "new"
        assert result.delta == 75

    def test_rising(self) -> None:
        existing = TrendRegistryEntry(relevance_score=50)
        new = TrendRegistryEntry(relevance_score=70)
        result = TrendRegistry._detect_velocity_change(existing, new, "test")
        assert result is not None
        assert result.direction == "rising"
        assert result.delta == 20

    def test_falling(self) -> None:
        existing = TrendRegistryEntry(relevance_score=80)
        new = TrendRegistryEntry(relevance_score=60)
        result = TrendRegistry._detect_velocity_change(existing, new, "test")
        assert result is not None
        assert result.direction == "falling"
        assert result.delta == -20

    def test_no_change(self) -> None:
        existing = TrendRegistryEntry(relevance_score=75)
        new = TrendRegistryEntry(relevance_score=80)
        result = TrendRegistry._detect_velocity_change(existing, new, "test")
        # Delta = 5, below threshold 15
        assert result is None

    def test_exact_threshold(self) -> None:
        existing = TrendRegistryEntry(relevance_score=50)
        new = TrendRegistryEntry(relevance_score=65)
        result = TrendRegistry._detect_velocity_change(existing, new, "test")
        # Delta = 15, exactly at threshold
        assert result is not None
        assert result.direction == "rising"


class TestScoreHistory:
    """Sorted Set score history operations."""

    def setup_method(self) -> None:
        self.mock_redis = AsyncMock()
        self.registry = TrendRegistry(self.mock_redis)

    async def test_get_score_history(self) -> None:
        self.mock_redis.zrangebyscore.return_value = [
            ("75", 1709337600.0),
            ("80", 1709424000.0),
        ]
        result = await self.registry.get_score_history("t1", "ev-charging")
        assert len(result) == 2

    async def test_get_score_history_empty(self) -> None:
        self.mock_redis.zrangebyscore.return_value = []
        result = await self.registry.get_score_history("t1", "nonexistent")
        assert result == []

    async def test_get_score_history_custom_days(self) -> None:
        self.mock_redis.zrangebyscore.return_value = []
        await self.registry.get_score_history("t1", "test", days=30)
        self.mock_redis.zrangebyscore.assert_awaited_once()

    async def test_get_score_history_error(self) -> None:
        self.mock_redis.zrangebyscore.side_effect = Exception("Redis error")
        result = await self.registry.get_score_history("t1", "test")
        assert result == []


class TestEviction:
    """Score eviction via zremrangebyscore."""

    def setup_method(self) -> None:
        self.mock_redis = AsyncMock()
        self.registry = TrendRegistry(self.mock_redis)

    async def test_evict_expired_scores(self) -> None:
        self.mock_redis.zremrangebyscore.return_value = 3
        removed = await self.registry.evict_expired_scores(
            "t1", "ev-charging", retention_days=90
        )
        assert removed == 3
        self.mock_redis.zremrangebyscore.assert_awaited_once()

    async def test_evict_no_expired(self) -> None:
        self.mock_redis.zremrangebyscore.return_value = 0
        removed = await self.registry.evict_expired_scores("t1", "test")
        assert removed == 0

    async def test_evict_error_returns_zero(self) -> None:
        self.mock_redis.zremrangebyscore.side_effect = Exception("Redis error")
        removed = await self.registry.evict_expired_scores("t1", "test")
        assert removed == 0


class TestRegistryModels:
    """Test Pydantic models for TrendRegistryEntry and TrendVelocity."""

    def test_trend_registry_entry_defaults(self) -> None:
        entry = TrendRegistryEntry()
        assert entry.trend_slug == ""
        assert entry.relevance_score == 0
        assert entry.recommendation == "monitor"
        assert entry.scan_count == 0
        assert entry.platforms == []

    def test_trend_registry_entry_full(self) -> None:
        entry = TrendRegistryEntry(**_make_entry())
        assert entry.trend_slug == "ev-charging"
        assert entry.relevance_score == 80
        assert entry.scan_count == 3

    def test_trend_velocity(self) -> None:
        velocity = TrendVelocity(
            trend_slug="test",
            direction="rising",
            delta=20,
            old_score=60,
            new_score=80,
        )
        assert velocity.direction == "rising"
        assert velocity.delta == 20
