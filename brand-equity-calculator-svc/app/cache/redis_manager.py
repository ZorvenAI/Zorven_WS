"""Async Redis manager — result caching + IP-based rate limiting.

Follows the fail-open pattern: all Redis errors are caught and logged,
never propagated.  The service continues without caching if Redis is
unavailable.
"""

import hashlib
import json
import logging
import re
from typing import Any, Optional

import redis.asyncio as aioredis

from app.core.config import settings

logger = logging.getLogger(__name__)


class RedisManager:
    """Lightweight async Redis wrapper for caching and rate limiting."""

    def __init__(self, redis_url: str) -> None:
        self.redis_url = redis_url
        self._redis: Optional[aioredis.Redis] = None

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(self.redis_url, decode_responses=True)
        return self._redis

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None

    # ── Rate limiting (IP-based) ──

    async def check_rate_limit(self, client_ip: str) -> bool:
        """Return True if the IP is within the rate limit, False otherwise."""
        try:
            r = await self._get_redis()
            key = f"equity:rate:{client_ip}"
            # Atomic incr + expire to avoid race where TTL is never set
            pipe = r.pipeline()
            pipe.incr(key)
            pipe.expire(key, 60)
            count, _ = await pipe.execute()
            return int(count) <= settings.RATE_LIMIT_PER_MINUTE
        except Exception:
            logger.warning("Redis rate-limit check failed — allowing request")
            return True  # Fail open

    # ── Result caching ──

    @staticmethod
    def build_cache_key(
        company_name: str,
        address: str,
        website: str,
        industry_type: str,
        business_size: str,
        scope: str,
    ) -> str:
        """Deterministic cache key from ALL normalized inputs."""
        normalized = re.sub(
            r"\s+",
            " ",
            re.sub(
                r"(,?\s*(inc|llc|ltd|corp|co|plc)\.?)$",
                "",
                company_name.lower().strip(),
                flags=re.IGNORECASE,
            ),
        ).strip()
        raw = (
            f"{normalized}|{address.lower().strip()}|{website.lower().strip()}"
            f"|{industry_type.lower()}|{business_size.lower()}|{scope.lower()}"
        )
        digest = hashlib.md5(raw.encode()).hexdigest()
        return f"equity:result:{digest}"

    async def get_cached_result(self, cache_key: str) -> Optional[dict[str, Any]]:
        """Return cached result dict or None."""
        try:
            r = await self._get_redis()
            data = await r.get(cache_key)
            if data:
                logger.info("Cache hit: %s", cache_key)
                return json.loads(data)
        except Exception:
            logger.warning("Redis cache read failed for %s", cache_key)
        return None

    async def set_cached_result(self, cache_key: str, result: dict[str, Any]) -> None:
        """Store result in cache with configured TTL."""
        try:
            r = await self._get_redis()
            await r.set(
                cache_key,
                json.dumps(result),
                ex=settings.RESULT_CACHE_TTL,
            )
            logger.info(
                "Cached result: %s (TTL=%ds)", cache_key, settings.RESULT_CACHE_TTL
            )
        except Exception:
            logger.warning("Redis cache write failed for %s", cache_key)
