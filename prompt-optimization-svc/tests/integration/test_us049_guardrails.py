"""Integration tests for optimization guardrails (US-049).

OPT-07 distributed lock guardrail with real Redis.
"""

import pytest

from tests.integration.conftest import REDIS_URL, requires_redis

from app.cache.prompt_cache import PromptCacheManager
from app.logic.guardrails import check_distributed_lock, run_pre_optimization_guardrails


@pytest.mark.integration
@requires_redis
class TestDistributedLockGuardrail:
    """OPT-07: Distributed lock guardrail with real Redis."""

    @pytest.fixture
    async def cache(self):
        mgr = PromptCacheManager(redis_url=REDIS_URL)
        await mgr.connect()
        yield mgr
        # Cleanup test locks
        r = await mgr.connect()
        async for key in r.scan_iter(match="prompt:optimization:lock:__test*"):
            await r.delete(key)
        await mgr.close()

    async def test_lock_acquired_passes(self, cache):
        result = await check_distributed_lock(cache, "__test-opt07-acquire", "owner-1")
        assert result.passed is True
        assert result.guardrail_id == "OPT-07"
        await cache.release_optimization_lock("__test-opt07-acquire", "owner-1")

    async def test_lock_already_held_fails(self, cache):
        await cache.acquire_optimization_lock("__test-opt07-contention", "owner-1")
        result = await check_distributed_lock(
            cache, "__test-opt07-contention", "owner-2"
        )
        assert result.passed is False
        assert "already locked" in result.message
        await cache.release_optimization_lock("__test-opt07-contention", "owner-1")

    async def test_details_include_holder(self, cache):
        await cache.acquire_optimization_lock("__test-opt07-info", "owner-1")
        result = await check_distributed_lock(cache, "__test-opt07-info", "owner-2")
        assert result.details.get("current_owner") == "owner-1"
        await cache.release_optimization_lock("__test-opt07-info", "owner-1")

    async def test_released_lock_can_be_reacquired(self, cache):
        r1 = await check_distributed_lock(cache, "__test-opt07-release", "owner-1")
        assert r1.passed is True
        await cache.release_optimization_lock("__test-opt07-release", "owner-1")
        r2 = await check_distributed_lock(cache, "__test-opt07-release", "owner-2")
        assert r2.passed is True
        await cache.release_optimization_lock("__test-opt07-release", "owner-2")

    async def test_same_owner_cannot_double_lock(self, cache):
        r1 = await check_distributed_lock(cache, "__test-opt07-double", "owner-1")
        assert r1.passed is True
        r2 = await check_distributed_lock(cache, "__test-opt07-double", "owner-1")
        assert r2.passed is False
        await cache.release_optimization_lock("__test-opt07-double", "owner-1")


@pytest.mark.integration
@requires_redis
class TestPreOptimizationGuardrails:
    """run_pre_optimization_guardrails orchestrator with real Redis."""

    @pytest.fixture
    async def cache(self):
        mgr = PromptCacheManager(redis_url=REDIS_URL)
        await mgr.connect()
        yield mgr
        r = await mgr.connect()
        async for key in r.scan_iter(match="prompt:optimization:lock:__test*"):
            await r.delete(key)
        await mgr.close()

    async def test_all_pass_when_dataset_sufficient_and_lock_free(self, cache):
        examples = [1, 2, 3, 4, 5]
        chain = await run_pre_optimization_guardrails(
            examples=examples,
            min_dataset_size=3,
            cache_manager=cache,
            optimization_group="__test-pre-all-pass",
            lock_owner="owner-1",
        )
        assert chain.all_passed is True
        ids = [r.guardrail_id for r in chain.results]
        assert ids == ["OPT-01", "OPT-07"]
        await cache.release_optimization_lock("__test-pre-all-pass", "owner-1")

    async def test_dataset_failure_short_circuits_before_lock(self, cache):
        """OPT-01 failure should prevent OPT-07 lock acquisition."""
        examples = [1]  # Below minimum of 3
        chain = await run_pre_optimization_guardrails(
            examples=examples,
            min_dataset_size=3,
            cache_manager=cache,
            optimization_group="__test-pre-short-circuit",
            lock_owner="owner-1",
        )
        assert chain.all_passed is False
        assert chain.first_failure.guardrail_id == "OPT-01"
        # Only OPT-01 should be in results — OPT-07 was never attempted
        assert len(chain.results) == 1
        assert chain.results[0].guardrail_id == "OPT-01"

    async def test_lock_contention_fails_after_dataset_passes(self, cache):
        """OPT-01 passes but OPT-07 fails when lock is already held."""
        await cache.acquire_optimization_lock("__test-pre-lock-fail", "owner-1")
        chain = await run_pre_optimization_guardrails(
            examples=[1, 2, 3, 4, 5],
            min_dataset_size=3,
            cache_manager=cache,
            optimization_group="__test-pre-lock-fail",
            lock_owner="owner-2",
        )
        assert chain.all_passed is False
        assert chain.first_failure.guardrail_id == "OPT-07"
        ids = [r.guardrail_id for r in chain.results]
        assert ids == ["OPT-01", "OPT-07"]
        await cache.release_optimization_lock("__test-pre-lock-fail", "owner-1")

    async def test_ordering_opt01_before_opt07(self, cache):
        """OPT-01 is always checked before OPT-07."""
        chain = await run_pre_optimization_guardrails(
            examples=[1, 2, 3],
            min_dataset_size=3,
            cache_manager=cache,
            optimization_group="__test-pre-ordering",
            lock_owner="owner-1",
        )
        assert chain.results[0].guardrail_id == "OPT-01"
        assert chain.results[1].guardrail_id == "OPT-07"
        await cache.release_optimization_lock("__test-pre-ordering", "owner-1")
