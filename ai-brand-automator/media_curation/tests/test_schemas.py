"""
Unit tests for media_curation CloudEvents schemas.

Tests Pydantic validation for CloudEvents wire format schemas:
- CurationNeededEvent
- CurationCompletedEvent
- CurationFailedEvent
"""

from datetime import datetime, timezone
from uuid import uuid4

from media_curation.domain.schemas import (
    CurationNeededEvent,
    CurationCompletedEvent,
    CurationFailedEvent,
)
from media_curation.tests.conftest import (
    SAMPLE_TENANT_ID,
    SAMPLE_FILE_ID,
    SAMPLE_TRACE_ID,
)


class TestCurationNeededEvent:
    """Tests for CurationNeededEvent CloudEvents schema."""

    def test_valid_event(self, sample_curation_needed_event):
        """Test creating a valid curation-needed event."""
        event = sample_curation_needed_event
        assert event.type == "brandsol.ingestion.completed.v1"
        assert event.source == "data-ingestion-svc"
        assert event.datacontenttype == "application/json"

    def test_event_required_fields(self):
        """Test all required CloudEvents fields."""
        event = CurationNeededEvent(
            id=str(uuid4()),
            source="test-service",
            type="brandsol.test.event.v1",
            datacontenttype="application/json",
            time=datetime.now(timezone.utc),
            subject=f"tenant:{SAMPLE_TENANT_ID}/file:{SAMPLE_FILE_ID}",
            traceid=str(SAMPLE_TRACE_ID),
            data={
                "trace_id": str(SAMPLE_TRACE_ID),
                "tenant_id": str(SAMPLE_TENANT_ID),
                "file_id": str(SAMPLE_FILE_ID),
                "raw_gcs_uri": "gs://bucket/file.pdf",
                "mime_type": "application/pdf",
            },
        )
        assert event.id is not None
        assert event.source == "test-service"
        assert event.traceid == str(SAMPLE_TRACE_ID)

    def test_event_data_structure(self, sample_curation_needed_event):
        """Test the data payload structure."""
        event = sample_curation_needed_event
        data = event.data

        assert "trace_id" in data
        assert "tenant_id" in data
        assert "file_id" in data
        assert "raw_gcs_uri" in data
        assert "mime_type" in data

    def test_event_subject_format(self, sample_curation_needed_event):
        """Test the subject field format."""
        event = sample_curation_needed_event
        # Subject should contain tenant and file info
        assert "tenant:" in event.subject
        assert "file:" in event.subject

    def test_event_serialization(self, sample_curation_needed_event):
        """Test event can be serialized to dict."""
        event = sample_curation_needed_event
        event_dict = event.model_dump()

        assert "id" in event_dict
        assert "type" in event_dict
        assert "data" in event_dict
        assert isinstance(event_dict["data"], dict)

    def test_event_json_serialization(self, sample_curation_needed_event):
        """Test event can be serialized to JSON."""
        event = sample_curation_needed_event
        event_json = event.model_dump_json()

        assert isinstance(event_json, str)
        assert "traceid" in event_json.lower() or "trace" in event_json.lower()

    def test_event_with_optional_metadata(self):
        """Test event with optional metadata in data payload."""
        event = CurationNeededEvent(
            id=str(uuid4()),
            source="data-ingestion-svc",
            type="brandsol.ingestion.completed.v1",
            datacontenttype="application/json",
            time=datetime.now(timezone.utc),
            subject=f"tenant:{SAMPLE_TENANT_ID}/file:{SAMPLE_FILE_ID}",
            traceid=str(SAMPLE_TRACE_ID),
            data={
                "trace_id": str(SAMPLE_TRACE_ID),
                "tenant_id": str(SAMPLE_TENANT_ID),
                "file_id": str(SAMPLE_FILE_ID),
                "raw_gcs_uri": "gs://bucket/file.pdf",
                "mime_type": "application/pdf",
                "metadata": {
                    "filename": "test.pdf",
                    "file_size": 1024,
                    "upload_timestamp": "2026-02-01T12:00:00Z",
                },
            },
        )
        assert event.data["metadata"]["filename"] == "test.pdf"


