"""
Unit Tests for Domain Models.

Tests for SyncEvent, SyncResult, SyncStatusRecord, and RateLimitStatus models.
"""

import json
from datetime import datetime, timezone
from uuid import UUID

import pytest
from hypothesis import given, settings, strategies as st
from pydantic import ValidationError as PydanticValidationError

from rag_index.domain.models import (
    SyncAction,
    SyncEvent,
    SyncResult,
    SyncStatus,
    SyncStatusRecord,
    RateLimitStatus,
)


# ============================================================================
# SyncAction Tests
# ============================================================================


class TestSyncAction:
    """Tests for SyncAction enum."""

    def test_upsert_action_value(self):
        """Test UPSERT action has correct value."""
        assert SyncAction.UPSERT.value == "UPSERT"

    def test_delete_action_value(self):
        """Test DELETE action has correct value."""
        assert SyncAction.DELETE.value == "DELETE"

    def test_action_is_string_enum(self):
        """Test that SyncAction is a string enum."""
        assert isinstance(SyncAction.UPSERT, str)
        assert SyncAction.UPSERT == "UPSERT"

    def test_action_from_string(self):
        """Test creating action from string."""
        assert SyncAction("UPSERT") == SyncAction.UPSERT
        assert SyncAction("DELETE") == SyncAction.DELETE

    def test_invalid_action_raises_error(self):
        """Test that invalid action raises ValueError."""
        with pytest.raises(ValueError):
            SyncAction("INVALID")


# ============================================================================
# SyncEvent Tests
# ============================================================================


class TestSyncEvent:
    """Tests for SyncEvent model."""

    def test_create_sync_event(self, sample_sync_event):
        """Test creating a valid SyncEvent."""
        assert sample_sync_event.action == SyncAction.UPSERT
        assert sample_sync_event.processed_gcs_uri.startswith("gs://")
        assert sample_sync_event.metadata == {"source": "test"}

    def test_sync_event_default_values(
        self, sample_trace_id, sample_tenant_id, sample_file_id
    ):
        """Test SyncEvent default values."""
        event = SyncEvent(
            trace_id=sample_trace_id,
            tenant_id=sample_tenant_id,
            file_id=sample_file_id,
            action=SyncAction.DELETE,
        )
        assert isinstance(event.event_id, UUID)
        assert event.processed_gcs_uri == ""
        assert isinstance(event.timestamp, datetime)
        assert event.metadata == {}

    def test_sync_event_document_id_property(self, sample_sync_event):
        """Test document_id property aliases file_id."""
        assert sample_sync_event.document_id == sample_sync_event.file_id

    def test_sync_event_to_dict(self, sample_sync_event):
        """Test SyncEvent serialization to dict."""
        data = sample_sync_event.to_dict()
        assert data["event_id"] == str(sample_sync_event.event_id)
        assert data["trace_id"] == sample_sync_event.trace_id
        assert data["tenant_id"] == sample_sync_event.tenant_id
        assert data["file_id"] == sample_sync_event.file_id
        assert data["action"] == "UPSERT"
        assert "timestamp" in data

    def test_sync_event_from_dict(self, sample_sync_event):
        """Test SyncEvent deserialization from dict."""
        data = sample_sync_event.to_dict()
        restored = SyncEvent.from_dict(data)
        assert restored.event_id == sample_sync_event.event_id
        assert restored.trace_id == sample_sync_event.trace_id
        assert restored.action == sample_sync_event.action

    def test_sync_event_gcs_uri_validation_valid(
        self, sample_trace_id, sample_tenant_id, sample_file_id
    ):
        """Test GCS URI validation accepts valid URIs."""
        event = SyncEvent(
            trace_id=sample_trace_id,
            tenant_id=sample_tenant_id,
            file_id=sample_file_id,
            processed_gcs_uri="gs://bucket/path/file.json",
            action=SyncAction.UPSERT,
        )
        assert event.processed_gcs_uri == "gs://bucket/path/file.json"

    def test_sync_event_gcs_uri_validation_invalid(
        self, sample_trace_id, sample_tenant_id, sample_file_id
    ):
        """Test GCS URI validation rejects invalid URIs."""
        with pytest.raises(PydanticValidationError):
            SyncEvent(
                trace_id=sample_trace_id,
                tenant_id=sample_tenant_id,
                file_id=sample_file_id,
                processed_gcs_uri="https://invalid-uri",
                action=SyncAction.UPSERT,
            )

    def test_sync_event_gcs_uri_empty_allowed_for_delete(self, sample_delete_event):
        """Test empty GCS URI is allowed for DELETE actions."""
        assert sample_delete_event.processed_gcs_uri == ""
        assert sample_delete_event.action == SyncAction.DELETE

    def test_sync_event_json_serializable(self, sample_sync_event):
        """Test SyncEvent can be serialized to JSON."""
        data = sample_sync_event.to_dict()
        json_str = json.dumps(data)
        restored = json.loads(json_str)
        assert restored["event_id"] == str(sample_sync_event.event_id)

    @pytest.mark.property
    @given(
        trace_id=st.text(
            min_size=1,
            max_size=50,
            alphabet=st.characters(whitelist_categories=("L", "N", "Pd")),
        ),
        tenant_id=st.text(
            min_size=1,
            max_size=50,
            alphabet=st.characters(whitelist_categories=("L", "N", "Pd")),
        ),
        file_id=st.text(
            min_size=1,
            max_size=100,
            alphabet=st.characters(whitelist_categories=("L", "N", "Pd")),
        ),
    )
    @settings(max_examples=20)
    def test_sync_event_property_roundtrip(self, trace_id, tenant_id, file_id):
        """Property test: SyncEvent serialization roundtrip."""
        event = SyncEvent(
            trace_id=trace_id,
            tenant_id=tenant_id,
            file_id=file_id,
            action=SyncAction.DELETE,
        )
        data = event.to_dict()
        restored = SyncEvent.from_dict(data)
        assert restored.trace_id == trace_id
        assert restored.tenant_id == tenant_id
        assert restored.file_id == file_id


