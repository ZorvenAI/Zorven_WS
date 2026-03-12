"""Circuit breaker - per-dependency fault tolerance.

States: CLOSED -> OPEN -> HALF_OPEN -> CLOSED

When a dependency fails repeatedly (failure_threshold times), the circuit
opens and calls are short-circuited for recovery_timeout_s seconds.
After that window, one probe call is allowed (HALF_OPEN). If it succeeds
the circuit closes; if it fails it re-opens.
"""

import asyncio
import logging
import time
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreakerOpen(Exception):
    """Raised when a call is attempted on an open circuit."""

    def __init__(self, name: str, fallback: str) -> None:
        self.name = name
        self.fallback = fallback
        super().__init__(f"Circuit breaker '{name}' is OPEN (fallback={fallback})")


class CircuitBreaker:
    """Per-dependency circuit breaker with configurable thresholds."""

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout_s: int = 30,
        fallback: str = "SKIP",
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout_s = recovery_timeout_s
        self.fallback = fallback

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float = 0
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        return self._state

    @property
    def failure_count(self) -> int:
        return self._failure_count

    async def call(self, func: Callable, *args: Any, **kwargs: Any) -> Any:
        """Execute func with circuit breaker protection."""
        async with self._lock:
            if self._state == CircuitState.OPEN:
                if self._should_attempt_reset():
                    self._state = CircuitState.HALF_OPEN
                    logger.info("Circuit breaker '%s' entering HALF_OPEN", self.name)
                else:
                    raise CircuitBreakerOpen(self.name, self.fallback)

        try:
            result = await func(*args, **kwargs)
            await self._on_success()
            return result
        except Exception:
            await self._on_failure()
            raise

    async def _on_success(self) -> None:
        """Record a successful call."""
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                logger.info("Circuit breaker '%s' recovered -> CLOSED", self.name)
            self._state = CircuitState.CLOSED
            self._failure_count = 0

    async def _on_failure(self) -> None:
        """Record a failed call."""
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()

            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                logger.warning(
                    "Circuit breaker '%s' re-opened from HALF_OPEN", self.name
                )
            elif self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN
                logger.warning(
                    "Circuit breaker '%s' OPENED after %d failures",
                    self.name,
                    self._failure_count,
                )

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt a probe call."""
        elapsed = time.monotonic() - self._last_failure_time
        return elapsed >= self.recovery_timeout_s

    def reset(self) -> None:
        """Manually reset the circuit breaker to CLOSED."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time = 0


def create_circuit_breakers(settings: Any) -> dict[str, CircuitBreaker]:
    """Create all circuit breakers per the design document."""
    cb_threshold = getattr(settings, "CB_FAILURE_THRESHOLD", 5)
    cb_recovery = getattr(settings, "CB_RECOVERY_TIMEOUT", 30)
    llm_threshold = getattr(settings, "CB_LLM_FAILURE_THRESHOLD", 3)
    llm_recovery = getattr(settings, "CB_LLM_RECOVERY_TIMEOUT", 60)

    return {
        "tavily": CircuitBreaker("tavily", cb_threshold, cb_recovery, "CACHE"),
        "httpx": CircuitBreaker("httpx", cb_threshold, cb_recovery, "SKIP"),
        "llm": CircuitBreaker("llm", llm_threshold, llm_recovery, "ESCALATE"),
        "rag_store": CircuitBreaker("rag_store", cb_threshold, cb_recovery, "SKIP"),
        "gcs": CircuitBreaker("gcs", cb_threshold, cb_recovery, "SKIP"),
        "kafka": CircuitBreaker("kafka", cb_threshold, cb_recovery, "LOG_LOCAL"),
    }
