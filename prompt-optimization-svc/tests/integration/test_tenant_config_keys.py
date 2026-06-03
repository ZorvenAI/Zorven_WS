"""Integration tests for tenant config keys (US-041).

Requires real Redis.
"""

from .conftest import REDIS_URL, requires_redis


@requires_redis
class TestTenantConfigRedis:
    async def test_get_defaults_without_config(self, real_redis):
        from app.cache.prompt_cache import PromptCacheManager
        from app.cache.tenant_config import TenantConfigManager

        cache = PromptCacheManager(redis_url=REDIS_URL)
        await cache.connect()
        try:
            mgr = TenantConfigManager(cache)
            tid = "__test_config_defaults"
            assert await mgr.get_optimization_enabled(tid) is True
            assert await mgr.get_auto_promotion(tid) is True
            assert await mgr.get_optimization_model(tid) == "claude-sonnet-4-6"
            assert await mgr.get_optimization_budget(tid) == 200
            assert await mgr.get_optimization_schedule(tid) == "monthly"
        finally:
            await cache.close()

    async def test_set_and_get_schedule(self, real_redis):
        from app.cache.prompt_cache import PromptCacheManager
        from app.cache.tenant_config import TenantConfigManager

        cache = PromptCacheManager(redis_url=REDIS_URL)
        await cache.connect()
        try:
            mgr = TenantConfigManager(cache)
            tid = "__test_schedule"
            await mgr.set_optimization_schedule(tid, "quarterly")
            assert await mgr.get_optimization_schedule(tid) == "quarterly"
        finally:
            r = await cache.connect()
            await r.delete("tenant:__test_schedule:config.wf3_optimization_schedule")
            await cache.close()

    async def test_set_and_get_budget(self, real_redis):
        from app.cache.prompt_cache import PromptCacheManager
        from app.cache.tenant_config import TenantConfigManager

        cache = PromptCacheManager(redis_url=REDIS_URL)
        await cache.connect()
        try:
            mgr = TenantConfigManager(cache)
            tid = "__test_budget"
            await mgr.set_optimization_budget(tid, 500)
            assert await mgr.get_optimization_budget(tid) == 500
        finally:
            r = await cache.connect()
            await r.delete("tenant:__test_budget:config.prompt_optimization_budget")
            await cache.close()
