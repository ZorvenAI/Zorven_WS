"""
Celery Tasks for Media Curation.

Async task processing for the curation pipeline.
"""

import asyncio
import logging
from typing import Optional
from uuid import UUID, uuid4
from datetime import datetime, timezone

from celery import shared_task

from media_curation.factory import (
    get_curation_service,
    create_kafka_producer,
    create_cache_adapter,
)
from media_curation.domain.models import (
    CurationEvent,
    ContentType,
)
from media_curation.domain.exceptions import (
    RetryableError,
    NonRetryableError,
    DuplicateEventError,
)


logger = logging.getLogger(__name__)


def _run_async(coro):
    """Helper to run async coroutines in sync context."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _detect_content_type(mime_type: str) -> ContentType:
    """Detect ContentType from MIME type string."""
    if mime_type.startswith("video/"):
        return ContentType.VIDEO
    elif mime_type.startswith("audio/"):
        return ContentType.AUDIO
    elif mime_type.startswith("image/"):
        return ContentType.IMAGE
    else:
        return ContentType.DOCUMENT


logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    name="media_curation.process_curation_event",
    autoretry_for=(RetryableError,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=3,
    acks_late=True,
    reject_on_worker_lost=True,
    queue="curation",
)
def process_curation_event(
    self,
    event_id: str,
    trace_id: str,
    tenant_id: str,
    source_path: str,
    file_type: str,
    brand_id: Optional[str] = None,
    file_size_bytes: int = 0,
    metadata: Optional[dict] = None,
) -> dict:
    """
    Process a single curation event asynchronously.

    This task:
    1. Loads tenant configuration from Redis
    2. Routes to appropriate processor based on MIME type
    3. Extracts text/metadata from content
    4. Redacts PII if enabled
    5. Publishes curated document to Kafka

    Args:
        event_id: Unique event identifier
        trace_id: Trace ID for distributed tracing
        tenant_id: Tenant identifier
        source_path: GCS path to source file
        file_type: MIME type of the file
        brand_id: Optional brand identifier
        file_size_bytes: File size in bytes
        metadata: Optional additional metadata

    Returns:
        Dict with processing result

    Raises:
        RetryableError: Triggers Celery retry
    """
    logger.info(
        "Processing curation event via Celery",
        extra={
            "event_id": event_id,
            "trace_id": trace_id,
            "tenant_id": tenant_id,
            "task_id": self.request.id,
        },
    )

    try:
        # Build CurationEvent
        event = CurationEvent(
            event_id=UUID(event_id),
            trace_id=UUID(trace_id),
            timestamp=datetime.now(timezone.utc),
            tenant_id=UUID(tenant_id) if isinstance(tenant_id, str) else tenant_id,
            file_id=uuid4(),  # Generate file ID
            raw_gcs_uri=source_path,
            mime_type=file_type,
            content_type=_detect_content_type(file_type),
            source_service="api",
            metadata=metadata or {},
        )

        # Get curation service and process
        service = get_curation_service()

        # Process the event (CurationService.process_event is sync)
        result = service.process_event(event)

        logger.info(
            "Curation event processed successfully",
            extra={
                "event_id": event_id,
                "trace_id": trace_id,
                "task_id": self.request.id,
                "document_id": str(result.document_id) if result else None,
            },
        )

        return {
            "status": "success",
            "event_id": event_id,
            "trace_id": trace_id,
            "document_id": str(result.document_id) if result else None,
            "output_uri": result.output_gcs_uri if result else None,
        }

    except DuplicateEventError:
        logger.info("Skipping duplicate event", extra={"event_id": event_id})
        return {
            "status": "skipped",
            "event_id": event_id,
            "reason": "duplicate",
        }

    except NonRetryableError as e:
        logger.error(
            "Non-retryable error processing curation event",
            extra={"event_id": event_id, "error": str(e)},
        )
        # Send to DLQ via Kafka producer
        try:
            producer = create_kafka_producer()
            event = CurationEvent(
                event_id=UUID(event_id),
                trace_id=UUID(trace_id),
                timestamp=datetime.now(timezone.utc),
                tenant_id=UUID(tenant_id) if isinstance(tenant_id, str) else tenant_id,
                file_id=uuid4(),
                raw_gcs_uri=source_path,
                mime_type=file_type,
                content_type=_detect_content_type(file_type),
                source_service="api",
                metadata=metadata or {},
            )
            _run_async(
                producer.publish_to_dlq(event, e, retry_count=self.request.retries)
            )
        except Exception as dlq_error:
            logger.error(f"Failed to send to DLQ: {dlq_error}")

        return {
            "status": "failed",
            "event_id": event_id,
            "error": str(e),
            "sent_to_dlq": True,
        }

    except RetryableError:
        # Let Celery handle the retry
        raise

    except Exception:
        logger.exception(
            "Unexpected error processing curation event",
            extra={"event_id": event_id},
        )
        raise


@shared_task(
    bind=True,
    name="media_curation.process_batch",
    acks_late=True,
    queue="curation",
)
def process_batch(self, events: list[dict]) -> dict:
    """
    Process a batch of curation events.

    Args:
        events: List of event dicts

    Returns:
        Dict with batch processing results
    """
    logger.info(
        f"Processing batch of {len(events)} curation events",
        extra={"task_id": self.request.id, "batch_size": len(events)},
    )

    results = {
        "total": len(events),
        "success": 0,
        "skipped": 0,
        "failed": 0,
        "details": [],
    }

    for event_dict in events:
        try:
            result = process_curation_event(
                event_id=event_dict["event_id"],
                trace_id=event_dict["trace_id"],
                tenant_id=event_dict["tenant_id"],
                source_path=event_dict["source_path"],
                file_type=event_dict["file_type"],
                brand_id=event_dict.get("brand_id"),
                file_size_bytes=event_dict.get("file_size_bytes", 0),
                metadata=event_dict.get("metadata"),
            )

            if result["status"] == "success":
                results["success"] += 1
            elif result["status"] == "skipped":
                results["skipped"] += 1
            else:
                results["failed"] += 1

            results["details"].append(result)

        except Exception as e:
            results["failed"] += 1
            results["details"].append(
                {
                    "status": "failed",
                    "event_id": event_dict.get("event_id"),
                    "error": str(e),
                }
            )

    logger.info(
        "Batch curation processing complete",
        extra={
            "total": results["total"],
            "success": results["success"],
            "failed": results["failed"],
        },
    )

    return results


@shared_task(
    bind=True,
    name="media_curation.check_status",
    queue="curation",
)
def check_status(self, trace_id: str) -> Optional[dict]:
    """
    Check the curation status of an event by trace_id.

    Args:
        trace_id: The trace ID to look up

    Returns:
        Status dict or None if not found
    """
    cache = create_cache_adapter()
    status_record = _run_async(cache.get_status(trace_id))

    if status_record:
        return {
            "trace_id": str(status_record.trace_id),
            "event_id": str(status_record.event_id),
            "status": status_record.status.value,
            "message": status_record.message,
            "output_gcs_uri": status_record.output_gcs_uri,
            "updated_at": status_record.updated_at.isoformat(),
        }

    return None


@shared_task(
    bind=True,
    name="media_curation.reprocess_from_dlq",
    acks_late=True,
    queue="curation",
)
def reprocess_from_dlq(self, dlq_message: dict) -> dict:
    """
    Reprocess an event from the Dead Letter Queue.

    Args:
        dlq_message: DLQ message containing original_event and error info

    Returns:
        Dict with reprocessing result
    """
    original_event = dlq_message.get("original_event", {})
    event_id = original_event.get("event_id")

    logger.info(
        "Reprocessing curation event from DLQ",
        extra={"event_id": event_id, "task_id": self.request.id},
    )

    try:
        return process_curation_event(
            event_id=original_event["event_id"],
            trace_id=original_event["trace_id"],
            tenant_id=original_event["tenant_id"],
            source_path=original_event["source_path"],
            file_type=original_event["file_type"],
            brand_id=original_event.get("brand_id"),
            file_size_bytes=original_event.get("file_size_bytes", 0),
            metadata=original_event.get("metadata"),
        )
    except Exception as e:
        logger.error(
            "Failed to reprocess DLQ curation event",
            extra={"event_id": event_id, "error": str(e)},
        )
        raise
