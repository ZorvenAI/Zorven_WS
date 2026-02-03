"""
Rate Limiter Implementation.

Provides a sliding window rate limiter for controlling API request rates
to Vertex AI Discovery Engine (600 req/min limit).
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from rag_index.domain.exceptions import RateLimitExceededError
from rag_index.domain.models import RateLimitStatus
from rag_index.ports.redis_port import RedisPort

logger = logging.getLogger(__name__)


@dataclass
class RateLimiterConfig:
    """Configuration for rate limiter.

    Attributes:
        limit: Maximum requests per window (default: 600)
        window_seconds: Time window in seconds (default: 60)
        key: Redis key prefix for rate limiting
        burst_limit: Maximum burst size allowed (default: limit * 0.1)
        wait_on_limit: Whether to wait when rate limited (default: True)
        max_wait_seconds: Maximum time to wait for rate limit (default: 30)
    """

    limit: int = 600
    window_seconds: int = 60
    key: str = "rag_sync_rate"
    burst_limit: Optional[int] = None
    wait_on_limit: bool = True
    max_wait_seconds: int = 30

    def __post_init__(self):
        if self.burst_limit is None:
            self.burst_limit = int(self.limit * 0.1)


class SlidingWindowRateLimiter:
    """Sliding window rate limiter using Redis.

    Implements a sliding window algorithm for rate limiting that provides
    smoother request distribution compared to fixed window counters.

    The sliding window approach:
    1. Uses two windows: current and previous
    2. Calculates weighted count based on time position in current window
    3. Provides more accurate rate limiting at window boundaries

    Example:
        config = RateLimiterConfig(limit=600, window_seconds=60)
        limiter = SlidingWindowRateLimiter(redis_port, config)

        # Check if request is allowed
        if await limiter.acquire():
            # Make API call
            pass
    """

    def __init__(
        self,
        redis_port: RedisPort,
        config: Optional[RateLimiterConfig] = None,
    ):
        """Initialize rate limiter.

        Args:
            redis_port: Redis port for storing rate limit counters
            config: Rate limiter configuration
        """
        self.redis = redis_port
        self.config = config or RateLimiterConfig()
        self._local_counter = 0
        self._window_start = time.time()

    async def acquire(self, count: int = 1) -> bool:
        """Attempt to acquire rate limit tokens.

        Args:
            count: Number of tokens to acquire (default: 1)

        Returns:
            True if tokens were acquired, False if rate limited

        Raises:
            RateLimitExceededError: If wait_on_limit is False and limit exceeded
        """
        status = await self.get_status()

        if status.remaining < count:
            if not self.config.wait_on_limit:
                raise RateLimitExceededError(
                    message="Rate limit exceeded",
                    retry_after_seconds=self._calculate_retry_after(status),
                    current_count=status.current_count,
                    limit=status.limit,
                )

            # Wait for capacity
            waited = await self._wait_for_capacity(count)
            if not waited:
                raise RateLimitExceededError(
                    message="Rate limit exceeded after waiting",
                    retry_after_seconds=self._calculate_retry_after(status),
                    current_count=status.current_count,
                    limit=status.limit,
                )

        # Increment counter
        await self.redis.increment_rate_counter(
            key=self.config.key,
            window_seconds=self.config.window_seconds,
        )

        return True

    async def get_status(self) -> RateLimitStatus:
        """Get current rate limit status.

        Returns:
            Current rate limit status including count, limit, and remaining
        """
        return await self.redis.check_rate_limit(
            key=self.config.key,
            limit=self.config.limit,
            window_seconds=self.config.window_seconds,
        )

    async def get_remaining(self) -> int:
        """Get remaining requests in current window.

        Returns:
            Number of remaining requests allowed
        """
        status = await self.get_status()
        return status.remaining

    async def is_limited(self) -> bool:
        """Check if currently rate limited.

        Returns:
            True if rate limited, False otherwise
        """
        status = await self.get_status()
        return status.is_limited

    async def _wait_for_capacity(self, count: int) -> bool:
        """Wait for rate limit capacity to become available.

        Args:
            count: Number of tokens needed

        Returns:
            True if capacity became available, False if timeout
        """
        start_time = time.time()
        wait_interval = 0.5  # Start with 500ms
        max_interval = 5.0  # Max 5 second intervals

        while True:
            elapsed = time.time() - start_time
            if elapsed >= self.config.max_wait_seconds:
                logger.warning(f"Rate limit wait timeout after {elapsed:.1f}s")
                return False

            status = await self.get_status()
            if status.remaining >= count:
                logger.debug(f"Rate limit capacity available after {elapsed:.1f}s wait")
                return True

            # Exponential backoff with jitter
            jitter = wait_interval * 0.1
            actual_wait = min(wait_interval + jitter, max_interval)

            logger.debug(
                f"Rate limited, waiting {actual_wait:.1f}s "
                f"(remaining: {status.remaining}/{status.limit})"
            )

            await asyncio.sleep(actual_wait)
            wait_interval = min(wait_interval * 1.5, max_interval)

    def _calculate_retry_after(self, status: RateLimitStatus) -> int:
        """Calculate seconds until rate limit resets.

        Args:
            status: Current rate limit status

        Returns:
            Seconds until more capacity is available
        """
        if status.reset_at:
            delta = status.reset_at - datetime.now(timezone.utc)
            return max(1, int(delta.total_seconds()))
        return self.config.window_seconds


class InMemoryRateLimiter:
    """In-memory rate limiter for testing and development.

    This implementation doesn't require Redis and can be used
    for local development or testing scenarios.
    """

    def __init__(self, config: Optional[RateLimiterConfig] = None):
        """Initialize in-memory rate limiter.

        Args:
            config: Rate limiter configuration
        """
        self.config = config or RateLimiterConfig()
        self._counter = 0
        self._window_start = time.time()
        self._lock = asyncio.Lock()

    async def acquire(self, count: int = 1) -> bool:
        """Attempt to acquire rate limit tokens."""
        async with self._lock:
            self._maybe_reset_window()

            if self._counter + count > self.config.limit:
                if not self.config.wait_on_limit:
                    raise RateLimitExceededError(
                        message="Rate limit exceeded",
                        retry_after_seconds=self._seconds_until_reset(),
                        current_count=self._counter,
                        limit=self.config.limit,
                    )

                # Wait for window reset
                await asyncio.sleep(self._seconds_until_reset())
                self._maybe_reset_window()

            self._counter += count
            return True

    async def get_status(self) -> RateLimitStatus:
        """Get current rate limit status."""
        async with self._lock:
            self._maybe_reset_window()
            return RateLimitStatus(
                current_count=self._counter,
                limit=self.config.limit,
                window_seconds=self.config.window_seconds,
                remaining=max(0, self.config.limit - self._counter),
            )

    async def get_remaining(self) -> int:
        """Get remaining requests in current window."""
        status = await self.get_status()
        return status.remaining

    async def is_limited(self) -> bool:
        """Check if currently rate limited."""
        status = await self.get_status()
        return status.is_limited

    def _maybe_reset_window(self):
        """Reset counter if window has expired."""
        now = time.time()
        elapsed = now - self._window_start
        if elapsed >= self.config.window_seconds:
            self._counter = 0
            self._window_start = now

    def _seconds_until_reset(self) -> int:
        """Calculate seconds until window resets."""
        elapsed = time.time() - self._window_start
        return max(1, int(self.config.window_seconds - elapsed))
