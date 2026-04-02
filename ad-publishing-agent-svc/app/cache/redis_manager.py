"""Async Redis manager for Ad Publishing Agent (DB 23, fail-open).

Extends standard cache pattern with approval-specific operations:
- Approval request storage (24h TTL)
- Campaign registry (permanent)
- Duplicate campaign detection
- Preparation data cache (for resume after approval)
"""

import hashlib
import json
import logging
from typing import Any

import redis.asyncio as aioredis

from app.core.config import settings

logger = logging.getLogger(__name__)

PREFIX = "adpub"


class RedisManager:
    """Async Redis wrapper with fail-open semantics."""

    def __init__(self):
        self._redis: aioredis.Redis | None = None

    async def connect(self):
        """Establish Redis connection (fail-open)."""
        try:
            self._redis = aioredis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=5,
            )
            await self._redis.ping()
            logger.info("Redis connected: %s", settings.REDIS_URL)
        except Exception as exc:
            logger.warning("Redis unavailable (fail-open): %s", exc)
            self._redis = None

    async def close(self):
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()

    @property
    def available(self) -> bool:
        return self._redis is not None

    # ── Result caching ──

    async def get_cached_result(
        self, tenant_id: str, prompt_hash: str
    ) -> dict[str, Any] | None:
        """Get cached result by prompt hash."""
        if not self._redis:
            return None
        try:
            key = f"{PREFIX}:{tenant_id}:result:{prompt_hash}"
            data = await self._redis.get(key)
            return json.loads(data) if data else None
        except Exception as exc:
            logger.warning("Redis get_cached_result error: %s", exc)
            return None

    async def cache_result(
        self, tenant_id: str, prompt_hash: str, result: dict[str, Any]
    ):
        """Cache result with TTL."""
        if not self._redis:
            return
        try:
            key = f"{PREFIX}:{tenant_id}:result:{prompt_hash}"
            await self._redis.set(
                key,
                json.dumps(result, default=str),
                ex=settings.RESULT_CACHE_TTL,
            )
        except Exception as exc:
            logger.warning("Redis cache_result error: %s", exc)

    # ── Generic JSON helpers ──

    async def set_json(self, key: str, data: dict[str, Any], ttl: int = 86400):
        """Set a JSON value with TTL."""
        if not self._redis:
            return
        try:
            await self._redis.set(key, json.dumps(data, default=str), ex=ttl)
        except Exception as exc:
            logger.warning("Redis set_json error: %s", exc)

    async def get_json(self, key: str) -> dict[str, Any] | None:
        """Get a JSON value."""
        if not self._redis:
            return None
        try:
            data = await self._redis.get(key)
            return json.loads(data) if data else None
        except Exception as exc:
            logger.warning("Redis get_json error: %s", exc)
            return None

    # ── Approval requests (24h TTL) ──

    async def store_approval_request(
        self, request_id: str, tenant_id: str, data: dict[str, Any]
    ):
        """Store approval request with 24h TTL."""
        if not self._redis:
            return
        try:
            key = f"{PREFIX}:{tenant_id}:approval:{request_id}"
            await self._redis.set(
                key,
                json.dumps(data, default=str),
                ex=settings.APPROVAL_EXPIRY_SECONDS,
            )
            # Add to pending set for listing
            pending_key = f"{PREFIX}:{tenant_id}:approvals:pending"
            await self._redis.sadd(pending_key, request_id)
            await self._redis.expire(
                pending_key, settings.APPROVAL_EXPIRY_SECONDS
            )
        except Exception as exc:
            logger.warning("Redis store_approval_request error: %s", exc)

    async def get_approval_request(
        self, request_id: str, tenant_id: str
    ) -> dict[str, Any] | None:
        """Get approval request by ID."""
        if not self._redis:
            return None
        try:
            key = f"{PREFIX}:{tenant_id}:approval:{request_id}"
            data = await self._redis.get(key)
            return json.loads(data) if data else None
        except Exception as exc:
            logger.warning("Redis get_approval_request error: %s", exc)
            return None

    async def update_approval_request(
        self, request_id: str, tenant_id: str, data: dict[str, Any]
    ):
        """Update an existing approval request (preserves remaining TTL)."""
        if not self._redis:
            return
        try:
            key = f"{PREFIX}:{tenant_id}:approval:{request_id}"
            ttl = await self._redis.ttl(key)
            if ttl > 0:
                await self._redis.set(
                    key, json.dumps(data, default=str), ex=ttl
                )
            else:
                # Expired or missing — store with full TTL
                await self._redis.set(
                    key,
                    json.dumps(data, default=str),
                    ex=settings.APPROVAL_EXPIRY_SECONDS,
                )
        except Exception as exc:
            logger.warning("Redis update_approval_request error: %s", exc)

    async def list_pending_approvals(
        self, tenant_id: str
    ) -> list[dict[str, Any]]:
        """List all pending approval requests for a tenant."""
        if not self._redis:
            return []
        try:
            pending_key = f"{PREFIX}:{tenant_id}:approvals:pending"
            request_ids = await self._redis.smembers(pending_key)
            results = []
            for rid in request_ids:
                data = await self.get_approval_request(rid, tenant_id)
                if data and data.get("status") == "pending":
                    results.append(data)
            return results
        except Exception as exc:
            logger.warning("Redis list_pending_approvals error: %s", exc)
            return []

    # ── Preparation data (for resume after approval) ──

    async def store_preparation(
        self, request_id: str, tenant_id: str, data: dict[str, Any]
    ):
        """Store preparation data for Phase B resume."""
        if not self._redis:
            return
        try:
            key = f"{PREFIX}:{tenant_id}:prep:{request_id}"
            await self._redis.set(
                key,
                json.dumps(data, default=str),
                ex=settings.APPROVAL_EXPIRY_SECONDS,
            )
        except Exception as exc:
            logger.warning("Redis store_preparation error: %s", exc)

    async def get_preparation(
        self, request_id: str, tenant_id: str
    ) -> dict[str, Any] | None:
        """Get preparation data for Phase B resume."""
        if not self._redis:
            return None
        try:
            key = f"{PREFIX}:{tenant_id}:prep:{request_id}"
            data = await self._redis.get(key)
            return json.loads(data) if data else None
        except Exception as exc:
            logger.warning("Redis get_preparation error: %s", exc)
            return None

    # ── Campaign registry (permanent) ──

    async def save_campaign_registry(
        self, tenant_id: str, campaign_id: str, data: dict[str, Any]
    ):
        """Save published campaign to permanent registry."""
        if not self._redis:
            return
        try:
            key = f"{PREFIX}:{tenant_id}:registry:{campaign_id}"
            await self._redis.set(key, json.dumps(data, default=str))
        except Exception as exc:
            logger.warning("Redis save_campaign_registry error: %s", exc)

    async def check_duplicate_campaign(
        self, tenant_id: str, campaign_name: str
    ) -> bool:
        """Check if a campaign with the same name already exists."""
        if not self._redis:
            return False
        try:
            pattern = f"{PREFIX}:{tenant_id}:registry:*"
            cursor = 0
            while True:
                cursor, keys = await self._redis.scan(
                    cursor=cursor, match=pattern, count=100
                )
                for key in keys:
                    data = await self._redis.get(key)
                    if data:
                        record = json.loads(data)
                        if record.get("campaign_name") == campaign_name:
                            return True
                if cursor == 0:
                    break
            return False
        except Exception as exc:
            logger.warning("Redis check_duplicate_campaign error: %s", exc)
            return False

    # ── Rate limiting ──

    async def check_rate_limit(self, tenant_id: str) -> bool:
        """Check if tenant is within rate limits (3/min — publishing is costly)."""
        if not self._redis:
            return True
        try:
            key = f"{PREFIX}:rate:{tenant_id}"
            count = await self._redis.incr(key)
            if count == 1:
                await self._redis.expire(key, 60)
            return count <= 3
        except Exception:
            return True

    # ── Helpers ──

    @staticmethod
    def hash_prompt(prompt: str) -> str:
        """Generate MD5 hash of prompt for cache key."""
        return hashlib.md5(prompt.encode()).hexdigest()

    @staticmethod
    def hash_inputs(prompt: str, **context: Any) -> str:
        """Generate MD5 hash of prompt + context for cache key."""
        payload = json.dumps(
            {"prompt": prompt, **context}, sort_keys=True, default=str
        )
        return hashlib.md5(payload.encode()).hexdigest()
