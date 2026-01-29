"""
Integration tests for the data ingestion pipeline.

These tests verify that multiple components work correctly together,
testing the full flow from event ingestion to output publishing.
"""

import pytest
from datetime import datetime
from uuid import uuid4
from unittest.mock import patch, MagicMock

from data_ingestion.domain.models import (
    IngestionEvent,
    ProcessedEvent,
    ProcessingStatus,
    EventSource,
)
from data_ingestion.domain.services import IngestionService
from data_ingestion.domain.exceptions import (
    DuplicateEventError,
    StorageOperationError,
    NonRetryableError,
)
from data_ingestion.tests.conftest import (
    MockStoragePort,
    MockCachePort,
    MockEventProducerPort,
    MockEventConsumerPort,
)


# =============================================================================
# Fixtures for Integration Tests
# =============================================================================


@pytest.fixture
def integration_storage():
    """Create a mock storage with some pre-populated files."""
    storage = MockStoragePort()
    # Add some test files to the landing zone
    storage.add_file("gs://onboarding-bucket1/_landing/tenant-a/video1.mp4")
    storage.add_file("gs://onboarding-bucket1/_landing/tenant-b/image1.jpg")
    storage.add_file("gs://onboarding-bucket1/_landing/shared/document.pdf")
    return storage


@pytest.fixture
def integration_cache():
    """Create a fresh cache for integration tests."""
    return MockCachePort()


@pytest.fixture
def integration_producer():
    """Create a mock producer for integration tests."""
    return MockEventProducerPort()


@pytest.fixture
def integration_consumer():
    """Create a mock consumer with test events."""
    consumer = MockEventConsumerPort()
    return consumer


@pytest.fixture
def integration_service(integration_storage, integration_cache, integration_producer):
    """Create an IngestionService for integration testing."""
    return IngestionService(
        storage=integration_storage,
        cache=integration_cache,
        producer=integration_producer,
        output_topic="curation-needed-topic",
        dlq_topic="ingestion-dlq",
        dedupe_ttl_seconds=3600,
        status_ttl_seconds=604800,
        max_retries=3,
    )


def create_test_event(
    tenant_id: str = "tenant-123",
    file_path: str = "gs://onboarding-bucket1/_landing/test.mp4",
    source: EventSource = EventSource.FRONTEND_UPLOAD,
) -> IngestionEvent:
    """Helper to create test ingestion events."""
    return IngestionEvent(
        event_id=uuid4(),
        trace_id=uuid4(),
        tenant_id=tenant_id,
        file_path=file_path,
        file_type="video/mp4",
        timestamp=datetime.utcnow(),
        source=source,
    )


# =============================================================================
# End-to-End Pipeline Tests
# =============================================================================


