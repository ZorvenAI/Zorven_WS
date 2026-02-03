"""
Throttled Vertex AI Adapter.

Wraps the VertexAIAdapter with rate limiting to respect
the Vertex AI Discovery Engine quota (600 req/min).
"""

import logging
from typing import Any, Optional

from rag_index.adapters.rate_limiter import (
    InMemoryRateLimiter,
    RateLimiterConfig,
    SlidingWindowRateLimiter,
)
from rag_index.adapters.vertex_ai_adapter import VertexAIAdapter
from rag_index.domain.exceptions import RateLimitExceededError
from rag_index.domain.models import SyncEvent, SyncResult
from rag_index.ports.redis_port import RedisPort
from rag_index.ports.vertex_ai_port import VertexAIPort

logger = logging.getLogger(__name__)


class ThrottledVertexAIAdapter(VertexAIPort):
    """Throttled Vertex AI adapter with rate limiting.

    This adapter wraps a VertexAIAdapter and applies rate limiting
    to ensure we don't exceed the Vertex AI Discovery Engine quota
    of 600 requests per minute.

    The Throttling Proxy Pattern is used here:
    1. Before each request, check rate limit status
    2. If limit exceeded, wait or raise error based on config
    3. After acquiring token, delegate to underlying adapter
    4. Track successful requests for rate limiting

    Example:
        redis_adapter = RedisAdapter()
        vertex_adapter = VertexAIAdapter()
        throttled = ThrottledVertexAIAdapter(
            vertex_adapter=vertex_adapter,
            redis_port=redis_adapter,
            rate_limit=600,
        )

        result = await throttled.upsert_document(event, content)
    """

    def __init__(
        self,
        vertex_adapter: Optional[VertexAIAdapter] = None,
        redis_port: Optional[RedisPort] = None,
        rate_limit: int = 600,
        rate_window_seconds: int = 60,
        wait_on_limit: bool = True,
        max_wait_seconds: int = 30,
        use_in_memory_limiter: bool = False,
    ):
        """Initialize throttled adapter.

        Args:
            vertex_adapter: Underlying Vertex AI adapter (created if None)
            redis_port: Redis port for rate limiting (required unless in-memory)
            rate_limit: Maximum requests per window (default: 600)
            rate_window_seconds: Time window in seconds (default: 60)
            wait_on_limit: Whether to wait when rate limited (default: True)
            max_wait_seconds: Maximum time to wait (default: 30)
            use_in_memory_limiter: Use in-memory limiter for testing
        """
        self._vertex_adapter = vertex_adapter or VertexAIAdapter()
        self._redis_port = redis_port

        # Configure rate limiter
        config = RateLimiterConfig(
            limit=rate_limit,
            window_seconds=rate_window_seconds,
            key="rag_sync_vertex_ai_rate",
            wait_on_limit=wait_on_limit,
            max_wait_seconds=max_wait_seconds,
        )

        if use_in_memory_limiter or redis_port is None:
            self._rate_limiter = InMemoryRateLimiter(config)
            logger.info("Using in-memory rate limiter")
        else:
            self._rate_limiter = SlidingWindowRateLimiter(redis_port, config)
            logger.info(
                f"Using Redis-based rate limiter: "
                f"{rate_limit} req/{rate_window_seconds}s"
            )

    async def upsert_document(
        self,
        event: SyncEvent,
        document_content: dict[str, Any],
    ) -> SyncResult:
        """Insert or update a document with rate limiting.

        Args:
            event: The sync event containing document metadata
            document_content: The curated document content to index

        Returns:
            SyncResult with operation status and details

        Raises:
            RateLimitExceededError: If rate limit exceeded and not waiting
            DocumentUpsertError: If the upsert operation fails
        """
        # Acquire rate limit token
        try:
            await self._rate_limiter.acquire()
        except RateLimitExceededError:
            logger.warning(
                f"Rate limit exceeded for upsert: "
                f"event_id={event.event_id}, trace_id={event.trace_id}"
            )
            raise

        # Delegate to underlying adapter
        logger.debug(
            f"Upserting document with rate limiting: "
            f"file_id={event.file_id}, trace_id={event.trace_id}"
        )

        return await self._vertex_adapter.upsert_document(event, document_content)

    async def delete_document(self, event: SyncEvent) -> SyncResult:
        """Delete a document with rate limiting.

        Args:
            event: The sync event containing document identifier

        Returns:
            SyncResult with operation status

        Raises:
            RateLimitExceededError: If rate limit exceeded and not waiting
            DocumentDeleteError: If the delete operation fails
        """
        # Acquire rate limit token
        try:
            await self._rate_limiter.acquire()
        except RateLimitExceededError:
            logger.warning(
                f"Rate limit exceeded for delete: "
                f"event_id={event.event_id}, trace_id={event.trace_id}"
            )
            raise

        # Delegate to underlying adapter
        logger.debug(
            f"Deleting document with rate limiting: "
            f"file_id={event.file_id}, trace_id={event.trace_id}"
        )

        return await self._vertex_adapter.delete_document(event)

    async def get_document(
        self,
        document_id: str,
        tenant_id: str,
    ) -> Optional[dict[str, Any]]:
        """Retrieve a document with rate limiting.

        Args:
            document_id: The document identifier
            tenant_id: The tenant identifier

        Returns:
            Document content if found, None otherwise
        """
        # Acquire rate limit token
        try:
            await self._rate_limiter.acquire()
        except RateLimitExceededError:
            logger.warning(
                f"Rate limit exceeded for get_document: document_id={document_id}"
            )
            raise

        return await self._vertex_adapter.get_document(document_id, tenant_id)

    async def check_connection(self) -> bool:
        """Check if the Vertex AI connection is healthy.

        Note: This doesn't consume rate limit tokens as it's a health check.

        Returns:
            True if connection is healthy, False otherwise
        """
        return await self._vertex_adapter.check_connection()

    def get_data_store_path(self, tenant_id: str) -> str:
        """Get the Vertex AI data store path for a tenant.

        Args:
            tenant_id: The tenant identifier

        Returns:
            The fully qualified data store path
        """
        return self._vertex_adapter.get_data_store_path(tenant_id)

    async def get_rate_limit_status(self):
        """Get current rate limit status.

        Returns:
            Current rate limit status
        """
        return await self._rate_limiter.get_status()

    async def get_remaining_requests(self) -> int:
        """Get remaining requests in current window.

        Returns:
            Number of remaining requests allowed
        """
        return await self._rate_limiter.get_remaining()

    async def is_rate_limited(self) -> bool:
        """Check if currently rate limited.

        Returns:
            True if rate limited, False otherwise
        """
        return await self._rate_limiter.is_limited()
