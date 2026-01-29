"""
Unit tests for domain models.

Tests Pydantic models, validation, and serialization.
"""

import pytest
from datetime import datetime
from uuid import uuid4

from data_ingestion.domain.models import (
    IngestionEvent,
    ProcessedEvent,
    FileMetadata,
    ProcessingStatus,
    EventSource,
    FileType,
)


class TestIngestionEvent:
    """Tests for IngestionEvent model."""

    def test_create_valid_event(self):
        """Test creating a valid ingestion event."""
        event = IngestionEvent(
            event_id=uuid4(),
            trace_id=uuid4(),
            tenant_id="tenant-123",
            file_path="gs://bucket/_landing/file.mp4",
            file_type="video/mp4",
            timestamp=datetime.utcnow(),
            source=EventSource.FRONTEND_UPLOAD,
        )

        assert event.tenant_id == "tenant-123"
        assert event.file_path == "gs://bucket/_landing/file.mp4"
        assert event.source == EventSource.FRONTEND_UPLOAD

    def test_tenant_id_normalized_to_lowercase(self):
        """Test that tenant_id is normalized to lowercase."""
        event = IngestionEvent(
            event_id=uuid4(),
            trace_id=uuid4(),
            tenant_id="TENANT-123",
            file_path="gs://bucket/_landing/file.mp4",
            file_type="video/mp4",
            timestamp=datetime.utcnow(),
            source=EventSource.API_INTEGRATION,
        )

        assert event.tenant_id == "tenant-123"

    def test_invalid_tenant_id_special_chars(self):
        """Test that special characters in tenant_id are rejected."""
        with pytest.raises(ValueError, match="alphanumeric"):
            IngestionEvent(
                event_id=uuid4(),
                trace_id=uuid4(),
                tenant_id="tenant/123",
                file_path="gs://bucket/_landing/file.mp4",
                file_type="video/mp4",
                timestamp=datetime.utcnow(),
                source=EventSource.API_INTEGRATION,
            )

    def test_invalid_file_path_not_gcs(self):
        """Test that non-GCS paths are rejected."""
        with pytest.raises(ValueError, match="GCS URI"):
            IngestionEvent(
                event_id=uuid4(),
                trace_id=uuid4(),
                tenant_id="tenant-123",
                file_path="/local/path/file.mp4",
                file_type="video/mp4",
                timestamp=datetime.utcnow(),
                source=EventSource.API_INTEGRATION,
            )

    def test_metadata_optional(self):
        """Test that metadata defaults to empty dict."""
        event = IngestionEvent(
            event_id=uuid4(),
            trace_id=uuid4(),
            tenant_id="tenant-123",
            file_path="gs://bucket/_landing/file.mp4",
            file_type="video/mp4",
            timestamp=datetime.utcnow(),
            source=EventSource.API_INTEGRATION,
        )

        assert event.metadata == {}

    def test_metadata_dict(self):
        """Test that metadata can be a dict."""
        event = IngestionEvent(
            event_id=uuid4(),
            trace_id=uuid4(),
            tenant_id="tenant-123",
            file_path="gs://bucket/_landing/file.mp4",
            file_type="video/mp4",
            timestamp=datetime.utcnow(),
            source=EventSource.API_INTEGRATION,
            metadata={"key": "value", "count": 42},
        )

        assert event.metadata == {"key": "value", "count": 42}

    def test_serialization(self):
        """Test model serialization to dict."""
        event_id = uuid4()
        trace_id = uuid4()
        timestamp = datetime(2026, 1, 29, 12, 0, 0)

        event = IngestionEvent(
            event_id=event_id,
            trace_id=trace_id,
            tenant_id="tenant-123",
            file_path="gs://bucket/_landing/file.mp4",
            file_type="video/mp4",
            timestamp=timestamp,
            source=EventSource.BATCH_IMPORT,
        )

        data = event.model_dump()

        assert data["event_id"] == event_id
        assert data["tenant_id"] == "tenant-123"
        assert data["source"] == EventSource.BATCH_IMPORT


class TestProcessedEvent:
    """Tests for ProcessedEvent model."""

    def test_create_valid_processed_event(self):
        """Test creating a valid processed event."""
        event = ProcessedEvent(
            event_id=uuid4(),
            trace_id=uuid4(),
            timestamp=datetime.utcnow(),
            tenant_id="tenant-123",
            source_path="gs://bucket/_landing/file.mp4",
            destination_path="gs://bucket/tenant-123/raw/2026/01/29/file.mp4",
            status=ProcessingStatus.RAW_STORED,
            processing_duration_ms=150,
        )

        assert event.status == ProcessingStatus.RAW_STORED
        assert event.processing_duration_ms == 150
        assert event.error_message is None

    def test_failed_status_with_error(self):
        """Test creating a failed processed event with error message."""
        event = ProcessedEvent(
            event_id=uuid4(),
            trace_id=uuid4(),
            timestamp=datetime.utcnow(),
            tenant_id="tenant-123",
            source_path="gs://bucket/_landing/file.mp4",
            destination_path="",
            status=ProcessingStatus.FAILED,
            processing_duration_ms=50,
            error_message="File not found in landing zone",
        )

        assert event.status == ProcessingStatus.FAILED
        assert event.error_message == "File not found in landing zone"


class TestProcessingStatus:
    """Tests for ProcessingStatus enum."""

    def test_all_statuses_exist(self):
        """Test that all expected statuses exist."""
        assert ProcessingStatus.PENDING
        assert ProcessingStatus.VALIDATING
        assert ProcessingStatus.MOVING
        assert ProcessingStatus.RAW_STORED
        assert ProcessingStatus.FAILED
        assert ProcessingStatus.DUPLICATE

    def test_status_values(self):
        """Test status string values."""
        assert ProcessingStatus.PENDING.value == "pending"
        assert ProcessingStatus.RAW_STORED.value == "raw_stored"


class TestEventSource:
    """Tests for EventSource enum."""

    def test_all_sources_exist(self):
        """Test that all expected sources exist."""
        assert EventSource.KONG_GATEWAY
        assert EventSource.DJANGO_BACKEND
        assert EventSource.FRONTEND_UPLOAD
        assert EventSource.API_INTEGRATION
        assert EventSource.BATCH_IMPORT

    def test_source_values(self):
        """Test source string values."""
        assert EventSource.KONG_GATEWAY.value == "kong-gateway"
        assert EventSource.FRONTEND_UPLOAD.value == "frontend-upload"


class TestFileType:
    """Tests for FileType enum."""

    def test_all_file_types_exist(self):
        """Test that all expected file types exist."""
        assert FileType.IMAGE
        assert FileType.VIDEO
        assert FileType.DOCUMENT
        assert FileType.AUDIO
        assert FileType.OTHER


class TestFileMetadata:
    """Tests for FileMetadata model."""

    def test_create_file_metadata(self):
        """Test creating file metadata."""
        now = datetime.utcnow()
        metadata = FileMetadata(
            bucket="test-bucket",
            path="path/to/file.mp4",
            full_uri="gs://test-bucket/path/to/file.mp4",
            size_bytes=1024 * 1024,
            content_type="video/mp4",
            created_at=now,
            updated_at=now,
            md5_hash="abc123def456",
        )

        assert metadata.bucket == "test-bucket"
        assert metadata.path == "path/to/file.mp4"
        assert metadata.full_uri == "gs://test-bucket/path/to/file.mp4"
        assert metadata.size_bytes == 1024 * 1024
        assert metadata.content_type == "video/mp4"
        assert metadata.md5_hash == "abc123def456"