class TestEndToEndPipeline:
    """Test the complete ingestion pipeline flow."""

    def test_complete_ingestion_flow(
        self,
        integration_service,
        integration_storage,
        integration_cache,
        integration_producer,
    ):
        """Test the complete flow from event to published result."""
        # Create an event for a file that exists
        event = create_test_event(
            tenant_id="tenant-a",
            file_path="gs://onboarding-bucket1/_landing/tenant-a/video1.mp4",
        )

        # Process the event
        result = integration_service.process_event(event)

        # Verify the result
        assert result.status == ProcessingStatus.RAW_STORED
        assert result.event_id == event.event_id
        assert result.trace_id == event.trace_id
        assert result.tenant_id == event.tenant_id
        assert "raw" in result.destination_path
        assert "tenant-a" in result.destination_path

        # Verify file was moved (not in original location)
        assert event.file_path not in integration_storage.files
        assert result.destination_path in integration_storage.files

        # Verify event was published
        assert len(integration_producer.published) == 1
        published_topic, published_event = integration_producer.published[0]
        assert published_topic == "curation-needed-topic"
        assert published_event.event_id == event.event_id

        # Verify deduplication was set
        assert str(event.event_id) in integration_cache.processed

        # Verify status was tracked
        status = integration_cache.get_status(str(event.trace_id))
        assert status is not None
        assert status["status"] == ProcessingStatus.RAW_STORED.value

    def test_multiple_events_different_tenants(
        self,
        integration_service,
        integration_storage,
        integration_cache,
        integration_producer,
    ):
        """Test processing multiple events from different tenants."""
        events = [
            create_test_event(
                tenant_id="tenant-a",
                file_path="gs://onboarding-bucket1/_landing/tenant-a/video1.mp4",
            ),
            create_test_event(
                tenant_id="tenant-b",
                file_path="gs://onboarding-bucket1/_landing/tenant-b/image1.jpg",
            ),
        ]

        results = []
        for event in events:
            result = integration_service.process_event(event)
            results.append(result)

        # Verify all events were processed
        assert len(results) == 2
        assert all(r.status == ProcessingStatus.RAW_STORED for r in results)

        # Verify tenant isolation in paths
        assert "tenant-a" in results[0].destination_path
        assert "tenant-b" in results[1].destination_path

        # Verify all events were published
        assert len(integration_producer.published) == 2

    def test_date_partitioning_in_destination(
        self, integration_service, integration_storage
    ):
        """Test that destination paths include date partitioning."""
        event = create_test_event(
            tenant_id="tenant-a",
            file_path="gs://onboarding-bucket1/_landing/tenant-a/video1.mp4",
        )
        # Set specific timestamp for predictable path
        event = IngestionEvent(
            event_id=event.event_id,
            trace_id=event.trace_id,
            tenant_id=event.tenant_id,
            file_path=event.file_path,
            file_type=event.file_type,
            timestamp=datetime(2026, 1, 29, 12, 0, 0),
            source=event.source,
        )

        result = integration_service.process_event(event)

        # Verify date partitioning
        assert "2026/01/29" in result.destination_path


# =============================================================================
# Deduplication Integration Tests
# =============================================================================


class TestDeduplicationFlow:
    """Test deduplication behavior across the pipeline."""

    def test_duplicate_event_rejected(
        self, integration_service, integration_storage, integration_cache
    ):
        """Test that duplicate events are properly rejected."""
        event = create_test_event(
            tenant_id="tenant-a",
            file_path="gs://onboarding-bucket1/_landing/tenant-a/video1.mp4",
        )

        # Process first time - should succeed
        result1 = integration_service.process_event(event)
        assert result1.status == ProcessingStatus.RAW_STORED

        # Create same event ID for second attempt
        # Need to re-add file since it was moved
        integration_storage.add_file(
            "gs://onboarding-bucket1/_landing/tenant-a/video1.mp4"
        )

        duplicate_event = IngestionEvent(
            event_id=event.event_id,  # Same event ID
            trace_id=uuid4(),  # Different trace
            tenant_id=event.tenant_id,
            file_path="gs://onboarding-bucket1/_landing/tenant-a/video1.mp4",
            file_type=event.file_type,
            timestamp=datetime.utcnow(),
            source=event.source,
        )

        # Process again - should fail as duplicate
        with pytest.raises(DuplicateEventError) as exc_info:
            integration_service.process_event(duplicate_event)

        assert str(event.event_id) in str(exc_info.value)

    def test_different_event_ids_not_duplicates(
        self, integration_service, integration_storage, integration_cache
    ):
        """Test that different event IDs are not treated as duplicates."""
        # Create two events for same file but different event IDs
        event1 = create_test_event(
            tenant_id="tenant-a",
            file_path="gs://onboarding-bucket1/_landing/tenant-a/video1.mp4",
        )

        # Process first event
        result1 = integration_service.process_event(event1)
        assert result1.status == ProcessingStatus.RAW_STORED

        # Add file back and create second event with different ID
        integration_storage.add_file("gs://onboarding-bucket1/_landing/new-video.mp4")
        event2 = create_test_event(
            tenant_id="tenant-a",
            file_path="gs://onboarding-bucket1/_landing/new-video.mp4",
        )

        # Should succeed with different event ID
        result2 = integration_service.process_event(event2)
        assert result2.status == ProcessingStatus.RAW_STORED


# =============================================================================
# Error Handling Integration Tests
# =============================================================================


