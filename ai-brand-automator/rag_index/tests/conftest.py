"""
Test Configuration for RAG Index Service.

Provides pytest fixtures for testing domain models,
ports, adapters, and service components.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from rag_index.domain.models import (
    SyncAction,
    SyncEvent,
    SyncResult,
    SyncStatus,
    SyncStatusRecord,
    RateLimitStatus,
)
from rag_index.domain.schemas import (
    RagSyncReadyEvent,
    RagSyncReadyEventData,
)


# ============================================================================
# Domain Model Fixtures
# ============================================================================


@pytest.fixture
def sample_event_id():
    """Generate a sample event ID."""
    return uuid4()


@pytest.fixture
def sample_trace_id():
    """Generate a sample trace ID."""
    return f"trace-{uuid4().hex[:16]}"


@pytest.fixture
def sample_tenant_id():
    """Generate a sample tenant ID."""
    return f"tenant-{uuid4().hex[:8]}"


@pytest.fixture
def sample_file_id():
    """Generate a sample file ID."""
    return f"file-{uuid4().hex[:12]}"


@pytest.fixture
def sample_gcs_uri(sample_tenant_id, sample_file_id):
    """Generate a sample GCS URI."""
    return f"gs://prevision-curated-docs/{sample_tenant_id}/{sample_file_id}.json"


@pytest.fixture
def sample_sync_event(
    sample_event_id,
    sample_trace_id,
    sample_tenant_id,
    sample_file_id,
    sample_gcs_uri,
):
    """Create a sample SyncEvent for testing."""
    return SyncEvent(
        event_id=sample_event_id,
        trace_id=sample_trace_id,
        tenant_id=sample_tenant_id,
        file_id=sample_file_id,
        processed_gcs_uri=sample_gcs_uri,
        action=SyncAction.UPSERT,
        metadata={"source": "test"},
    )


@pytest.fixture
def sample_delete_event(
    sample_event_id,
    sample_trace_id,
    sample_tenant_id,
    sample_file_id,
):
    """Create a sample DELETE SyncEvent for testing."""
    return SyncEvent(
        event_id=sample_event_id,
        trace_id=sample_trace_id,
        tenant_id=sample_tenant_id,
        file_id=sample_file_id,
        processed_gcs_uri="",
        action=SyncAction.DELETE,
    )


@pytest.fixture
def sample_sync_result(sample_event_id, sample_trace_id):
    """Create a sample SyncResult for testing."""
    return SyncResult(
        event_id=sample_event_id,
        trace_id=sample_trace_id,
        status="COMPLETED",
        operation_id="operation-123",
        processing_time_ms=150,
    )


@pytest.fixture
def sample_failed_result(sample_event_id, sample_trace_id):
    """Create a sample failed SyncResult for testing."""
    return SyncResult(
        event_id=sample_event_id,
        trace_id=sample_trace_id,
        status="FAILED",
        error_message="Test error message",
        processing_time_ms=50,
    )


@pytest.fixture
def sample_status_record(
    sample_event_id, sample_trace_id, sample_tenant_id, sample_file_id
):
    """Create a sample SyncStatusRecord for testing."""
    return SyncStatusRecord(
        event_id=sample_event_id,
        trace_id=sample_trace_id,
        tenant_id=sample_tenant_id,
        file_id=sample_file_id,
        action=SyncAction.UPSERT,
        status=SyncStatus.IN_PROGRESS,
        retry_count=0,
    )


@pytest.fixture
def sample_rate_limit_status():
    """Create a sample RateLimitStatus for testing."""
    return RateLimitStatus(
        current_count=100,
        limit=600,
        window_seconds=60,
        remaining=500,
    )


# ============================================================================
# CloudEvents Schema Fixtures
# ============================================================================


@pytest.fixture
def sample_rag_sync_ready_event(
    sample_trace_id,
    sample_tenant_id,
    sample_file_id,
    sample_gcs_uri,
):
    """Create a sample RagSyncReadyEvent for testing."""
    return RagSyncReadyEvent(
        data=RagSyncReadyEventData(
            tenant_id=sample_tenant_id,
            file_id=sample_file_id,
            processed_gcs_uri=sample_gcs_uri,
            action=SyncAction.UPSERT,
            trace_id=sample_trace_id,
        )
    )


@pytest.fixture
def sample_kafka_message(sample_rag_sync_ready_event):
    """Create a sample Kafka message dict for testing."""
    return sample_rag_sync_ready_event.model_dump(mode="json")


# ============================================================================
# Mock Fixtures
# ============================================================================


@pytest.fixture
def mock_redis():
    """Create a mock Redis client."""
    redis_mock = MagicMock()
    redis_mock.get = MagicMock(return_value=None)
    redis_mock.set = MagicMock(return_value=True)
    redis_mock.delete = MagicMock(return_value=1)
    redis_mock.incr = MagicMock(return_value=1)
    redis_mock.expire = MagicMock(return_value=True)
    redis_mock.ttl = MagicMock(return_value=60)
    return redis_mock


@pytest.fixture
def mock_kafka_producer():
    """Create a mock Kafka producer."""
    producer_mock = AsyncMock()
    producer_mock.send = AsyncMock(return_value=None)
    producer_mock.flush = AsyncMock(return_value=None)
    return producer_mock


@pytest.fixture
def mock_vertex_ai_client():
    """Create a mock Vertex AI Discovery Engine client."""
    client_mock = MagicMock()
    client_mock.import_documents = MagicMock()
    client_mock.delete_document = MagicMock()
    return client_mock


@pytest.fixture
def mock_gcs_client():
    """Create a mock GCS client."""
    client_mock = MagicMock()
    bucket_mock = MagicMock()
    blob_mock = MagicMock()
    blob_mock.download_as_text = MagicMock(return_value='{"content": "test"}')
    bucket_mock.blob = MagicMock(return_value=blob_mock)
    client_mock.bucket = MagicMock(return_value=bucket_mock)
    return client_mock