# ============================================================================
# SyncResult Tests
# ============================================================================


class TestSyncResult:
    """Tests for SyncResult model."""

    def test_create_sync_result(self, sample_sync_result):
        """Test creating a valid SyncResult."""
        assert sample_sync_result.status == "COMPLETED"
        assert sample_sync_result.operation_id == "operation-123"
        assert sample_sync_result.processing_time_ms == 150

    def test_sync_result_failed_status(self, sample_failed_result):
        """Test creating a failed SyncResult."""
        assert sample_failed_result.status == "FAILED"
        assert sample_failed_result.error_message == "Test error message"

    def test_sync_result_pending_status(self, sample_event_id, sample_trace_id):
        """Test creating a pending SyncResult."""
        result = SyncResult(
            event_id=sample_event_id,
            trace_id=sample_trace_id,
            status="PENDING",
        )
        assert result.status == "PENDING"
        assert result.operation_id is None

    def test_sync_result_to_dict(self, sample_sync_result):
        """Test SyncResult serialization to dict."""
        data = sample_sync_result.to_dict()
        assert data["event_id"] == str(sample_sync_result.event_id)
        assert data["status"] == "COMPLETED"
        assert data["operation_id"] == "operation-123"

    def test_sync_result_from_dict(self, sample_sync_result):
        """Test SyncResult deserialization from dict."""
        data = sample_sync_result.to_dict()
        restored = SyncResult.from_dict(data)
        assert restored.event_id == sample_sync_result.event_id
        assert restored.status == sample_sync_result.status

    def test_sync_result_invalid_status_raises_error(
        self, sample_event_id, sample_trace_id
    ):
        """Test that invalid status raises error."""
        with pytest.raises(PydanticValidationError):
            SyncResult(
                event_id=sample_event_id,
                trace_id=sample_trace_id,
                status="INVALID_STATUS",
            )


# ============================================================================
# SyncStatusRecord Tests
# ============================================================================