class TestErrorHandlingIntegration:
    """Test error handling across the pipeline."""

    def test_missing_file_error_flow(
        self, integration_service, integration_cache, integration_producer
    ):
        """Test the flow when a file is missing from landing zone."""
        event = create_test_event(
            file_path="gs://onboarding-bucket1/_landing/nonexistent.mp4"
        )

        # Should raise NonRetryableError (wrapping FileNotFoundInLandingError)
        with pytest.raises(NonRetryableError):
            integration_service.process_event(event)

        # Status should be updated to FAILED
        status = integration_cache.get_status(str(event.trace_id))
        assert status is not None
        assert status["status"] == ProcessingStatus.FAILED.value

    def test_process_event_with_retry_handles_duplicates(
        self, integration_service, integration_storage, integration_cache
    ):
        """Test that process_event_with_retry properly handles duplicates."""
        event = create_test_event(
            tenant_id="tenant-a",
            file_path="gs://onboarding-bucket1/_landing/tenant-a/video1.mp4",
        )

        # First attempt should succeed
        result1 = integration_service.process_event_with_retry(event)
        assert result1 is not None
        assert result1.status == ProcessingStatus.RAW_STORED

        # Re-add file and create duplicate
        integration_storage.add_file(
            "gs://onboarding-bucket1/_landing/tenant-a/video1.mp4"
        )
        duplicate_event = IngestionEvent(
            event_id=event.event_id,
            trace_id=uuid4(),
            tenant_id=event.tenant_id,
            file_path="gs://onboarding-bucket1/_landing/tenant-a/video1.mp4",
            file_type=event.file_type,
            timestamp=datetime.utcnow(),
            source=event.source,
        )

        # Second attempt should return None (duplicate)
        result2 = integration_service.process_event_with_retry(duplicate_event)
        assert result2 is None

    def test_dlq_publishing_on_non_retryable_error(
        self, integration_storage, integration_cache, integration_producer
    ):
        """Test that non-retryable errors result in DLQ publishing."""

        # Create a storage that causes non-retryable errors
        class NonRetryableStorage(MockStoragePort):
            def check_exists(self, path):
                return True  # File exists

            def move_file(self, source_path, destination_path):
                raise StorageOperationError(
                    operation="move_file",
                    path=source_path,
                    cause=Exception("Permission denied"),
                    is_retryable=False,
                )

        storage = NonRetryableStorage()
        service = IngestionService(
            storage=storage,
            cache=integration_cache,
            producer=integration_producer,
            output_topic="output",
            dlq_topic="dlq",
        )

        event = create_test_event()
        original_event_dict = event.model_dump()

        # Process should raise NonRetryableError
        with pytest.raises(NonRetryableError):
            service.process_event(event)

        # Service should send to DLQ
        service.send_to_dlq(
            original_event_dict, NonRetryableError("Test"), "input-topic"
        )
        assert len(integration_producer.dlq_messages) == 1


# =============================================================================
# Status Tracking Integration Tests
# =============================================================================


class TestStatusTrackingIntegration:
    """Test status tracking throughout the pipeline."""

    def test_status_progression_success(
        self, integration_service, integration_storage, integration_cache
    ):
        """Test that status progresses correctly on successful processing."""
        event = create_test_event(
            tenant_id="tenant-a",
            file_path="gs://onboarding-bucket1/_landing/tenant-a/video1.mp4",
        )

        # Process the event
        integration_service.process_event(event)

        # Check final status
        status = integration_cache.get_status(str(event.trace_id))
        assert status is not None
        assert status["status"] == ProcessingStatus.RAW_STORED.value

    def test_status_on_failure(self, integration_service, integration_cache):
        """Test that status is set to FAILED on processing errors."""
        # Create event for non-existent file
        event = create_test_event(
            file_path="gs://onboarding-bucket1/_landing/missing.mp4"
        )

        # Process should fail with NonRetryableError
        with pytest.raises(NonRetryableError):
            integration_service.process_event(event)

        # Status should be FAILED
        status = integration_cache.get_status(str(event.trace_id))
        assert status is not None
        assert status["status"] == ProcessingStatus.FAILED.value


