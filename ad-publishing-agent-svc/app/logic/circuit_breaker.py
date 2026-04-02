"""Per-API circuit breakers for Meta Marketing API calls.

States: CLOSED (normal), OPEN (tripped), HALF_OPEN (testing).
Uses in-memory state (Redis-backed version for production).

Four named breakers:
  meta_campaign:  3 failures / 60s → ESCALATE (no retry — could duplicate)
  meta_ad_set:    3 failures / 60s → ROLLBACK + ESCALATE
  meta_ad_image:  5 failures / 60s → RETRY with backoff
  meta_ad:        2 failures / 30s → ROLLBACK ALL + ESCALATE (strictest)
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
    ESCALATE = "escalate"
    ROLLBACK_ESCALATE = "rollback_escalate"
    RETRY = "retry"
    ROLLBACK_ALL_ESCALATE = "rollback_all_escalate"


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
                "Circuit breaker '%s' TRIPPED: %d failures in %ds — "
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
    "meta_campaign": CircuitBreaker(
        name="meta_campaign",
        max_failures=3,
        window_seconds=60,
        action=BreakerAction.ESCALATE,
    ),
    "meta_ad_set": CircuitBreaker(
        name="meta_ad_set",
        max_failures=3,
        window_seconds=60,
        action=BreakerAction.ROLLBACK_ESCALATE,
    ),
    "meta_ad_image": CircuitBreaker(
        name="meta_ad_image",
        max_failures=5,
        window_seconds=60,
        action=BreakerAction.RETRY,
    ),
    "meta_ad": CircuitBreaker(
        name="meta_ad",
        max_failures=2,
        window_seconds=30,
        action=BreakerAction.ROLLBACK_ALL_ESCALATE,
    ),
}


def get_breaker(name: str) -> CircuitBreaker:
    """Get a named circuit breaker."""
    return BREAKERS[name]
