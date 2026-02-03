"""
Unit Tests for SyncOrchestrator.

Tests the service layer orchestration of document synchronization.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from rag_index.domain.exceptions import (
    DocumentNotFoundError,
    RateLimitExceededError,
    SyncError,
    SyncValidationError,
)
from rag_index.domain.models import (
    RateLimitStatus,
    SyncAction,
    SyncEvent,
    SyncResult,
    SyncStatus,
    SyncStatusRecord,
)
from rag_index.services.sync_orchestrator import OrchestratorConfig, SyncOrchestrator


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_vertex_ai():
    """Create mock Vertex AI port."""
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
def mock_gcs():
    """Create mock GCS port."""
    port = AsyncMock()
    port.read_document = AsyncMock(
        return_value={
            "id": "doc-123",
            "content": "Test document content",
            "metadata": {"author": "test"},
        }
    )
    port.check_connection = AsyncMock(return_value=True)
    return port


@pytest.fixture
def mock_redis():
    """Create mock Redis port."""
    port = AsyncMock()
    port.set_sync_status = AsyncMock()
    port.get_sync_status = AsyncMock(return_value=None)
    port.check_connection = AsyncMock(return_value=True)
    return port


@pytest.fixture
def mock_kafka():
    """Create mock Kafka port."""
    port = AsyncMock()
    port.publish = AsyncMock()
    port.check_connection = AsyncMock(return_value=True)
    return port


@pytest.fixture
def orchestrator(mock_vertex_ai, mock_gcs, mock_redis, mock_kafka):
    """Create SyncOrchestrator with mock ports."""
    return SyncOrchestrator(
        vertex_ai_port=mock_vertex_ai,
        gcs_port=mock_gcs,
        redis_port=mock_redis,
        kafka_port=mock_kafka,
    )


@pytest.fixture
def orchestrator_no_kafka(mock_vertex_ai, mock_gcs, mock_redis):
    """Create SyncOrchestrator without Kafka."""
    return SyncOrchestrator(
        vertex_ai_port=mock_vertex_ai,
        gcs_port=mock_gcs,
        redis_port=mock_redis,
    )


@pytest.fixture
def upsert_event():
    """Create UPSERT sync event."""
    return SyncEvent(
        trace_id="trace-123",
        tenant_id="tenant-456",
        file_id="file-789",
        processed_gcs_uri="gs://bucket/path/doc.json",
        action=SyncAction.UPSERT,
    )


@pytest.fixture
def delete_event():
    """Create DELETE sync event."""
    return SyncEvent(
        trace_id="trace-123",
        tenant_id="tenant-456",
        file_id="file-789",
        action=SyncAction.DELETE,
    )


# ============================================================================
# OrchestratorConfig Tests
# ============================================================================


class TestOrchestratorConfig:
    """Tests for OrchestratorConfig."""

    def test_default_values(self):
        """Test default configuration values."""
        config = OrchestratorConfig()
        assert config.max_retries == 3
        assert config.retry_delay_seconds == 1.0
        assert config.status_ttl_seconds == 86400
        assert config.enable_dlq is True
        assert config.dlq_topic == "rag-sync-dlq"
        assert config.completed_topic == "rag-sync-completed"

    def test_custom_values(self):
        """Test custom configuration values."""
        config = OrchestratorConfig(
            max_retries=5,
            retry_delay_seconds=2.0,
            status_ttl_seconds=3600,
            enable_dlq=False,
            dlq_topic="custom-dlq",
            completed_topic="custom-completed",
        )
        assert config.max_retries == 5
        assert config.retry_delay_seconds == 2.0
        assert config.status_ttl_seconds == 3600
        assert config.enable_dlq is False
        assert config.dlq_topic == "custom-dlq"
        assert config.completed_topic == "custom-completed"


# ============================================================================
# SyncOrchestrator Initialization Tests
# ============================================================================


class TestSyncOrchestratorInit:
    """Tests for SyncOrchestrator initialization."""

    def test_init_with_all_ports(
        self,
        mock_vertex_ai,
        mock_gcs,
        mock_redis,
        mock_kafka,
    ):
        """Test initialization with all ports."""
        orchestrator = SyncOrchestrator(
            vertex_ai_port=mock_vertex_ai,
            gcs_port=mock_gcs,
            redis_port=mock_redis,
            kafka_port=mock_kafka,
        )
        assert orchestrator._vertex_ai == mock_vertex_ai
        assert orchestrator._gcs == mock_gcs
        assert orchestrator._redis == mock_redis
        assert orchestrator._kafka == mock_kafka

    def test_init_without_kafka(self, mock_vertex_ai, mock_gcs, mock_redis):
        """Test initialization without Kafka port."""
        orchestrator = SyncOrchestrator(
            vertex_ai_port=mock_vertex_ai,
            gcs_port=mock_gcs,
            redis_port=mock_redis,
        )
        assert orchestrator._kafka is None

    def test_init_with_custom_config(
        self,
        mock_vertex_ai,
        mock_gcs,
        mock_redis,
    ):
        """Test initialization with custom config."""
        config = OrchestratorConfig(max_retries=10)
        orchestrator = SyncOrchestrator(
            vertex_ai_port=mock_vertex_ai,
            gcs_port=mock_gcs,
            redis_port=mock_redis,
            config=config,
        )
        assert orchestrator._config.max_retries == 10


# ============================================================================
# UPSERT Processing Tests
# ============================================================================


class TestUpsertProcessing:
    """Tests for UPSERT event processing."""

    async def test_upsert_success(
        self,
        orchestrator,
        upsert_event,
        mock_vertex_ai,
        mock_gcs,
        mock_redis,
    ):
        """Test successful UPSERT processing."""
        result = await orchestrator.process_event(upsert_event)

        assert result.status == "COMPLETED"
        mock_gcs.read_document.assert_called_once_with(upsert_event.processed_gcs_uri)
        mock_vertex_ai.upsert_document.assert_called_once()

    async def test_upsert_updates_status_to_in_progress(
        self,
        orchestrator,
        upsert_event,
        mock_redis,
    ):
        """Test status is updated to IN_PROGRESS."""
        await orchestrator.process_event(upsert_event)

        # First call should be IN_PROGRESS
        first_call = mock_redis.set_sync_status.call_args_list[0]
        assert first_call[1]["status"].status == SyncStatus.IN_PROGRESS

    async def test_upsert_updates_status_to_completed(
        self,
        orchestrator,
        upsert_event,
        mock_redis,
    ):
        """Test status is updated to COMPLETED."""
        await orchestrator.process_event(upsert_event)

        # Last call should be COMPLETED
        last_call = mock_redis.set_sync_status.call_args_list[-1]
        assert last_call[1]["status"].status == SyncStatus.COMPLETED

    async def test_upsert_publishes_completion(
        self,
        orchestrator,
        upsert_event,
        mock_kafka,
    ):
        """Test completion event is published."""
        await orchestrator.process_event(upsert_event)

        mock_kafka.publish.assert_called()
        call_kwargs = mock_kafka.publish.call_args[1]
        assert call_kwargs["topic"] == "rag-sync-completed"
        assert call_kwargs["key"] == upsert_event.tenant_id

    async def test_upsert_returns_processing_time(
        self,
        orchestrator,
        upsert_event,
    ):
        """Test result includes processing time."""
        result = await orchestrator.process_event(upsert_event)

        assert result.processing_time_ms >= 0

    async def test_upsert_document_not_found(
        self,
        orchestrator,
        upsert_event,
        mock_gcs,
    ):
        """Test UPSERT fails when document not found."""
        mock_gcs.read_document.side_effect = DocumentNotFoundError(
            "gs://bucket/path/doc.json"
        )

        with pytest.raises(SyncError):
            await orchestrator.process_event(upsert_event)

    async def test_upsert_gcs_fetch_error(
        self,
        orchestrator,
        upsert_event,
        mock_gcs,
    ):
        """Test UPSERT fails on GCS fetch error."""
        mock_gcs.read_document.side_effect = Exception("GCS connection failed")

        with pytest.raises(SyncError):
            await orchestrator.process_event(upsert_event)


# ============================================================================
# DELETE Processing Tests
# ============================================================================


class TestDeleteProcessing:
    """Tests for DELETE event processing."""

    async def test_delete_success(
        self,
        orchestrator,
        delete_event,
        mock_vertex_ai,
        mock_gcs,
    ):
        """Test successful DELETE processing."""
        result = await orchestrator.process_event(delete_event)

        assert result.status == "COMPLETED"
        mock_vertex_ai.delete_document.assert_called_once()
        mock_gcs.read_document.assert_not_called()

    async def test_delete_updates_status(
        self,
        orchestrator,
        delete_event,
        mock_redis,
    ):
        """Test DELETE updates status correctly."""
        await orchestrator.process_event(delete_event)

        # Should have at least 2 status updates
        assert mock_redis.set_sync_status.call_count >= 2

    async def test_delete_publishes_completion(
        self,
        orchestrator,
        delete_event,
        mock_kafka,
    ):
        """Test DELETE publishes completion event."""
        await orchestrator.process_event(delete_event)

        mock_kafka.publish.assert_called()


# ============================================================================
# Validation Tests
# ============================================================================


class TestEventValidation:
    """Tests for event validation."""

    async def test_missing_tenant_id(self, orchestrator):
        """Test validation fails for missing tenant_id."""
        event = SyncEvent(
            trace_id="trace-123",
            tenant_id="",  # Empty tenant_id
            file_id="file-789",
            action=SyncAction.DELETE,
        )

        with pytest.raises(SyncValidationError, match="tenant_id"):
            await orchestrator.process_event(event)

    async def test_missing_file_id(self, orchestrator):
        """Test validation fails for missing file_id."""
        event = SyncEvent(
            trace_id="trace-123",
            tenant_id="tenant-456",
            file_id="",  # Empty file_id
            action=SyncAction.DELETE,
        )

        with pytest.raises(SyncValidationError, match="file_id"):
            await orchestrator.process_event(event)

    async def test_missing_gcs_uri_for_upsert(self, orchestrator):
        """Test validation fails for UPSERT without GCS URI."""
        event = SyncEvent(
            trace_id="trace-123",
            tenant_id="tenant-456",
            file_id="file-789",
            processed_gcs_uri="",  # Empty for UPSERT
            action=SyncAction.UPSERT,
        )

        with pytest.raises(SyncValidationError, match="processed_gcs_uri"):
            await orchestrator.process_event(event)


# ============================================================================
# Error Handling Tests
# ============================================================================


class TestErrorHandling:
    """Tests for error handling."""

    async def test_rate_limit_error_propagates(
        self,
        orchestrator,
        upsert_event,
        mock_vertex_ai,
        mock_gcs,
    ):
        """Test rate limit error is propagated."""
        mock_vertex_ai.upsert_document.side_effect = RateLimitExceededError(
            limit=600,
            current_count=600,
        )

        with pytest.raises(RateLimitExceededError):
            await orchestrator.process_event(upsert_event)

    async def test_rate_limit_updates_status_to_failed(
        self,
        orchestrator,
        upsert_event,
        mock_vertex_ai,
        mock_redis,
        mock_gcs,
    ):
        """Test rate limit error updates status to FAILED."""
        mock_vertex_ai.upsert_document.side_effect = RateLimitExceededError(
            limit=600,
            current_count=600,
        )

        with pytest.raises(RateLimitExceededError):
            await orchestrator.process_event(upsert_event)

        # Should have FAILED status
        last_call = mock_redis.set_sync_status.call_args_list[-1]
        assert last_call[1]["status"].status == SyncStatus.FAILED

    async def test_vertex_ai_error_publishes_to_dlq(
        self,
        orchestrator,
        upsert_event,
        mock_vertex_ai,
        mock_kafka,
        mock_gcs,
    ):
        """Test Vertex AI error publishes to DLQ."""
        mock_vertex_ai.upsert_document.side_effect = Exception("Vertex AI failed")

        with pytest.raises(SyncError):
            await orchestrator.process_event(upsert_event)

        # Should have published to DLQ
        calls = [
            c
            for c in mock_kafka.publish.call_args_list
            if c[1]["topic"] == "rag-sync-dlq"
        ]
        assert len(calls) == 1

    async def test_dlq_disabled(
        self,
        mock_vertex_ai,
        mock_gcs,
        mock_redis,
        mock_kafka,
        upsert_event,
    ):
        """Test DLQ publishing can be disabled."""
        config = OrchestratorConfig(enable_dlq=False)
        orchestrator = SyncOrchestrator(
            vertex_ai_port=mock_vertex_ai,
            gcs_port=mock_gcs,
            redis_port=mock_redis,
            kafka_port=mock_kafka,
            config=config,
        )

        mock_vertex_ai.upsert_document.side_effect = Exception("Vertex AI failed")

        with pytest.raises(SyncError):
            await orchestrator.process_event(upsert_event)

        # Should NOT have published to DLQ
        dlq_calls = [
            c
            for c in mock_kafka.publish.call_args_list
            if c[1]["topic"] == "rag-sync-dlq"
        ]
        assert len(dlq_calls) == 0


# ============================================================================
# Status Tracking Tests
# ============================================================================


class TestStatusTracking:
    """Tests for status tracking in Redis."""

    async def test_get_status(self, orchestrator, mock_redis):
        """Test getting event status."""
        expected_status = SyncStatusRecord(
            event_id=uuid.uuid4(),
            trace_id="trace-123",
            tenant_id="tenant-456",
            file_id="file-789",
            action=SyncAction.UPSERT,
            status=SyncStatus.COMPLETED,
            last_updated=datetime.now(timezone.utc),
        )
        mock_redis.get_sync_status.return_value = expected_status

        status = await orchestrator.get_status("event-123")

        assert status == expected_status
        mock_redis.get_sync_status.assert_called_once_with("event-123")

    async def test_get_status_not_found(self, orchestrator, mock_redis):
        """Test getting status for non-existent event."""
        mock_redis.get_sync_status.return_value = None

        status = await orchestrator.get_status("non-existent")

        assert status is None

    async def test_status_update_failure_is_non_fatal(
        self,
        orchestrator,
        upsert_event,
        mock_redis,
    ):
        """Test that status update failure doesn't break processing."""
        mock_redis.set_sync_status.side_effect = Exception("Redis error")

        # Should still succeed
        result = await orchestrator.process_event(upsert_event)
        assert result.status == "COMPLETED"