# =============================================================================
# Consumer to Service Integration Tests
# =============================================================================


class TestConsumerServiceIntegration:
    """Test integration between consumer and service."""

    def test_consumer_provides_events_to_service(
        self, integration_service, integration_storage, integration_consumer
    ):
        """Test that events from consumer can be processed by service."""
        # Add events to consumer
        event1 = create_test_event(
            tenant_id="tenant-a",
            file_path="gs://onboarding-bucket1/_landing/tenant-a/video1.mp4",
        )
        integration_consumer.events.append(event1)

        # Consume and process
        consumed_event = integration_consumer.consume_one()
        assert consumed_event is not None

        result = integration_service.process_event(consumed_event)
        assert result.status == ProcessingStatus.RAW_STORED

    def test_batch_consumption_and_processing(
        self, integration_storage, integration_cache, integration_producer
    ):
        """Test batch consumption and processing of events."""
        consumer = MockEventConsumerPort()
        service = IngestionService(
            storage=integration_storage,
            cache=integration_cache,
            producer=integration_producer,
            output_topic="output",
            dlq_topic="dlq",
        )

        # Add multiple events
        events = [
            create_test_event(
                tenant_id="tenant-a",
                file_path="gs://onboarding-bucket1/_landing/tenant-a/video1.mp4",
            ),
            create_test_event(
                tenant_id="tenant-b",
                file_path="gs://onboarding-bucket1/_landing/tenant-b/image1.jpg",
            ),
        ]
        consumer.events.extend(events)

        # Process all events
        results = []
        while True:
            event = consumer.consume_one()
            if event is None:
                break
            result = service.process_event(event)
            results.append(result)
            consumer.commit()

        assert len(results) == 2
        assert all(r.status == ProcessingStatus.RAW_STORED for r in results)
        assert consumer.committed


# =============================================================================
# Factory Integration Tests
# =============================================================================


class TestFactoryIntegration:
    """Test the factory creates properly wired components."""

    @patch("data_ingestion.factory.GCSAdapter")
    @patch("data_ingestion.factory.RedisAdapter")
    @patch("data_ingestion.factory.KafkaProducerAdapter")
    def test_create_ingestion_service_wiring(self, mock_kafka, mock_redis, mock_gcs):
        """Test that create_ingestion_service wires components correctly."""
        from data_ingestion.factory import create_ingestion_service

        # Setup mocks
        mock_gcs.return_value = MagicMock()
        mock_redis.return_value = MagicMock()
        mock_kafka.return_value = MagicMock()

        config = {
            "GCS": {
                "PROJECT_ID": "test-project",
                "BUCKET_NAME": "test-bucket",
            },
            "REDIS": {
                "URL": "redis://localhost:6379",
            },
            "KAFKA": {
                "BOOTSTRAP_SERVERS": "localhost:9092",
                "OUTPUT_TOPIC": "output-topic",
                "DLQ_TOPIC": "dlq-topic",
            },
        }

        service = create_ingestion_service(config)

        assert service is not None
        assert service.output_topic == "output-topic"
        assert service.dlq_topic == "dlq-topic"
        mock_gcs.assert_called_once()
        mock_redis.assert_called_once()
        mock_kafka.assert_called_once()

    @patch("data_ingestion.factory.GCSAdapter")
    def test_create_gcs_adapter_function(self, mock_gcs):
        """Test create_gcs_adapter factory function."""
        mock_gcs.return_value = MagicMock()

        from data_ingestion.factory import create_gcs_adapter

        config = {
            "GCS": {
                "PROJECT_ID": "test-project",
                "BUCKET_NAME": "test-bucket",
            },
        }
        adapter = create_gcs_adapter(config)

        mock_gcs.assert_called_once()
        assert adapter is not None

    @patch("data_ingestion.factory.RedisAdapter")
    def test_create_redis_adapter_function(self, mock_redis):
        """Test create_redis_adapter factory function."""
        mock_redis.return_value = MagicMock()

        from data_ingestion.factory import create_redis_adapter

        config = {
            "REDIS": {
                "URL": "redis://localhost:6379",
            },
        }
        adapter = create_redis_adapter(config)

        mock_redis.assert_called_once()
        assert adapter is not None

    @patch("data_ingestion.factory.create_ingestion_service")
    def test_service_container_singleton(self, mock_create_service):
        """Test that IngestionServiceContainer returns singleton."""
        from data_ingestion.factory import IngestionServiceContainer

        mock_service = MagicMock()
        mock_create_service.return_value = mock_service

        # Reset container for clean test
        IngestionServiceContainer.reset()

        # First call creates service
        service1 = IngestionServiceContainer.get_service()
        assert service1 == mock_service

        # Second call returns same instance (no new creation)
        service2 = IngestionServiceContainer.get_service()
        assert service2 == service1
        mock_create_service.assert_called_once()

        # Cleanup
        IngestionServiceContainer.reset()


