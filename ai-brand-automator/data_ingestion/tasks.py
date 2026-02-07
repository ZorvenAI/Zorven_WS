"""
Celery tasks for data ingestion pipeline.

These tasks allow processing ingestion events asynchronously
via the existing Celery infrastructure.
"""

import logging
from typing import Optional
from uuid import UUID, uuid4
from datetime import datetime

from celery import shared_task

from data_ingestion.factory import create_ingestion_service, get_data_ingestion_config
from data_ingestion.domain.models import IngestionEvent, EventSource
from data_ingestion.domain.exceptions import (
    DuplicateEventError,
    NonRetryableError,
    RetryableError,
)


logger = logging.getLogger(__name__)


from data_ingestion.domain.path_generator import extract_object_path as _extract_gcs_path  # noqa: E402


def _update_asset_after_ingestion(
    asset_id: str,
    status: str,
    error_msg: str = "",
    new_gcs_path: str = "",
) -> bool:
    """Update BrandAsset pipeline_status and gcs_path after ingestion.

    Args:
        asset_id: The asset ID (integer as string)
        status: The new pipeline status (ingested, failed)
        error_msg: Error message if status is failed
        new_gcs_path: New GCS path after file was moved (gs:// URI)

    Returns:
        True if update succeeded, False otherwise
    """
    from django.db import close_old_connections
    from onboarding.models import BrandAsset

    for attempt in range(2):
        try:
            if attempt > 0:
                close_old_connections()

            try:
                aid = int(asset_id)
                asset = BrandAsset.objects.filter(id=aid).first()
            except (ValueError, TypeError):
                asset = None

            if asset:
                asset.pipeline_status = status
                update_fields = ["pipeline_status"]
                if new_gcs_path:
                    asset.gcs_path = _extract_gcs_path(new_gcs_path)
                    update_fields.append("gcs_path")
                if status == "ingested":
                    asset.pipeline_error = ""
                    update_fields.append("pipeline_error")
                elif error_msg:
                    asset.pipeline_error = error_msg
                    update_fields.append("pipeline_error")
                asset.save(update_fields=update_fields)
                logger.info(
                    "Updated BrandAsset %s: status=%s, gcs_path=%s",
                    asset.id,
                    status,
                    asset.gcs_path,
                )
                return True
            else:
                logger.warning("BrandAsset not found for asset_id: %s", asset_id)
                return False

        except Exception:
            if attempt == 0:
                logger.warning(
                    "DB error updating BrandAsset (will retry): %s",
                    asset_id,
                    exc_info=True,
                )
                continue
            logger.exception("Failed to update BrandAsset status after retry")
            return False

    return False


