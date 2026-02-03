"""
Redis Port.

Abstract interface for Redis operations including status tracking
and rate limiting.
"""

from abc import ABC, abstractmethod
from typing import Optional

from rag_index.domain.models import RateLimitStatus, SyncStatusRecord


class RedisPort(ABC):
    """Abstract interface for Redis operations.

    This port defines the contract for status tracking and rate limiting
    operations using Redis.
    """

    # =========================================================================
    # Status Tracking Methods
    # =========================================================================

    @abstractmethod
    async def save_status(
        self,
        record: SyncStatusRecord,
        ttl_seconds: int = 86400,  # 24 hours default
    ) -> None:
        """Save a sync status record to Redis.

        Args:
            record: The status record to save
            ttl_seconds: Time-to-live in seconds

        Raises:
            RedisError: If the save operation fails
        """

    @abstractmethod
    async def get_status(
        self,
        event_id: str,
    ) -> Optional[SyncStatusRecord]:
        """Get a sync status record from Redis.

        Args:
            event_id: The event identifier

        Returns:
            The status record if found, None otherwise

        Raises:
            RedisError: If the get operation fails
        """

    @abstractmethod
    async def update_status(
        self,
        event_id: str,
        status: str,
        error_message: Optional[str] = None,
    ) -> None:
        """Update the status of an existing record.

        Args:
            event_id: The event identifier
            status: The new status value
            error_message: Optional error message for failed status

        Raises:
            StatusNotFoundError: If the record doesn't exist
            RedisError: If the update operation fails
        """

    @abstractmethod
    async def delete_status(
        self,
        event_id: str,
    ) -> bool:
        """Delete a sync status record from Redis.

        Args:
            event_id: The event identifier

        Returns:
            True if deleted, False if not found

        Raises:
            RedisError: If the delete operation fails
        """

    # =========================================================================
    # Rate Limiting Methods
    # =========================================================================

    @abstractmethod
    async def check_rate_limit(
        self,
        key: str = "rag_sync_rate",
        limit: int = 600,
        window_seconds: int = 60,
    ) -> RateLimitStatus:
        """Check current rate limit status.

        Args:
            key: The rate limit key
            limit: Maximum requests per window
            window_seconds: Time window in seconds

        Returns:
            Current rate limit status
        """

    @abstractmethod
    async def increment_rate_counter(
        self,
        key: str = "rag_sync_rate",
        window_seconds: int = 60,
    ) -> int:
        """Increment the rate limit counter.

        Args:
            key: The rate limit key
            window_seconds: Time window in seconds

        Returns:
            The new counter value

        Raises:
            RedisError: If the increment operation fails
        """

    @abstractmethod
    async def get_rate_limit_remaining(
        self,
        key: str = "rag_sync_rate",
        limit: int = 600,
    ) -> int:
        """Get the number of remaining requests in the current window.

        Args:
            key: The rate limit key
            limit: Maximum requests per window

        Returns:
            Number of remaining requests
        """

    # =========================================================================
    # Connection Methods
    # =========================================================================

    @abstractmethod
    async def check_connection(self) -> bool:
        """Check if the Redis connection is healthy.

        Returns:
            True if connection is healthy, False otherwise
        """

    @abstractmethod
    async def close(self) -> None:
        """Close the Redis connection."""
