"""
Unit Tests for SyncOrchestrator.process_inline_document().

Tests the inline document sync path (no GCS fetch) used by DB-to-RAG sync.
"""

import uuid
from unittest.mock import AsyncMock

import pytest

from rag_index.domain.exceptions import (
    RateLimitExceededError,
    SyncError,
    SyncValidationError,
)
from rag_index.domain.models import (
    SyncAction,
    SyncEvent,
    SyncResult,
    SyncStatus,
)
from rag_index.services.sync_orchestrator import SyncOrchestrator

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_vertex_ai():
    port = AsyncMock()
    port.upsert_document = AsyncMock(
        return_value=SyncResult(
            event_id=uuid.uuid4(),
            trace_id="trace-inline",
            status="COMPLETED",
            operation_id="op-inline-123",
        )
    )
    port.check_connection = AsyncMock(return_value=True)
    return port


@pytest.fixture
def mock_gcs():
    port = AsyncMock()
    port.check_connection = AsyncMock(return_value=True)
    return port


@pytest.fixture
def mock_redis():
    port = AsyncMock()
    port.set_sync_status = AsyncMock()
    port.get_sync_status = AsyncMock(return_value=None)
    port.check_connection = AsyncMock(return_value=True)
    return port


@pytest.fixture
def mock_kafka():
    port = AsyncMock()
    port.publish = AsyncMock()
    port.check_connection = AsyncMock(return_value=True)
    return port


@pytest.fixture
def orchestrator(mock_vertex_ai, mock_gcs, mock_redis, mock_kafka):
    return SyncOrchestrator(
        vertex_ai_port=mock_vertex_ai,
        gcs_port=mock_gcs,
        redis_port=mock_redis,
        kafka_port=mock_kafka,
    )


@pytest.fixture
def inline_event():
    """Inline event — no processed_gcs_uri needed."""
    return SyncEvent(
        trace_id="trace-inline",
        tenant_id="tenant-7",
        file_id="company-42",
        action=SyncAction.UPSERT,
        metadata={"source": "db_sync", "model_name": "Company"},
    )


@pytest.fixture
def sample_document():
    return {
        "document_type": "company_profile",
        "metadata": {"name": "Acme Corp", "industry": "Technology"},
        "extracted_text": "Company: Acme Corp\nIndustry: Technology",
    }


# ============================================================================
# Happy path
# ============================================================================


@pytest.mark.asyncio
async def test_process_inline_document_success(
    orchestrator, mock_vertex_ai, mock_redis, mock_kafka, inline_event, sample_document
):
    result = await orchestrator.process_inline_document(inline_event, sample_document)

    assert result.status == "COMPLETED"
    assert result.processing_time_ms >= 0

    # Vertex AI was called with the document
    mock_vertex_ai.upsert_document.assert_awaited_once_with(
        inline_event, sample_document
    )

    # GCS was NOT called
    orchestrator._gcs.read_document.assert_not_awaited()

    # Status was updated to IN_PROGRESS then COMPLETED
    assert mock_redis.set_sync_status.await_count == 2

    # Kafka completion event was published
    mock_kafka.publish.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_inline_document_no_gcs_uri_required(
    orchestrator, inline_event, sample_document
):
    """Inline events don't need processed_gcs_uri."""
    assert inline_event.processed_gcs_uri == ""
    result = await orchestrator.process_inline_document(inline_event, sample_document)
    assert result.status == "COMPLETED"


# ============================================================================
# Validation
# ============================================================================


@pytest.mark.asyncio
async def test_inline_validation_missing_tenant_id(orchestrator, sample_document):
    event = SyncEvent(
        trace_id="t",
        tenant_id="",
        file_id="company-1",
        action=SyncAction.UPSERT,
    )
    with pytest.raises(SyncValidationError, match="tenant_id"):
        await orchestrator.process_inline_document(event, sample_document)


@pytest.mark.asyncio
async def test_inline_validation_missing_file_id(orchestrator, sample_document):
    event = SyncEvent(
        trace_id="t",
        tenant_id="tenant-1",
        file_id="",
        action=SyncAction.UPSERT,
    )
    with pytest.raises(SyncValidationError, match="file_id"):
        await orchestrator.process_inline_document(event, sample_document)


# ============================================================================
# Error handling
# ============================================================================


@pytest.mark.asyncio
async def test_inline_rate_limit_error(
    orchestrator, mock_vertex_ai, mock_redis, inline_event, sample_document
):
    mock_vertex_ai.upsert_document.side_effect = RateLimitExceededError(
        "Rate limit exceeded",
        limit=600,
        current_count=601,
    )

    with pytest.raises(RateLimitExceededError):
        await orchestrator.process_inline_document(inline_event, sample_document)

    # Status should be set to FAILED
    calls = mock_redis.set_sync_status.call_args_list
    last_call = calls[-1]
    status_record = last_call.kwargs.get("status") or last_call[1].get("status")
    assert status_record.status == SyncStatus.FAILED


@pytest.mark.asyncio
async def test_inline_general_error_raises_sync_error(
    orchestrator, mock_vertex_ai, inline_event, sample_document
):
    mock_vertex_ai.upsert_document.side_effect = RuntimeError("Connection lost")

    with pytest.raises(SyncError, match="Failed to process inline document"):
        await orchestrator.process_inline_document(inline_event, sample_document)


@pytest.mark.asyncio
async def test_inline_error_publishes_to_dlq(
    orchestrator, mock_vertex_ai, mock_kafka, inline_event, sample_document
):
    mock_vertex_ai.upsert_document.side_effect = RuntimeError("Boom")

    with pytest.raises(SyncError):
        await orchestrator.process_inline_document(inline_event, sample_document)

    # DLQ publish should have been attempted
    assert mock_kafka.publish.await_count >= 1
    dlq_call = mock_kafka.publish.call_args_list[-1]
    assert dlq_call.kwargs.get("topic") == "rag-sync-dlq"


# ============================================================================
# No Kafka configured
# ============================================================================


@pytest.mark.asyncio
async def test_inline_no_kafka_succeeds(
    mock_vertex_ai, mock_gcs, mock_redis, inline_event, sample_document
):
    orchestrator = SyncOrchestrator(
        vertex_ai_port=mock_vertex_ai,
        gcs_port=mock_gcs,
        redis_port=mock_redis,
        kafka_port=None,
    )

    result = await orchestrator.process_inline_document(inline_event, sample_document)
    assert result.status == "COMPLETED"
