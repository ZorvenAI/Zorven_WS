"""Tests for per-API circuit breakers.

Covers state transitions (CLOSED -> OPEN -> HALF_OPEN -> CLOSED),
failure counting, window pruning, and pre-configured breakers.
"""

import time

import pytest
from unittest.mock import patch

from app.logic.circuit_breaker import (
    BREAKERS,
    BreakerAction,
    BreakerState,
    CircuitBreaker,
    get_breaker,
)


class TestCircuitBreakerStates:
    """Test state transitions and core behavior."""

    def setup_method(self):
        self.breaker = CircuitBreaker(
            name="test_breaker",
            max_failures=3,
            window_seconds=10,
            action=BreakerAction.SKIP_CAMPAIGN,
        )

    def test_initial_state_closed(self):
        assert self.breaker.state == BreakerState.CLOSED
        assert self.breaker.is_open is False

    def test_single_failure_stays_closed(self):
        result = self.breaker.record_failure()
        assert result is None
        assert self.breaker.state == BreakerState.CLOSED

    def test_trips_after_max_failures(self):
        for _ in range(2):
            self.breaker.record_failure()
        result = self.breaker.record_failure()
        assert result is not None
        assert result["state"] == "open"
        assert result["action"] == BreakerAction.SKIP_CAMPAIGN.value
        assert self.breaker.state == BreakerState.OPEN
        assert self.breaker.is_open is True

    def test_open_blocks_calls(self):
        for _ in range(3):
            self.breaker.record_failure()
        assert self.breaker.is_open is True

    def test_half_open_after_window_expires(self):
        """After window_seconds, breaker transitions to HALF_OPEN."""
        for _ in range(3):
            self.breaker.record_failure()
        assert self.breaker.state == BreakerState.OPEN

        # Simulate time passing beyond the window
        self.breaker._last_trip_time = time.time() - 11
        assert self.breaker.is_open is False
        assert self.breaker.state == BreakerState.HALF_OPEN

    def test_half_open_success_closes(self):
        """A success in HALF_OPEN transitions back to CLOSED."""
        for _ in range(3):
            self.breaker.record_failure()
        self.breaker._last_trip_time = time.time() - 11
        _ = self.breaker.is_open  # Trigger HALF_OPEN transition

        self.breaker.record_success()
        assert self.breaker.state == BreakerState.CLOSED
        assert len(self.breaker._failures) == 0

    def test_half_open_failure_reopens(self):
        """A failure in HALF_OPEN transitions back to OPEN."""
        breaker = CircuitBreaker(
            name="test",
            max_failures=1,
            window_seconds=10,
            action=BreakerAction.SKIP_CAMPAIGN,
        )
        breaker.record_failure()
        assert breaker.state == BreakerState.OPEN

        breaker._last_trip_time = time.time() - 11
        _ = breaker.is_open  # -> HALF_OPEN

        result = breaker.record_failure()
        assert result is not None
        assert breaker.state == BreakerState.OPEN

    def test_success_in_closed_is_noop(self):
        """record_success in CLOSED state does nothing."""
        self.breaker.record_success()
        assert self.breaker.state == BreakerState.CLOSED

    def test_reset_clears_state(self):
        for _ in range(3):
            self.breaker.record_failure()
        assert self.breaker.state == BreakerState.OPEN
        self.breaker.reset()
        assert self.breaker.state == BreakerState.CLOSED
        assert len(self.breaker._failures) == 0
        assert self.breaker._last_trip_time == 0


class TestFailureWindowPruning:
    """Test that old failures outside the window are pruned."""

    def test_old_failures_pruned(self):
        breaker = CircuitBreaker(
            name="test",
            max_failures=3,
            window_seconds=5,
            action=BreakerAction.LOG_RETRY,
        )
        # Record 2 failures "in the past"
        old_time = time.time() - 10
        breaker._failures = [old_time, old_time + 1]

        # One more failure now should NOT trip (old ones pruned)
        result = breaker.record_failure()
        assert result is None
        assert breaker.state == BreakerState.CLOSED
        # Only the recent failure should remain
        assert len(breaker._failures) == 1


class TestPreConfiguredBreakers:
    """Test the 5 pre-configured breakers from the module."""

    def setup_method(self):
        # Reset all breakers before each test
        for b in BREAKERS.values():
            b.reset()

    def test_meta_insights_config(self):
        b = get_breaker("meta_insights")
        assert b.max_failures == 3
        assert b.window_seconds == 60
        assert b.action == BreakerAction.SKIP_CAMPAIGN

    def test_meta_management_config(self):
        b = get_breaker("meta_management")
        assert b.max_failures == 2
        assert b.window_seconds == 30
        assert b.action == BreakerAction.STOP_ESCALATE

    def test_llm_config(self):
        b = get_breaker("llm")
        assert b.max_failures == 3
        assert b.window_seconds == 60
        assert b.action == BreakerAction.SKIP_NARRATIVE

    def test_kafka_config(self):
        b = get_breaker("kafka")
        assert b.max_failures == 3
        assert b.window_seconds == 60
        assert b.action == BreakerAction.BUFFER_REDIS

    def test_campaign_registry_config(self):
        b = get_breaker("campaign_registry")
        assert b.max_failures == 3
        assert b.window_seconds == 60
        assert b.action == BreakerAction.LOG_RETRY

    def test_five_breakers_exist(self):
        assert len(BREAKERS) == 5
        expected = {
            "meta_insights",
            "meta_management",
            "llm",
            "kafka",
            "campaign_registry",
        }
        assert set(BREAKERS.keys()) == expected

    def test_get_breaker_unknown_raises(self):
        with pytest.raises(KeyError):
            get_breaker("nonexistent")

    def test_meta_management_trips_at_2(self):
        """meta_management breaker trips after 2 failures (not 3)."""
        b = get_breaker("meta_management")
        b.record_failure()
        result = b.record_failure()
        assert result is not None
        assert b.state == BreakerState.OPEN
