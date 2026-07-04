"""Integration tests for circuit breaker and auto-rollback (US-050).

Tests prompt loader with circuit breaker using real Redis, and
rollback window validation with real datetime.
"""

from datetime import datetime, timedelta, timezone

import pytest

from tests.integration.conftest import REDIS_URL, requires_redis

from app.cache.prompt_cache import PromptCacheManager
from app.logic.circuit_breaker import (
    CircuitBreakerConfig,
    CircuitState,
    MLflowCircuitBreaker,
)
from app.services.prompt_loader import ZorvenPromptLoader
from app.tasks.prompt_health_check import _is_within_rollback_window


@pytest.mark.integration
@requires_redis
class TestLoaderCircuitBreakerWithRedis:
    """Prompt loader with circuit breaker and real Redis cache."""

    @pytest.fixture
    async def cache(self):
        mgr = PromptCacheManager(redis_url=REDIS_URL)
        await mgr.connect()
        yield mgr
        # Cleanup test keys
        r = await mgr.connect()
        async for key in r.scan_iter(match="prompt:__test-cb*"):
            await r.delete(key)
        await mgr.close()

    async def test_circuit_open_returns_cached_prompt(self, cache):
        """AC-1: When circuit is OPEN, loader returns Redis-cached prompt."""
        # Pre-populate cache
        await cache.set_prompt("__test-cb-cached", "cached template", ttl=60)

        # Create circuit in OPEN state
        cb = MLflowCircuitBreaker(CircuitBreakerConfig(failure_threshold_seconds=0))
        cb.record_failure()  # Opens immediately
        assert cb.state == CircuitState.OPEN

        loader = ZorvenPromptLoader(
            prompt_cache=cache,
            mlflow_registry=None,
            circuit_breaker=cb,
        )
        result = await loader.load("__test-cb-cached", fallback_template="fallback")
        assert result == "cached template"

    async def test_circuit_open_no_cache_returns_fallback(self, cache):
        """AC-2: When circuit OPEN and no cache, fallback is engaged."""
        cb = MLflowCircuitBreaker(CircuitBreakerConfig(failure_threshold_seconds=0))
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        loader = ZorvenPromptLoader(
            prompt_cache=cache,
            mlflow_registry=None,
            circuit_breaker=cb,
        )
        result = await loader.load(
            "__test-cb-no-cache", fallback_template="hardcoded fallback"
        )
        assert result == "hardcoded fallback"

    async def test_circuit_closed_allows_mlflow_attempt(self, cache):
        """CLOSED circuit allows MLflow tier (even if MLflow is None here)."""
        cb = MLflowCircuitBreaker()
        assert cb.state == CircuitState.CLOSED

        loader = ZorvenPromptLoader(
            prompt_cache=cache,
            mlflow_registry=None,  # No MLflow → falls to fallback
            circuit_breaker=cb,
        )
        result = await loader.load("__test-cb-closed", fallback_template="fallback")
        # With no MLflow registry, falls to fallback
        assert result == "fallback"
        # Circuit should still be CLOSED (no failure recorded since
        # mlflow_registry is None — the tier 2 block is skipped entirely)
        assert cb.state == CircuitState.CLOSED

    async def test_half_open_recovery_on_success(self, cache):
        """HALF_OPEN → CLOSED when MLflow probe succeeds."""
        cb = MLflowCircuitBreaker(
            CircuitBreakerConfig(
                failure_threshold_seconds=0, half_open_interval_seconds=0
            )
        )
        cb.record_failure()  # OPEN
        cb.should_allow_request()  # HALF_OPEN
        assert cb.state == CircuitState.HALF_OPEN

        # Simulate success
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

        # Now loader should work normally with cached data
        await cache.set_prompt("__test-cb-recovery", "recovered", ttl=60)
        loader = ZorvenPromptLoader(
            prompt_cache=cache,
            mlflow_registry=None,
            circuit_breaker=cb,
        )
        result = await loader.load("__test-cb-recovery")
        assert result == "recovered"


@pytest.mark.integration
class TestRollbackWindowRealTime:
    """Rollback window validation with real datetime."""

    def test_recent_promotion_within_window(self):
        promoted = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        assert _is_within_rollback_window(promoted, 48) is True

    def test_old_promotion_outside_window(self):
        promoted = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
        assert _is_within_rollback_window(promoted, 48) is False
