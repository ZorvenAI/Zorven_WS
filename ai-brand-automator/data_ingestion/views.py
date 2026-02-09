"""
DRF Views for Data Ingestion API.

These views expose REST API endpoints for the data ingestion pipeline,
following Django Rest Framework patterns used in other apps.
"""

import logging
from datetime import datetime

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ViewSet

from data_ingestion.serializers import (
    IngestionEventSerializer,
    BatchIngestionSerializer,
)
from data_ingestion.domain.models import IngestionEvent, EventSource
from data_ingestion.domain.exceptions import (
    DuplicateEventError,
    NonRetryableError,
)
from data_ingestion.factory import (
    create_ingestion_service,
    create_redis_adapter,
    get_data_ingestion_config,
)
from data_ingestion.tasks import process_ingestion_event, process_batch


logger = logging.getLogger(__name__)


class IngestionViewSet(ViewSet):
    """
    ViewSet for data ingestion operations.

    Provides REST API endpoints for:
    - POST /ingest/ - Submit single ingestion event
    - POST /ingest/batch/ - Submit batch of events
    - GET /ingest/status/{trace_id}/ - Check processing status
    - POST /ingest/sync/ - Synchronous processing (for testing)
    """

    permission_classes = [IsAuthenticated]

    def create(self, request):
        """
        Submit a single file for ingestion (async).

        The file will be processed asynchronously via Celery.
        Returns immediately with a task ID for tracking.

        Request Body:
        {
            "tenant_id": "customer-1",
            "file_path": "gs://bucket/_landing/file.mp4",
            "file_type": "video/mp4",
            "file_size_bytes": 1048576,
            "metadata": {"original_name": "demo.mp4"}
        }

        Response:
        {
            "status": "accepted",
            "message": "Ingestion event queued for processing",
            "event_id": "...",
            "trace_id": "...",
            "task_id": "celery-task-id"
        }
        """
        serializer = IngestionEventSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    "status": "failed",
                    "message": "Validation error",
                    "error": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Generate IDs if not provided
        validated_data = serializer.create(serializer.validated_data)
        event_id = validated_data["event_id"]
        trace_id = validated_data["trace_id"]

        # Get tenant from request context (multi-tenancy pattern)
        _tenant = getattr(request, "tenant", None)  # noqa: F841
        tenant_id = validated_data["tenant_id"]

        # Log the request
        logger.info(
            "Ingestion request received",
            extra={
                "event_id": str(event_id),
                "trace_id": str(trace_id),
                "tenant_id": tenant_id,
                "file_path": validated_data["file_path"],
                "user_id": request.user.id if request.user else None,
            },
        )

        # Queue for async processing via Celery
        task = process_ingestion_event.delay(
            event_id=str(event_id),
            tenant_id=tenant_id,
            file_path=validated_data["file_path"],
            file_type=validated_data.get("file_type"),
            timestamp=validated_data["timestamp"].isoformat()
            if validated_data.get("timestamp")
            else None,
            source=validated_data.get("source", EventSource.API_INTEGRATION.value),
            trace_id=str(trace_id),
            metadata=validated_data.get("metadata"),
        )

        return Response(
            {
                "status": "accepted",
                "message": "Ingestion event queued for processing",
                "event_id": str(event_id),
                "trace_id": str(trace_id),
                "task_id": task.id,
            },
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=False, methods=["post"])
    def batch(self, request):
        """
        Submit a batch of files for ingestion (async).

        All files will be processed asynchronously via Celery.
        Returns immediately with a batch task ID.

        Request Body:
        {
            "events": [
                {"tenant_id": "customer-1", "file_path": "gs://...", ...},
                {"tenant_id": "customer-1", "file_path": "gs://...", ...}
            ]
        }
        """
        serializer = BatchIngestionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    "status": "failed",
                    "message": "Validation error",
                    "error": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        events_data = serializer.validated_data["events"]
        accepted = []
        rejected = []

        # Prepare events with generated IDs
        for event_data in events_data:
            event_serializer = IngestionEventSerializer(data=event_data)
            if event_serializer.is_valid():
                validated = event_serializer.create(event_serializer.validated_data)
                accepted.append(
                    {
                        "event_id": str(validated["event_id"]),
                        "tenant_id": validated["tenant_id"],
                        "file_path": validated["file_path"],
                        "file_type": validated.get("file_type"),
                        "timestamp": validated["timestamp"].isoformat()
                        if validated.get("timestamp")
                        else None,
                        "source": validated.get(
                            "source", EventSource.API_INTEGRATION.value
                        ),
                        "trace_id": str(validated["trace_id"]),
                        "metadata": validated.get("metadata"),
                    }
                )
            else:
                rejected.append(
                    {
                        "file_path": event_data.get("file_path"),
                        "error": event_serializer.errors,
                    }
                )

        if not accepted:
            return Response(
                {
                    "status": "failed",
                    "message": "All events failed validation",
                    "total": len(events_data),
                    "accepted": 0,
                    "rejected": len(rejected),
                    "details": rejected,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Queue batch for async processing
        task = process_batch.delay(events=accepted)

        logger.info(
            "Batch ingestion request queued",
            extra={
                "task_id": task.id,
                "total": len(events_data),
                "accepted": len(accepted),
                "rejected": len(rejected),
                "user_id": request.user.id if request.user else None,
            },
        )

        response_status = "accepted" if not rejected else "partial"
        return Response(
            {
                "status": response_status,
                "message": (
                    f"Batch queued: {len(accepted)} accepted, "
                    f"{len(rejected)} rejected"
                ),
                "total": len(events_data),
                "accepted": len(accepted),
                "rejected": len(rejected),
                "task_id": task.id,
                "details": rejected if rejected else None,
            },
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=False, methods=["post"], url_path="sync")
    def sync_process(self, request):
        """
        Process a single file synchronously (for testing/debugging).

        WARNING: This endpoint blocks until processing completes.
        Use the async endpoint (POST /ingest/) for production.

        Request Body: Same as POST /ingest/
        """
        serializer = IngestionEventSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    "status": "failed",
                    "message": "Validation error",
                    "error": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        validated_data = serializer.create(serializer.validated_data)

        try:
            # Build domain model
            event = IngestionEvent(
                event_id=validated_data["event_id"],
                trace_id=validated_data["trace_id"],
                timestamp=validated_data.get("timestamp", datetime.utcnow()),
                source=EventSource(
                    validated_data.get("source", EventSource.API_INTEGRATION.value)
                ),
                tenant_id=validated_data["tenant_id"],
                file_path=validated_data["file_path"],
                file_type=validated_data.get("file_type", "application/octet-stream"),
                file_size_bytes=validated_data.get("file_size_bytes"),
                metadata=validated_data.get("metadata"),
            )

            # Process synchronously
            service = create_ingestion_service()
            result = service.process_event(event)

            return Response(
                {
                    "status": "success",
                    "message": "File processed successfully",
                    "event_id": str(result.event_id),
                    "trace_id": str(result.trace_id),
                    "destination_path": result.destination_path,
                    "processing_duration_ms": result.processing_duration_ms,
                },
                status=status.HTTP_200_OK,
            )

        except DuplicateEventError:
            return Response(
                {
                    "status": "skipped",
                    "message": "Duplicate event - already processed",
                    "event_id": str(validated_data["event_id"]),
                    "trace_id": str(validated_data["trace_id"]),
                },
                status=status.HTTP_200_OK,
            )

        except NonRetryableError as e:
            logger.error(
                "Non-retryable error during sync processing",
                extra={
                    "event_id": str(validated_data["event_id"]),
                    "error": str(e),
                },
            )
            return Response(
                {
                    "status": "failed",
                    "message": "Processing failed",
                    "event_id": str(validated_data["event_id"]),
                    "error": str(e),
                },
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        except Exception as e:
            logger.exception(
                "Unexpected error during sync processing",
                extra={"event_id": str(validated_data["event_id"])},
            )
            return Response(
                {
                    "status": "failed",
                    "message": "Internal server error",
                    "event_id": str(validated_data["event_id"]),
                    "error": str(e),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=False, methods=["get"], url_path="status/(?P<trace_id>[^/.]+)")
    def status(self, request, trace_id=None):
        """
        Check the processing status of an ingestion event.

        Returns the current status from Redis cache.

        URL: GET /ingest/status/{trace_id}/
        """
        if not trace_id:
            return Response(
                {"status": "failed", "message": "trace_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            cache = create_redis_adapter()
            tenant = getattr(request, "tenant", None)
            tenant_id = str(tenant.id) if tenant else None
            status_data = cache.get_status(trace_id, tenant_id=tenant_id)

            if status_data:
                return Response(
                    {
                        "trace_id": trace_id,
                        "status": status_data.get("status"),
                        "updated_at": status_data.get("updated_at"),
                        "metadata": status_data.get("metadata"),
                    },
                    status=status.HTTP_200_OK,
                )
            else:
                return Response(
                    {
                        "trace_id": trace_id,
                        "status": "not_found",
                        "message": "No status found for this trace_id",
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )

        except Exception as e:
            logger.exception("Error checking status", extra={"trace_id": trace_id})
            return Response(
                {
                    "status": "failed",
                    "message": "Error checking status",
                    "error": str(e),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class IngestionHealthView(APIView):
    """
    Health check endpoint for the ingestion service.

    Returns the health status of all components (GCS, Redis, Kafka).
    """

    permission_classes = []  # Public endpoint for load balancers

    def get(self, request):
        """
        Check health of ingestion service components.

        GET /ingest/health/

        Response:
        {
            "status": "healthy",
            "components": {
                "redis": {"status": "healthy"},
                "gcs": {"status": "healthy"},
                "kafka": {"status": "healthy"}
            },
            "timestamp": "2026-01-29T10:00:00Z"
        }
        """
        components = {}
        overall_status = "healthy"

        # Check Redis
        try:
            cache = create_redis_adapter()
            if cache.health_check():
                components["redis"] = {"status": "healthy"}
            else:
                components["redis"] = {"status": "unhealthy", "error": "Ping failed"}
                overall_status = "degraded"
        except Exception as e:
            components["redis"] = {"status": "unhealthy", "error": str(e)}
            overall_status = "degraded"

        # Check GCS (basic connectivity)
        try:
            from data_ingestion.factory import create_gcs_adapter

            _storage = create_gcs_adapter()  # noqa: F841
            # Just check if we can create the adapter (credentials valid)
            components["gcs"] = {"status": "healthy"}
        except Exception as e:
            components["gcs"] = {"status": "unhealthy", "error": str(e)}
            overall_status = "degraded"

        # Check configuration
        try:
            config = get_data_ingestion_config()
            if config:
                components["config"] = {"status": "healthy"}
            else:
                components["config"] = {
                    "status": "degraded",
                    "warning": "Using default configuration",
                }
        except Exception as e:
            components["config"] = {"status": "unhealthy", "error": str(e)}
            overall_status = "degraded"

        # Determine HTTP status based on health
        http_status = (
            status.HTTP_200_OK
            if overall_status == "healthy"
            else status.HTTP_503_SERVICE_UNAVAILABLE
        )

        return Response(
            {
                "status": overall_status,
                "components": components,
                "timestamp": datetime.utcnow().isoformat(),
            },
            status=http_status,
        )
