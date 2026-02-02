"""
DRF Serializers for Data Ingestion API.

These serializers handle validation and transformation of API requests/responses.
They work alongside the Pydantic domain models for internal processing.
"""

from rest_framework import serializers
from uuid import uuid4
from datetime import datetime

from data_ingestion.domain.models import EventSource, ProcessingStatus


class IngestionEventSerializer(serializers.Serializer):
    """
    Serializer for creating/validating ingestion events via API.

    This is the main input serializer for the POST /ingest/ endpoint.
    """

    event_id = serializers.UUIDField(
        required=False,
        help_text="Unique event ID (auto-generated if not provided)",
    )
    trace_id = serializers.UUIDField(
        required=False,
        help_text="Trace ID for distributed tracing (auto-generated if not provided)",
    )
    timestamp = serializers.DateTimeField(
        required=False,
        help_text="Event timestamp (defaults to now)",
    )
    source = serializers.ChoiceField(
        choices=[(e.value, e.value) for e in EventSource],
        required=False,
        default=EventSource.API_INTEGRATION.value,
        help_text="Source system that generated this event",
    )
    tenant_id = serializers.CharField(
        max_length=100,
        help_text="Tenant identifier (e.g., 'customer-1')",
    )
    file_path = serializers.CharField(
        help_text="Full GCS path to the file (e.g., 'gs://bucket/_landing/file.mp4')",
    )
    file_type = serializers.CharField(
        required=False,
        default="application/octet-stream",
        help_text="MIME type of the file",
    )
    file_size_bytes = serializers.IntegerField(
        required=False,
        min_value=0,
        allow_null=True,
        help_text="File size in bytes",
    )
    metadata = serializers.DictField(
        required=False,
        default=dict,
        help_text="Additional metadata about the file",
    )

    def validate_tenant_id(self, value):
        """Validate tenant_id contains only safe characters."""
        import re

        if not re.match(r"^[a-zA-Z0-9_-]+$", value):
            raise serializers.ValidationError(
                "tenant_id must contain only alphanumeric characters, "
                "hyphens, and underscores"
            )
        return value.lower()

    def validate_file_path(self, value):
        """Validate file_path is a valid GCS path."""
        if not value.startswith("gs://"):
            raise serializers.ValidationError(
                "file_path must be a GCS URI starting with 'gs://'"
            )
        return value

    def create(self, validated_data):
        """Generate defaults for optional fields."""
        if "event_id" not in validated_data or validated_data["event_id"] is None:
            validated_data["event_id"] = uuid4()
        if "trace_id" not in validated_data or validated_data["trace_id"] is None:
            validated_data["trace_id"] = uuid4()
        if "timestamp" not in validated_data or validated_data["timestamp"] is None:
            validated_data["timestamp"] = datetime.utcnow()
        return validated_data


class BatchEventItemSerializer(serializers.Serializer):
    """Loose serializer for batch items - allows partial validation."""

    event_id = serializers.UUIDField(required=False)
    trace_id = serializers.UUIDField(required=False)
    timestamp = serializers.DateTimeField(required=False)
    source = serializers.ChoiceField(
        choices=[(e.value, e.value) for e in EventSource],
        required=False,
    )
    tenant_id = serializers.CharField(required=False, allow_blank=True)
    file_path = serializers.CharField(required=False, allow_blank=True)
    file_type = serializers.CharField(required=False)
    file_size_bytes = serializers.IntegerField(required=False, min_value=0)
    metadata = serializers.DictField(required=False)


class BatchIngestionSerializer(serializers.Serializer):
    """
    Serializer for batch ingestion requests.

    Uses a loose validation to allow the view to process valid events
    and reject invalid ones individually.
    """

    events = BatchEventItemSerializer(many=True)

    def validate_events(self, value):
        """Validate batch size limits."""
        max_batch_size = 100
        if len(value) > max_batch_size:
            raise serializers.ValidationError(
                f"Batch size exceeds maximum of {max_batch_size} events"
            )
        if len(value) == 0:
            raise serializers.ValidationError("At least one event is required")
        return value


class ProcessedEventSerializer(serializers.Serializer):
    """
    Serializer for processed event responses.

    This is the output serializer returned after successful processing.
    """

    event_id = serializers.UUIDField()
    trace_id = serializers.UUIDField()
    timestamp = serializers.DateTimeField()
    tenant_id = serializers.CharField()
    source_path = serializers.CharField()
    destination_path = serializers.CharField()
    status = serializers.ChoiceField(
        choices=[(s.value, s.value) for s in ProcessingStatus]
    )
    processing_duration_ms = serializers.IntegerField(allow_null=True)
    error_message = serializers.CharField(allow_null=True, required=False)


class FileMetadataSerializer(serializers.Serializer):
    """Serializer for file metadata responses."""

    bucket = serializers.CharField()
    path = serializers.CharField()
    full_uri = serializers.CharField()
    size_bytes = serializers.IntegerField()
    content_type = serializers.CharField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField(allow_null=True)
    md5_hash = serializers.CharField(allow_null=True)
    etag = serializers.CharField(allow_null=True)


class IngestionStatusSerializer(serializers.Serializer):
    """Serializer for ingestion status check responses."""

    trace_id = serializers.CharField()
    status = serializers.CharField()
    updated_at = serializers.DateTimeField(required=False)
    metadata = serializers.DictField(required=False)


class IngestionResponseSerializer(serializers.Serializer):
    """Standard response serializer for ingestion endpoints."""

    status = serializers.ChoiceField(
        choices=["success", "accepted", "failed", "skipped"]
    )
    message = serializers.CharField()
    event_id = serializers.UUIDField(required=False)
    trace_id = serializers.UUIDField(required=False)
    task_id = serializers.CharField(
        required=False, help_text="Celery task ID for async processing"
    )
    destination_path = serializers.CharField(required=False)
    processing_duration_ms = serializers.IntegerField(required=False)
    error = serializers.CharField(required=False)


class BatchIngestionResponseSerializer(serializers.Serializer):
    """Response serializer for batch ingestion."""

    status = serializers.ChoiceField(choices=["accepted", "partial", "failed"])
    message = serializers.CharField()
    total = serializers.IntegerField()
    accepted = serializers.IntegerField()
    rejected = serializers.IntegerField()
    task_id = serializers.CharField(required=False, help_text="Celery batch task ID")
    details = serializers.ListField(
        child=serializers.DictField(),
        required=False,
    )


class HealthCheckSerializer(serializers.Serializer):
    """Serializer for health check responses."""

    status = serializers.ChoiceField(choices=["healthy", "degraded", "unhealthy"])
    components = serializers.DictField()
    timestamp = serializers.DateTimeField()
