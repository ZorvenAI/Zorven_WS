"""
Sync Orchestrator Service.

Coordinates document synchronization between GCS and Vertex AI Discovery Engine.
Implements the Hexagonal Architecture pattern with dependency injection.
"""

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from rag_index.domain.exceptions import (
    DocumentFetchError,
    DocumentNotFoundError,
    RateLimitExceededError,
    SyncError,
    SyncValidationError,
)
from rag_index.domain.models import (
    RateLimitStatus,
    SyncAction,
    SyncEvent,
    SyncResult,
    SyncStatus,
    SyncStatusRecord,
)
from rag_index.ports.gcs_port import GCSPort
from rag_index.ports.kafka_port import KafkaPort
from rag_index.ports.redis_port import RedisPort
from rag_index.ports.vertex_ai_port import VertexAIPort

logger = logging.getLogger(__name__)


@dataclass
class OrchestratorConfig:
    """Configuration for the SyncOrchestrator.

    Attributes:
        max_retries: Maximum retry attempts for transient failures
        retry_delay_seconds: Base delay between retries (exponential backoff)
        status_ttl_seconds: TTL for status records in Redis
        enable_dlq: Whether to publish failed events to DLQ
        dlq_topic: Topic name for dead letter queue
        completed_topic: Topic name for completed events
    """

    max_retries: int = 3
    retry_delay_seconds: float = 1.0
    status_ttl_seconds: int = 86400  # 24 hours
    enable_dlq: bool = True
    dlq_topic: str = "rag-sync-dlq"
    completed_topic: str = "rag-sync-completed"