@shared_task(
    bind=True,
    name="data_ingestion.process_ingestion_event",
    autoretry_for=(RetryableError,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=3,
    acks_late=True,
    reject_on_worker_lost=True,
)
def process_ingestion_event(
    self,
    event_id: str,
    tenant_id: str,
    file_path: str,
    file_type: Optional[str] = None,
    timestamp: Optional[str] = None,
    source: Optional[str] = None,
    trace_id: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> dict:
    """
    Process a single ingestion event asynchronously.

    This task can be called directly or triggered by a Kafka consumer
    to leverage Celery's retry and monitoring capabilities.

    Args:
        event_id: Unique event identifier
        tenant_id: Tenant identifier
        file_path: GCS path to the file in landing zone
        file_type: MIME type of the file (default: application/octet-stream)
        timestamp: ISO format timestamp (default: now)
        source: Event source (API, GCS_TRIGGER, BATCH, MANUAL)
        trace_id: Optional trace ID for distributed tracing
        metadata: Optional additional metadata

    Returns:
        Dict with processing result

    Raises:
        RetryableError: Triggers Celery retry
    """
    logger.info(
        "Processing ingestion event via Celery",
        extra={
            "event_id": event_id,
            "tenant_id": tenant_id,
            "task_id": self.request.id,
        },
    )

    try:
        # Build IngestionEvent
        event = IngestionEvent(
            event_id=UUID(event_id),
            tenant_id=tenant_id,
            file_path=file_path,
            file_type=file_type or "application/octet-stream",
            timestamp=datetime.fromisoformat(timestamp)
            if timestamp
            else datetime.utcnow(),
            source=EventSource(source) if source else EventSource.FRONTEND_UPLOAD,
            trace_id=UUID(trace_id) if trace_id else uuid4(),
            metadata=metadata,
        )

        # Create service and process
        service = create_ingestion_service()
        result = service.process_event(event)

        # Update BrandAsset status and gcs_path after successful ingestion
        asset_id = (metadata or {}).get("asset_id")
        if asset_id:
            _update_asset_after_ingestion(
                str(asset_id),
                "ingested",
                new_gcs_path=result.destination_path,
            )

        logger.info(
            "Event processed successfully via Celery",
            extra={
                "event_id": event_id,
                "destination": result.destination_path,
                "duration_ms": result.processing_duration_ms,
            },
        )

        return {
            "status": "success",
            "event_id": event_id,
            "destination_path": result.destination_path,
            "processing_duration_ms": result.processing_duration_ms,
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
            "Non-retryable error processing event",
            extra={"event_id": event_id, "error": str(e)},
        )
        # Send to DLQ
        _send_to_dlq(event_id, tenant_id, file_path, e)
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
            "Unexpected error processing event", extra={"event_id": event_id}
        )
        raise


@shared_task(
    bind=True,
    name="data_ingestion.process_batch",
    acks_late=True,
)
def process_batch(self, events: list[dict]) -> dict:
    """
    Process a batch of ingestion events.

    Args:
        events: List of event dicts with keys:
            - event_id, tenant_id, file_path, timestamp, source, trace_id, metadata

    Returns:
        Dict with batch processing results
    """
    logger.info(
        f"Processing batch of {len(events)} events",
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
            result = process_ingestion_event(
                event_id=event_dict["event_id"],
                tenant_id=event_dict["tenant_id"],
                file_path=event_dict["file_path"],
                timestamp=event_dict.get("timestamp"),
                source=event_dict.get("source"),
                trace_id=event_dict.get("trace_id"),
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
        "Batch processing complete",
        extra={
            "total": results["total"],
            "success": results["success"],
            "failed": results["failed"],
        },
    )

    return results


@shared_task(
    bind=True,
    name="data_ingestion.check_status",
)
def check_status(self, trace_id: str) -> Optional[dict]:
    """
    Check the processing status of an event by trace_id.

    Args:
        trace_id: The trace ID to look up

    Returns:
        Status dict or None if not found
    """
    from data_ingestion.factory import create_redis_adapter

    cache = create_redis_adapter()
    return cache.get_status(trace_id)


@shared_task(
    bind=True,
    name="data_ingestion.reprocess_from_dlq",
    acks_late=True,
)
def reprocess_from_dlq(self, dlq_message: dict) -> dict:
    """
    Reprocess an event from the Dead Letter Queue.

    This task attempts to reprocess a failed event,
    typically after the underlying issue has been fixed.

    Args:
        dlq_message: DLQ message containing original_event and error info

    Returns:
        Dict with reprocessing result
    """
    original_event = dlq_message.get("original_event", {})
    event_id = original_event.get("event_id")

    logger.info(
        "Reprocessing event from DLQ",
        extra={"event_id": event_id, "task_id": self.request.id},
    )

    try:
        return process_ingestion_event(
            event_id=original_event["event_id"],
            tenant_id=original_event["tenant_id"],
            file_path=original_event["file_path"],
            timestamp=original_event.get("timestamp"),
            source=original_event.get("source"),
            trace_id=original_event.get("trace_id"),
            metadata=original_event.get("metadata"),
        )
    except Exception as e:
        logger.error(
            "Failed to reprocess DLQ event",
            extra={"event_id": event_id, "error": str(e)},
        )
        raise


def _send_to_dlq(
    event_id: str,
    tenant_id: str,
    file_path: str,
    error: Exception,
) -> None:
    """Helper to send failed event to DLQ."""
    try:
        from data_ingestion.factory import create_kafka_producer

        config = get_data_ingestion_config()
        kafka_config = config.get("KAFKA", {})

        producer = create_kafka_producer()
        # Support both nested KAFKA config and flat keys (KAFKA_INPUT_TOPIC)
        source_topic = kafka_config.get(
            "INPUT_TOPIC",
            config.get("KAFKA_INPUT_TOPIC", "raw-ingestion-topic"),
        )
        producer.publish_to_dlq(
            original_event={
                "event_id": event_id,
                "tenant_id": tenant_id,
                "file_path": file_path,
            },
            error=error,
            source_topic=source_topic,
        )
        producer.flush()
    except Exception as e:
        logger.error(
            "Failed to send to DLQ", extra={"event_id": event_id, "error": str(e)}
        )
