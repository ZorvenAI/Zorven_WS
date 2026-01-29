"""
Ingestion Service - The main orchestrator for the data ingestion pipeline.

This service coordinates the flow:
1. Validate incoming event
2. Check for duplicates (Redis)
3. Verify file exists in landing zone (GCS)
4. Generate destination path
5. Move file to raw storage (GCS)
6. Update status (Redis)
7. Publish output event (Kafka)
"""

import logging
import time
from datetime import datetime
from typing import Optional
from uuid import UUID

from data_ingestion.domain.models import (
    IngestionEvent,
    ProcessedEvent,
    ProcessingStatus,
)
from data_ingestion.domain.exceptions import (
    DuplicateEventError,
    FileNotFoundInLandingError,
    StorageOperationError,
    CacheOperationError,
    EventPublishError,
    RetryableError,
    NonRetryableError,
)
from data_ingestion.domain.path_generator import generate_raw_path
from data_ingestion.ports.storage_port import StoragePort
from data_ingestion.ports.cache_port import CachePort
from data_ingestion.ports.event_port import EventProducerPort


logger = logging.getLogger(__name__)


class IngestionService:
    """
    Main orchestrator for the data ingestion pipeline.

    Uses dependency injection for all external dependencies (ports).
    This allows for easy testing with mock implementations.
    """

    def __init__(
        self,
        storage: StoragePort,
        cache: CachePort,
        producer: EventProducerPort,
        output_topic: str,
        dlq_topic: str,
        dedupe_ttl_seconds: int = 3600,
        status_ttl_seconds: int = 604800,
        max_retries: int = 3,
        retry_backoff_seconds: float = 1.0,
    ):
        """
        Initialize the ingestion service.

        Args:
            storage: Storage port implementation (GCS)
            cache: Cache port implementation (Redis)
            producer: Event producer port implementation (Kafka)
            output_topic: Kafka topic to publish successful events
            dlq_topic: Kafka topic for dead letter queue
            dedupe_ttl_seconds: TTL for deduplication keys (default 1 hour)
            status_ttl_seconds: TTL for status keys (default 7 days)
            max_retries: Maximum retry attempts for transient errors
            retry_backoff_seconds: Initial backoff delay for retries
        """
        self.storage = storage
        self.cache = cache
        self.producer = producer
        self.output_topic = output_topic
        self.dlq_topic = dlq_topic
        self.dedupe_ttl_seconds = dedupe_ttl_seconds
        self.status_ttl_seconds = status_ttl_seconds
        self.max_retries = max_retries
        self.retry_backoff_seconds = retry_backoff_seconds

    def process_event(self, event: IngestionEvent) -> ProcessedEvent:
        """
        Process a single ingestion event.

        This is the main entry point for the ingestion pipeline.

        Args:
            event: The ingestion event to process

        Returns:
            ProcessedEvent with the result of processing

        Raises:
            DuplicateEventError: If event was already processed (should skip)
            FileNotFoundInLandingError: If source file doesn't exist (send to DLQ)
            RetryableError: If a transient error occurred (should retry)
            NonRetryableError: If a permanent error occurred (send to DLQ)
        """
        start_time = time.time()
        trace_id = event.trace_id
        event_id = str(event.event_id)

        logger.info(
            "Processing event",
            extra={
                "trace_id": str(trace_id),
                "event_id": event_id,
                "tenant_id": event.tenant_id,
                "file_path": event.file_path,
            },
        )

        try:
            # Step 1: Check for duplicate
            self._check_duplicate(event_id, trace_id)

            # Step 2: Update status to VALIDATING
            self._update_status(trace_id, ProcessingStatus.VALIDATING)

            # Step 3: Validate file exists in landing zone
            self._validate_file_exists(event.file_path, trace_id)

            # Step 4: Update status to MOVING
            self._update_status(trace_id, ProcessingStatus.MOVING)

            # Step 5: Generate destination path and move file
            destination_path = self._move_file_to_raw(event, trace_id)

            # Step 6: Mark as processed (deduplication)
            self._mark_processed(event_id, trace_id)

            # Step 7: Update status to RAW_STORED
            self._update_status(
                trace_id,
                ProcessingStatus.RAW_STORED,
                metadata={"destination_path": destination_path},
            )

            # Step 8: Create and publish output event
            processing_duration_ms = int((time.time() - start_time) * 1000)
            processed_event = ProcessedEvent(
                event_id=event.event_id,
                trace_id=trace_id,
                timestamp=datetime.utcnow(),
                tenant_id=event.tenant_id,
                source_path=event.file_path,
                destination_path=destination_path,
                status=ProcessingStatus.RAW_STORED,
                processing_duration_ms=processing_duration_ms,
            )

            self._publish_output_event(processed_event, trace_id)

            logger.info(
                "Event processed successfully",
                extra={
                    "trace_id": str(trace_id),
                    "event_id": event_id,
                    "destination_path": destination_path,
                    "duration_ms": processing_duration_ms,
                },
            )

            return processed_event

        except DuplicateEventError:
            # Expected case - just re-raise, don't log as error
            logger.debug(
                "Skipping duplicate event",
                extra={"trace_id": str(trace_id), "event_id": event_id},
            )
            raise

        except FileNotFoundInLandingError as e:
            # Permanent error - file doesn't exist
            self._update_status(
                trace_id,
                ProcessingStatus.FAILED,
                metadata={"error": str(e)},
            )
            raise NonRetryableError(
                cause=e,
                reason="File not found in landing zone",
                trace_id=trace_id,
            )

        except (StorageOperationError, CacheOperationError) as e:
            # Potentially transient errors
            if getattr(e, "is_retryable", True):
                raise RetryableError(
                    cause=e,
                    retry_count=0,
                    max_retries=self.max_retries,
                    trace_id=trace_id,
                )
            else:
                self._update_status(
                    trace_id,
                    ProcessingStatus.FAILED,
                    metadata={"error": str(e)},
                )
                raise NonRetryableError(cause=e, trace_id=trace_id)

        except EventPublishError as e:
            # Kafka publish failed - retryable
            raise RetryableError(
                cause=e,
                retry_count=0,
                max_retries=self.max_retries,
                trace_id=trace_id,
            )

        except Exception as e:
            # Unexpected error
            logger.exception(
                "Unexpected error processing event",
                extra={"trace_id": str(trace_id), "event_id": event_id},
            )
            self._update_status(
                trace_id,
                ProcessingStatus.FAILED,
                metadata={"error": str(e), "error_type": type(e).__name__},
            )
            raise NonRetryableError(
                cause=e,
                reason="Unexpected error",
                trace_id=trace_id,
            )

    def process_event_with_retry(
        self,
        event: IngestionEvent,
        retry_count: int = 0,
    ) -> Optional[ProcessedEvent]:
        """
        Process an event with automatic retry for transient errors.

        Args:
            event: The ingestion event to process
            retry_count: Current retry attempt (0-based)

        Returns:
            ProcessedEvent if successful, None if duplicate

        Raises:
            NonRetryableError: If a permanent error occurred
            RetryableError: If max retries exceeded
        """
        try:
            return self.process_event(event)

        except DuplicateEventError:
            # Duplicate - return None to signal skip
            return None

        except RetryableError:
            if retry_count < self.max_retries:
                # Calculate exponential backoff
                delay = self.retry_backoff_seconds * (2**retry_count)
                logger.warning(
                    f"Retrying event after {delay}s",
                    extra={
                        "trace_id": str(event.trace_id),
                        "retry_count": retry_count + 1,
                        "max_retries": self.max_retries,
                    },
                )
                time.sleep(delay)
                return self.process_event_with_retry(event, retry_count + 1)
            else:
                # Max retries exceeded
                logger.error(
                    "Max retries exceeded",
                    extra={
                        "trace_id": str(event.trace_id),
                        "retry_count": retry_count,
                    },
                )
                raise

    def _check_duplicate(self, event_id: str, trace_id: UUID) -> None:
        """Check if event has already been processed."""
        try:
            if self.cache.is_duplicate(event_id):
                raise DuplicateEventError(
                    event_id=UUID(event_id),
                    trace_id=trace_id,
                )
        except CacheOperationError:
            # Cache error during dedup check - log and continue
            # Better to potentially reprocess than to fail
            logger.warning(
                "Cache error during dedup check, continuing",
                extra={"trace_id": str(trace_id), "event_id": event_id},
            )

    def _validate_file_exists(self, file_path: str, trace_id: UUID) -> None:
        """Validate that the source file exists in landing zone."""
        if not self.storage.check_exists(file_path):
            raise FileNotFoundInLandingError(
                file_path=file_path,
                trace_id=trace_id,
            )

    def _move_file_to_raw(self, event: IngestionEvent, trace_id: UUID) -> str:
        """Move file from landing zone to raw storage."""
        # Generate destination path
        destination_path = generate_raw_path(
            tenant_id=event.tenant_id,
            source_path=event.file_path,
            timestamp=event.timestamp,
        )

        # Move the file
        result_path = self.storage.move_file(
            source_path=event.file_path,
            destination_path=destination_path,
        )

        logger.debug(
            "File moved successfully",
            extra={
                "trace_id": str(trace_id),
                "source": event.file_path,
                "destination": result_path,
            },
        )

        return result_path

    def _mark_processed(self, event_id: str, trace_id: UUID) -> None:
        """Mark event as processed for deduplication."""
        try:
            self.cache.mark_processed(event_id, ttl_seconds=self.dedupe_ttl_seconds)
        except CacheOperationError as e:
            # Log but don't fail - dedup is best-effort
            logger.warning(
                "Failed to mark event as processed",
                extra={
                    "trace_id": str(trace_id),
                    "event_id": event_id,
                    "error": str(e),
                },
            )

    def _update_status(
        self,
        trace_id: UUID,
        status: ProcessingStatus,
        metadata: Optional[dict] = None,
    ) -> None:
        """Update processing status in cache."""
        try:
            self.cache.update_status(
                trace_id=str(trace_id),
                status=status.value,
                ttl_seconds=self.status_ttl_seconds,
                metadata=metadata,
            )
        except CacheOperationError as e:
            # Log but don't fail - status tracking is not critical
            logger.warning(
                "Failed to update status",
                extra={
                    "trace_id": str(trace_id),
                    "status": status.value,
                    "error": str(e),
                },
            )

    def _publish_output_event(
        self,
        processed_event: ProcessedEvent,
        trace_id: UUID,
    ) -> None:
        """Publish the processed event to the output topic."""
        self.producer.publish(
            topic=self.output_topic,
            event=processed_event,
            key=processed_event.tenant_id,
        )
        logger.debug(
            "Output event published",
            extra={
                "trace_id": str(trace_id),
                "topic": self.output_topic,
            },
        )

    def send_to_dlq(
        self,
        original_event: dict,
        error: Exception,
        source_topic: str,
    ) -> None:
        """
        Send a failed event to the Dead Letter Queue.

        Args:
            original_event: The original event that failed
            error: The exception that caused the failure
            source_topic: The topic the event came from
        """
        try:
            self.producer.publish_to_dlq(
                original_event=original_event,
                error=error,
                source_topic=source_topic,
            )
            logger.info(
                "Event sent to DLQ",
                extra={
                    "source_topic": source_topic,
                    "error_type": type(error).__name__,
                },
            )
        except EventPublishError as e:
            logger.error(
                "Failed to send event to DLQ",
                extra={"error": str(e)},
            )
            raise
