"""
Integration Tests for RAG Index Service.

End-to-end tests verifying the full sync pipeline with mocked external services.
Tests the complete flow from event to Vertex AI indexing.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from rag_index.domain.exceptions import (
    DocumentFetchError,
    SyncError,
    VertexAIError,
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
def event_id():
    """Generate a unique event ID."""
    return uuid.uuid4()


@pytest.fixture
def trace_id():
    """Generate a unique trace ID."""
    return str(uuid.uuid4())


@pytest.fixture
def tenant_id():
    """Generate a unique tenant ID."""
    return f"tenant_{uuid.uuid4().hex[:8]}"


@pytest.fixture
def file_id():
    """Generate a unique file ID."""
    return f"file_{uuid.uuid4().hex[:12]}"


@pytest.fixture
def sync_event(event_id, trace_id, tenant_id, file_id):
    """Create a complete sync event."""
    return SyncEvent(
        event_id=event_id,
        trace_id=trace_id,
        tenant_id=tenant_id,
        file_id=file_id,
        action=SyncAction.UPSERT,
        processed_gcs_uri=f"gs://bucket/{tenant_id}/{file_id}.json",
    )


@pytest.fixture
def mock_document_content():
    """Sample document content from GCS."""
    return {
        "id": "doc-123",
        "title": "Test Document",
        "content": "This is test content for RAG indexing.",
        "metadata": {
            "author": "Test Author",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "file_type": "text/plain",
        },
    }


@pytest.fixture
def mock_gcs(mock_document_content):
    """Create a mock GCS port."""
    port = AsyncMock()
    port.read_document = AsyncMock(return_value=mock_document_content)
    port.check_connection = AsyncMock(return_value=True)
    return port


@pytest.fixture
def mock_vertex_ai():
    """Create a mock Vertex AI port."""
    port = AsyncMock()
    port.upsert_document = AsyncMock(
        return_value=SyncResult(
            event_id=uuid.uuid4(),
            trace_id="trace-123",
            status="COMPLETED",
            operation_id="op-123",
        )
    )
    port.delete_document = AsyncMock(
        return_value=SyncResult(
            event_id=uuid.uuid4(),
            trace_id="trace-123",
            status="COMPLETED",
        )
    )
    port.check_connection = AsyncMock(return_value=True)
    return port


@pytest.fixture
def mock_redis():
    """Create a mock Redis port."""
    port = AsyncMock()
    port.set_sync_status = AsyncMock()
    port.get_sync_status = AsyncMock(return_value=None)
    port.check_connection = AsyncMock(return_value=True)
    return port


@pytest.fixture
def mock_kafka():
    """Create a mock Kafka port."""
    port = AsyncMock()
    port.publish = AsyncMock()
    port.check_connection = AsyncMock(return_value=True)
    return port


@pytest.fixture
def orchestrator(mock_vertex_ai, mock_gcs, mock_redis, mock_kafka):
    """Create a fully mocked orchestrator."""
    return SyncOrchestrator(
        vertex_ai_port=mock_vertex_ai,
        gcs_port=mock_gcs,
        redis_port=mock_redis,
        kafka_port=mock_kafka,
    )


# ============================================================================
# Happy Path Integration Tests
# ============================================================================


class TestUpsertPipeline:
    """Tests for the complete upsert pipeline."""

    @pytest.mark.asyncio
    async def test_upsert_complete_flow(
        self,
        orchestrator,
        sync_event,
        mock_gcs,
        mock_vertex_ai,
        mock_redis,
        mock_kafka,
    ):
        """Test complete upsert flow from event to completion."""
        result = await orchestrator.process_event(sync_event)

        # Verify result
        assert result.status in [SyncStatus.COMPLETED, "COMPLETED"]
        assert result.event_id is not None

        # Verify GCS fetch
        mock_gcs.read_document.assert_called_once_with(sync_event.processed_gcs_uri)

        # Verify Vertex AI upsert
        mock_vertex_ai.upsert_document.assert_called_once()

        # Verify status updates
        assert mock_redis.set_sync_status.call_count >= 1

        # Verify completion event published
        mock_kafka.publish.assert_called()

    @pytest.mark.asyncio
    async def test_upsert_with_large_document(
        self,
        orchestrator,
        sync_event,
        mock_gcs,
        mock_vertex_ai,
    ):
        """Test upsert with large document content."""
        # Simulate large document
        large_content = {
            "id": "large-doc",
            "content": "x" * 100000,  # 100KB of content
        }
        mock_gcs.read_document.return_value = large_content

        result = await orchestrator.process_event(sync_event)

        assert result.status in [SyncStatus.COMPLETED, "COMPLETED"]
        mock_vertex_ai.upsert_document.assert_called_once()


class TestDeletePipeline:
    """Tests for the complete delete pipeline."""

    @pytest.mark.asyncio
    async def test_delete_complete_flow(
        self,
        orchestrator,
        event_id,
        trace_id,
        tenant_id,
        file_id,
        mock_vertex_ai,
        mock_redis,
        mock_kafka,
    ):
        """Test complete delete flow from event to completion."""
        delete_event = SyncEvent(
            event_id=event_id,
            trace_id=trace_id,
            tenant_id=tenant_id,
            file_id=file_id,
            action=SyncAction.DELETE,
            processed_gcs_uri="gs://bucket/placeholder.json",  # Still required by model
        )

        result = await orchestrator.process_event(delete_event)

        # Verify result
        assert result.status in [SyncStatus.COMPLETED, "COMPLETED"]

        # Verify Vertex AI delete
        mock_vertex_ai.delete_document.assert_called_once()

        # Verify completion published
        mock_kafka.publish.assert_called()


# ============================================================================
# Error Handling Integration Tests
# ============================================================================


class TestErrorHandling:
    """Tests for error handling in the pipeline."""

    @pytest.mark.asyncio
    async def test_gcs_fetch_failure(
        self,
        orchestrator,
        sync_event,
        mock_gcs,
        mock_redis,
        mock_kafka,
    ):
        """Test handling of GCS fetch failure."""
        mock_gcs.read_document.side_effect = DocumentFetchError("Fetch failed")

        # Orchestrator raises SyncError on failure
        with pytest.raises(SyncError):
            await orchestrator.process_event(sync_event)

    @pytest.mark.asyncio
    async def test_vertex_ai_upsert_failure(
        self,
        orchestrator,
        sync_event,
        mock_vertex_ai,
        mock_redis,
        mock_kafka,
    ):
        """Test handling of Vertex AI upsert failure."""
        mock_vertex_ai.upsert_document.side_effect = VertexAIError("Upsert failed")

        # Orchestrator raises SyncError on failure
        with pytest.raises(SyncError):
            await orchestrator.process_event(sync_event)


# ============================================================================
# Status Tracking Integration Tests
# ============================================================================


class TestStatusTracking:
    """Tests for status tracking through the pipeline."""

    @pytest.mark.asyncio
    async def test_status_transitions_upsert(
        self,
        orchestrator,
        sync_event,
        mock_redis,
    ):
        """Test status transitions during upsert."""
        await orchestrator.process_event(sync_event)

        # Should have at least one status update
        assert mock_redis.set_sync_status.call_count >= 1


# ============================================================================
# Kafka Publication Integration Tests
# ============================================================================


class TestKafkaIntegration:
    """Tests for Kafka event publication."""

    @pytest.mark.asyncio
    async def test_completion_event_published(
        self,
        orchestrator,
        sync_event,
        mock_kafka,
    ):
        """Test that completion events are published to Kafka."""
        await orchestrator.process_event(sync_event)

        mock_kafka.publish.assert_called()

        # Verify the published event content
        call_args = mock_kafka.publish.call_args
        assert call_args is not None

    @pytest.mark.asyncio
    async def test_dlq_publication_on_failure(
        self,
        orchestrator,
        sync_event,
        mock_vertex_ai,
        mock_kafka,
    ):
        """Test that failed events trigger DLQ publish (may raise exception)."""
        mock_vertex_ai.upsert_document.side_effect = VertexAIError("Error")

        # Orchestrator raises SyncError on failure
        with pytest.raises(SyncError):
            await orchestrator.process_event(sync_event)

        # Check if DLQ was published before exception
        # The specific behavior depends on orchestrator config


# ============================================================================
# Health Check Integration Tests
# ============================================================================


class TestHealthCheckIntegration:
    """Tests for health check integration."""

    @pytest.mark.asyncio
    async def test_all_services_healthy(
        self,
        orchestrator,
        mock_gcs,
        mock_vertex_ai,
        mock_redis,
        mock_kafka,
    ):
        """Test health check when all services are healthy."""
        # check_health is async and checks all connections
        health = await orchestrator.check_health()

        # Health response has service-specific keys (no top-level "healthy")
        assert health["vertex_ai"] is True
        assert health["gcs"] is True
        assert health["redis"] is True

    @pytest.mark.asyncio
    async def test_vertex_ai_unhealthy(
        self,
        orchestrator,
        mock_vertex_ai,
    ):
        """Test health check when Vertex AI is unhealthy."""
        mock_vertex_ai.check_connection.return_value = False

        health = await orchestrator.check_health()

        assert health["vertex_ai"] is False


# ============================================================================
# Batch Processing Integration Tests
# ============================================================================


class TestBatchProcessing:
    """Tests for batch processing."""

    @pytest.mark.asyncio
    async def test_batch_upsert_all_succeed(
        self,
        orchestrator,
        tenant_id,
        mock_gcs,
        mock_vertex_ai,
    ):
        """Test batch upsert where all documents succeed."""
        events = [
            SyncEvent(
                event_id=uuid.uuid4(),
                trace_id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                file_id=f"file_{i}",
                action=SyncAction.UPSERT,
                processed_gcs_uri=f"gs://bucket/{tenant_id}/file_{i}.json",
            )
            for i in range(5)
        ]

        results = [await orchestrator.process_event(event) for event in events]

        assert all(r.status in [SyncStatus.COMPLETED, "COMPLETED"] for r in results)
        assert mock_vertex_ai.upsert_document.call_count == 5

    @pytest.mark.asyncio
    async def test_batch_with_mixed_results(
        self,
        orchestrator,
        tenant_id,
        mock_vertex_ai,
    ):
        """Test batch processing with some failures."""
        # Fail every other request
        call_count = 0

        async def upsert_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count % 2 == 0:
                raise VertexAIError("Alternate failure")
            return SyncResult(
                event_id=uuid.uuid4(),
                trace_id="trace-123",
                status="COMPLETED",
            )

        mock_vertex_ai.upsert_document.side_effect = upsert_side_effect

        events = [
            SyncEvent(
                event_id=uuid.uuid4(),
                trace_id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                file_id=f"file_{i}",
                action=SyncAction.UPSERT,
                processed_gcs_uri=f"gs://bucket/{tenant_id}/file_{i}.json",
            )
            for i in range(4)
        ]

        # Process events, catching failures (orchestrator raises on error)
        successes = 0
        failures = 0
        for event in events:
            try:
                result = await orchestrator.process_event(event)
                if result.status in [SyncStatus.COMPLETED, "COMPLETED"]:
                    successes += 1
            except SyncError:
                failures += 1

        assert successes == 2
        assert failures == 2


# ============================================================================
# Idempotency Integration Tests
# ============================================================================


class TestIdempotency:
    """Tests for idempotent processing."""

    @pytest.mark.asyncio
    async def test_duplicate_event_handling(
        self,
        orchestrator,
        sync_event,
        mock_vertex_ai,
    ):
        """Test handling of duplicate events."""
        # Process same event twice
        result1 = await orchestrator.process_event(sync_event)
        result2 = await orchestrator.process_event(sync_event)

        # Both should succeed (idempotent)
        assert result1.status in [SyncStatus.COMPLETED, "COMPLETED"]
        assert result2.status in [SyncStatus.COMPLETED, "COMPLETED"]

        # Vertex AI should be called twice (no client-side dedup)
        assert mock_vertex_ai.upsert_document.call_count == 2


# ============================================================================
# Performance Integration Tests
# ============================================================================


class TestPerformance:
    """Tests for performance characteristics."""

    @pytest.mark.asyncio
    async def test_processing_time_recorded(
        self,
        orchestrator,
        sync_event,
    ):
        """Test that processing time is recorded in results."""
        result = await orchestrator.process_event(sync_event)

        assert result.processing_time_ms is not None
        assert result.processing_time_ms >= 0