class SyncOrchestrator:
    """Orchestrates document synchronization operations.

    This is the core service layer that coordinates all adapters to
    process sync events. It follows the Hexagonal Architecture pattern
    with ports (interfaces) injected as dependencies.

    The orchestrator handles:
    - UPSERT: Fetch document from GCS, index in Vertex AI
    - DELETE: Remove document from Vertex AI index

    It also manages:
    - Status tracking in Redis
    - Event publishing to Kafka (completed/DLQ)
    - Retry logic with exponential backoff
    - Rate limit awareness

    Example:
        orchestrator = SyncOrchestrator(
            vertex_ai_port=vertex_adapter,
            gcs_port=gcs_adapter,
            redis_port=redis_adapter,
            kafka_port=kafka_adapter,
        )

        result = await orchestrator.process_event(sync_event)
    """

    def __init__(
        self,
        vertex_ai_port: VertexAIPort,
        gcs_port: GCSPort,
        redis_port: RedisPort,
        kafka_port: Optional[KafkaPort] = None,
        config: Optional[OrchestratorConfig] = None,
    ):
        """Initialize the orchestrator with injected ports.

        Args:
            vertex_ai_port: Port for Vertex AI Discovery Engine operations
            gcs_port: Port for Google Cloud Storage operations
            redis_port: Port for Redis status tracking
            kafka_port: Optional port for event publishing
            config: Optional configuration overrides
        """
        self._vertex_ai = vertex_ai_port
        self._gcs = gcs_port
        self._redis = redis_port
        self._kafka = kafka_port
        self._config = config or OrchestratorConfig()

        logger.info(
            "SyncOrchestrator initialized",
            extra={
                "max_retries": self._config.max_retries,
                "enable_dlq": self._config.enable_dlq,
            },
        )

    async def process_event(self, event: SyncEvent) -> SyncResult:
        """Process a sync event.

        Main entry point for processing document sync events.
        Handles both UPSERT and DELETE actions with proper
        error handling and status tracking.

        Args:
            event: The sync event to process

        Returns:
            SyncResult with processing outcome

        Raises:
            SyncValidationError: If event validation fails
            SyncError: If processing fails after all retries
        """
        start_time = time.time()

        logger.info(
            "Processing sync event",
            extra={
                "event_id": str(event.event_id),
                "trace_id": event.trace_id,
                "action": event.action.value,
                "file_id": event.file_id,
                "tenant_id": event.tenant_id,
            },
        )

        # Validate event
        self._validate_event(event)

        # Update status to IN_PROGRESS
        await self._update_status(event, SyncStatus.IN_PROGRESS)

        try:
            # Route to appropriate handler
            if event.action == SyncAction.UPSERT:
                result = await self._handle_upsert(event)
            else:
                result = await self._handle_delete(event)

            # Calculate processing time
            processing_time_ms = int((time.time() - start_time) * 1000)
            result = SyncResult(
                event_id=result.event_id,
                trace_id=result.trace_id,
                status=result.status,
                operation_id=result.operation_id,
                processing_time_ms=processing_time_ms,
            )

            # Update status to COMPLETED
            await self._update_status(event, SyncStatus.COMPLETED, result)

            # Publish completion event
            await self._publish_completed(event, result)

            logger.info(
                "Sync event processed successfully",
                extra={
                    "event_id": str(event.event_id),
                    "trace_id": event.trace_id,
                    "processing_time_ms": processing_time_ms,
                },
            )

            return result

        except RateLimitExceededError as e:
            # Don't retry rate limit errors - let caller handle
            logger.warning(
                "Rate limit exceeded",
                extra={
                    "event_id": str(event.event_id),
                    "trace_id": event.trace_id,
                    "limit": e.limit,
                    "current_count": e.current_count,
                },
            )

            processing_time_ms = int((time.time() - start_time) * 1000)
            result = SyncResult(
                event_id=event.event_id,
                trace_id=event.trace_id,
                status="FAILED",
                error_message=str(e),
                processing_time_ms=processing_time_ms,
            )

            await self._update_status(event, SyncStatus.FAILED, result)
            raise

        except Exception as e:
            logger.exception(
                "Sync event processing failed",
                extra={
                    "event_id": str(event.event_id),
                    "trace_id": event.trace_id,
                    "error": str(e),
                },
            )

            processing_time_ms = int((time.time() - start_time) * 1000)
            result = SyncResult(
                event_id=event.event_id,
                trace_id=event.trace_id,
                status="FAILED",
                error_message=str(e),
                processing_time_ms=processing_time_ms,
            )

            await self._update_status(event, SyncStatus.FAILED, result)

            # Publish to DLQ
            await self._publish_dlq(event, result, e)

            raise SyncError(
                message=f"Failed to process sync event: {e}",
                event_id=str(event.event_id),
                tenant_id=event.tenant_id,
            ) from e

    async def process_inline_document(
        self,
        event: SyncEvent,
        document_content: dict[str, Any],
    ) -> SyncResult:
        """Process an inline document (no GCS fetch needed).

        Used for DB-to-RAG sync where content is already structured
        in memory. Skips GCS fetch while reusing status tracking,
        rate limiting, and DLQ infrastructure.

        Args:
            event: The sync event (processed_gcs_uri not required)
            document_content: The document dict to upsert

        Returns:
            SyncResult with processing outcome

        Raises:
            SyncValidationError: If event validation fails
            SyncError: If processing fails
        """
        start_time = time.time()

        logger.info(
            "Processing inline document sync",
            extra={
                "event_id": str(event.event_id),
                "trace_id": event.trace_id,
                "file_id": event.file_id,
                "tenant_id": event.tenant_id,
            },
        )

        self._validate_inline_event(event)
        await self._update_status(event, SyncStatus.IN_PROGRESS)

        try:
            result = await self._vertex_ai.upsert_document(event, document_content)

            processing_time_ms = int((time.time() - start_time) * 1000)
            result = SyncResult(
                event_id=result.event_id,
                trace_id=result.trace_id,
                status=result.status,
                operation_id=result.operation_id,
                processing_time_ms=processing_time_ms,
            )

            await self._update_status(event, SyncStatus.COMPLETED, result)
            await self._publish_completed(event, result)

            logger.info(
                "Inline document synced successfully",
                extra={
                    "event_id": str(event.event_id),
                    "trace_id": event.trace_id,
                    "processing_time_ms": processing_time_ms,
                },
            )

            return result

        except RateLimitExceededError as e:
            logger.warning(
                "Rate limit exceeded for inline sync",
                extra={
                    "event_id": str(event.event_id),
                    "trace_id": event.trace_id,
                    "limit": e.limit,
                    "current_count": e.current_count,
                },
            )

            processing_time_ms = int((time.time() - start_time) * 1000)
            result = SyncResult(
                event_id=event.event_id,
                trace_id=event.trace_id,
                status="FAILED",
                error_message=str(e),
                processing_time_ms=processing_time_ms,
            )

            await self._update_status(event, SyncStatus.FAILED, result)
            raise

        except Exception as e:
            logger.exception(
                "Inline document sync failed",
                extra={
                    "event_id": str(event.event_id),
                    "trace_id": event.trace_id,
                    "error": str(e),
                },
            )

            processing_time_ms = int((time.time() - start_time) * 1000)
            result = SyncResult(
                event_id=event.event_id,
                trace_id=event.trace_id,
                status="FAILED",
                error_message=str(e),
                processing_time_ms=processing_time_ms,
            )

            await self._update_status(event, SyncStatus.FAILED, result)
            await self._publish_dlq(event, result, e)

            raise SyncError(
                message=f"Failed to process inline document: {e}",
                event_id=str(event.event_id),
                tenant_id=event.tenant_id,
            ) from e

    async def _handle_upsert(self, event: SyncEvent) -> SyncResult:
        """Handle UPSERT action.

        1. Fetch document content from GCS
        2. Index document in Vertex AI

        Args:
            event: The sync event

        Returns:
            SyncResult from Vertex AI operation
        """
        logger.debug(
            "Handling UPSERT",
            extra={
                "event_id": str(event.event_id),
                "gcs_uri": event.processed_gcs_uri,
            },
        )

        # Fetch document from GCS
        try:
            document = await self._gcs.read_document(event.processed_gcs_uri)
        except DocumentNotFoundError:
            logger.warning(
                "Document not found in GCS",
                extra={
                    "event_id": str(event.event_id),
                    "gcs_uri": event.processed_gcs_uri,
                },
            )
            raise
        except Exception as e:
            raise DocumentFetchError(
                f"Failed to fetch document from GCS: {e}",
                gcs_uri=event.processed_gcs_uri,
            ) from e

        # Index in Vertex AI
        result = await self._vertex_ai.upsert_document(event, document)

        return result

    async def _handle_delete(self, event: SyncEvent) -> SyncResult:
        """Handle DELETE action.

        Remove document from Vertex AI index.

        Args:
            event: The sync event

        Returns:
            SyncResult from Vertex AI operation
        """
        logger.debug(
            "Handling DELETE",
            extra={
                "event_id": str(event.event_id),
                "file_id": event.file_id,
            },
        )

        result = await self._vertex_ai.delete_document(event)

        return result

    def _validate_event(self, event: SyncEvent) -> None:
        """Validate sync event.

        Args:
            event: The event to validate

        Raises:
            SyncValidationError: If validation fails
        """
        if not event.tenant_id:
            raise SyncValidationError("tenant_id is required")

        if not event.file_id:
            raise SyncValidationError("file_id is required")

        if event.action == SyncAction.UPSERT and not event.processed_gcs_uri:
            raise SyncValidationError("processed_gcs_uri is required for UPSERT")

    def _validate_inline_event(self, event: SyncEvent) -> None:
        """Validate inline sync event (no GCS URI required).

        Args:
            event: The event to validate

        Raises:
            SyncValidationError: If validation fails
        """
        if not event.tenant_id:
            raise SyncValidationError("tenant_id is required")

        if not event.file_id:
            raise SyncValidationError("file_id is required")

    async def _update_status(
        self,
        event: SyncEvent,
        status: SyncStatus,
        result: Optional[SyncResult] = None,
    ) -> None:
        """Update event status in Redis.

        Args:
            event: The sync event
            status: New status
            result: Optional result if completed/failed
        """
        try:
            record = SyncStatusRecord(
                event_id=event.event_id,
                trace_id=event.trace_id,
                tenant_id=event.tenant_id,
                file_id=event.file_id,
                action=event.action,
                status=status,
                last_updated=datetime.now(timezone.utc),
                error_message=result.error_message if result else None,
            )

            await self._redis.set_sync_status(
                event_id=str(event.event_id),
                status=record,
                ttl_seconds=self._config.status_ttl_seconds,
            )

            logger.debug(
                "Status updated",
                extra={
                    "event_id": str(event.event_id),
                    "status": status.value,
                },
            )
        except Exception as e:
            # Status update failure is non-fatal
            logger.warning(
                "Failed to update status in Redis",
                extra={
                    "event_id": str(event.event_id),
                    "error": str(e),
                },
            )

    async def _publish_completed(
        self,
        event: SyncEvent,
        result: SyncResult,
    ) -> None:
        """Publish completion event to Kafka.

        Args:
            event: The original sync event
            result: The processing result
        """
        if not self._kafka:
            return

        try:
            await self._kafka.publish(
                topic=self._config.completed_topic,
                key=event.tenant_id,
                value={
                    "event_id": str(event.event_id),
                    "trace_id": event.trace_id,
                    "tenant_id": event.tenant_id,
                    "file_id": event.file_id,
                    "action": event.action.value,
                    "status": result.status,
                    "operation_id": result.operation_id,
                    "processing_time_ms": result.processing_time_ms,
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                },
            )

            logger.debug(
                "Published completion event",
                extra={
                    "event_id": str(event.event_id),
                    "topic": self._config.completed_topic,
                },
            )
        except Exception as e:
            # Publishing failure is non-fatal
            logger.warning(
                "Failed to publish completion event",
                extra={
                    "event_id": str(event.event_id),
                    "error": str(e),
                },
            )

    async def _publish_dlq(
        self,
        event: SyncEvent,
        result: SyncResult,
        error: Exception,
    ) -> None:
        """Publish failed event to DLQ.

        Args:
            event: The original sync event
            result: The failed result
            error: The exception that caused failure
        """
        if not self._kafka or not self._config.enable_dlq:
            return

        try:
            await self._kafka.publish(
                topic=self._config.dlq_topic,
                key=event.tenant_id,
                value={
                    "original_event": event.to_dict(),
                    "error_type": type(error).__name__,
                    "error_message": str(error),
                    "trace_id": event.trace_id,
                    "failed_at": datetime.now(timezone.utc).isoformat(),
                    "processing_time_ms": result.processing_time_ms,
                },
            )

            logger.info(
                "Published to DLQ",
                extra={
                    "event_id": str(event.event_id),
                    "topic": self._config.dlq_topic,
                },
            )
        except Exception as e:
            # DLQ publishing failure is logged but non-fatal
            logger.error(
                "Failed to publish to DLQ",
                extra={
                    "event_id": str(event.event_id),
                    "error": str(e),
                },
            )

    async def get_status(self, event_id: str) -> Optional[SyncStatusRecord]:
        """Get the status of a sync event.

        Args:
            event_id: The event ID to look up

        Returns:
            SyncStatusRecord if found, None otherwise
        """
        return await self._redis.get_sync_status(event_id)

    async def get_rate_limit_status(self) -> Optional[RateLimitStatus]:
        """Get current rate limit status.

        Returns:
            RateLimitStatus if the Vertex AI port supports it
        """
        if hasattr(self._vertex_ai, "get_rate_limit_status"):
            return await self._vertex_ai.get_rate_limit_status()
        return None

    async def check_health(self) -> dict[str, Any]:
        """Check health of all connected services.

        Returns:
            Dictionary with health status of each service
        """
        health = {
            "vertex_ai": False,
            "redis": False,
            "gcs": False,
            "kafka": False,
        }

        # Check Vertex AI
        try:
            health["vertex_ai"] = await self._vertex_ai.check_connection()
        except Exception as e:
            logger.warning(f"Vertex AI health check failed: {e}")

        # Check Redis
        try:
            health["redis"] = await self._redis.check_connection()
        except Exception as e:
            logger.warning(f"Redis health check failed: {e}")

        # Check GCS
        try:
            health["gcs"] = await self._gcs.check_connection()
        except Exception as e:
            logger.warning(f"GCS health check failed: {e}")

        # Check Kafka
        if self._kafka:
            try:
                health["kafka"] = await self._kafka.check_connection()
            except Exception as e:
                logger.warning(f"Kafka health check failed: {e}")
        else:
            health["kafka"] = None  # Not configured

        return health
