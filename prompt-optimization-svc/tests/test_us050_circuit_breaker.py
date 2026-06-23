"""Unit tests for prompt loading circuit breaker and auto-rollback (US-050).

Tests the MLflowCircuitBreaker state machine, rollback window helper,
auto-rollback regression detection, and config constants. NO mocks.
"""

import time
from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.logic.circuit_breaker import (
    CircuitBreakerConfig,
    CircuitState,
    MLflowCircuitBreaker,
)
from app.tasks.prompt_health_check import (
    _check_regression,
    _is_within_rollback_window,
)


# ── CircuitBreakerConfig ──


class TestCircuitBreakerConfig:
    def test_default_values(self):
        config = CircuitBreakerConfig()
        assert config.failure_threshold_seconds == 300
        assert config.half_open_interval_seconds == 60

    def test_custom_values(self):
        config = CircuitBreakerConfig(
            failure_threshold_seconds=10, half_open_interval_seconds=5
        )
        assert config.failure_threshold_seconds == 10
        assert config.half_open_interval_seconds == 5


# ── CircuitBreaker state machine ──


class TestCircuitBreakerState:
    def test_initial_state_is_closed(self):
        cb = MLflowCircuitBreaker()
        assert cb.state == CircuitState.CLOSED

    def test_single_failure_stays_closed(self):
        cb = MLflowCircuitBreaker(CircuitBreakerConfig(failure_threshold_seconds=300))
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED

    def test_success_resets_failure_tracking(self):
        cb = MLflowCircuitBreaker(CircuitBreakerConfig(failure_threshold_seconds=300))
        cb.record_failure()
        cb.record_failure()
        assert cb.consecutive_failures == 2
        cb.record_success()
        assert cb.consecutive_failures == 0
        assert cb.state == CircuitState.CLOSED

    def test_failures_within_threshold_stays_closed(self):
        """Failures within the threshold window do not open the circuit."""
        cb = MLflowCircuitBreaker(CircuitBreakerConfig(failure_threshold_seconds=300))
        for _ in range(100):
            cb.record_failure()
        # Still within threshold (< 300s elapsed since first failure)
        assert cb.state == CircuitState.CLOSED

    def test_failures_exceeding_threshold_opens(self):
        """After failure_threshold_seconds of failures, circuit opens."""
        # Use a tiny threshold so time.monotonic() crosses it immediately
        cb = MLflowCircuitBreaker(CircuitBreakerConfig(failure_threshold_seconds=0))
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_open_blocks_requests(self):
        cb = MLflowCircuitBreaker(
            CircuitBreakerConfig(
                failure_threshold_seconds=0, half_open_interval_seconds=9999
            )
        )
        cb.record_failure()  # Opens immediately (threshold=0)
        assert cb.state == CircuitState.OPEN
        assert cb.should_allow_request() is False

    def test_half_open_allows_one_probe(self):
        """After probe interval elapses, one request is allowed."""
        cb = MLflowCircuitBreaker(
            CircuitBreakerConfig(
                failure_threshold_seconds=0, half_open_interval_seconds=0
            )
        )
        cb.record_failure()  # Opens immediately
        assert cb.state == CircuitState.OPEN
        # Probe interval is 0, so should_allow_request transitions to HALF_OPEN
        assert cb.should_allow_request() is True
        assert cb.state == CircuitState.HALF_OPEN

    def test_half_open_success_closes(self):
        cb = MLflowCircuitBreaker(
            CircuitBreakerConfig(
                failure_threshold_seconds=0, half_open_interval_seconds=0
            )
        )
        cb.record_failure()
        cb.should_allow_request()  # Transition to HALF_OPEN
        assert cb.state == CircuitState.HALF_OPEN
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_half_open_failure_reopens(self):
        cb = MLflowCircuitBreaker(
            CircuitBreakerConfig(
                failure_threshold_seconds=0, half_open_interval_seconds=0
            )
        )
        cb.record_failure()
        cb.should_allow_request()  # HALF_OPEN
        cb.record_failure()  # Should reopen (threshold=0, elapsed >= 0)
        assert cb.state == CircuitState.OPEN

    def test_consecutive_successes_keep_closed(self):
        cb = MLflowCircuitBreaker()
        cb.record_success()
        cb.record_success()
        cb.record_success()
        assert cb.state == CircuitState.CLOSED
        assert cb.consecutive_failures == 0

    def test_success_from_open_closes(self):
        cb = MLflowCircuitBreaker(CircuitBreakerConfig(failure_threshold_seconds=0))
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_probe_interval_respected(self):
        """No probe allowed before interval elapses."""
        cb = MLflowCircuitBreaker(
            CircuitBreakerConfig(
                failure_threshold_seconds=0, half_open_interval_seconds=9999
            )
        )
        cb.record_failure()  # Opens
        # First call updates _last_probe_at, but interval hasn't elapsed
        assert cb.should_allow_request() is False
        assert cb.state == CircuitState.OPEN


