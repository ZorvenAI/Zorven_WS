"""Integration tests for tenant overrides (US-039).

Requires real Redis.
"""

from .conftest import REDIS_URL, requires_redis


@requires_redis
class TestTenantOverrideRedis:
    async def test_create_caches_in_redis(self, real_redis):
        from app.cache.prompt_cache import PromptCacheManager
        from app.logic.tenant_override import TENANT_CACHE_KEY, create_tenant_override

        cache = PromptCacheManager(redis_url=REDIS_URL)
        await cache.connect()
        try:
            await create_tenant_override(
                prompt_name="__test_override",
                tenant_id="__test_tenant",
                template="Override template",
                prompt_cache=cache,
            )
            r = await cache.connect()
            key = TENANT_CACHE_KEY.format(
                name="__test_override", tenant_id="__test_tenant"
            )
            val = await r.get(key)
            assert val == "Override template"
        finally:
            r = await cache.connect()
            await r.delete("prompt:__test_override:tenant:__test_tenant")
            await cache.close()

    async def test_delete_removes_from_redis(self, real_redis):
        from app.cache.prompt_cache import PromptCacheManager
        from app.logic.tenant_override import (
            TENANT_CACHE_KEY,
            create_tenant_override,
            delete_tenant_override,
        )

        cache = PromptCacheManager(redis_url=REDIS_URL)
        await cache.connect()
        try:
            await create_tenant_override(
                prompt_name="__test_del",
                tenant_id="__test_t",
                template="To be deleted",
                prompt_cache=cache,
            )
            deleted = await delete_tenant_override(
                prompt_name="__test_del",
                tenant_id="__test_t",
                prompt_cache=cache,
            )
            assert deleted is True

            r = await cache.connect()
            key = TENANT_CACHE_KEY.format(name="__test_del", tenant_id="__test_t")
            assert await r.get(key) is None
        finally:
            r = await cache.connect()
            await r.delete("prompt:__test_del:tenant:__test_t")
            await cache.close()
