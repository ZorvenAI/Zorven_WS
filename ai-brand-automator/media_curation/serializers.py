"""
DRF Serializers for Media Curation API.

Serializers for request validation and response formatting.
"""

from rest_framework import serializers


class CurationRequestSerializer(serializers.Serializer):
    """Serializer for curation request."""

    tenant_id = serializers.CharField(max_length=255)
    brand_id = serializers.CharField(max_length=255, required=False, allow_null=True)
    source_path = serializers.CharField(max_length=2048)
    file_type = serializers.CharField(max_length=255)
    file_size_bytes = serializers.IntegerField(min_value=0, default=0)
    metadata = serializers.DictField(required=False, default=dict)

    def validate_source_path(self, value: str) -> str:
        """Validate source_path is a GCS URI."""
        if not value.startswith("gs://"):
            raise serializers.ValidationError(
                "source_path must be a GCS URI (gs://...)"
            )
        return value


class BatchCurationRequestSerializer(serializers.Serializer):
    """Serializer for batch curation request."""

    events = CurationRequestSerializer(many=True)

    def validate_events(self, value):
        """Validate batch size."""
        if len(value) > 100:
            raise serializers.ValidationError("Maximum batch size is 100 events")
        if len(value) == 0:
            raise serializers.ValidationError("At least one event is required")
        return value


class CurationResponseSerializer(serializers.Serializer):
    """Serializer for curation submission response."""

    event_id = serializers.UUIDField()
    trace_id = serializers.UUIDField()
    status = serializers.CharField()
    message = serializers.CharField()


class BatchCurationResponseSerializer(serializers.Serializer):
    """Serializer for batch curation response."""

    accepted = serializers.IntegerField()
    rejected = serializers.IntegerField()
    results = CurationResponseSerializer(many=True)


class CurationStatusSerializer(serializers.Serializer):
    """Serializer for curation status response."""

    trace_id = serializers.UUIDField()
    event_id = serializers.UUIDField()
    status = serializers.CharField()
    content_type = serializers.CharField(allow_null=True)
    started_at = serializers.DateTimeField()
    completed_at = serializers.DateTimeField(allow_null=True)
    processing_duration_ms = serializers.IntegerField()
    error_message = serializers.CharField(allow_null=True)
    retry_count = serializers.IntegerField()
    destination_path = serializers.CharField(allow_null=True)


class CuratedDocumentSerializer(serializers.Serializer):
    """Serializer for curated document output."""

    document_id = serializers.UUIDField()
    event_id = serializers.UUIDField()
    trace_id = serializers.UUIDField()
    tenant_id = serializers.CharField()
    brand_id = serializers.CharField(allow_null=True)
    source_path = serializers.CharField()
    destination_path = serializers.CharField(allow_null=True)
    file_type = serializers.CharField()
    content_type = serializers.CharField()
    title = serializers.CharField(allow_null=True)
    content = serializers.CharField()
    summary = serializers.CharField(allow_null=True)
    entities = serializers.ListField(child=serializers.DictField())
    keywords = serializers.ListField(child=serializers.CharField())
    language = serializers.CharField()
    status = serializers.CharField()
    confidence_score = serializers.FloatField()
    pii_redacted = serializers.BooleanField()
    pii_findings_count = serializers.IntegerField()
    created_at = serializers.DateTimeField()
    processing_duration_ms = serializers.IntegerField()
    metadata = serializers.DictField()


class HealthCheckSerializer(serializers.Serializer):
    """Serializer for health check response."""

    status = serializers.CharField()
    timestamp = serializers.DateTimeField()
    components = serializers.DictField()


class ComponentHealthSerializer(serializers.Serializer):
    """Serializer for individual component health."""

    status = serializers.CharField()
    error = serializers.CharField(required=False, allow_null=True)
    latency_ms = serializers.IntegerField(required=False)


class TenantConfigSerializer(serializers.Serializer):
    """Serializer for tenant curation configuration CRUD."""

    tenant_id = serializers.CharField(max_length=255)
    enabled = serializers.BooleanField(default=True)
    max_file_size_mb = serializers.IntegerField(min_value=1, max_value=500, default=100)
    allowed_file_types = serializers.ListField(
        child=serializers.CharField(max_length=50),
        default=[
            "application/pdf",
            "image/jpeg",
            "image/png",
            "video/mp4",
            "audio/mpeg",
        ],
    )
    pii_detection_enabled = serializers.BooleanField(default=True)
    pii_redaction_enabled = serializers.BooleanField(default=True)
    language_detection_enabled = serializers.BooleanField(default=True)
    summarization_enabled = serializers.BooleanField(default=True)
    entity_extraction_enabled = serializers.BooleanField(default=True)
    output_bucket = serializers.CharField(
        max_length=255, required=False, allow_blank=True
    )
    callback_url = serializers.URLField(required=False, allow_blank=True)
    metadata = serializers.DictField(required=False, default=dict)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)

    def validate_allowed_file_types(self, value):
        """Validate allowed file types are valid MIME types."""
        valid_mime_prefixes = ["application/", "image/", "video/", "audio/", "text/"]
        for mime_type in value:
            if not any(mime_type.startswith(prefix) for prefix in valid_mime_prefixes):
                prefixes = ", ".join(valid_mime_prefixes)
                raise serializers.ValidationError(
                    f"Invalid MIME type: {mime_type}. Must start with: {prefixes}"
                )
        return value


class SyncCurationRequestSerializer(serializers.Serializer):
    """Serializer for synchronous curation request (testing)."""

    tenant_id = serializers.CharField(max_length=255)
    brand_id = serializers.CharField(max_length=255, required=False, allow_null=True)
    source_path = serializers.CharField(max_length=2048)
    file_type = serializers.CharField(max_length=255)
    file_size_bytes = serializers.IntegerField(min_value=0, default=0)
    metadata = serializers.DictField(required=False, default=dict)
    timeout_seconds = serializers.IntegerField(min_value=1, max_value=300, default=60)

    def validate_source_path(self, value: str) -> str:
        """Validate source_path is a GCS URI."""
        if not value.startswith("gs://"):
            raise serializers.ValidationError(
                "source_path must be a GCS URI (gs://...)"
            )
        return value


class SyncCurationResponseSerializer(serializers.Serializer):
    """Serializer for synchronous curation response."""

    event_id = serializers.UUIDField()
    trace_id = serializers.UUIDField()
    status = serializers.CharField()
    document = CuratedDocumentSerializer(allow_null=True)
    processing_duration_ms = serializers.IntegerField()
    error = serializers.CharField(allow_null=True)
