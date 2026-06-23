"""Hypothesis property-based tests for circuit breaker and auto-rollback (US-050)."""

from datetime import datetime, timedelta, timezone

from hypothesis import given, settings
from hypothesis import strategies as st

from app.logic.circuit_breaker import (
    CircuitBreakerConfig,
    CircuitState,
    MLflowCircuitBreaker,
)
from app.tasks.prompt_health_check import _is_within_rollback_window


class TestCircuitBreakerProperties:
    @settings(max_examples=50, deadline=None)
    @given(threshold=st.integers(min_value=1, max_value=3600))
    def test_circuit_never_opens_before_threshold(self, threshold):
        """The circuit must stay CLOSED if failures haven't persisted
        for failure_threshold_seconds."""
        cb = MLflowCircuitBreaker(
            CircuitBreakerConfig(failure_threshold_seconds=threshold)
        )
        # Record failures — but since time.monotonic() advances minimally,
        # the threshold (≥1s) should not be exceeded
        for _ in range(10):
            cb.record_failure()
        assert cb.state == CircuitState.CLOSED

    @settings(max_examples=50, deadline=None)
    @given(
        n_failures=st.integers(min_value=0, max_value=20),
    )
    def test_record_success_always_closes(self, n_failures):
        """Any sequence ending in record_success() yields CLOSED state."""
        cb = MLflowCircuitBreaker(CircuitBreakerConfig(failure_threshold_seconds=0))
        for _ in range(n_failures):
            cb.record_failure()
        cb.record_success()
        assert cb.state == CircuitState.CLOSED
        assert cb.consecutive_failures == 0

    @settings(max_examples=50, deadline=None)
    @given(n=st.integers(min_value=1, max_value=50))
    def test_consecutive_failures_monotonic(self, n):
        """consecutive_failures increases with each failure, resets on success."""
        cb = MLflowCircuitBreaker(CircuitBreakerConfig(failure_threshold_seconds=9999))
        for i in range(1, n + 1):
            cb.record_failure()
            assert cb.consecutive_failures == i
        cb.record_success()
        assert cb.consecutive_failures == 0


class TestRollbackWindowProperties:
    @settings(max_examples=50, deadline=None)
    @given(hours_ago=st.integers(min_value=0, max_value=47))
    def test_within_window_returns_true(self, hours_ago):
        """Promotions within the window always return True."""
        promoted = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()
        assert _is_within_rollback_window(promoted, 48) is True

    @settings(max_examples=50, deadline=None)
    @given(hours_ago=st.integers(min_value=49, max_value=1000))
    def test_outside_window_returns_false(self, hours_ago):
        """Promotions outside the window always return False."""
        promoted = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()
        assert _is_within_rollback_window(promoted, 48) is False


class TestCircuitBreakerConfigProperties:
    @settings(max_examples=30, deadline=None)
    @given(
        threshold=st.integers(min_value=1, max_value=10000),
        interval=st.integers(min_value=1, max_value=10000),
    )
    def test_any_positive_config_is_valid(self, threshold, interval):
        config = CircuitBreakerConfig(
            failure_threshold_seconds=threshold,
            half_open_interval_seconds=interval,
        )
        assert config.failure_threshold_seconds > 0
        assert config.half_open_interval_seconds > 0