# ============================================================================
# Health Check Tests
# ============================================================================


class TestHealthCheck:
    """Tests for health check functionality."""

    async def test_check_health_all_healthy(
        self,
        orchestrator,
        mock_vertex_ai,
        mock_gcs,
        mock_redis,
        mock_kafka,
    ):
        """Test health check when all services healthy."""
        health = await orchestrator.check_health()

        assert health["vertex_ai"] is True
        assert health["redis"] is True
        assert health["gcs"] is True
        assert health["kafka"] is True

    async def test_check_health_vertex_ai_unhealthy(
        self,
        orchestrator,
        mock_vertex_ai,
    ):
        """Test health check with unhealthy Vertex AI."""
        mock_vertex_ai.check_connection.side_effect = Exception("Connection failed")

        health = await orchestrator.check_health()

        assert health["vertex_ai"] is False

    async def test_check_health_no_kafka(
        self,
        orchestrator_no_kafka,
    ):
        """Test health check without Kafka configured."""
        health = await orchestrator_no_kafka.check_health()

        assert health["kafka"] is None


# ============================================================================
# Rate Limit Status Tests
# ============================================================================


class TestRateLimitStatus:
    """Tests for rate limit status."""

    async def test_get_rate_limit_status(self, mock_vertex_ai, mock_gcs, mock_redis):
        """Test getting rate limit status from Vertex AI port."""
        mock_vertex_ai.get_rate_limit_status = AsyncMock(
            return_value=RateLimitStatus(
                current_count=100,
                limit=600,
                remaining=500,
            )
        )

        orchestrator = SyncOrchestrator(
            vertex_ai_port=mock_vertex_ai,
            gcs_port=mock_gcs,
            redis_port=mock_redis,
        )

        status = await orchestrator.get_rate_limit_status()

        assert status.remaining == 500

    async def test_get_rate_limit_status_not_supported(
        self,
        orchestrator,
        mock_vertex_ai,
    ):
        """Test getting rate limit status when not supported."""
        # Remove the method
        del mock_vertex_ai.get_rate_limit_status

        status = await orchestrator.get_rate_limit_status()

        assert status is None


# ============================================================================
# No Kafka Port Tests
# ============================================================================


class TestNoKafkaPort:
    """Tests for orchestrator without Kafka port."""

    async def test_process_without_kafka(
        self,
        orchestrator_no_kafka,
        upsert_event,
    ):
        """Test processing works without Kafka port."""
        result = await orchestrator_no_kafka.process_event(upsert_event)

        assert result.status == "COMPLETED"

    async def test_no_completion_published_without_kafka(
        self,
        orchestrator_no_kafka,
        upsert_event,
    ):
        """Test no completion event published without Kafka."""
        # Should complete without error
        result = await orchestrator_no_kafka.process_event(upsert_event)
        assert result.status == "COMPLETED"

    async def test_no_dlq_published_without_kafka(
        self,
        orchestrator_no_kafka,
        upsert_event,
        mock_vertex_ai,
        mock_gcs,
    ):
        """Test no DLQ event published without Kafka."""
        mock_vertex_ai.upsert_document.side_effect = Exception("Error")

        with pytest.raises(SyncError):
            await orchestrator_no_kafka.process_event(upsert_event)
        # Should complete without error about missing Kafka
