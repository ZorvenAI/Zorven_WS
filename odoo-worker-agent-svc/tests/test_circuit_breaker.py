"""Tests for circuit breaker."""

import time
from unittest.mock import patch

from app.services.circuit_breaker import CircuitBreaker, CircuitState


def test_initial_state_closed():
    """Circuit breaker should start CLOSED."""
    cb = CircuitBreaker()
    assert cb.state == CircuitState.CLOSED
    assert not cb.is_open


def test_remains_closed_under_threshold():
    """Should stay CLOSED below failure threshold."""
    cb = CircuitBreaker(failure_threshold=3)
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.CLOSED


def test_opens_at_threshold():
    """Should transition to OPEN at failure threshold."""
    cb = CircuitBreaker(failure_threshold=3)
    cb.record_failure()
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    assert cb.is_open


def test_success_resets():
    """Success should reset failure count."""
    cb = CircuitBreaker(failure_threshold=3)
    cb.record_failure()
    cb.record_failure()
    cb.record_success()
    assert cb.state == CircuitState.CLOSED
    # Should need full threshold again
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.CLOSED


def test_half_open_after_timeout():
    """Should transition to HALF_OPEN after reset timeout."""
    cb = CircuitBreaker(failure_threshold=1, reset_timeout=0.01)
    cb.record_failure()
    assert cb.state == CircuitState.OPEN

    time.sleep(0.02)  # Wait for reset timeout
    assert cb.state == CircuitState.HALF_OPEN


def test_half_open_success_closes():
    """Success in HALF_OPEN should close the circuit."""
    cb = CircuitBreaker(failure_threshold=1, reset_timeout=0.01)
    cb.record_failure()
    time.sleep(0.02)
    assert cb.state == CircuitState.HALF_OPEN

    cb.record_success()
    assert cb.state == CircuitState.CLOSED


def test_half_open_failure_reopens():
    """Failure in HALF_OPEN should reopen the circuit."""
    cb = CircuitBreaker(failure_threshold=1, reset_timeout=0.01)
    cb.record_failure()
    time.sleep(0.02)
    assert cb.state == CircuitState.HALF_OPEN

    cb.record_failure()
    assert cb.state == CircuitState.OPEN


def test_manual_reset():
    """Manual reset should close the circuit."""
    cb = CircuitBreaker(failure_threshold=1)
    cb.record_failure()
    assert cb.state == CircuitState.OPEN

    cb.reset()
    assert cb.state == CircuitState.CLOSED
    assert not cb.is_open
