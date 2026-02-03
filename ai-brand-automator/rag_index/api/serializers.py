"""
DRF Serializers for RAG Index API.

Serializers for sync events, status records, health checks,
and rate limit information.
"""

from rest_framework import serializers

from rag_index.domain.models import (
    RateLimitStatus,
    SyncAction,
    SyncEvent,
    SyncResult,
    SyncStatusRecord,
)


class SyncActionSerializer(serializers.Serializer):
    """Serializer for sync action enum."""

    action = serializers.ChoiceField(
        choices=[(a.value, a.value) for a in SyncAction],
        help_text="The type of sync action to perform",
    )


class SyncEventSerializer(serializers.Serializer):
    """Serializer for sync events (incoming requests).

    Validates and deserializes sync event data from API requests.
    """

    event_id = serializers.UUIDField(
        required=False,
        help_text="Unique identifier for the event (auto-generated if not provided)",
    )
    trace_id = serializers.UUIDField(
        required=False,
        help_text="Trace ID for distributed tracing",
    )
    tenant_id = serializers.CharField(
        max_length=255,
        help_text="Tenant identifier",
    )
    file_id = serializers.CharField(
        max_length=255,
        help_text="File/document identifier",
    )
    action = serializers.ChoiceField(
        choices=[(a.value, a.value) for a in SyncAction],
        help_text="Sync action type (UPSERT or DELETE)",
    )
    gcs_uri = serializers.CharField(
        max_length=1024,
        required=False,
        allow_blank=True,
        help_text="GCS URI for the document (required for UPSERT)",
    )
    priority = serializers.IntegerField(
        required=False,
        default=0,
        min_value=0,
        max_value=10,
        help_text="Priority level (0-10, higher is more urgent)",
    )
    metadata = serializers.DictField(
        required=False,
        default=dict,
        help_text="Additional metadata for the sync operation",
    )

    def validate(self, attrs):
        """Validate that UPSERT actions have a GCS URI."""
        action = attrs.get("action")
        gcs_uri = attrs.get("gcs_uri", "")

        if action == SyncAction.UPSERT.value and not gcs_uri:
            raise serializers.ValidationError(
                {"gcs_uri": "GCS URI is required for UPSERT actions"}
            )

        if gcs_uri and not gcs_uri.startswith("gs://"):
            raise serializers.ValidationError(
                {"gcs_uri": "GCS URI must start with 'gs://'"}
            )

        return attrs

    def create(self, validated_data):
        """Create a SyncEvent from validated data."""
        # Convert action string to enum
        validated_data["action"] = SyncAction(validated_data["action"])
        return SyncEvent.from_dict(validated_data)


class SyncResultSerializer(serializers.Serializer):
    """Serializer for sync results (outgoing responses)."""

    event_id = serializers.UUIDField(
        help_text="Event identifier",
    )
    trace_id = serializers.CharField(
        help_text="Trace ID for distributed tracing",
    )
    status = serializers.CharField(
        help_text="Result status (COMPLETED, FAILED, PENDING)",
    )
    operation_id = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        help_text="Vertex AI operation ID",
    )
    error_message = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        help_text="Error message if failed",
    )
    processing_time_ms = serializers.IntegerField(
        required=False,
        help_text="Processing time in milliseconds",
    )

    @classmethod
    def from_sync_result(cls, result: SyncResult) -> dict:
        """Convert a SyncResult to serialized data."""
        return {
            "event_id": str(result.event_id),
            "trace_id": result.trace_id,
            "status": result.status,
            "operation_id": result.operation_id or "",
            "error_message": result.error_message or "",
            "processing_time_ms": result.processing_time_ms,
        }


