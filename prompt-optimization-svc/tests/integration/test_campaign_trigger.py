"""Integration tests for campaign trigger (US-038).

Requires real Redis.
"""

from .conftest import REDIS_URL, requires_redis


@requires_redis
class TestDebounceWithRedis:
    """AC-1: Debounce set/check via real Redis."""

    async def test_debounce_set_and_check(self, real_redis):
        from app.cache.prompt_cache import PromptCacheManager
        from app.logic.debounce import clear_debounce, is_debounced, set_debounce

        cache = PromptCacheManager(redis_url=REDIS_URL)
        await cache.connect()
        try:
            tenant = "__test_debounce_tenant"
            agent = "cga"

            # Initially not debounced
            assert await is_debounced(cache, tenant, agent) is False

            # Set debounce
            await set_debounce(cache, tenant, agent)
            assert await is_debounced(cache, tenant, agent) is True

            # Clear
            await clear_debounce(cache, tenant, agent)
            assert await is_debounced(cache, tenant, agent) is False
        finally:
            r = await cache.connect()
            await r.delete("reopt:debounce:__test_debounce_tenant:cga")
            await cache.close()

    async def test_different_agents_independent(self, real_redis):
        from app.cache.prompt_cache import PromptCacheManager
        from app.logic.debounce import clear_debounce, is_debounced, set_debounce

        cache = PromptCacheManager(redis_url=REDIS_URL)
        await cache.connect()
        try:
            tenant = "__test_debounce_ind"

            await set_debounce(cache, tenant, "cga")
            assert await is_debounced(cache, tenant, "cga") is True
            assert await is_debounced(cache, tenant, "coa") is False
        finally:
            r = await cache.connect()
            await r.delete("reopt:debounce:__test_debounce_ind:cga")
            await cache.close()
