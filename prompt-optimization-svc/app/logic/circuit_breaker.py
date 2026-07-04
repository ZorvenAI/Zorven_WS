"""MLflow circuit breaker (§17.2 Production Safety Net, US-050).

Three-state circuit breaker for MLflow prompt loading:
    CLOSED    — normal operation, all requests go to MLflow
    OPEN      — MLflow down ≥5 min, skip tier 2 entirely
    HALF_OPEN — periodic probe (every 60s) to check recovery

In-memory, per-process state. No Redis dependency to avoid circular
dependencies (the breaker protects the MLflow path, and Redis itself
may be down per AC-2).
"""

import enum
import logging
import time
from dataclasses import dataclass

from app.metrics import CIRCUIT_BREAKER_STATE

logger = logging.getLogger(__name__)

# Gauge values for Prometheus
_STATE_GAUGE = {
    "CLOSED": 0.0,
    "OPEN": 1.0,
    "HALF_OPEN": 2.0,
}


class CircuitState(str, enum.Enum):
    """Circuit breaker states."""

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


@dataclass
class CircuitBreakerConfig:
    """Configuration for the MLflow circuit breaker."""

    failure_threshold_seconds: int = 300  # 5 min
    half_open_interval_seconds: int = 60  # probe every 60s


class MLflowCircuitBreaker:
    """In-memory, per-process circuit breaker for MLflow availability.

    Tracks consecutive failures using monotonic time. After
    ``failure_threshold_seconds`` of uninterrupted failures the circuit
    opens, skipping MLflow calls until a half-open probe succeeds.
    """

    def __init__(self, config: CircuitBreakerConfig | None = None) -> None:
        self._config = config or CircuitBreakerConfig()
        self._state = CircuitState.CLOSED
        self._first_failure_at: float | None = None
        self._last_probe_at: float = 0.0
        self._consecutive_failures: int = 0
        CIRCUIT_BREAKER_STATE.set(_STATE_GAUGE[self._state.value])

    @property
    def state(self) -> CircuitState:
        """Current circuit breaker state."""
        return self._state

    @property
    def consecutive_failures(self) -> int:
        """Number of consecutive failures since last success."""
        return self._consecutive_failures

    def _set_state(self, new_state: CircuitState) -> None:
        """Transition to a new state and update the Prometheus gauge."""
        if self._state != new_state:
            logger.info(
                "Circuit breaker: %s → %s (failures=%d)",
                self._state.value,
                new_state.value,
                self._consecutive_failures,
            )
            self._state = new_state
            CIRCUIT_BREAKER_STATE.set(_STATE_GAUGE[new_state.value])

    def should_allow_request(self) -> bool:
        """Check if a request to MLflow should be attempted.

        Returns:
            True for CLOSED (always), True once per probe interval
            for OPEN/HALF_OPEN, False otherwise.
        """
        if self._state == CircuitState.CLOSED:
            return True

        now = time.monotonic()
        elapsed_since_probe = now - self._last_probe_at
        if elapsed_since_probe >= self._config.half_open_interval_seconds:
            self._set_state(CircuitState.HALF_OPEN)
            self._last_probe_at = now
            return True

        return False

    def record_success(self) -> None:
        """Record a successful MLflow call. Resets to CLOSED."""
        self._consecutive_failures = 0
        self._first_failure_at = None
        self._set_state(CircuitState.CLOSED)

    def record_failure(self) -> None:
        """Record a failed MLflow call. May transition to OPEN."""
        now = time.monotonic()
        self._consecutive_failures += 1

        if self._first_failure_at is None:
            self._first_failure_at = now

        elapsed = now - self._first_failure_at
        if elapsed >= self._config.failure_threshold_seconds:
            if self._state != CircuitState.OPEN:
                self._last_probe_at = now
            self._set_state(CircuitState.OPEN)
