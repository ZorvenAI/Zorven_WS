"""Tests for circuit breaker — state transitions."""

import asyncio

import pytest

from app.circuit_breaker.breaker import (
    CircuitBreaker,
    CircuitBreakerOpen,
    CircuitState,
    create_circuit_breakers,
)


class TestCircuitBreaker:
    async def test_starts_closed(self):
        cb = CircuitBreaker("test", failure_threshold=3)
        assert cb.state == CircuitState.CLOSED

    async def test_stays_closed_on_success(self):
        cb = CircuitBreaker("test", failure_threshold=3)
        result = await cb.call(self._success_func)
        assert result == "ok"
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    async def test_opens_after_threshold_failures(self):
        cb = CircuitBreaker("test", failure_threshold=3)
        for _ in range(3):
            with pytest.raises(ValueError):
                await cb.call(self._fail_func)
        assert cb.state == CircuitState.OPEN
        assert cb.failure_count == 3

    async def test_open_circuit_raises_immediately(self):
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout_s=60)
        with pytest.raises(ValueError):
            await cb.call(self._fail_func)
        assert cb.state == CircuitState.OPEN

        with pytest.raises(CircuitBreakerOpen):
            await cb.call(self._success_func)

    async def test_half_open_after_recovery_timeout(self):
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout_s=0)
        with pytest.raises(ValueError):
            await cb.call(self._fail_func)
        assert cb.state == CircuitState.OPEN

        # Recovery timeout is 0, so should transition to HALF_OPEN
        result = await cb.call(self._success_func)
        assert result == "ok"
        assert cb.state == CircuitState.CLOSED

    async def test_half_open_reopens_on_failure(self):
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout_s=0)
        with pytest.raises(ValueError):
            await cb.call(self._fail_func)

        with pytest.raises(ValueError):
            await cb.call(self._fail_func)
        assert cb.state == CircuitState.OPEN

    async def test_reset(self):
        cb = CircuitBreaker("test", failure_threshold=1)
        with pytest.raises(ValueError):
            await cb.call(self._fail_func)
        assert cb.state == CircuitState.OPEN

        cb.reset()
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    async def test_under_threshold_stays_closed(self):
        cb = CircuitBreaker("test", failure_threshold=5)
        for _ in range(4):
            with pytest.raises(ValueError):
                await cb.call(self._fail_func)
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 4

    async def test_fallback_attribute(self):
        cb = CircuitBreaker("test", failure_threshold=1, fallback="CACHE")
        with pytest.raises(ValueError):
            await cb.call(self._fail_func)

        try:
            await cb.call(self._success_func)
        except CircuitBreakerOpen as exc:
            assert exc.fallback == "CACHE"
            assert exc.name == "test"

    @staticmethod
    async def _success_func():
        return "ok"

    @staticmethod
    async def _fail_func():
        raise ValueError("boom")


class TestCreateCircuitBreakers:
    def test_creates_all_breakers(self):
        class FakeSettings:
            CB_FAILURE_THRESHOLD = 5
            CB_RECOVERY_TIMEOUT = 30
            CB_LLM_FAILURE_THRESHOLD = 3
            CB_LLM_RECOVERY_TIMEOUT = 60

        breakers = create_circuit_breakers(FakeSettings())
        assert "tavily" in breakers
        assert "llm" in breakers
        assert "worldbank" in breakers
        assert "rag_store" in breakers
        assert "kafka" in breakers
        assert "newsapi" in breakers

    def test_llm_has_lower_threshold(self):
        class FakeSettings:
            CB_FAILURE_THRESHOLD = 5
            CB_RECOVERY_TIMEOUT = 30
            CB_LLM_FAILURE_THRESHOLD = 3
            CB_LLM_RECOVERY_TIMEOUT = 60

        breakers = create_circuit_breakers(FakeSettings())
        assert breakers["llm"].failure_threshold == 3
        assert breakers["tavily"].failure_threshold == 5
