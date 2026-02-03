"""
Redis Adapter.

Concrete implementation of RedisPort for status tracking
and rate limiting operations.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from django.conf import settings

from rag_index.domain.exceptions import (
    RedisError,
    StatusNotFoundError,
)
from rag_index.domain.models import RateLimitStatus, SyncStatusRecord
from rag_index.ports.redis_port import RedisPort

logger = logging.getLogger(__name__)


class RedisAdapter(RedisPort):
    """Concrete adapter for Redis operations.

    This adapter handles status tracking and rate limiting
    using Redis as the backend.

    Configuration is loaded from Django settings:
    - REDIS_URL: Redis connection URL
    - RAG_SYNC_RATE_LIMIT: Maximum requests per window (default: 600)
    - RAG_SYNC_RATE_WINDOW: Time window in seconds (default: 60)
    """

    STATUS_KEY_PREFIX = "rag_sync:status:"
    RATE_KEY_PREFIX = "rag_sync:rate:"

    def __init__(
        self,
        redis_url: Optional[str] = None,
        rate_limit: int = 600,
        rate_window: int = 60,
    ):
        """Initialize Redis adapter.

        Args:
            redis_url: Redis connection URL
            rate_limit: Maximum requests per window
            rate_window: Time window in seconds
        """
        self.redis_url = redis_url or getattr(
            settings, "REDIS_URL", "redis://localhost:6379/0"
        )
        self.rate_limit = rate_limit or getattr(settings, "RAG_SYNC_RATE_LIMIT", 600)
        self.rate_window = rate_window or getattr(settings, "RAG_SYNC_RATE_WINDOW", 60)
        self._client = None
        self._initialized = False

    def _get_client(self):
        """Get or create the Redis client.

        Lazy initialization to avoid import errors when Redis is not available.
        """
        if self._client is None:
            try:
                import redis.asyncio as redis

                self._client = redis.from_url(
                    self.redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                )
                self._initialized = True
            except ImportError:
                logger.warning("redis not installed. Using mock mode for development.")
                self._client = None
                self._initialized = False
            except Exception as e:
                logger.error(f"Failed to connect to Redis: {e}")
                self._client = None
                self._initialized = False
        return self._client

    def _get_status_key(self, event_id: str) -> str:
        """Get the Redis key for a status record."""
        return f"{self.STATUS_KEY_PREFIX}{event_id}"

    def _get_rate_key(self, key: str = "default") -> str:
        """Get the Redis key for rate limiting."""
        return f"{self.RATE_KEY_PREFIX}{key}"

    # =========================================================================
    # Status Tracking Methods
    # =========================================================================

    async def save_status(
        self,
        record: SyncStatusRecord,
        ttl_seconds: int = 86400,
    ) -> None:
        """Save a sync status record to Redis."""
        try:
            client = self._get_client()

            if client is None:
                logger.info(f"[MOCK] Saving status for {record.event_id}")
                return

            key = self._get_status_key(str(record.event_id))
            data = json.dumps(record.to_dict())

            await client.set(key, data, ex=ttl_seconds)

            logger.debug(f"Saved status for event {record.event_id}")

        except Exception as e:
            logger.error(f"Failed to save status: {e}")
            raise RedisError(f"Failed to save status: {e}")

    async def get_status(
        self,
        event_id: str,
    ) -> Optional[SyncStatusRecord]:
        """Get a sync status record from Redis."""
        try:
            client = self._get_client()

            if client is None:
                logger.info(f"[MOCK] Getting status for {event_id}")
                return None

            key = self._get_status_key(event_id)
            data = await client.get(key)

            if data is None:
                return None

            return SyncStatusRecord.from_dict(json.loads(data))

        except Exception as e:
            logger.error(f"Failed to get status: {e}")
            raise RedisError(f"Failed to get status: {e}")

    async def update_status(
        self,
        event_id: str,
        status: str,
        error_message: Optional[str] = None,
    ) -> None:
        """Update the status of an existing record."""
        try:
            client = self._get_client()

            if client is None:
                logger.info(f"[MOCK] Updating status for {event_id} to {status}")
                return

            key = self._get_status_key(event_id)
            data = await client.get(key)

            if data is None:
                raise StatusNotFoundError(event_id=event_id)

            record_data = json.loads(data)
            record_data["status"] = status
            if error_message:
                record_data["error_message"] = error_message
            if status in ("COMPLETED", "FAILED"):
                record_data["completed_at"] = datetime.now(timezone.utc).isoformat()

            # Get TTL and preserve it
            ttl = await client.ttl(key)
            if ttl < 0:
                ttl = 86400  # Default 24 hours

            await client.set(key, json.dumps(record_data), ex=ttl)

            logger.debug(f"Updated status for event {event_id} to {status}")

        except StatusNotFoundError:
            raise
        except Exception as e:
            logger.error(f"Failed to update status: {e}")
            raise RedisError(f"Failed to update status: {e}")

    async def delete_status(self, event_id: str) -> bool:
        """Delete a sync status record from Redis."""
        try:
            client = self._get_client()

            if client is None:
                logger.info(f"[MOCK] Deleting status for {event_id}")
                return True

            key = self._get_status_key(event_id)
            result = await client.delete(key)

            return result > 0

        except Exception as e:
            logger.error(f"Failed to delete status: {e}")
            raise RedisError(f"Failed to delete status: {e}")

    # =========================================================================
    # Rate Limiting Methods
    # =========================================================================

    async def check_rate_limit(
        self,
        key: str = "rag_sync_rate",
        limit: int = 600,
        window_seconds: int = 60,
    ) -> RateLimitStatus:
        """Check current rate limit status using sliding window."""
        try:
            client = self._get_client()

            if client is None:
                return RateLimitStatus(
                    current_count=0,
                    limit=limit,
                    remaining=limit,
                )

            redis_key = self._get_rate_key(key)

            # Get current count
            count_str = await client.get(redis_key)
            current_count = int(count_str) if count_str else 0

            # Get TTL for reset time
            ttl = await client.ttl(redis_key)
            reset_at = None
            if ttl > 0:
                reset_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)

            return RateLimitStatus(
                current_count=current_count,
                limit=limit,
                window_seconds=window_seconds,
                remaining=max(0, limit - current_count),
                reset_at=reset_at,
            )

        except Exception as e:
            logger.error(f"Failed to check rate limit: {e}")
            # Return safe default on error
            return RateLimitStatus(
                current_count=0,
                limit=limit,
                remaining=limit,
            )

    async def increment_rate_counter(
        self,
        key: str = "rag_sync_rate",
        window_seconds: int = 60,
    ) -> int:
        """Increment the rate limit counter using sliding window."""
        try:
            client = self._get_client()

            if client is None:
                logger.info(f"[MOCK] Incrementing rate counter for {key}")
                return 1

            redis_key = self._get_rate_key(key)

            # Increment with INCR, which handles creation
            count = await client.incr(redis_key)

            # Set expiry only if this is a new key (count == 1)
            if count == 1:
                await client.expire(redis_key, window_seconds)

            return count

        except Exception as e:
            logger.error(f"Failed to increment rate counter: {e}")
            raise RedisError(f"Failed to increment rate counter: {e}")

    async def get_rate_limit_remaining(
        self,
        key: str = "rag_sync_rate",
        limit: int = 600,
    ) -> int:
        """Get the number of remaining requests in the current window."""
        status = await self.check_rate_limit(key, limit)
        return status.remaining

    # =========================================================================
    # Connection Methods
    # =========================================================================

    async def check_connection(self) -> bool:
        """Check if the Redis connection is healthy."""
        try:
            client = self._get_client()

            if client is None:
                return True  # Mock mode

            await client.ping()
            return True

        except Exception as e:
            logger.error(f"Redis connection check failed: {e}")
            return False

    async def close(self) -> None:
        """Close the Redis connection."""
        if self._client is not None:
            try:
                await self._client.close()
            except Exception as e:
                logger.error(f"Error closing Redis connection: {e}")
            finally:
                self._client = None
                self._initialized = False
