"""
Redis Adapter - Redis implementation of CachePort.

Handles deduplication and status tracking for the ingestion pipeline.
"""

import json
import logging
from datetime import datetime
from typing import Optional

import redis
from redis.exceptions import RedisError

from data_ingestion.ports.cache_port import CachePort
from data_ingestion.domain.exceptions import CacheOperationError


logger = logging.getLogger(__name__)


class RedisAdapter(CachePort):
    """
    Redis adapter implementing CachePort.

    Uses redis-py for all Redis operations.
    Supports both deduplication (short TTL) and status tracking (longer TTL).
    """

    # Key prefixes for organization
    DEDUPE_PREFIX = "ingestion:dedupe:"
    STATUS_PREFIX = "ingestion:status:"

    def __init__(
        self,
        redis_url: str,
        dedupe_ttl_seconds: int = 3600,
        status_ttl_seconds: int = 604800,
        connection_pool: Optional[redis.ConnectionPool] = None,
    ):
        """
        Initialize the Redis adapter.

        Args:
            redis_url: Redis connection URL (redis://host:port/db)
            dedupe_ttl_seconds: Default TTL for deduplication keys (1 hour)
            status_ttl_seconds: Default TTL for status keys (7 days)
            connection_pool: Optional connection pool for connection reuse
        """
        self.redis_url = redis_url
        self.dedupe_ttl_seconds = dedupe_ttl_seconds
        self.status_ttl_seconds = status_ttl_seconds

        if connection_pool:
            self.client = redis.Redis(connection_pool=connection_pool)
        else:
            self.client = redis.from_url(redis_url, decode_responses=True)

        logger.info(
            "Redis adapter initialized",
            extra={
                "redis_url": self._mask_url(redis_url),
                "dedupe_ttl": dedupe_ttl_seconds,
                "status_ttl": status_ttl_seconds,
            },
        )

    @staticmethod
    def _mask_url(url: str) -> str:
        """Mask password in Redis URL for logging."""
        if "@" in url:
            # redis://:password@host:port/db -> redis://***@host:port/db
            prefix, rest = url.split("@", 1)
            return f"{prefix.rsplit(':', 1)[0]}:***@{rest}"
        return url

    def _dedupe_key(self, event_id: str) -> str:
        """Generate deduplication key."""
        return f"{self.DEDUPE_PREFIX}{event_id}"

    def _status_key(self, trace_id: str) -> str:
        """Generate status tracking key."""
        return f"{self.STATUS_PREFIX}{trace_id}"

    def is_duplicate(self, event_id: str) -> bool:
        """
        Check if an event has already been processed.

        Args:
            event_id: The event ID to check

        Returns:
            True if event was already processed, False otherwise

        Raises:
            CacheOperationError: If there's a Redis error
        """
        try:
            key = self._dedupe_key(event_id)
            exists = self.client.exists(key)
            return bool(exists)
        except RedisError as e:
            logger.error(
                "Redis error checking duplicate",
                extra={"event_id": event_id, "error": str(e)},
            )
            raise CacheOperationError(
                operation="is_duplicate",
                key=event_id,
                cause=e,
            )

    def mark_processed(
        self,
        event_id: str,
        ttl_seconds: Optional[int] = None,
    ) -> None:
        """
        Mark an event as processed for deduplication.

        Args:
            event_id: The event ID to mark
            ttl_seconds: TTL in seconds (uses default if not provided)

        Raises:
            CacheOperationError: If there's a Redis error
        """
        try:
            key = self._dedupe_key(event_id)
            ttl = ttl_seconds or self.dedupe_ttl_seconds

            # Store timestamp when processed
            self.client.setex(
                key,
                ttl,
                datetime.utcnow().isoformat(),
            )

            logger.debug(
                "Event marked as processed",
                extra={"event_id": event_id, "ttl": ttl},
            )
        except RedisError as e:
            logger.error(
                "Redis error marking processed",
                extra={"event_id": event_id, "error": str(e)},
            )
            raise CacheOperationError(
                operation="mark_processed",
                key=event_id,
                cause=e,
            )

    def update_status(
        self,
        trace_id: str,
        status: str,
        ttl_seconds: Optional[int] = None,
        metadata: Optional[dict] = None,
    ) -> None:
        """
        Update processing status for tracking.

        Args:
            trace_id: The trace ID for the event
            status: Current processing status
            ttl_seconds: TTL in seconds (uses default if not provided)
            metadata: Optional additional metadata

        Raises:
            CacheOperationError: If there's a Redis error
        """
        try:
            key = self._status_key(trace_id)
            ttl = ttl_seconds or self.status_ttl_seconds

            # Build status record
            status_record = {
                "status": status,
                "updated_at": datetime.utcnow().isoformat(),
            }
            if metadata:
                status_record["metadata"] = metadata

            # Use HSET for structured data
            self.client.hset(
                key,
                mapping={
                    "status": status,
                    "updated_at": status_record["updated_at"],
                    "data": json.dumps(status_record),
                },
            )
            self.client.expire(key, ttl)

            logger.debug(
                "Status updated",
                extra={"trace_id": trace_id, "status": status},
            )
        except RedisError as e:
            logger.error(
                "Redis error updating status",
                extra={"trace_id": trace_id, "status": status, "error": str(e)},
            )
            raise CacheOperationError(
                operation="update_status",
                key=trace_id,
                cause=e,
            )

    def get_status(self, trace_id: str) -> Optional[dict]:
        """
        Get current processing status.

        Args:
            trace_id: The trace ID to look up

        Returns:
            Status dict with 'status', 'updated_at', and optional 'metadata',
            or None if not found

        Raises:
            CacheOperationError: If there's a Redis error
        """
        try:
            key = self._status_key(trace_id)
            data = self.client.hget(key, "data")

            if data:
                return json.loads(data)
            return None

        except RedisError as e:
            logger.error(
                "Redis error getting status",
                extra={"trace_id": trace_id, "error": str(e)},
            )
            raise CacheOperationError(
                operation="get_status",
                key=trace_id,
                cause=e,
            )

    def delete(self, key: str) -> bool:
        """
        Delete a key from Redis.

        Args:
            key: The key to delete (will be prefixed appropriately)

        Returns:
            True if key was deleted, False if it didn't exist

        Raises:
            CacheOperationError: If there's a Redis error
        """
        try:
            # Try both prefixed versions
            deleted = self.client.delete(
                self._dedupe_key(key),
                self._status_key(key),
            )
            return deleted > 0
        except RedisError as e:
            logger.error(
                "Redis error deleting key",
                extra={"key": key, "error": str(e)},
            )
            raise CacheOperationError(
                operation="delete",
                key=key,
                cause=e,
            )

    def get(self, key: str) -> Optional[str]:
        """
        Get a raw value from Redis.

        Args:
            key: The key to get

        Returns:
            The value, or None if not found

        Raises:
            CacheOperationError: If there's a Redis error
        """
        try:
            return self.client.get(key)
        except RedisError as e:
            logger.error(
                "Redis error getting key",
                extra={"key": key, "error": str(e)},
            )
            raise CacheOperationError(
                operation="get",
                key=key,
                cause=e,
            )

    def set_with_ttl(
        self,
        key: str,
        value: str,
        ttl_seconds: int,
    ) -> None:
        """
        Set a key-value pair with TTL.

        Args:
            key: The key to set
            value: The value to store
            ttl_seconds: TTL in seconds (required)

        Raises:
            CacheOperationError: If there's a Redis error
        """
        try:
            self.client.setex(key, ttl_seconds, value)
        except RedisError as e:
            logger.error(
                "Redis error setting key with TTL",
                extra={"key": key, "ttl": ttl_seconds, "error": str(e)},
            )
            raise CacheOperationError(
                operation="set_with_ttl",
                key=key,
                cause=e,
            )

    def set(
        self,
        key: str,
        value: str,
        ttl_seconds: Optional[int] = None,
    ) -> None:
        """
        Set a raw value in Redis.

        Args:
            key: The key to set
            value: The value to store
            ttl_seconds: Optional TTL

        Raises:
            CacheOperationError: If there's a Redis error
        """
        try:
            if ttl_seconds:
                self.client.setex(key, ttl_seconds, value)
            else:
                self.client.set(key, value)
        except RedisError as e:
            logger.error(
                "Redis error setting key",
                extra={"key": key, "error": str(e)},
            )
            raise CacheOperationError(
                operation="set",
                key=key,
                cause=e,
            )

    def health_check(self) -> bool:
        """
        Check if Redis connection is healthy.

        Returns:
            True if healthy, False otherwise
        """
        try:
            return self.client.ping()
        except RedisError:
            return False

    def close(self) -> None:
        """Close the Redis connection."""
        try:
            self.client.close()
        except RedisError as e:
            # Best-effort cleanup: log and ignore close errors so shutdown
            # is not interrupted.
            logger.debug(
                "Redis error while closing client; ignoring during cleanup",
                exc_info=e,
            )