class TestSyncStatusRecord:
    """Tests for SyncStatusRecord model."""

    def test_create_status_record(self, sample_status_record):
        """Test creating a valid SyncStatusRecord."""
        assert sample_status_record.status == SyncStatus.IN_PROGRESS
        assert sample_status_record.retry_count == 0
        assert isinstance(sample_status_record.last_updated, datetime)

    def test_status_record_pending(
        self, sample_event_id, sample_trace_id, sample_tenant_id, sample_file_id
    ):
        """Test creating a PENDING status record."""
        record = SyncStatusRecord(
            event_id=sample_event_id,
            trace_id=sample_trace_id,
            tenant_id=sample_tenant_id,
            file_id=sample_file_id,
            action=SyncAction.UPSERT,
            status=SyncStatus.PENDING,
        )
        assert record.status == SyncStatus.PENDING

    def test_status_record_completed(
        self, sample_event_id, sample_trace_id, sample_tenant_id, sample_file_id
    ):
        """Test creating a COMPLETED status record."""
        now = datetime.now(timezone.utc)
        record = SyncStatusRecord(
            event_id=sample_event_id,
            trace_id=sample_trace_id,
            tenant_id=sample_tenant_id,
            file_id=sample_file_id,
            action=SyncAction.UPSERT,
            status=SyncStatus.COMPLETED,
            last_updated=now,
        )
        assert record.status == SyncStatus.COMPLETED
        assert record.last_updated == now

    def test_status_record_failed(
        self, sample_event_id, sample_trace_id, sample_tenant_id, sample_file_id
    ):
        """Test creating a FAILED status record."""
        record = SyncStatusRecord(
            event_id=sample_event_id,
            trace_id=sample_trace_id,
            tenant_id=sample_tenant_id,
            file_id=sample_file_id,
            action=SyncAction.DELETE,
            status=SyncStatus.FAILED,
            error_message="Connection timeout",
            retry_count=3,
        )
        assert record.status == SyncStatus.FAILED
        assert record.error_message == "Connection timeout"
        assert record.retry_count == 3

    def test_status_record_to_dict(self, sample_status_record):
        """Test SyncStatusRecord serialization to dict."""
        data = sample_status_record.to_dict()
        assert data["event_id"] == str(sample_status_record.event_id)
        assert data["status"] == "IN_PROGRESS"
        assert "last_updated" in data

    def test_status_record_from_dict(self, sample_status_record):
        """Test SyncStatusRecord deserialization from dict."""
        data = sample_status_record.to_dict()
        restored = SyncStatusRecord.from_dict(data)
        assert restored.event_id == sample_status_record.event_id
        assert restored.status == sample_status_record.status


# ============================================================================
# RateLimitStatus Tests
# ============================================================================


class TestRateLimitStatus:
    """Tests for RateLimitStatus model."""

    def test_create_rate_limit_status(self, sample_rate_limit_status):
        """Test creating a valid RateLimitStatus."""
        assert sample_rate_limit_status.current_count == 100
        assert sample_rate_limit_status.limit == 600
        assert sample_rate_limit_status.remaining == 500

    def test_rate_limit_status_default_values(self):
        """Test RateLimitStatus default values."""
        status = RateLimitStatus()
        assert status.current_count == 0
        assert status.limit == 600
        assert status.remaining == 600

    def test_rate_limit_is_limited_false(self, sample_rate_limit_status):
        """Test is_limited property when not limited."""
        assert sample_rate_limit_status.is_limited is False

    def test_rate_limit_is_limited_true(self):
        """Test is_limited property when limited."""
        status = RateLimitStatus(current_count=600, limit=600)
        assert status.is_limited is True

    def test_rate_limit_available(self, sample_rate_limit_status):
        """Test available property."""
        assert sample_rate_limit_status.available == 500

    def test_rate_limit_available_zero(self):
        """Test available property when exhausted."""
        status = RateLimitStatus(current_count=700, limit=600)
        assert status.available == 0
