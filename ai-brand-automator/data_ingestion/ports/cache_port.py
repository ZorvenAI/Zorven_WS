"""
Cache Port - Abstract interface for caching and deduplication.

This port defines how the domain layer interacts with the cache (Redis).
Used for event deduplication and pipeline status tracking.
"""

from abc import ABC, abstractmethod
from typing import Optional


class CachePort(ABC):
    """
    Abstract interface for cache operations.

    Implementations:
        - RedisAdapter: Redis implementation
        - MockCacheAdapter: For testing
    """

    @abstractmethod
    def is_duplicate(self, event_id: str) -> bool:
        """
        Check if an event has already been processed.

        Uses SETNX-style logic: returns True if key already exists.

        Args:
            event_id: Unique event identifier

        Returns:
            True if event was already processed (duplicate), False if new

        Raises:
            CacheOperationError: If the cache operation fails
        """
        pass

    @abstractmethod
    def mark_processed(self, event_id: str, ttl_seconds: int = 3600) -> None:
        """
        Mark an event as processed to prevent reprocessing.

        Args:
            event_id: Unique event identifier
            ttl_seconds: Time-to-live for the deduplication key (default 1 hour)

        Raises:
            CacheOperationError: If the cache operation fails
        """
        pass

    @abstractmethod
    def update_status(
        self,
        trace_id: str,
        status: str,
        ttl_seconds: int = 604800,
        metadata: Optional[dict] = None,
    ) -> None:
        """
        Update the processing status for a trace.

        Used to track the pipeline status for monitoring/debugging.

        Args:
            trace_id: Trace identifier for distributed tracing
            status: Status string (e.g., 'RAW_STORED', 'FAILED')
            ttl_seconds: Time-to-live for the status key (default 7 days)
            metadata: Optional additional metadata to store with status

        Raises:
            CacheOperationError: If the cache operation fails
        """
        pass

    @abstractmethod
    def get_status(self, trace_id: str) -> Optional[dict]:
        """
        Get the current processing status for a trace.

        Args:
            trace_id: Trace identifier

        Returns:
            Status dict with 'status' and optional 'metadata', or None if not found

        Raises:
            CacheOperationError: If the cache operation fails
        """
        pass

    @abstractmethod
    def set_with_ttl(self, key: str, value: str, ttl_seconds: int) -> None:
        """
        Set a key-value pair with TTL.

        Generic method for arbitrary cache operations.

        Args:
            key: Cache key
            value: Value to store (will be serialized to string)
            ttl_seconds: Time-to-live in seconds

        Raises:
            CacheOperationError: If the cache operation fails
        """
        pass

    @abstractmethod
    def get(self, key: str) -> Optional[str]:
        """
        Get a value by key.

        Args:
            key: Cache key

        Returns:
            Value if exists, None otherwise

        Raises:
            CacheOperationError: If the cache operation fails
        """
        pass

    @abstractmethod
    def delete(self, key: str) -> bool:
        """
        Delete a key from cache.

        Args:
            key: Cache key to delete

        Returns:
            True if key was deleted, False if it didn't exist

        Raises:
            CacheOperationError: If the cache operation fails
        """
        pass
