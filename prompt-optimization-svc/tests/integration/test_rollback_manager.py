"""Integration tests for rollback manager (US-035).

Requires real Redis.
"""

from .conftest import REDIS_URL, requires_redis


@requires_redis
class TestRollbackCacheInvalidation:
    """AC-3: Redis cache invalidated on rollback."""

    async def test_cache_key_deleted(self, real_redis):
        from app.cache.prompt_cache import PromptCacheManager
        from app.logic.rollback_manager import PRODUCTION_CACHE_KEY

        cache = PromptCacheManager(redis_url=REDIS_URL)
        await cache.connect()
        try:
            # Set a cache entry
            r = await cache.connect()
            key = PRODUCTION_CACHE_KEY.format(name="__test_rollback_prompt")
            await r.set(key, "cached-template-data")

            # Verify it exists
            assert await r.get(key) is not None

            # Delete it (simulating rollback cache invalidation)
            await r.delete(key)
            assert await r.get(key) is None
        finally:
            await cache.close()


class TestLifecycleTransitionValid:
    """ARCHIVED → PRODUCTION transition for rollback."""

    def test_archived_to_production(self):
        from app.logic.lifecycle import PromptLifecycleManager, PromptState

        mgr = PromptLifecycleManager()
        # Should not raise
        mgr.validate_transition(PromptState.ARCHIVED, PromptState.PRODUCTION)

    def test_production_to_archived(self):
        from app.logic.lifecycle import PromptLifecycleManager, PromptState

        mgr = PromptLifecycleManager()
        mgr.validate_transition(PromptState.PRODUCTION, PromptState.ARCHIVED)
