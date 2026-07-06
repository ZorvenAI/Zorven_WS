"""E2E tests for circuit breaker behavior (US-060).

Exercises: starts closed, sustained failures open circuit,
half-open probe after interval, loader fallback when open.
"""

import time

import pytest

from app.logic.circuit_breaker import (
    CircuitBreakerConfig,
    CircuitState,
    MLflowCircuitBreaker,
)


@pytest.mark.e2e
class TestCircuitBreaker:
    """Circuit breaker state transitions and loader integration."""

    def test_circuit_breaker_starts_closed(self):
        """Fresh breaker starts CLOSED, allows requests."""
        breaker = MLflowCircuitBreaker(CircuitBreakerConfig())
        assert breaker.state == CircuitState.CLOSED
        assert breaker.should_allow_request() is True
        assert breaker.consecutive_failures == 0

    def test_sustained_failures_open_circuit(self):
        """Failures for >threshold seconds -> OPEN state."""
        # Use a very short threshold for testing (1 second)
        config = CircuitBreakerConfig(
            failure_threshold_seconds=1,
            half_open_interval_seconds=60,
        )
        breaker = MLflowCircuitBreaker(config)

        # Record initial failure
        breaker.record_failure()
        assert breaker.state == CircuitState.CLOSED  # Not yet open

        # Wait past the threshold
        time.sleep(1.1)

        # Record another failure — should trigger OPEN
        breaker.record_failure()
        assert breaker.state == CircuitState.OPEN
        assert breaker.should_allow_request() is False

        # Verify success resets to CLOSED
        breaker.record_success()
        assert breaker.state == CircuitState.CLOSED
        assert breaker.should_allow_request() is True

    def test_half_open_probe_after_interval(self):
        """After OPEN, wait interval -> HALF_OPEN, allows one probe."""
        config = CircuitBreakerConfig(
            failure_threshold_seconds=1,
            half_open_interval_seconds=1,  # Short probe interval for testing
        )
        breaker = MLflowCircuitBreaker(config)

        # Force circuit OPEN
        breaker.record_failure()
        time.sleep(1.1)
        breaker.record_failure()
        assert breaker.state == CircuitState.OPEN

        # Wait for probe interval
        time.sleep(1.1)

        # Should transition to HALF_OPEN and allow one probe
        allowed = breaker.should_allow_request()
        assert allowed is True
        assert breaker.state == CircuitState.HALF_OPEN

        # Immediate second request should be blocked (only one probe)
        assert breaker.should_allow_request() is False

        # Successful probe should close the circuit
        breaker.record_success()
        assert breaker.state == CircuitState.CLOSED
        assert breaker.should_allow_request() is True

    async def test_loader_uses_fallback_when_circuit_open(
        self, e2e_cache, e2e_prompt_name
    ):
        """Force OPEN circuit, load with fallback -> fallback returned."""
        from app.services.prompt_loader import ZorvenPromptLoader

        name = e2e_prompt_name("breaker-fallback")

        # Create a breaker that's already OPEN
        config = CircuitBreakerConfig(
            failure_threshold_seconds=0,
            half_open_interval_seconds=3600,  # Long probe to stay OPEN
        )
        breaker = MLflowCircuitBreaker(config)

        # Force OPEN: record failure immediately (threshold=0)
        breaker.record_failure()
        assert breaker.state == CircuitState.OPEN

        # Create loader with no MLflow registry and the open breaker
        loader = ZorvenPromptLoader(
            prompt_cache=e2e_cache,
            mlflow_registry=None,  # No MLflow available
            circuit_breaker=breaker,
        )

        # Load should return fallback since cache is empty and MLflow unavailable
        result = await loader.load(
            name=name,
            fallback_template="Emergency fallback template",
        )
        assert result == "Emergency fallback template"