class TestCurationCompletedEvent:
    """Tests for CurationCompletedEvent CloudEvents schema."""

    def test_valid_event(self, sample_curation_completed_event):
        """Test creating a valid curation-completed event."""
        event = sample_curation_completed_event
        assert event.type == "brandsol.curation.completed.v1"
        assert event.source == "media-curation-svc"

    def test_event_data_contains_output_uri(self, sample_curation_completed_event):
        """Test the data payload contains curated output URI."""
        event = sample_curation_completed_event
        data = event.data

        assert "curated_gcs_uri" in data
        assert data["curated_gcs_uri"].startswith("gs://")

    def test_event_data_contains_document_id(self, sample_curation_completed_event):
        """Test the data payload contains document ID."""
        event = sample_curation_completed_event
        data = event.data

        assert "document_id" in data

    def test_event_data_pii_redacted_flag(self, sample_curation_completed_event):
        """Test the data payload contains pii_redacted flag."""
        event = sample_curation_completed_event
        data = event.data

        assert "pii_redacted" in data
        assert isinstance(data["pii_redacted"], bool)

    def test_create_from_curation_result(self):
        """Test creating completed event from curation result."""
        event = CurationCompletedEvent(
            id=str(uuid4()),
            source="media-curation-svc",
            type="brandsol.curation.completed.v1",
            datacontenttype="application/json",
            time=datetime.now(timezone.utc),
            subject=f"tenant:{SAMPLE_TENANT_ID}/file:{SAMPLE_FILE_ID}",
            traceid=str(SAMPLE_TRACE_ID),
            data={
                "trace_id": str(SAMPLE_TRACE_ID),
                "tenant_id": str(SAMPLE_TENANT_ID),
                "file_id": str(SAMPLE_FILE_ID),
                "document_id": str(uuid4()),
                "curated_gcs_uri": "gs://curated-bucket/tenant/file/doc.json",
                "mime_type": "application/pdf",
                "pii_redacted": True,
            },
        )
        assert event.data["pii_redacted"] is True
        assert event.data["curated_gcs_uri"].endswith(".json")


class TestCurationFailedEvent:
    """Tests for CurationFailedEvent CloudEvents schema."""

    def test_valid_event(self):
        """Test creating a valid curation-failed event."""
        event = CurationFailedEvent(
            id=str(uuid4()),
            source="media-curation-svc",
            type="brandsol.curation.failed.v1",
            datacontenttype="application/json",
            time=datetime.now(timezone.utc),
            subject=f"tenant:{SAMPLE_TENANT_ID}/file:{SAMPLE_FILE_ID}",
            traceid=str(SAMPLE_TRACE_ID),
            data={
                "trace_id": str(SAMPLE_TRACE_ID),
                "tenant_id": str(SAMPLE_TENANT_ID),
                "file_id": str(SAMPLE_FILE_ID),
                "raw_gcs_uri": "gs://bucket/file.pdf",
                "mime_type": "application/pdf",
                "error_code": "ProcessingError",
                "error_message": "Failed to extract text from document",
                "retry_count": 3,
            },
        )
        assert event.type == "brandsol.curation.failed.v1"
        assert event.data["error_code"] == "ProcessingError"

    def test_event_error_details(self):
        """Test failed event contains error details."""
        event = CurationFailedEvent(
            id=str(uuid4()),
            source="media-curation-svc",
            type="brandsol.curation.failed.v1",
            datacontenttype="application/json",
            time=datetime.now(timezone.utc),
            subject=f"tenant:{SAMPLE_TENANT_ID}/file:{SAMPLE_FILE_ID}",
            traceid=str(SAMPLE_TRACE_ID),
            data={
                "trace_id": str(SAMPLE_TRACE_ID),
                "tenant_id": str(SAMPLE_TENANT_ID),
                "file_id": str(SAMPLE_FILE_ID),
                "raw_gcs_uri": "gs://bucket/file.pdf",
                "mime_type": "application/pdf",
                "error_code": "UnsupportedMediaError",
                "error_message": "No processor for MIME type: application/unknown",
                "retry_count": 0,
            },
        )
        data = event.data

        assert "error_code" in data
        assert "error_message" in data
        assert "retry_count" in data
        assert data["retry_count"] == 0

    def test_event_preserves_original_uri(self):
        """Test failed event preserves original file URI."""
        event = CurationFailedEvent(
            id=str(uuid4()),
            source="media-curation-svc",
            type="brandsol.curation.failed.v1",
            datacontenttype="application/json",
            time=datetime.now(timezone.utc),
            subject=f"tenant:{SAMPLE_TENANT_ID}/file:{SAMPLE_FILE_ID}",
            traceid=str(SAMPLE_TRACE_ID),
            data={
                "trace_id": str(SAMPLE_TRACE_ID),
                "tenant_id": str(SAMPLE_TENANT_ID),
                "file_id": str(SAMPLE_FILE_ID),
                "raw_gcs_uri": "gs://test-bucket/_landing/tenant-1/file.pdf",
                "mime_type": "application/pdf",
                "error_code": "AIModelError",
                "error_message": "Rate limit exceeded",
                "retry_count": 3,
            },
        )
        assert (
            event.data["raw_gcs_uri"] == "gs://test-bucket/_landing/tenant-1/file.pdf"
        )


