"""Integration tests for canary routing and dashboard endpoints.

Requires real Redis at POI_PROMPT_CACHE_REDIS_URL.
"""

import uuid

import pytest

from .conftest import REDIS_URL, requires_redis

RUN_ID = uuid.uuid4().hex[:8]
TEST_PREFIX = f"__canary_routing_{RUN_ID}_"


@requires_redis
class TestCanaryRouting:
    """Canary routing and dashboard integration tests with real Redis."""

    async def test_canary_routing_deterministic(self):
        """Same tenant_id always gets same routing decision."""
        from app.logic.canary_manager import is_canary_request

        tenant = f"{TEST_PREFIX}tenant-stable"
        results = [is_canary_request(tenant) for _ in range(100)]
        assert len(set(results)) == 1, "is_canary_request should be deterministic"

    async def test_start_canary_and_list_active(self, real_redis):
        """Start 2 canaries, verify list_active_canaries returns both."""
        from app.cache.prompt_cache import PromptCacheManager
        from app.logic.canary_manager import CanaryManager

        cache = PromptCacheManager(redis_url=REDIS_URL)
        await cache.connect()
        try:
            mgr = CanaryManager(cache)
            name1 = f"{TEST_PREFIX}active-1"
            name2 = f"{TEST_PREFIX}active-2"

            await mgr.start_canary(name1, 2, 1, "mra")
            await mgr.start_canary(name2, 3, 2, "cga")

            active = await mgr.list_active_canaries()
            active_names = {c.prompt_name for c in active}

            assert name1 in active_names
            assert name2 in active_names
        finally:
            r = await cache.connect()
            await r.delete(f"prompt:canary:{name1}")
            await r.delete(f"prompt:canary:{name2}")
            await cache.close()

    async def test_canary_metrics_comparison(self, real_redis):
        """Record metrics for both versions, verify comparison."""
        from app.cache.prompt_cache import PromptCacheManager
        from app.logic.canary_manager import CanaryManager

        cache = PromptCacheManager(redis_url=REDIS_URL)
        await cache.connect()
        try:
            mgr = CanaryManager(cache)
            name = f"{TEST_PREFIX}comparison"

            await mgr.start_canary(name, 2, 1, "bpa")

            # Record metrics for both versions
            await mgr.record_canary_metric(name, 1, "json_compliance", 0.90)
            await mgr.record_canary_metric(name, 1, "brand_voice", 0.85)
            await mgr.record_canary_metric(name, 2, "json_compliance", 0.92)
            await mgr.record_canary_metric(name, 2, "brand_voice", 0.88)

            comparison = await mgr.get_canary_comparison(name)
            assert comparison is not None
            assert comparison["canary_version"] == 2
            assert comparison["production_version"] == 1
            assert comparison["status"] == "healthy"
            # Canary is better, so regression should be negative
            assert comparison["regression_pct"] is not None
            assert comparison["regression_pct"] < 0
        finally:
            r = await cache.connect()
            await r.delete(f"prompt:canary:{name}")
            await r.delete(f"prompt:metrics:{name}:v1")
            await r.delete(f"prompt:metrics:{name}:v2")
            await cache.close()

    async def test_rollback_records_history(self, real_redis):
        """Rollback records outcome in canary history."""
        from app.cache.prompt_cache import PromptCacheManager
        from app.logic.canary_manager import CanaryManager

        cache = PromptCacheManager(redis_url=REDIS_URL)
        await cache.connect()
        try:
            mgr = CanaryManager(cache)
            name = f"{TEST_PREFIX}rollback-hist"

            await mgr.start_canary(name, 2, 1, "cga")
            await mgr.rollback_canary(name)

            # State should be cleared
            state = await mgr.get_canary_state(name)
            assert state is None

            # History should contain the rollback
            history = await mgr.list_canary_history()
            rollback_entries = [h for h in history if h["prompt_name"] == name]
            assert len(rollback_entries) == 1
            assert rollback_entries[0]["outcome"] == "rolled_back"
        finally:
            r = await cache.connect()
            await r.delete(f"prompt:canary:{name}")
            await r.delete(f"prompt:canary_history:{name}:v2")
            await cache.close()

    async def test_promote_canary_records_history(self, real_redis):
        """Promote records outcome in canary history."""
        from app.cache.prompt_cache import PromptCacheManager
        from app.logic.canary_manager import CanaryManager

        cache = PromptCacheManager(redis_url=REDIS_URL)
        await cache.connect()
        try:
            mgr = CanaryManager(cache)
            name = f"{TEST_PREFIX}promote-hist"

            await mgr.start_canary(name, 2, 1, "mra")
            await mgr.promote_canary(name)

            # State should be cleared
            state = await mgr.get_canary_state(name)
            assert state is None

            # History should contain the promotion
            history = await mgr.list_canary_history()
            promoted_entries = [h for h in history if h["prompt_name"] == name]
            assert len(promoted_entries) == 1
            assert promoted_entries[0]["outcome"] == "promoted"
        finally:
            r = await cache.connect()
            await r.delete(f"prompt:canary:{name}")
            await r.delete(f"prompt:canary_history:{name}:v2")
            await cache.close()

    async def test_no_active_canary_returns_none(self, real_redis):
        """get_canary_state returns None for non-existent canary."""
        from app.cache.prompt_cache import PromptCacheManager
        from app.logic.canary_manager import CanaryManager

        cache = PromptCacheManager(redis_url=REDIS_URL)
        await cache.connect()
        try:
            mgr = CanaryManager(cache)
            state = await mgr.get_canary_state(f"{TEST_PREFIX}nonexistent")
            assert state is None
        finally:
            await cache.close()

    async def test_canary_comparison_no_canary_returns_none(self, real_redis):
        """get_canary_comparison returns None when no canary exists."""
        from app.cache.prompt_cache import PromptCacheManager
        from app.logic.canary_manager import CanaryManager

        cache = PromptCacheManager(redis_url=REDIS_URL)
        await cache.connect()
        try:
            mgr = CanaryManager(cache)
            comparison = await mgr.get_canary_comparison(f"{TEST_PREFIX}no-canary")
            assert comparison is None
        finally:
            await cache.close()

    async def test_regression_triggers_rollback(self, real_redis):
        """Record poor metrics, check regression triggers rollback."""
        from app.cache.prompt_cache import PromptCacheManager
        from app.logic.canary_manager import CanaryManager

        cache = PromptCacheManager(redis_url=REDIS_URL)
        await cache.connect()
        try:
            mgr = CanaryManager(cache)
            name = f"{TEST_PREFIX}regression"

            await mgr.start_canary(name, 2, 1, "coa")

            # Production scores high, canary scores low (>5% regression)
            await mgr.record_canary_metric(name, 1, "json_compliance", 0.95)
            await mgr.record_canary_metric(name, 2, "json_compliance", 0.80)

            regression = await mgr.check_canary_regression(name)
            assert regression is not None
            assert regression > 0.05

            # Canary should be rolled back (cleared)
            state = await mgr.get_canary_state(name)
            assert state is None
        finally:
            r = await cache.connect()
            await r.delete(f"prompt:canary:{name}")
            await r.delete(f"prompt:metrics:{name}:v1")
            await r.delete(f"prompt:metrics:{name}:v2")
            await r.delete(f"prompt:canary_history:{name}:v2")
            await cache.close()
