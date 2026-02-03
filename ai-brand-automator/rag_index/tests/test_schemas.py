"""
Unit Tests for CloudEvents Schemas.

Tests for RagSyncReadyEvent, RagSyncCompletedEvent, and RagSyncDLQEvent schemas.
"""

import json


from rag_index.domain.models import SyncAction, SyncEvent
from rag_index.domain.schemas import (
    CloudEventBase,
    RagSyncReadyEvent,
    RagSyncReadyEventData,
    RagSyncCompletedEvent,
    RagSyncDLQEvent,
)


# ============================================================================
# CloudEventBase Tests
# ============================================================================


class TestCloudEventBase:
    """Tests for CloudEventBase schema."""

    def test_default_specversion(self):
        """Test default specversion is 1.0."""
        event = CloudEventBase(source="/test", type="test.event")
        assert event.specversion == "1.0"

    def test_auto_generated_id(self):
        """Test that id is auto-generated."""
        event = CloudEventBase(source="/test", type="test.event")
        assert event.id is not None
        assert len(event.id) == 36  # UUID format

    def test_auto_generated_time(self):
        """Test that time is auto-generated."""
        event = CloudEventBase(source="/test", type="test.event")
        assert event.time is not None

    def test_default_content_type(self):
        """Test default datacontenttype is JSON."""
        event = CloudEventBase(source="/test", type="test.event")
        assert event.datacontenttype == "application/json"


# ============================================================================
# RagSyncReadyEvent Tests
# ============================================================================


class TestRagSyncReadyEvent:
    """Tests for RagSyncReadyEvent schema."""

    def test_create_rag_sync_ready_event(self, sample_rag_sync_ready_event):
        """Test creating a valid RagSyncReadyEvent."""
        assert sample_rag_sync_ready_event.type == "com.prevision.rag.sync.ready"
        assert sample_rag_sync_ready_event.source == "/media-curation-svc"
        assert sample_rag_sync_ready_event.data.action == SyncAction.UPSERT

    def test_from_kafka_message(self, sample_kafka_message):
        """Test parsing from Kafka message."""
        event = RagSyncReadyEvent.from_kafka_message(sample_kafka_message)
        assert event.type == "com.prevision.rag.sync.ready"
        assert event.data.tenant_id is not None

    def test_to_sync_event(self, sample_rag_sync_ready_event):
        """Test converting to SyncEvent domain model."""
        sync_event = sample_rag_sync_ready_event.to_sync_event()
        assert isinstance(sync_event, SyncEvent)
        assert sync_event.tenant_id == sample_rag_sync_ready_event.data.tenant_id
        assert sync_event.file_id == sample_rag_sync_ready_event.data.file_id
        assert sync_event.action == sample_rag_sync_ready_event.data.action


class TestRagSyncReadyEventData:
    """Tests for RagSyncReadyEventData schema."""

    def test_create_data(
        self, sample_trace_id, sample_tenant_id, sample_file_id, sample_gcs_uri
    ):
        """Test creating event data."""
        data = RagSyncReadyEventData(
            tenant_id=sample_tenant_id,
            file_id=sample_file_id,
            processed_gcs_uri=sample_gcs_uri,
            action=SyncAction.UPSERT,
            trace_id=sample_trace_id,
        )
        assert data.tenant_id == sample_tenant_id
        assert data.metadata == {}


# ============================================================================
# RagSyncCompletedEvent Tests
# ============================================================================


class TestRagSyncCompletedEvent:
    """Tests for RagSyncCompletedEvent schema."""

    def test_create_from_sync_result(
        self, sample_sync_result, sample_tenant_id, sample_file_id
    ):
        """Test creating from SyncResult."""
        event = RagSyncCompletedEvent.from_sync_result(
            result=sample_sync_result,
            tenant_id=sample_tenant_id,
            file_id=sample_file_id,
        )
        assert event.type == "com.prevision.rag.sync.completed"
        assert event.source == "/rag-index-svc"
        assert event.data.status == "COMPLETED"
        assert event.data.tenant_id == sample_tenant_id

    def test_to_kafka_message(
        self, sample_sync_result, sample_tenant_id, sample_file_id
    ):
        """Test converting to Kafka message."""
        event = RagSyncCompletedEvent.from_sync_result(
            result=sample_sync_result,
            tenant_id=sample_tenant_id,
            file_id=sample_file_id,
        )
        message = event.to_kafka_message()
        assert isinstance(message, dict)
        assert message["type"] == "com.prevision.rag.sync.completed"
        assert "data" in message

    def test_json_serializable(
        self, sample_sync_result, sample_tenant_id, sample_file_id
    ):
        """Test event can be serialized to JSON."""
        event = RagSyncCompletedEvent.from_sync_result(
            result=sample_sync_result,
            tenant_id=sample_tenant_id,
            file_id=sample_file_id,
        )
        message = event.to_kafka_message()
        json_str = json.dumps(message)
        assert json_str is not None


# ============================================================================
# RagSyncDLQEvent Tests
# ============================================================================


class TestRagSyncDLQEvent:
    """Tests for RagSyncDLQEvent schema."""

    def test_create_from_failed_event(self, sample_trace_id):
        """Test creating from failed event."""
        original_event = {
            "type": "com.prevision.rag.sync.ready",
            "data": {"file_id": "file-123", "tenant_id": "tenant-456"},
        }
        error = ValueError("Test processing error")

        dlq_event = RagSyncDLQEvent.from_failed_event(
            original_event=original_event,
            error=error,
            trace_id=sample_trace_id,
            retry_count=3,
        )

        assert dlq_event.type == "com.prevision.rag.sync.dlq"
        assert dlq_event.source == "/rag-index-svc"
        assert dlq_event.data.error_type == "ValueError"
        assert dlq_event.data.retry_count == 3

    def test_to_kafka_message(self, sample_trace_id):
        """Test converting to Kafka message."""
        original_event = {"data": {"file_id": "file-123"}}
        error = Exception("Test error")

        dlq_event = RagSyncDLQEvent.from_failed_event(
            original_event=original_event,
            error=error,
            trace_id=sample_trace_id,
        )
        message = dlq_event.to_kafka_message()

        assert isinstance(message, dict)
        assert message["data"]["original_event"] == original_event

    def test_dlq_preserves_original_event(self, sample_trace_id):
        """Test that DLQ event preserves original event data."""
        original = {"type": "test", "data": {"key": "value"}}
        error = Exception("Error")

        dlq_event = RagSyncDLQEvent.from_failed_event(
            original_event=original,
            error=error,
            trace_id=sample_trace_id,
        )

        assert dlq_event.data.original_event == original