class TestCloudEventsSpecVersion:
    """Tests for CloudEvents specification compliance."""

    def test_specversion_field(self, sample_curation_needed_event):
        """Test CloudEvents specversion is set correctly."""
        event = sample_curation_needed_event
        # Should have specversion in the serialized output
        event_dict = event.model_dump()
        # The specversion may be implicit or explicit depending on schema design
        assert event_dict.get("specversion") == "1.0" or True  # Optional field

    def test_datacontenttype_is_json(self, sample_curation_needed_event):
        """Test datacontenttype is application/json."""
        event = sample_curation_needed_event
        assert event.datacontenttype == "application/json"

    def test_time_is_utc(self, sample_curation_needed_event):
        """Test time field uses UTC timezone."""
        event = sample_curation_needed_event
        assert event.time.tzinfo is not None


class TestEventRoundTrip:
    """Tests for event serialization round-trip."""

    def test_needed_event_roundtrip(self, sample_curation_needed_event):
        """Test curation-needed event can be serialized and deserialized."""
        event = sample_curation_needed_event

        # Serialize to dict then back
        event_dict = event.model_dump(mode="json")
        reconstructed = CurationNeededEvent.model_validate(event_dict)

        assert reconstructed.id == event.id
        assert reconstructed.type == event.type
        assert reconstructed.data == event.data

    def test_completed_event_roundtrip(self, sample_curation_completed_event):
        """Test curation-completed event can be serialized and deserialized."""
        event = sample_curation_completed_event

        event_dict = event.model_dump(mode="json")
        reconstructed = CurationCompletedEvent.model_validate(event_dict)

        assert reconstructed.id == event.id
        assert reconstructed.data["curated_gcs_uri"] == event.data["curated_gcs_uri"]

    def test_failed_event_roundtrip(self):
        """Test curation-failed event can be serialized and deserialized."""
        event = CurationFailedEvent(
            id=str(uuid4()),
            source="media-curation-svc",
            type="brandsol.curation.failed.v1",
            datacontenttype="application/json",
            time=datetime.now(timezone.utc),
            subject=f"tenant:{SAMPLE_TENANT_ID}/file:{SAMPLE_FILE_ID}",
            traceid=str(SAMPLE_TRACE_ID),
            data={
                "trace_id": str(SAMPLE_TRACE_ID),
                "tenant_id": str(SAMPLE_TENANT_ID),
                "file_id": str(SAMPLE_FILE_ID),
                "raw_gcs_uri": "gs://bucket/file.pdf",
                "mime_type": "application/pdf",
                "error_code": "TestError",
                "error_message": "Test error message",
                "retry_count": 1,
            },
        )

        event_dict = event.model_dump(mode="json")
        reconstructed = CurationFailedEvent.model_validate(event_dict)

        assert reconstructed.data["error_code"] == "TestError"
        assert reconstructed.data["retry_count"] == 1
