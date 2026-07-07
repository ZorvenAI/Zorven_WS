"""Integration tests for dataset size configuration (US-029).

Requires real Redis.
"""

import pytest

from .conftest import REDIS_URL, requires_redis


@requires_redis
class TestDatasetSizeRedis:
    """Dataset size config with real Redis."""

    async def test_get_default_without_config(self, real_redis):
        from app.cache.prompt_cache import PromptCacheManager
        from app.cache.tenant_config import DEFAULT_DATASET_SIZE, TenantConfigManager

        cache = PromptCacheManager(redis_url=REDIS_URL)
        await cache.connect()
        try:
            mgr = TenantConfigManager(cache)
            size = await mgr.get_golden_dataset_size("__test_no_config")
            assert size == DEFAULT_DATASET_SIZE
        finally:
            await cache.close()

    async def test_set_and_get(self, real_redis):
        from app.cache.prompt_cache import PromptCacheManager
        from app.cache.tenant_config import TenantConfigManager

        cache = PromptCacheManager(redis_url=REDIS_URL)
        await cache.connect()
        try:
            mgr = TenantConfigManager(cache)
            await mgr.set_golden_dataset_size("__test_ds_size", 25)
            size = await mgr.get_golden_dataset_size("__test_ds_size")
            assert size == 25
        finally:
            # Cleanup
            r = await cache.connect()
            await r.delete("tenant:__test_ds_size:config.golden_dataset_default_size")
            await cache.close()

    async def test_clamped_value_stored(self, real_redis):
        from app.cache.prompt_cache import PromptCacheManager
        from app.cache.tenant_config import MAX_DATASET_SIZE, TenantConfigManager

        cache = PromptCacheManager(redis_url=REDIS_URL)
        await cache.connect()
        try:
            mgr = TenantConfigManager(cache)
            await mgr.set_golden_dataset_size("__test_ds_clamp", 999)
            size = await mgr.get_golden_dataset_size("__test_ds_clamp")
            assert size == MAX_DATASET_SIZE
        finally:
            r = await cache.connect()
            await r.delete("tenant:__test_ds_clamp:config.golden_dataset_default_size")
            await cache.close()

    async def test_no_tenant_returns_default(self, real_redis):
        from app.cache.prompt_cache import PromptCacheManager
        from app.cache.tenant_config import DEFAULT_DATASET_SIZE, TenantConfigManager

        cache = PromptCacheManager(redis_url=REDIS_URL)
        await cache.connect()
        try:
            mgr = TenantConfigManager(cache)
            size = await mgr.get_golden_dataset_size(None)
            assert size == DEFAULT_DATASET_SIZE
        finally:
            await cache.close()
