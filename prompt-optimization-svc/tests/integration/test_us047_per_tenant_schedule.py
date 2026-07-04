"""Integration tests for per-tenant WF3 schedule (US-047).

Requires real Redis. PostgreSQL tests require real database.
"""

from .conftest import REDIS_URL, requires_redis


@requires_redis
class TestGetAllTenantSchedules:
    """Test get_all_tenant_schedules() Redis SCAN."""

    async def test_returns_all_tenants(self, real_redis):
        from app.cache.prompt_cache import PromptCacheManager
        from app.cache.tenant_config import TenantConfigManager

        cache = PromptCacheManager(redis_url=REDIS_URL)
        await cache.connect()
        keys = []
        try:
            mgr = TenantConfigManager(cache)
            # Set schedules for 3 test tenants
            for tid, sched in [
                ("__us047_t1", "biweekly"),
                ("__us047_t2", "quarterly"),
                ("__us047_t3", "monthly"),
            ]:
                await mgr.set_optimization_schedule(tid, sched)
                keys.append(f"tenant:{tid}:config.wf3_optimization_schedule")

            result = await mgr.get_all_tenant_schedules()
            assert result["__us047_t1"] == "biweekly"
            assert result["__us047_t2"] == "quarterly"
            assert result["__us047_t3"] == "monthly"
        finally:
            r = await cache.connect()
            for k in keys:
                await r.delete(k)
            await cache.close()

    async def test_empty_when_no_custom_schedules(self, real_redis):
        from app.cache.prompt_cache import PromptCacheManager
        from app.cache.tenant_config import TenantConfigManager

        cache = PromptCacheManager(redis_url=REDIS_URL)
        await cache.connect()
        try:
            mgr = TenantConfigManager(cache)
            # Clean up any leftover test keys
            r = await cache.connect()
            pattern = "tenant:__us047_empty_*:config.wf3_optimization_schedule"
            async for key in r.scan_iter(match=pattern):
                await r.delete(key)

            # Verify no results for nonexistent prefix pattern
            result = await mgr.get_all_tenant_schedules()
            # Filter to only our test tenants
            test_results = {
                k: v for k, v in result.items() if k.startswith("__us047_empty")
            }
            assert test_results == {}
        finally:
            await cache.close()


@requires_redis
class TestPerTenantScheduleReadWrite:
    """Test per-tenant schedule CRUD with Redis."""

    async def test_set_and_get_per_tenant(self, real_redis):
        from app.cache.prompt_cache import PromptCacheManager
        from app.cache.tenant_config import TenantConfigManager

        cache = PromptCacheManager(redis_url=REDIS_URL)
        await cache.connect()
        key = "tenant:__us047_rw:config.wf3_optimization_schedule"
        try:
            mgr = TenantConfigManager(cache)
            await mgr.set_optimization_schedule("__us047_rw", "biweekly")
            assert await mgr.get_optimization_schedule("__us047_rw") == "biweekly"
        finally:
            r = await cache.connect()
            await r.delete(key)
            await cache.close()

    async def test_update_overwrites(self, real_redis):
        from app.cache.prompt_cache import PromptCacheManager
        from app.cache.tenant_config import TenantConfigManager

        cache = PromptCacheManager(redis_url=REDIS_URL)
        await cache.connect()
        key = "tenant:__us047_upd:config.wf3_optimization_schedule"
        try:
            mgr = TenantConfigManager(cache)
            await mgr.set_optimization_schedule("__us047_upd", "biweekly")
            await mgr.set_optimization_schedule("__us047_upd", "quarterly")
            assert await mgr.get_optimization_schedule("__us047_upd") == "quarterly"
        finally:
            r = await cache.connect()
            await r.delete(key)
            await cache.close()

    async def test_missing_tenant_returns_default(self, real_redis):
        from app.cache.prompt_cache import PromptCacheManager
        from app.cache.tenant_config import DEFAULT_SCHEDULE, TenantConfigManager

        cache = PromptCacheManager(redis_url=REDIS_URL)
        await cache.connect()
        try:
            mgr = TenantConfigManager(cache)
            result = await mgr.get_optimization_schedule("__us047_nonexistent")
            assert result == DEFAULT_SCHEDULE
        finally:
            await cache.close()

    async def test_none_tenant_returns_default(self, real_redis):
        from app.cache.prompt_cache import PromptCacheManager
        from app.cache.tenant_config import DEFAULT_SCHEDULE, TenantConfigManager

        cache = PromptCacheManager(redis_url=REDIS_URL)
        await cache.connect()
        try:
            mgr = TenantConfigManager(cache)
            result = await mgr.get_optimization_schedule(None)
            assert result == DEFAULT_SCHEDULE
        finally:
            await cache.close()


@requires_redis
class TestEffectiveScheduleIntegration:
    """Test most-aggressive-wins logic with real Redis."""

    async def test_biweekly_wins_over_quarterly(self, real_redis):
        from app.cache.prompt_cache import PromptCacheManager
        from app.cache.tenant_config import TenantConfigManager
        from app.tasks.optimize_wf3_pipeline import SCHEDULE_PRIORITY

        cache = PromptCacheManager(redis_url=REDIS_URL)
        await cache.connect()
        keys = []
        try:
            mgr = TenantConfigManager(cache)
            await mgr.set_optimization_schedule("__us047_eff1", "quarterly")
            await mgr.set_optimization_schedule("__us047_eff2", "biweekly")
            keys = [
                "tenant:__us047_eff1:config.wf3_optimization_schedule",
                "tenant:__us047_eff2:config.wf3_optimization_schedule",
            ]

            schedules = await mgr.get_all_tenant_schedules()
            test_schedules = {
                k: v for k, v in schedules.items() if k.startswith("__us047_eff")
            }
            most_aggressive = min(
                test_schedules.values(),
                key=lambda s: SCHEDULE_PRIORITY.get(s, 3),
            )
            assert most_aggressive == "biweekly"
        finally:
            r = await cache.connect()
            for k in keys:
                await r.delete(k)
            await cache.close()
