"""
DRF Views for RAG Index API.

ViewSets for sync operations, status tracking, health checks,
and rate limit information.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from django.conf import settings
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from rag_index.api.serializers import (
    BatchSyncRequestSerializer,
    RateLimitStatusSerializer,
    SyncEventSerializer,
    SyncStatusRecordSerializer,
)
from rag_index.domain.exceptions import (
    StatusNotFoundError,
)
from rag_index.tasks.sync_tasks import (
    batch_sync_documents,
    get_orchestrator,
    run_async,
    sync_document,
)

logger = logging.getLogger(__name__)

# Service version (can be overridden by settings)
SERVICE_VERSION = getattr(settings, "RAG_INDEX_VERSION", "1.0.0")


def get_trace_id(request: Request) -> str:
    """Extract or generate trace ID from request."""
    trace_id = request.headers.get("X-Trace-ID")
    if not trace_id:
        trace_id = str(uuid.uuid4())
    return trace_id


def error_response(
    error_type: str,
    message: str,
    details: Optional[dict] = None,
    trace_id: Optional[str] = None,
    status_code: int = status.HTTP_400_BAD_REQUEST,
) -> Response:
    """Create a standardized error response."""
    data = {
        "error": error_type,
        "message": message,
    }
    if details:
        data["details"] = details
    if trace_id:
        data["trace_id"] = trace_id
    return Response(data, status=status_code)


class HealthViewSet(viewsets.ViewSet):
    """Health check endpoints.

    Provides endpoints for service health monitoring and readiness checks.
    """

    permission_classes = [AllowAny]

    @action(detail=False, methods=["get"], url_path="")
    def health(self, request: Request) -> Response:
        """Get overall service health.

        Returns health status of all components including Vertex AI,
        Redis, GCS, and Kafka.
        """
        trace_id = get_trace_id(request)

        try:
            orchestrator = get_orchestrator()
            health_result = run_async(orchestrator.check_health())

            # Determine overall status
            all_healthy = all(
                v is True for v in health_result.values() if v is not None
            )

            response_data = {
                "status": "healthy" if all_healthy else "degraded",
                "version": SERVICE_VERSION,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "components": health_result,
            }

            status_code = (
                status.HTTP_200_OK
                if all_healthy
                else status.HTTP_503_SERVICE_UNAVAILABLE
            )

            return Response(response_data, status=status_code)

        except Exception as e:
            logger.error(
                "Health check failed", extra={"trace_id": trace_id, "error": str(e)}
            )
            return Response(
                {
                    "status": "unhealthy",
                    "version": SERVICE_VERSION,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "components": {},
                    "error": str(e),
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

    @action(detail=False, methods=["get"])
    def ready(self, request: Request) -> Response:
        """Kubernetes readiness probe.

        Returns 200 if service is ready to accept traffic.
        """
        try:
            orchestrator = get_orchestrator()
            health_result = run_async(orchestrator.check_health())

            # Check critical components (health_result values are booleans)
            vertex_ai_healthy = health_result.get("vertex_ai", False) is True

            if vertex_ai_healthy:
                return Response({"ready": True}, status=status.HTTP_200_OK)
            else:
                return Response(
                    {"ready": False, "reason": "Vertex AI unhealthy"},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
        except Exception as e:
            return Response(
                {"ready": False, "reason": str(e)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

    @action(detail=False, methods=["get"])
    def live(self, request: Request) -> Response:
        """Kubernetes liveness probe.

        Returns 200 if service is alive (basic check).
        """
        return Response({"alive": True}, status=status.HTTP_200_OK)


class SyncStatusViewSet(viewsets.ViewSet):
    """Sync status endpoints.

    Provides endpoints for checking the status of sync operations.
    """

    permission_classes = [IsAuthenticated]

    def retrieve(self, request: Request, pk: str = None) -> Response:
        """Get status of a specific sync event.

        Args:
            pk: Event ID to look up

        Returns:
            Status record for the event
        """
        trace_id = get_trace_id(request)

        try:
            event_id = uuid.UUID(pk)
        except ValueError:
            return error_response(
                "invalid_event_id",
                f"Invalid event ID format: {pk}",
                trace_id=trace_id,
            )

        try:
            orchestrator = get_orchestrator()
            status_record = run_async(orchestrator.get_status(event_id))

            if status_record is None:
                return error_response(
                    "not_found",
                    f"Status not found for event: {pk}",
                    trace_id=trace_id,
                    status_code=status.HTTP_404_NOT_FOUND,
                )

            return Response(
                SyncStatusRecordSerializer.from_status_record(status_record),
                status=status.HTTP_200_OK,
            )

        except StatusNotFoundError:
            return error_response(
                "not_found",
                f"Status not found for event: {pk}",
                trace_id=trace_id,
                status_code=status.HTTP_404_NOT_FOUND,
            )
        except Exception as e:
            logger.error(
                "Failed to get status",
                extra={"trace_id": trace_id, "event_id": pk, "error": str(e)},
            )
            return error_response(
                "internal_error",
                "Failed to retrieve status",
                details={"error": str(e)},
                trace_id=trace_id,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class SyncTriggerViewSet(viewsets.ViewSet):
    """Sync trigger endpoints.

    Provides endpoints for triggering sync operations.
    """

    permission_classes = [IsAuthenticated]

    def create(self, request: Request) -> Response:
        """Trigger a sync operation.

        Accepts a sync event and dispatches it for processing.

        Request body:
            - tenant_id: Tenant identifier
            - file_id: File/document identifier
            - action: UPSERT or DELETE
            - gcs_uri: GCS URI (required for UPSERT)
            - priority: Optional priority (0-10)
            - metadata: Optional metadata dict
        """
        trace_id = get_trace_id(request)

        serializer = SyncEventSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                "validation_error",
                "Invalid sync event data",
                details=serializer.errors,
                trace_id=trace_id,
            )

        try:
            # Create the event
            event_data = serializer.validated_data.copy()
            if "event_id" not in event_data or not event_data["event_id"]:
                event_data["event_id"] = uuid.uuid4()
            if "trace_id" not in event_data or not event_data["trace_id"]:
                event_data["trace_id"] = trace_id

            # Convert to dict for Celery task
            event_dict = {
                "event_id": str(event_data["event_id"]),
                "trace_id": str(event_data.get("trace_id", "")),
                "tenant_id": event_data["tenant_id"],
                "file_id": event_data["file_id"],
                "action": event_data["action"],
                "processed_gcs_uri": event_data.get("gcs_uri", ""),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "priority": event_data.get("priority", 0),
                "metadata": event_data.get("metadata", {}),
            }

            # Dispatch to Celery
            task = sync_document.delay(event_dict)

            logger.info(
                "Sync task dispatched",
                extra={
                    "trace_id": trace_id,
                    "event_id": str(event_data["event_id"]),
                    "task_id": task.id,
                },
            )

            return Response(
                {
                    "event_id": str(event_data["event_id"]),
                    "task_id": task.id,
                    "status": "dispatched",
                },
                status=status.HTTP_202_ACCEPTED,
            )

        except Exception as e:
            logger.error(
                "Failed to dispatch sync", extra={"trace_id": trace_id, "error": str(e)}
            )
            return error_response(
                "dispatch_error",
                "Failed to dispatch sync task",
                details={"error": str(e)},
                trace_id=trace_id,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=False, methods=["post"])
    def batch(self, request: Request) -> Response:
        """Trigger batch sync operations.

        Accepts multiple sync events and dispatches them for processing.

        Request body:
            - events: List of sync events
            - stop_on_error: Whether to stop on first dispatch error
        """
        trace_id = get_trace_id(request)

        serializer = BatchSyncRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                "validation_error",
                "Invalid batch request",
                details=serializer.errors,
                trace_id=trace_id,
            )

        try:
            events = serializer.validated_data["events"]
            stop_on_error = serializer.validated_data.get("stop_on_error", False)

            # Convert events to dicts for Celery
            event_dicts = []
            for event_data in events:
                if "event_id" not in event_data or not event_data["event_id"]:
                    event_data["event_id"] = uuid.uuid4()

                event_dicts.append(
                    {
                        "event_id": str(event_data["event_id"]),
                        "trace_id": trace_id,
                        "tenant_id": event_data["tenant_id"],
                        "file_id": event_data["file_id"],
                        "action": event_data["action"],
                        "processed_gcs_uri": event_data.get("gcs_uri", ""),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "priority": event_data.get("priority", 0),
                        "metadata": event_data.get("metadata", {}),
                    }
                )

            # Dispatch batch to Celery
            task = batch_sync_documents.delay(event_dicts, stop_on_error)

            logger.info(
                "Batch sync task dispatched",
                extra={
                    "trace_id": trace_id,
                    "batch_size": len(event_dicts),
                    "task_id": task.id,
                },
            )

            return Response(
                {
                    "task_id": task.id,
                    "batch_size": len(event_dicts),
                    "status": "dispatched",
                },
                status=status.HTTP_202_ACCEPTED,
            )

        except Exception as e:
            logger.error(
                "Failed to dispatch batch sync",
                extra={"trace_id": trace_id, "error": str(e)},
            )
            return error_response(
                "dispatch_error",
                "Failed to dispatch batch sync task",
                details={"error": str(e)},
                trace_id=trace_id,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class RateLimitViewSet(viewsets.ViewSet):
    """Rate limit status endpoints.

    Provides endpoints for checking rate limit status.
    """

    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=["get"], url_path="")
    def status(self, request: Request) -> Response:
        """Get current rate limit status.

        Returns current rate limit information for Vertex AI operations.
        """
        trace_id = get_trace_id(request)

        try:
            orchestrator = get_orchestrator()
            rate_status = run_async(orchestrator.get_rate_limit_status())

            if rate_status is None:
                return Response(
                    {
                        "message": "Rate limiting not configured or in mock mode",
                        "is_limited": False,
                    },
                    status=status.HTTP_200_OK,
                )

            return Response(
                RateLimitStatusSerializer.from_rate_limit_status(rate_status),
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            logger.error(
                "Failed to get rate limit status",
                extra={"trace_id": trace_id, "error": str(e)},
            )
            return error_response(
                "internal_error",
                "Failed to retrieve rate limit status",
                details={"error": str(e)},
                trace_id=trace_id,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