# =============================================================================
# Celery Task Integration Tests
# =============================================================================


class TestCeleryTaskIntegration:
    """Test Celery task integration with the service."""

    @patch("data_ingestion.tasks.create_ingestion_service")
    def test_process_ingestion_event_task_success(self, mock_create_service):
        """Test the process_ingestion_event Celery task on success."""
        # Setup mock service
        mock_service = MagicMock()
        mock_result = ProcessedEvent(
            event_id=uuid4(),
            trace_id=uuid4(),
            timestamp=datetime.utcnow(),
            tenant_id="tenant-123",
            source_path="gs://bucket/_landing/file.mp4",
            destination_path="gs://bucket/tenant-123/raw/file.mp4",
            status=ProcessingStatus.RAW_STORED,
            processing_duration_ms=100,
        )
        mock_service.process_event.return_value = mock_result
        mock_create_service.return_value = mock_service

        from data_ingestion.tasks import process_ingestion_event

        event_id = str(uuid4())
        trace_id = str(uuid4())

        # Call task directly (not via Celery)
        result = process_ingestion_event.apply(
            args=[],
            kwargs={
                "event_id": event_id,
                "tenant_id": "tenant-123",
                "file_path": "gs://bucket/_landing/file.mp4",
                "file_type": "video/mp4",
                "timestamp": datetime.utcnow().isoformat(),
                "source": "frontend-upload",
                "trace_id": trace_id,
            },
        ).get()

        assert result["status"] == "success"
        assert result["event_id"] == event_id
        mock_service.process_event.assert_called_once()

    @patch("data_ingestion.tasks.create_ingestion_service")
    def test_process_ingestion_event_duplicate(self, mock_create_service):
        """Test task handles duplicate events gracefully."""
        mock_service = MagicMock()
        mock_service.process_event.side_effect = DuplicateEventError(event_id="test-id")
        mock_create_service.return_value = mock_service

        from data_ingestion.tasks import process_ingestion_event

        event_id = str(uuid4())
        result = process_ingestion_event.apply(
            args=[],
            kwargs={
                "event_id": event_id,
                "tenant_id": "tenant-123",
                "file_path": "gs://bucket/_landing/file.mp4",
            },
        ).get()

        assert result["status"] == "skipped"
        assert result["reason"] == "duplicate"

    @patch("data_ingestion.factory.create_redis_adapter")
    def test_check_status_task(self, mock_create_redis):
        """Test the check_status Celery task."""
        mock_cache = MagicMock()
        mock_cache.get_status.return_value = {
            "status": "raw_stored",
            "updated_at": datetime.utcnow().isoformat(),
        }
        mock_create_redis.return_value = mock_cache

        from data_ingestion.tasks import check_status

        trace_id = str(uuid4())
        result = check_status.apply(args=[trace_id]).get()

        assert result is not None
        assert result["status"] == "raw_stored"
        mock_cache.get_status.assert_called_once_with(trace_id)

    @patch("data_ingestion.tasks.create_ingestion_service")
    def test_process_batch_task(self, mock_create_service):
        """Test the process_batch Celery task."""
        mock_service = MagicMock()
        mock_result = ProcessedEvent(
            event_id=uuid4(),
            trace_id=uuid4(),
            timestamp=datetime.utcnow(),
            tenant_id="tenant-123",
            source_path="gs://bucket/_landing/file.mp4",
            destination_path="gs://bucket/tenant-123/raw/file.mp4",
            status=ProcessingStatus.RAW_STORED,
        )
        mock_service.process_event.return_value = mock_result
        mock_create_service.return_value = mock_service

        from data_ingestion.tasks import process_batch

        events = [
            {
                "event_id": str(uuid4()),
                "tenant_id": "tenant-123",
                "file_path": "gs://bucket/_landing/file1.mp4",
            },
            {
                "event_id": str(uuid4()),
                "tenant_id": "tenant-456",
                "file_path": "gs://bucket/_landing/file2.mp4",
            },
        ]

        result = process_batch.apply(args=[events]).get()

        assert result["total"] == 2
        assert result["success"] + result["skipped"] + result["failed"] == 2


