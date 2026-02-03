"""
Unit Tests for Celery Tasks.

Tests for sync_document, batch_sync_documents, and retry_failed_syncs tasks.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from rag_index.domain.exceptions import (
    RateLimitExceededError,
    SyncError,
    SyncValidationError,
)
from rag_index.domain.models import SyncAction, SyncEvent, SyncResult
from rag_index.tasks.sync_tasks import (
    batch_sync_documents,
    retry_failed_syncs,
    run_async,
    sync_document,
    get_orchestrator,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def sample_event_data():
    """Create sample event data dictionary."""
    return {
        "event_id": str(uuid.uuid4()),
        "trace_id": str(uuid.uuid4()),
        "tenant_id": "tenant-123",
        "file_id": "file-456",
        "processed_gcs_uri": "gs://bucket/path/doc.json",
        "action": "UPSERT",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "metadata": {},
    }


@pytest.fixture
def sample_delete_event_data():
    """Create sample DELETE event data."""
    return {
        "event_id": str(uuid.uuid4()),
        "trace_id": str(uuid.uuid4()),
        "tenant_id": "tenant-123",
        "file_id": "file-456",
        "processed_gcs_uri": "",
        "action": "DELETE",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "metadata": {},
    }


@pytest.fixture
def mock_orchestrator():
    """Create mock SyncOrchestrator."""
    orchestrator = MagicMock()
    orchestrator.process_event = AsyncMock(
        return_value=SyncResult(
            event_id=uuid.uuid4(),
            trace_id=str(uuid.uuid4()),
            status="COMPLETED",
            operation_id="op-123",
            processing_time_ms=150,
        )
    )
    return orchestrator


# ============================================================================
# run_async Tests
# ============================================================================


class TestRunAsync:
    """Tests for run_async helper function."""

    def test_run_async_success(self):
        """Test running async coroutine successfully."""

        async def sample_coro():
            return "success"

        result = run_async(sample_coro())
        assert result == "success"

    def test_run_async_with_exception(self):
        """Test run_async propagates exceptions."""

        async def failing_coro():
            raise ValueError("test error")

        with pytest.raises(ValueError, match="test error"):
            run_async(failing_coro())


# ============================================================================
# get_orchestrator Tests
# ============================================================================


class TestGetOrchestrator:
    """Tests for get_orchestrator factory function."""

    @pytest.mark.django_db
    def test_get_orchestrator_returns_orchestrator(self, settings):
        """Test get_orchestrator creates orchestrator."""
        # Use pytest-django settings fixture
        settings.RAG_INDEX_MOCK_MODE = True
        settings.GCP_PROJECT_ID = "test-project"
        settings.GCP_LOCATION = "us-central1"
        settings.VERTEX_AI_DATA_STORE_ID = "test-store"
        settings.REDIS_URL = "redis://localhost:6379"
        settings.KAFKA_BOOTSTRAP_SERVERS = None

        orchestrator = get_orchestrator()

        assert orchestrator is not None
        assert orchestrator._vertex_ai is not None
        assert orchestrator._gcs is not None
        assert orchestrator._redis is not None


# ============================================================================
# sync_document Unit Logic Tests
# ============================================================================


class TestSyncDocumentLogic:
    """Tests for sync_document task logic without Celery infrastructure."""

    def test_event_parsing_valid(self, sample_event_data):
        """Test parsing valid event data."""
        event = SyncEvent.from_dict(sample_event_data)
        assert event.tenant_id == "tenant-123"
        assert event.action == SyncAction.UPSERT

    def test_event_parsing_delete(self, sample_delete_event_data):
        """Test parsing DELETE event data."""
        event = SyncEvent.from_dict(sample_delete_event_data)
        assert event.action == SyncAction.DELETE

    def test_event_parsing_invalid(self):
        """Test parsing invalid event data raises exception."""
        invalid_data = {"invalid": "data"}
        with pytest.raises(Exception):
            SyncEvent.from_dict(invalid_data)


# ============================================================================
# batch_sync_documents Tests (no Celery infrastructure needed)
# ============================================================================


class TestBatchSyncDocumentsLogic:
    """Tests for batch_sync_documents task logic."""

    def test_batch_dispatch_calls_sync_document(self, sample_event_data):
        """Test batch dispatches individual sync_document tasks."""
        mock_async_result = MagicMock()
        mock_async_result.id = "sub-task-123"

        events = [sample_event_data, sample_event_data]

        # Create a mock self with request
        mock_self = MagicMock()
        mock_self.request = MagicMock()
        mock_self.request.id = "task-123"

        # Get the actual underlying function (not the bound method)
        # __wrapped__ returns a method, __wrapped__.__func__ returns the function
        wrapped_func = batch_sync_documents.__wrapped__.__func__

        # Create a mock task
        mock_task = MagicMock()
        mock_task.delay.return_value = mock_async_result

        # Save original and patch globals (must patch the function's globals)
        original = wrapped_func.__globals__["sync_document"]
        wrapped_func.__globals__["sync_document"] = mock_task

        try:
            result = wrapped_func(mock_self, events)

            assert result["total"] == 2
            assert result["dispatched"] == 2
            assert mock_task.delay.call_count == 2
        finally:
            # Restore original globals
            wrapped_func.__globals__["sync_document"] = original


# ============================================================================
# Task Configuration Tests
# ============================================================================


class TestTaskConfiguration:
    """Tests for task configuration and attributes."""

    def test_sync_document_max_retries(self):
        """Test sync_document has correct max_retries."""
        assert sync_document.max_retries == 5

    def test_sync_document_acks_late(self):
        """Test sync_document acks late."""
        assert sync_document.acks_late is True

    def test_sync_document_autoretry_for_sync_error(self):
        """Test sync_document autoretries for SyncError."""
        assert SyncError in sync_document.autoretry_for

    def test_sync_document_retry_backoff(self):
        """Test sync_document has retry backoff enabled."""
        assert sync_document.retry_backoff is True

    def test_sync_document_retry_jitter(self):
        """Test sync_document has retry jitter enabled."""
        assert sync_document.retry_jitter is True

    def test_batch_sync_max_retries(self):
        """Test batch_sync has correct max_retries."""
        assert batch_sync_documents.max_retries == 3

    def test_task_names(self):
        """Test tasks have correct names."""
        assert sync_document.name == "rag_index.tasks.sync_document"
        assert batch_sync_documents.name == "rag_index.tasks.batch_sync_documents"
        assert retry_failed_syncs.name == "rag_index.tasks.retry_failed_syncs"

    def test_sync_document_reject_on_worker_lost(self):
        """Test sync_document requeues on worker lost."""
        assert sync_document.reject_on_worker_lost is True


# ============================================================================
# Exception Handling Logic Tests
# ============================================================================


class TestExceptionHandling:
    """Tests for exception handling logic."""

    def test_rate_limit_error_attributes(self):
        """Test RateLimitExceededError has required attributes."""
        error = RateLimitExceededError(
            limit=600,
            current_count=600,
            retry_after_seconds=30,
        )
        assert error.limit == 600
        assert error.current_count == 600
        assert error.retry_after_seconds == 30

    def test_sync_validation_error_not_retryable(self):
        """Test SyncValidationError is a non-retryable error type."""
        _ = SyncValidationError("tenant_id is required")
        # Validation errors should not be in autoretry_for
        assert SyncValidationError not in sync_document.autoretry_for

    def test_sync_error_is_retryable(self):
        """Test SyncError is in autoretry_for."""
        assert SyncError in sync_document.autoretry_for
