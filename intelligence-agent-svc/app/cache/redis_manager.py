"""
Async Redis manager for caching and rate limiting.

Key patterns:
  intel:benchmarks:{sector}  → JSON  → 30 days TTL  (industry royalty rates)
  intel:wacc:{region}        → JSON  → 30 days TTL  (discount rates by region)
  intel:rate:{tenant_id}     → Int   → 60s TTL      (rate limiting)
  intel:result:{md5(key)}    → JSON  → 4h TTL       (cached analysis results)

All operations fail gracefully (fail open) on Redis errors.
"""

import hashlib
import json
import logging
from typing import Any, Optional

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

# TTL constants
BENCHMARK_CACHE_TTL = 30 * 24 * 60 * 60  # 30 days
RESULT_CACHE_TTL = 4 * 60 * 60  # 4 hours
RATE_LIMIT_TTL = 60  # 1 minute


class RedisManager:
    """Async Redis manager for caching and rate limiting."""

    def __init__(self, redis_url: str) -> None:
        self.redis_url = redis_url
        self._redis: Optional[aioredis.Redis] = None

    async def _get_redis(self) -> aioredis.Redis:
        """Return a Redis connection, creating one if needed."""
        if self._redis is None:
            self._redis = aioredis.from_url(
                self.redis_url,
                decode_responses=True,
            )
        return self._redis

    async def close(self) -> None:
        """Close the Redis connection."""
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None

    @staticmethod
    def _hash(value: str) -> str:
        """Generate an MD5 hash for cache key construction."""
        return hashlib.md5(value.encode()).hexdigest()

    # --- Benchmark Cache ---

    async def get_benchmarks(self, sector: str) -> Optional[dict[str, Any]]:
        """Get cached industry benchmark data for a sector."""
        try:
            r = await self._get_redis()
            key = f"intel:benchmarks:{sector}"
            data = await r.get(key)
            if data is not None:
                logger.debug("Benchmark cache HIT for sector: %s", sector)
                return json.loads(data)
            return None
        except Exception as exc:
            logger.warning("Redis error in get_benchmarks: %s", exc)
            return None

    async def set_benchmarks(self, sector: str, data: dict[str, Any]) -> None:
        """Cache benchmark data with 30-day TTL."""
        try:
            r = await self._get_redis()
            key = f"intel:benchmarks:{sector}"
            await r.set(key, json.dumps(data), ex=BENCHMARK_CACHE_TTL)
            logger.debug("Benchmark cache SET for sector: %s", sector)
        except Exception as exc:
            logger.warning("Redis error in set_benchmarks: %s", exc)

    # --- WACC Cache ---

    async def get_wacc(self, region: str) -> Optional[float]:
        """Get cached WACC (discount rate) for a region."""
        try:
            r = await self._get_redis()
            key = f"intel:wacc:{region}"
            data = await r.get(key)
            if data is not None:
                logger.debug("WACC cache HIT for region: %s", region)
                return float(data)
            return None
        except Exception as exc:
            logger.warning("Redis error in get_wacc: %s", exc)
            return None

    async def set_wacc(self, region: str, rate: float) -> None:
        """Cache WACC with 30-day TTL."""
        try:
            r = await self._get_redis()
            key = f"intel:wacc:{region}"
            await r.set(key, json.dumps(rate), ex=BENCHMARK_CACHE_TTL)
            logger.debug("WACC cache SET for region: %s", region)
        except Exception as exc:
            logger.warning("Redis error in set_wacc: %s", exc)

    # --- Result Cache ---

    async def get_cached_result(self, cache_key: str) -> Optional[dict[str, Any]]:
        """Get cached analysis result."""
        try:
            r = await self._get_redis()
            key = f"intel:result:{self._hash(cache_key)}"
            data = await r.get(key)
            if data is not None:
                logger.debug("Result cache HIT for key: %s", cache_key[:50])
                return json.loads(data)
            return None
        except Exception as exc:
            logger.warning("Redis error in get_cached_result: %s", exc)
            return None

    async def set_cached_result(self, cache_key: str, result: dict[str, Any]) -> None:
        """Cache analysis result with 4-hour TTL."""
        try:
            r = await self._get_redis()
            key = f"intel:result:{self._hash(cache_key)}"
            await r.set(key, json.dumps(result), ex=RESULT_CACHE_TTL)
            logger.debug("Result cache SET for key: %s", cache_key[:50])
        except Exception as exc:
            logger.warning("Redis error in set_cached_result: %s", exc)

    # --- Rate Limiting ---

    async def check_rate_limit(self, tenant_id: str, limit: int = 10) -> bool:
        """
        Check if a tenant is within their rate limit.

        Uses INCR + EXPIRE pattern with 1-minute window.
        Returns True if within limit, False if exceeded.
        """
        try:
            r = await self._get_redis()
            key = f"intel:rate:{tenant_id}"
            count = await r.incr(key)
            if count == 1:
                await r.expire(key, RATE_LIMIT_TTL)
            return count <= limit
        except Exception as exc:
            logger.warning("Redis error in check_rate_limit: %s", exc)
            return True  # Fail open