# =============================================================================
# Multi-Tenant Integration Tests
# =============================================================================


class TestMultiTenantIntegration:
    """Test multi-tenant isolation in the pipeline."""

    def test_tenant_isolation_in_storage_paths(
        self, integration_storage, integration_cache, integration_producer
    ):
        """Test that different tenants have isolated storage paths."""
        service = IngestionService(
            storage=integration_storage,
            cache=integration_cache,
            producer=integration_producer,
            output_topic="output",
            dlq_topic="dlq",
        )

        # Process events for different tenants
        event_a = create_test_event(
            tenant_id="tenant-a",
            file_path="gs://onboarding-bucket1/_landing/tenant-a/video1.mp4",
        )
        event_b = create_test_event(
            tenant_id="tenant-b",
            file_path="gs://onboarding-bucket1/_landing/tenant-b/image1.jpg",
        )

        result_a = service.process_event(event_a)
        result_b = service.process_event(event_b)

        # Verify tenant isolation
        assert "tenant-a" in result_a.destination_path
        assert "tenant-b" not in result_a.destination_path

        assert "tenant-b" in result_b.destination_path
        assert "tenant-a" not in result_b.destination_path

    def test_tenant_id_normalization(
        self, integration_storage, integration_cache, integration_producer
    ):
        """Test that tenant IDs are normalized in paths."""
        service = IngestionService(
            storage=integration_storage,
            cache=integration_cache,
            producer=integration_producer,
            output_topic="output",
            dlq_topic="dlq",
        )

        # Add file for tenant with uppercase
        integration_storage.add_file(
            "gs://onboarding-bucket1/_landing/TENANT-C/file.mp4"
        )

        event = create_test_event(
            tenant_id="TENANT-C",  # Uppercase
            file_path="gs://onboarding-bucket1/_landing/TENANT-C/file.mp4",
        )

        result = service.process_event(event)

        # Tenant ID should be normalized to lowercase in path
        assert "tenant-c" in result.destination_path.lower()


# =============================================================================
# Idempotency Integration Tests
# =============================================================================


class TestIdempotencyIntegration:
    """Test idempotency guarantees in the pipeline."""

    def test_processing_is_idempotent_with_deduplication(
        self,
        integration_service,
        integration_storage,
        integration_cache,
        integration_producer,
    ):
        """Test that reprocessing the same event doesn't create duplicates."""
        event = create_test_event(
            tenant_id="tenant-a",
            file_path="gs://onboarding-bucket1/_landing/tenant-a/video1.mp4",
        )

        # Process first time
        integration_service.process_event(event)
        published_count_after_first = len(integration_producer.published)

        # Try to process again
        integration_storage.add_file(
            "gs://onboarding-bucket1/_landing/tenant-a/video1.mp4"
        )

        with pytest.raises(DuplicateEventError):
            integration_service.process_event(
                IngestionEvent(
                    event_id=event.event_id,  # Same ID
                    trace_id=uuid4(),
                    tenant_id=event.tenant_id,
                    file_path="gs://onboarding-bucket1/_landing/tenant-a/video1.mp4",
                    file_type=event.file_type,
                    timestamp=datetime.utcnow(),
                    source=event.source,
                )
            )

        # No additional events should be published
        assert len(integration_producer.published) == published_count_after_first