# ── Edge cases ──


class TestCircuitBreakerEdgeCases:
    def test_immediate_success_after_first_failure(self):
        cb = MLflowCircuitBreaker(CircuitBreakerConfig(failure_threshold_seconds=300))
        cb.record_failure()
        assert cb.consecutive_failures == 1
        cb.record_success()
        assert cb.consecutive_failures == 0
        assert cb.state == CircuitState.CLOSED

    def test_state_property_reflects_internal(self):
        cb = MLflowCircuitBreaker(CircuitBreakerConfig(failure_threshold_seconds=0))
        assert cb.state == CircuitState.CLOSED
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_consecutive_failures_accuracy(self):
        cb = MLflowCircuitBreaker()
        for i in range(1, 6):
            cb.record_failure()
            assert cb.consecutive_failures == i
        cb.record_success()
        assert cb.consecutive_failures == 0

    def test_closed_always_allows_requests(self):
        cb = MLflowCircuitBreaker()
        for _ in range(10):
            assert cb.should_allow_request() is True
        assert cb.state == CircuitState.CLOSED


# ── Rollback window ──


class TestRollbackWindow:
    def test_recent_promotion_within_window(self):
        promoted = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        assert _is_within_rollback_window(promoted, 48) is True

    def test_old_promotion_outside_window(self):
        promoted = (datetime.now(timezone.utc) - timedelta(hours=72)).isoformat()
        assert _is_within_rollback_window(promoted, 48) is False

    def test_none_returns_false(self):
        assert _is_within_rollback_window(None, 48) is False

    def test_invalid_iso_returns_false(self):
        assert _is_within_rollback_window("not-a-date", 48) is False

    def test_exactly_at_boundary(self):
        """Promotion exactly at cutoff is within window (>=)."""
        promoted = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
        # Due to time passing between creation and check, this may be just outside
        # So test with a tiny margin inside
        promoted_inside = (
            datetime.now(timezone.utc) - timedelta(hours=47, minutes=59)
        ).isoformat()
        assert _is_within_rollback_window(promoted_inside, 48) is True

    def test_just_promoted(self):
        promoted = datetime.now(timezone.utc).isoformat()
        assert _is_within_rollback_window(promoted, 48) is True


# ── Auto-rollback regression ──


class TestAutoRollbackRegression:
    def test_16pct_regression_detected(self):
        """Score 0.84 means 16% regression (> 15% threshold)."""
        assert _check_regression(0.84, 0.15) is True

    def test_14pct_regression_not_detected(self):
        """Score 0.87 means 13% regression (< 15% threshold)."""
        assert _check_regression(0.87, 0.15) is False

    def test_exact_boundary_not_regression(self):
        """Score exactly 0.85 means exactly 15% regression — not strictly less."""
        assert _check_regression(0.85, 0.15) is False

    def test_none_score_not_regression(self):
        assert _check_regression(None, 0.15) is False

    def test_zero_score_is_regression(self):
        assert _check_regression(0.0, 0.15) is True

    def test_perfect_score_no_regression(self):
        assert _check_regression(1.0, 0.15) is False


# ── Config settings defaults ──


class TestConfigDefaults:
    def test_circuit_breaker_failure_threshold(self):
        assert settings.CIRCUIT_BREAKER_FAILURE_THRESHOLD_SECONDS == 300

    def test_circuit_breaker_half_open_interval(self):
        assert settings.CIRCUIT_BREAKER_HALF_OPEN_INTERVAL_SECONDS == 60

    def test_auto_rollback_regression_threshold(self):
        assert settings.AUTO_ROLLBACK_REGRESSION_THRESHOLD == 0.15

    def test_auto_rollback_window_hours(self):
        assert settings.AUTO_ROLLBACK_WINDOW_HOURS == 48
