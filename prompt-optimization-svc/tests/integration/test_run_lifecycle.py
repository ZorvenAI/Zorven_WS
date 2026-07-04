"""Integration tests for run lifecycle with real Redis (US-020)."""

import pytest

from app.cache.prompt_cache import PromptCacheManager
from app.logic.run_lifecycle import RunLifecycleManager, RunState

from .conftest import REDIS_URL, requires_redis


@pytest.mark.integration
@requires_redis
class TestRunLifecycleRedis:
    """AC-1: States persisted to Redis progress hash."""

    @pytest.fixture
    async def manager(self):
        cache = PromptCacheManager(redis_url=REDIS_URL)
        await cache.connect()
        mgr = RunLifecycleManager(prompt_cache=cache)
        yield mgr
        r = await cache.connect()
        async for key in r.scan_iter(
            match="prompt:optimization:progress:__inttest*"
        ):
            await r.delete(key)
        await cache.close()

    async def test_full_lifecycle_persisted(self, manager):
        """Walk through the happy path and verify each state in Redis."""
        run_id = "__inttest-lifecycle-happy"
        transitions = [
            (RunState.QUEUED, RunState.ACQUIRING_LOCK),
            (RunState.ACQUIRING_LOCK, RunState.LOADING_DATA),
            (RunState.LOADING_DATA, RunState.OPTIMIZING),
            (RunState.OPTIMIZING, RunState.VALIDATING),
            (RunState.VALIDATING, RunState.CANARY),
            (RunState.CANARY, RunState.PROMOTING),
            (RunState.PROMOTING, RunState.COMPLETED),
        ]
        for from_s, to_s in transitions:
            await manager.transition(
                run_id, from_s, to_s, prompt_name="test"
            )

        state = await manager.get_run_state(run_id)
        assert state["state"] == "COMPLETED"

    async def test_deferred_stores_retry_time(self, manager):
        run_id = "__inttest-lifecycle-defer"
        retry_at = await manager.defer_on_lock_conflict(
            run_id, prompt_name="test"
        )
        state = await manager.get_run_state(run_id)
        assert state["state"] == "DEFERRED"
        assert state["deferred_until"] is not None
