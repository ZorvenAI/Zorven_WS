"""
Sync Tasks for RAG Index Service.

Celery tasks for processing document synchronization events.
Implements retry with exponential backoff and rate limit handling.
"""

import asyncio
import logging
from typing import Any, Optional

from celery import shared_task
from celery.exceptions import MaxRetriesExceededError, Reject

from rag_index.domain.exceptions import (
    RateLimitExceededError,
    SyncError,
    SyncValidationError,
)
from rag_index.domain.models import SyncEvent

logger = logging.getLogger(__name__)


def _update_asset_status(
    asset_id: str, status: str, error_msg: str = "", tenant_id: str = ""
) -> bool:
    """Update BrandAsset pipeline_status after indexing.

    Args:
        asset_id: The asset ID (integer as string)
        status: The new pipeline status (indexed, failed)
        error_msg: Error message if status is failed
        tenant_id: Optional tenant ID for scoped lookup

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
                qs = BrandAsset.objects.filter(id=aid)
                if tenant_id:
                    try:
                        qs = qs.filter(tenant_id=int(tenant_id))
                    except (ValueError, TypeError):
                        pass  # Non-integer tenant_id, skip FK filter
                asset = qs.first()
            except (ValueError, TypeError):
                asset = None

            if asset:
                asset.pipeline_status = status
                if error_msg:
                    asset.pipeline_error = error_msg
                asset.save(update_fields=["pipeline_status", "pipeline_error"])
                logger.info(
                    "Updated BrandAsset %s pipeline_status to %s",
                    asset.id,
                    status,
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


# ============================================================================
# Task Configuration
# ============================================================================

# Retry settings for transient failures
DEFAULT_MAX_RETRIES = 5
DEFAULT_RETRY_BACKOFF = 60  # Base delay in seconds
DEFAULT_RETRY_BACKOFF_MAX = 600  # Max delay in seconds

# Rate limit retry settings (longer delays)
RATE_LIMIT_RETRY_DELAY = 30  # Fixed delay for rate limit retries
RATE_LIMIT_MAX_RETRIES = 10


def get_orchestrator():
    """Get or create the SyncOrchestrator instance.

    This function creates the orchestrator with proper dependency injection.
    In production, adapters are configured from environment variables.

    Returns:
        SyncOrchestrator: Configured orchestrator instance
    """
    # Import here to avoid circular imports
    from django.conf import settings

    from rag_index.adapters import (
        GCSAdapter,
        KafkaAdapter,
        RedisAdapter,
        ThrottledVertexAIAdapter,
        VertexAIAdapter,
    )
    from rag_index.services import SyncOrchestrator

    # Check if we're in test/mock mode
    mock_mode = getattr(settings, "RAG_INDEX_MOCK_MODE", False)

    # Create adapters
    vertex_ai = VertexAIAdapter(
        project_id=getattr(settings, "VERTEX_AI_PROJECT_ID", "brandsol-project"),
        location=getattr(settings, "VERTEX_AI_LOCATION", "global"),
        data_store_id=getattr(settings, "VERTEX_AI_DATA_STORE_ID", "prevision-rag-dev"),
        mock_mode=mock_mode,
    )

    redis = RedisAdapter(
        redis_url=getattr(settings, "REDIS_URL", "redis://localhost:6379"),
    )

    gcs = GCSAdapter(
        project_id=getattr(settings, "GCP_PROJECT_ID", "test-project"),
        mock_mode=mock_mode,
    )

    # Wrap Vertex AI with throttling
    throttled_vertex_ai = ThrottledVertexAIAdapter(
        vertex_adapter=vertex_ai,
        redis_port=redis if not mock_mode else None,
        use_in_memory_limiter=mock_mode,
    )

    # Kafka is optional
    kafka = None
    kafka_bootstrap = getattr(settings, "KAFKA_BOOTSTRAP_SERVERS", None)
    if kafka_bootstrap and not mock_mode:
        kafka = KafkaAdapter(
            bootstrap_servers=kafka_bootstrap,
        )

    return SyncOrchestrator(
        vertex_ai_port=throttled_vertex_ai,
        gcs_port=gcs,
        redis_port=redis,
        kafka_port=kafka,
    )


def run_async(coro):
    """Run an async coroutine in sync context.

    Creates a new event loop for each task execution to avoid
    issues with Celery's sync execution model.
    """
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ============================================================================
# Main Sync Task
# ============================================================================


@shared_task(
    bind=True,
    name="rag_index.tasks.sync_document",
    max_retries=DEFAULT_MAX_RETRIES,
    default_retry_delay=DEFAULT_RETRY_BACKOFF,
    autoretry_for=(SyncError,),
    retry_backoff=True,
    retry_backoff_max=DEFAULT_RETRY_BACKOFF_MAX,
    retry_jitter=True,
    acks_late=True,  # Acknowledge after task completes
    reject_on_worker_lost=True,  # Requeue if worker dies
)
def sync_document(
    self,
    event_data: dict[str, Any],
) -> dict[str, Any]:
    """Process a document sync event.

    This is the main Celery task for processing sync events.
    It handles:
    - UPSERT: Fetch document from GCS and index in Vertex AI
    - DELETE: Remove document from Vertex AI index

    Args:
        self: Celery task instance (bound)
        event_data: Dictionary representation of SyncEvent

    Returns:
        Dictionary with sync result

    Raises:
        Reject: For non-retryable errors
        MaxRetriesExceededError: When all retries exhausted
    """
    # Parse event
    try:
        event = SyncEvent.from_dict(event_data)
    except Exception as e:
        logger.error(
            "Failed to parse sync event",
            extra={
                "event_data": event_data,
                "error": str(e),
            },
        )
        # Don't retry parse errors
        raise Reject(reason=f"Invalid event data: {e}", requeue=False)

    logger.info(
        "Processing sync task",
        extra={
            "task_id": self.request.id,
            "event_id": str(event.event_id),
            "trace_id": event.trace_id,
            "action": event.action.value,
            "retry_count": self.request.retries,
            "metadata": event.metadata,
            "asset_id": event.metadata.get("asset_id") if event.metadata else None,
        },
    )

    try:
        # Get orchestrator and process
        orchestrator = get_orchestrator()
        result = run_async(orchestrator.process_event(event))

        logger.info(
            "Sync task completed",
            extra={
                "task_id": self.request.id,
                "event_id": str(event.event_id),
                "status": result.status,
                "processing_time_ms": result.processing_time_ms,
            },
        )

        # Update BrandAsset status to indexed
        asset_id = event.metadata.get("asset_id") if event.metadata else None
        if asset_id:
            _update_asset_status(str(asset_id), "indexed", tenant_id=event.tenant_id)
        else:
            logger.warning(f"No asset_id in metadata for event {event.event_id}")

        return result.to_dict()

    except RateLimitExceededError as e:
        # Handle rate limit with fixed delay retry
        logger.warning(
            "Rate limit exceeded, scheduling retry",
            extra={
                "task_id": self.request.id,
                "event_id": str(event.event_id),
                "retry_count": self.request.retries,
                "retry_after_seconds": e.retry_after_seconds,
            },
        )

        # Use countdown for rate limit delays
        retry_delay = max(e.retry_after_seconds, RATE_LIMIT_RETRY_DELAY)

        try:
            raise self.retry(
                exc=e,
                countdown=retry_delay,
                max_retries=RATE_LIMIT_MAX_RETRIES,
            )
        except MaxRetriesExceededError:
            logger.error(
                "Max rate limit retries exceeded",
                extra={
                    "task_id": self.request.id,
                    "event_id": str(event.event_id),
                },
            )
            raise Reject(
                reason="Rate limit retries exhausted",
                requeue=False,
            )

    except SyncValidationError as e:
        # Validation errors are not retryable
        logger.error(
            "Sync validation error",
            extra={
                "task_id": self.request.id,
                "event_id": str(event.event_id),
                "error": str(e),
            },
        )
        raise Reject(reason=str(e), requeue=False)

    except SyncError as e:
        # SyncError will be auto-retried via autoretry_for
        logger.warning(
            "Sync error, will retry",
            extra={
                "task_id": self.request.id,
                "event_id": str(event.event_id),
                "error": str(e),
                "retry_count": self.request.retries,
            },
        )
        raise

    except Exception as e:
        # Unexpected errors
        logger.exception(
            "Unexpected error in sync task",
            extra={
                "task_id": self.request.id,
                "event_id": str(event.event_id),
            },
        )

        try:
            raise self.retry(exc=e)
        except MaxRetriesExceededError:
            raise Reject(
                reason=f"Max retries exceeded: {e}",
                requeue=False,
            )


# ============================================================================
# Batch Sync Task
# ============================================================================


@shared_task(
    bind=True,
    name="rag_index.tasks.batch_sync_documents",
    max_retries=3,
)
def batch_sync_documents(
    self,
    event_data_list: list[dict[str, Any]],
    stop_on_error: bool = False,
) -> dict[str, Any]:
    """Process multiple sync events in batch.

    Dispatches individual sync_document tasks for each event.
    Useful for bulk operations or reprocessing.

    Args:
        self: Celery task instance (bound)
        event_data_list: List of SyncEvent dictionaries
        stop_on_error: If True, stop on first error

    Returns:
        Dictionary with batch results
    """
    logger.info(
        "Starting batch sync",
        extra={
            "task_id": self.request.id,
            "batch_size": len(event_data_list),
        },
    )

    results = {
        "total": len(event_data_list),
        "dispatched": 0,
        "failed": 0,
        "task_ids": [],
        "errors": [],
    }

    for i, event_data in enumerate(event_data_list):
        try:
            # Dispatch individual task
            task = sync_document.delay(event_data)
            results["dispatched"] += 1
            results["task_ids"].append(task.id)

        except Exception as e:
            results["failed"] += 1
            results["errors"].append(
                {
                    "index": i,
                    "event_id": event_data.get("event_id"),
                    "error": str(e),
                }
            )

            if stop_on_error:
                logger.warning(
                    "Batch sync stopped on error",
                    extra={
                        "task_id": self.request.id,
                        "index": i,
                        "error": str(e),
                    },
                )
                break

    logger.info(
        "Batch sync completed",
        extra={
            "task_id": self.request.id,
            "dispatched": results["dispatched"],
            "failed": results["failed"],
        },
    )

    return results


# ============================================================================
# Retry Failed Syncs Task
# ============================================================================


@shared_task(
    bind=True,
    name="rag_index.tasks.retry_failed_syncs",
)
def retry_failed_syncs(
    self,
    tenant_id: Optional[str] = None,
    max_events: int = 100,
) -> dict[str, Any]:
    """Retry failed sync events from Redis.

    Queries Redis for events with FAILED status and
    dispatches retry tasks for each.

    Args:
        self: Celery task instance (bound)
        tenant_id: Optional tenant filter
        max_events: Maximum events to retry

    Returns:
        Dictionary with retry results
    """
    logger.info(
        "Starting failed sync retry",
        extra={
            "task_id": self.request.id,
            "tenant_id": tenant_id,
            "max_events": max_events,
        },
    )

    # This would query Redis for failed events
    # For now, return placeholder
    results = {
        "queried": 0,
        "retried": 0,
        "task_ids": [],
    }

    # TODO: Implement Redis query for failed events
    # This requires the RedisAdapter to support scanning
    # for events by status

    logger.info(
        "Failed sync retry completed",
        extra={
            "task_id": self.request.id,
            "retried": results["retried"],
        },
    )

    return results
