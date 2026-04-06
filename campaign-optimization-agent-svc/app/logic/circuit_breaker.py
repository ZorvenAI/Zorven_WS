"""Per-API circuit breakers for Campaign Optimization Agent.

States: CLOSED (normal), OPEN (tripped), HALF_OPEN (testing).
Uses in-memory state (Redis-backed version for production).

Five named breakers:
  meta_insights:      3 failures / 60s → SKIP campaign
  meta_management:    2 failures / 30s → STOP autonomous + ESCALATE
  llm:                3 failures / 60s → SKIP narrative
  kafka:              3 failures / 60s → buffer to Redis
  campaign_registry:  3 failures / 60s → log + retry next tick
"""

import logging
import time
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class BreakerState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class BreakerAction(str, Enum):
    SKIP_CAMPAIGN = "skip_campaign"
    STOP_ESCALATE = "stop_autonomous_escalate"
    SKIP_NARRATIVE = "skip_narrative"
    BUFFER_REDIS = "buffer_to_redis"
    LOG_RETRY = "log_retry_next_tick"


class CircuitBreaker:
    """In-memory circuit breaker for a single API endpoint."""

    def __init__(
        self,
        name: str,
        max_failures: int,
        window_seconds: int,
        action: BreakerAction,
    ):
        self.name = name
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        self.action = action
        self.state = BreakerState.CLOSED
        self._failures: list[float] = []
        self._last_trip_time: float = 0

    @property
    def is_open(self) -> bool:
        """Check if the breaker is open (tripped)."""
        if self.state == BreakerState.OPEN:
            # Auto-transition to HALF_OPEN after window expires
            if time.time() - self._last_trip_time > self.window_seconds:
                self.state = BreakerState.HALF_OPEN
                return False
            return True
        return False

    def record_success(self):
        """Record a successful call. Resets breaker if HALF_OPEN."""
        if self.state == BreakerState.HALF_OPEN:
            self.state = BreakerState.CLOSED
            self._failures.clear()
            logger.info("Circuit breaker '%s' closed (recovered)", self.name)

    def record_failure(self) -> dict[str, Any] | None:
        """Record a failed call. Returns trip info if breaker trips.

        Returns None if breaker is still closed, or a dict with
        action and details if the breaker trips.
        """
        now = time.time()
        self._failures.append(now)

        # Prune old failures outside the window
        cutoff = now - self.window_seconds
        self._failures = [t for t in self._failures if t > cutoff]

        if len(self._failures) >= self.max_failures:
            self.state = BreakerState.OPEN
            self._last_trip_time = now
            logger.error(
                "Circuit breaker '%s' TRIPPED: %d failures in %ds -- "
                "action: %s",
                self.name,
                len(self._failures),
                self.window_seconds,
                self.action.value,
            )
            return {
                "breaker": self.name,
                "state": BreakerState.OPEN.value,
                "failures": len(self._failures),
                "action": self.action.value,
            }

        return None

    def reset(self):
        """Manually reset the breaker."""
        self.state = BreakerState.CLOSED
        self._failures.clear()
        self._last_trip_time = 0


# Pre-configured breakers matching the design document
BREAKERS: dict[str, CircuitBreaker] = {
    "meta_insights": CircuitBreaker(
        name="meta_insights",
        max_failures=3,
        window_seconds=60,
        action=BreakerAction.SKIP_CAMPAIGN,
    ),
    "meta_management": CircuitBreaker(
        name="meta_management",
        max_failures=2,
        window_seconds=30,
        action=BreakerAction.STOP_ESCALATE,
    ),
    "llm": CircuitBreaker(
        name="llm",
        max_failures=3,
        window_seconds=60,
        action=BreakerAction.SKIP_NARRATIVE,
    ),
    "kafka": CircuitBreaker(
        name="kafka",
        max_failures=3,
        window_seconds=60,
        action=BreakerAction.BUFFER_REDIS,
    ),
    "campaign_registry": CircuitBreaker(
        name="campaign_registry",
        max_failures=3,
        window_seconds=60,
        action=BreakerAction.LOG_RETRY,
    ),
}


def get_breaker(name: str) -> CircuitBreaker:
    """Get a named circuit breaker."""
    return BREAKERS[name]
