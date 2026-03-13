"""Circuit breaker implementation for the Audience Persona Agent.

8 circuit breakers:
- tavily (5 failures, 30s recovery, fallback=CACHE)
- httpx (3 failures, 30s recovery, fallback=SKIP)
- odoo_survey (3 failures, 60s recovery, fallback=SKIP)
- odoo_crm (3 failures, 60s recovery, fallback=SKIP)
- llm (3 failures, 60s recovery, fallback=ESCALATE)
- rag_store (5 failures, 30s recovery, fallback=SKIP)
- gcs (5 failures, 30s recovery, fallback=ESCALATE)
- kafka (5 failures, 30s recovery, fallback=LOG_LOCAL)
"""

import asyncio
import logging
import time
from enum import Enum
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class FallbackAction(str, Enum):
    CACHE = "cache"
    SKIP = "skip"
    ESCALATE = "escalate"
    LOG_LOCAL = "log_local"


class CircuitBreaker:
    """Async circuit breaker with automatic state transitions."""

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: int = 30,
        fallback: FallbackAction = FallbackAction.SKIP,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.fallback = fallback
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0.0
        self._lock = asyncio.Lock()

    async def call(
        self,
        func: Callable[..., Coroutine[Any, Any, Any]],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Execute a function with circuit breaker protection."""
        async with self._lock:
            if self.state == CircuitState.OPEN:
                if time.monotonic() - self.last_failure_time > self.recovery_timeout:
                    self.state = CircuitState.HALF_OPEN
                    logger.info("Circuit %s: OPEN → HALF_OPEN", self.name)
                else:
                    raise CircuitOpenError(self.name, self.fallback)

        try:
            result = await func(*args, **kwargs)
            async with self._lock:
                if self.state == CircuitState.HALF_OPEN:
                    self.state = CircuitState.CLOSED
                    self.failure_count = 0
                    logger.info("Circuit %s: HALF_OPEN → CLOSED", self.name)
                elif self.state == CircuitState.CLOSED:
                    self.failure_count = 0
            return result
        except Exception as exc:
            async with self._lock:
                self.failure_count += 1
                self.last_failure_time = time.monotonic()
                if self.failure_count >= self.failure_threshold:
                    self.state = CircuitState.OPEN
                    logger.warning(
                        "Circuit %s: → OPEN (failures=%d, fallback=%s)",
                        self.name,
                        self.failure_count,
                        self.fallback.value,
                    )
            raise exc

    @property
    def is_open(self) -> bool:
        return self.state == CircuitState.OPEN


class CircuitOpenError(Exception):
    """Raised when a circuit breaker is open."""

    def __init__(self, name: str, fallback: FallbackAction) -> None:
        self.circuit_name = name
        self.fallback = fallback
        super().__init__(f"Circuit '{name}' is open (fallback={fallback.value})")


def create_breakers(settings: Any) -> dict[str, CircuitBreaker]:
    """Create all 8 circuit breakers from settings."""
    return {
        "tavily": CircuitBreaker(
            "tavily",
            failure_threshold=settings.CB_FAILURE_THRESHOLD,
            recovery_timeout=settings.CB_RECOVERY_TIMEOUT,
            fallback=FallbackAction.CACHE,
        ),
        "httpx": CircuitBreaker(
            "httpx",
            failure_threshold=3,
            recovery_timeout=settings.CB_RECOVERY_TIMEOUT,
            fallback=FallbackAction.SKIP,
        ),
        "odoo_survey": CircuitBreaker(
            "odoo_survey",
            failure_threshold=settings.CB_ODOO_FAILURE_THRESHOLD,
            recovery_timeout=settings.CB_ODOO_RECOVERY_TIMEOUT,
            fallback=FallbackAction.SKIP,
        ),
        "odoo_crm": CircuitBreaker(
            "odoo_crm",
            failure_threshold=settings.CB_ODOO_FAILURE_THRESHOLD,
            recovery_timeout=settings.CB_ODOO_RECOVERY_TIMEOUT,
            fallback=FallbackAction.SKIP,
        ),
        "llm": CircuitBreaker(
            "llm",
            failure_threshold=settings.CB_LLM_FAILURE_THRESHOLD,
            recovery_timeout=settings.CB_LLM_RECOVERY_TIMEOUT,
            fallback=FallbackAction.ESCALATE,
        ),
        "rag_store": CircuitBreaker(
            "rag_store",
            failure_threshold=settings.CB_FAILURE_THRESHOLD,
            recovery_timeout=settings.CB_RECOVERY_TIMEOUT,
            fallback=FallbackAction.SKIP,
        ),
        "gcs": CircuitBreaker(
            "gcs",
            failure_threshold=settings.CB_FAILURE_THRESHOLD,
            recovery_timeout=settings.CB_RECOVERY_TIMEOUT,
            fallback=FallbackAction.ESCALATE,
        ),
        "kafka": CircuitBreaker(
            "kafka",
            failure_threshold=settings.CB_FAILURE_THRESHOLD,
            recovery_timeout=settings.CB_RECOVERY_TIMEOUT,
            fallback=FallbackAction.LOG_LOCAL,
        ),
    }
