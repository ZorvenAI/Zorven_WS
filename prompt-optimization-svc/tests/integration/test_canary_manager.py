"""Integration tests for canary manager (US-033).

Requires real Redis.
"""

from .conftest import REDIS_URL, requires_redis


@requires_redis
class TestCanaryManagerRedis:
    """Canary state and metrics with real Redis."""

    async def test_start_and_get_canary(self, real_redis):
        from app.cache.prompt_cache import PromptCacheManager
        from app.logic.canary_manager import CanaryManager

        cache = PromptCacheManager(redis_url=REDIS_URL)
        await cache.connect()
        try:
            mgr = CanaryManager(cache)
            state = await mgr.start_canary(
                prompt_name="__test_canary_prompt",
                canary_version=2,
                production_version=1,
                agent_code="mra",
            )
            assert state.active is True
            assert state.canary_version == 2

            retrieved = await mgr.get_canary_state("__test_canary_prompt")
            assert retrieved is not None
            assert retrieved.canary_version == 2
            assert retrieved.agent_code == "mra"
        finally:
            r = await cache.connect()
            await r.delete("prompt:canary:__test_canary_prompt")
            await cache.close()

    async def test_record_and_get_metrics(self, real_redis):
        from app.cache.prompt_cache import PromptCacheManager
        from app.logic.canary_manager import CanaryManager

        cache = PromptCacheManager(redis_url=REDIS_URL)
        await cache.connect()
        try:
            mgr = CanaryManager(cache)
            await mgr.record_canary_metric(
                "__test_metrics_prompt", 5, "json_compliance", 0.95
            )
            await mgr.record_canary_metric(
                "__test_metrics_prompt", 5, "pii_safety", 0.88
            )

            metrics = await mgr.get_canary_metrics("__test_metrics_prompt", 5)
            assert metrics["json_compliance"] == 0.95
            assert metrics["pii_safety"] == 0.88
        finally:
            r = await cache.connect()
            await r.delete("prompt:metrics:__test_metrics_prompt:v5")
            await cache.close()

    async def test_rollback_clears_state(self, real_redis):
        from app.cache.prompt_cache import PromptCacheManager
        from app.logic.canary_manager import CanaryManager

        cache = PromptCacheManager(redis_url=REDIS_URL)
        await cache.connect()
        try:
            mgr = CanaryManager(cache)
            await mgr.start_canary("__test_rollback", 3, 2, "cga")

            rolled_back = await mgr.rollback_canary("__test_rollback")
            assert rolled_back is True

            state = await mgr.get_canary_state("__test_rollback")
            assert state is None
        finally:
            r = await cache.connect()
            await r.delete("prompt:canary:__test_rollback")
            await cache.close()

    async def test_nonexistent_canary_returns_none(self, real_redis):
        from app.cache.prompt_cache import PromptCacheManager
        from app.logic.canary_manager import CanaryManager

        cache = PromptCacheManager(redis_url=REDIS_URL)
        await cache.connect()
        try:
            mgr = CanaryManager(cache)
            state = await mgr.get_canary_state("__test_nonexistent")
            assert state is None
        finally:
            await cache.close()