class SyncStatusRecordSerializer(serializers.Serializer):
    """Serializer for sync status records."""

    event_id = serializers.UUIDField(
        help_text="Event identifier",
    )
    trace_id = serializers.CharField(
        help_text="Trace ID for distributed tracing",
    )
    tenant_id = serializers.CharField(
        help_text="Tenant identifier",
    )
    file_id = serializers.CharField(
        help_text="File/document identifier",
    )
    action = serializers.CharField(
        help_text="Sync action type",
    )
    status = serializers.CharField(
        help_text="Current status (PENDING, IN_PROGRESS, COMPLETED, FAILED)",
    )
    last_updated = serializers.DateTimeField(
        help_text="When the status record was last updated",
    )
    retry_count = serializers.IntegerField(
        help_text="Number of processing attempts",
    )
    error_message = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        help_text="Error message if failed",
    )

    @classmethod
    def from_status_record(cls, record: SyncStatusRecord) -> dict:
        """Convert a SyncStatusRecord to serialized data."""
        return {
            "event_id": str(record.event_id),
            "trace_id": record.trace_id,
            "tenant_id": record.tenant_id,
            "file_id": record.file_id,
            "action": record.action
            if isinstance(record.action, str)
            else record.action.value,
            "status": record.status.value
            if hasattr(record.status, "value")
            else record.status,
            "last_updated": record.last_updated.isoformat(),
            "retry_count": record.retry_count,
            "error_message": record.error_message,
        }


class RateLimitStatusSerializer(serializers.Serializer):
    """Serializer for rate limit status information."""

    current_count = serializers.IntegerField(
        help_text="Current request count in the window",
    )
    limit = serializers.IntegerField(
        help_text="Maximum requests allowed per window",
    )
    window_seconds = serializers.IntegerField(
        help_text="Time window in seconds",
    )
    remaining = serializers.IntegerField(
        help_text="Remaining requests in current window",
    )
    reset_at = serializers.DateTimeField(
        required=False,
        allow_null=True,
        help_text="When the rate limit will reset",
    )
    is_limited = serializers.BooleanField(
        help_text="Whether rate limiting is currently active",
    )

    @classmethod
    def from_rate_limit_status(cls, status: RateLimitStatus) -> dict:
        """Convert a RateLimitStatus to serialized data."""
        return {
            "current_count": status.current_count,
            "limit": status.limit,
            "window_seconds": status.window_seconds,
            "remaining": status.remaining,
            "reset_at": status.reset_at.isoformat() if status.reset_at else None,
            "is_limited": status.is_limited,
        }


class HealthCheckSerializer(serializers.Serializer):
    """Serializer for health check responses."""

    status = serializers.ChoiceField(
        choices=["healthy", "unhealthy", "degraded"],
        help_text="Overall service health status",
    )
    version = serializers.CharField(
        help_text="Service version",
    )
    timestamp = serializers.DateTimeField(
        help_text="Health check timestamp",
    )
    components = serializers.DictField(
        child=serializers.DictField(),
        help_text="Health status of individual components",
    )


class ComponentHealthSerializer(serializers.Serializer):
    """Serializer for individual component health."""

    name = serializers.CharField(
        help_text="Component name",
    )
    healthy = serializers.BooleanField(
        help_text="Whether the component is healthy",
    )
    latency_ms = serializers.FloatField(
        required=False,
        help_text="Component response latency in milliseconds",
    )
    message = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Additional health information",
    )


class BatchSyncRequestSerializer(serializers.Serializer):
    """Serializer for batch sync requests."""

    events = SyncEventSerializer(
        many=True,
        help_text="List of sync events to process",
    )
    stop_on_error = serializers.BooleanField(
        default=False,
        help_text="Whether to stop processing on first error",
    )

    def validate_events(self, events):
        """Validate that batch doesn't exceed maximum size."""
        max_batch_size = 100
        if len(events) > max_batch_size:
            raise serializers.ValidationError(
                f"Batch size exceeds maximum of {max_batch_size} events"
            )
        return events


class BatchSyncResponseSerializer(serializers.Serializer):
    """Serializer for batch sync responses."""

    total = serializers.IntegerField(
        help_text="Total number of events in batch",
    )
    dispatched = serializers.IntegerField(
        help_text="Number of events successfully dispatched",
    )
    failed = serializers.IntegerField(
        help_text="Number of events that failed to dispatch",
    )
    task_ids = serializers.ListField(
        child=serializers.CharField(),
        help_text="List of Celery task IDs for dispatched events",
    )
    errors = serializers.ListField(
        child=serializers.DictField(),
        help_text="List of errors for failed events",
    )


class ErrorResponseSerializer(serializers.Serializer):
    """Serializer for error responses."""

    error = serializers.CharField(
        help_text="Error type",
    )
    message = serializers.CharField(
        help_text="Human-readable error message",
    )
    details = serializers.DictField(
        required=False,
        help_text="Additional error details",
    )
    trace_id = serializers.CharField(
        required=False,
        help_text="Trace ID for debugging",
    )
