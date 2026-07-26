"""
End-to-End (E2E) tests for the data ingestion pipeline.

These tests verify the complete pipeline flow from file landing to
output event publishing, simulating real-world usage scenarios.
"""

import pytest
import json
from datetime import datetime
from uuid import uuid4
from unittest.mock import patch

from data_ingestion.domain.models import (
    IngestionEvent,
    ProcessingStatus,
    EventSource,
)
from data_ingestion.domain.services import IngestionService
from data_ingestion.domain.exceptions import (
    DuplicateEventError,
    FileNotFoundInLandingError,
    NonRetryableError,
    RetryableError,
)
from data_ingestion.tests.conftest import (
    MockStoragePort,
    MockCachePort,
    MockEventProducerPort,
    MockEventConsumerPort,
)


# =============================================================================
# E2E Test Fixtures
# =============================================================================


@pytest.fixture
def e2e_storage() -> MockStoragePort:
    """
    Create a mock storage simulating a real GCS bucket.
    Pre-populated with files in landing zone.
    """
    storage = MockStoragePort()

    # Simulate files that would be uploaded by various sources
    test_files = [
        # Frontend uploads
        (
            "gs://zorven-raw-assets/_landing/frontend/tenant-a/profile_video.mp4",
            b"video_content_a",
        ),
        (
            "gs://zorven-raw-assets/_landing/frontend/tenant-a/logo.png",
            b"image_content_a",
        ),
        (
            "gs://zorven-raw-assets/_landing/frontend/tenant-b/promo_video.mp4",
            b"video_content_b",
        ),
        # API uploads
        (
            "gs://zorven-raw-assets/_landing/api/tenant-c/bulk_upload_1.mp4",
            b"video_bulk_1",
        ),
        (
            "gs://zorven-raw-assets/_landing/api/tenant-c/bulk_upload_2.mp4",
            b"video_bulk_2",
        ),
        # Batch imports
        (
            "gs://zorven-raw-assets/_landing/batch/tenant-d/batch_file.mp4",
            b"batch_content",
        ),
        # Edge cases
        (
            "gs://zorven-raw-assets/_landing/special/tenant-e/file with spaces.mp4",
            b"space_file",
        ),
        (
            "gs://zorven-raw-assets/_landing/special/tenant-e/файл_unicode.mp4",
            b"unicode_file",
        ),
    ]

    for path, content in test_files:
        storage.add_file(path, content)

    return storage


@pytest.fixture
def e2e_cache() -> MockCachePort:
    """Create a fresh cache for E2E tests."""
    return MockCachePort()


@pytest.fixture
def e2e_producer() -> MockEventProducerPort:
    """Create a mock producer that tracks all published events."""
    return MockEventProducerPort()


@pytest.fixture
def e2e_consumer() -> MockEventConsumerPort:
    """Create a mock consumer for E2E tests."""
    return MockEventConsumerPort()


@pytest.fixture
def e2e_service(e2e_storage, e2e_cache, e2e_producer) -> IngestionService:
    """Create a fully configured IngestionService for E2E testing."""
    return IngestionService(
        storage=e2e_storage,
        cache=e2e_cache,
        producer=e2e_producer,
        output_topic="curation-needed-topic",
        dlq_topic="ingestion-dlq",
        dedupe_ttl_seconds=3600,
        status_ttl_seconds=604800,
        max_retries=3,
        retry_backoff_seconds=0.1,  # Fast retries for tests
    )


def create_ingestion_event(
    tenant_id: str,
    file_path: str,
    source: EventSource = EventSource.FRONTEND_UPLOAD,
    file_type: str = "video/mp4",
    metadata: dict = None,
) -> IngestionEvent:
    """Helper to create ingestion events for E2E tests."""
    return IngestionEvent(
        event_id=uuid4(),
        trace_id=uuid4(),
        tenant_id=tenant_id,
        file_path=file_path,
        file_type=file_type,
        timestamp=datetime.utcnow(),
        source=source,
        metadata=metadata or {},
    )


# =============================================================================
# E2E Scenario: Complete File Upload Flow
# =============================================================================


class TestE2ECompleteUploadFlow:
    """E2E tests for the complete file upload and processing flow."""

    def test_frontend_upload_complete_flow(
        self, e2e_service, e2e_storage, e2e_cache, e2e_producer
    ):
        """
        E2E Test: Frontend upload goes through complete pipeline.

        Scenario:
        1. User uploads video via frontend
        2. File lands in _landing zone
        3. Kafka event triggers ingestion
        4. File is moved to tenant's raw storage
        5. Output event is published
        6. Status is tracked throughout
        """
        # Arrange - file already in landing (from fixture)
        event = create_ingestion_event(
            tenant_id="tenant-a",
            file_path="gs://zorven-raw-assets/_landing/frontend/tenant-a/profile_video.mp4",
            source=EventSource.FRONTEND_UPLOAD,
            metadata={"uploaded_by": "user-123", "original_filename": "my_video.mp4"},
        )

        # Act - process the event
        result = e2e_service.process_event(event)

        # Assert - complete flow verification
        # 1. Result is successful
        assert result.status == ProcessingStatus.RAW_STORED
        assert result.event_id == event.event_id
        assert result.trace_id == event.trace_id

        # 2. File moved to correct location
        assert "tenant-a" in result.destination_path
        assert "/raw/" in result.destination_path
        assert "profile_video.mp4" in result.destination_path

        # 3. Source file no longer exists
        assert event.file_path not in e2e_storage.files

        # 4. Destination file exists
        assert result.destination_path in e2e_storage.files

        # 5. Output event was published
        assert len(e2e_producer.published) == 1
        topic, published_event = e2e_producer.published[0]
        assert topic == "curation-needed-topic"
        assert published_event.event_id == event.event_id

        # 6. Deduplication is set
        assert str(event.event_id) in e2e_cache.processed

        # 7. Status is tracked
        status = e2e_cache.get_status(str(event.trace_id))
        assert status is not None
        assert status["status"] == ProcessingStatus.RAW_STORED.value

    def test_api_batch_upload_flow(
        self, e2e_service, e2e_storage, e2e_cache, e2e_producer
    ):
        """
        E2E Test: API batch upload processes multiple files.

        Scenario:
        1. API client uploads multiple files
        2. Each file triggers separate ingestion event
        3. All files processed successfully
        4. All output events published
        """
        # Arrange - create events for batch files
        events = [
            create_ingestion_event(
                tenant_id="tenant-c",
                file_path="gs://zorven-raw-assets/_landing/api/tenant-c/bulk_upload_1.mp4",
                source=EventSource.API_INTEGRATION,
            ),
            create_ingestion_event(
                tenant_id="tenant-c",
                file_path="gs://zorven-raw-assets/_landing/api/tenant-c/bulk_upload_2.mp4",
                source=EventSource.API_INTEGRATION,
            ),
        ]

        # Act - process all events
        results = [e2e_service.process_event(event) for event in events]

        # Assert
        assert all(r.status == ProcessingStatus.RAW_STORED for r in results)
        assert len(e2e_producer.published) == 2
        assert all(str(e.event_id) in e2e_cache.processed for e in events)

        # All files should be in tenant-c's raw storage
        for result in results:
            assert "tenant-c" in result.destination_path
            assert "/raw/" in result.destination_path


# =============================================================================
# E2E Scenario: Kafka Consumer to Service Flow
# =============================================================================


class TestE2EKafkaConsumerFlow:
    """E2E tests for Kafka consumer to service integration."""

    def test_consumer_to_service_complete_flow(
        self, e2e_service, e2e_storage, e2e_consumer
    ):
        """
        E2E Test: Events from Kafka consumer flow through service.

        Scenario:
        1. Kafka consumer receives messages
        2. Messages are deserialized to IngestionEvents
        3. Service processes each event
        4. Consumer commits after successful processing
        """
        # Arrange - add events to consumer
        events = [
            create_ingestion_event(
                tenant_id="tenant-a",
                file_path="gs://zorven-raw-assets/_landing/frontend/tenant-a/profile_video.mp4",
            ),
            create_ingestion_event(
                tenant_id="tenant-b",
                file_path="gs://zorven-raw-assets/_landing/frontend/tenant-b/promo_video.mp4",
            ),
        ]
        e2e_consumer.events.extend(events)

        # Act - simulate consumer loop
        processed_count = 0
        while True:
            event = e2e_consumer.consume_one()
            if event is None:
                break

            result = e2e_service.process_event(event)
            assert result.status == ProcessingStatus.RAW_STORED

            e2e_consumer.commit()
            processed_count += 1

        # Assert
        assert processed_count == 2
        assert e2e_consumer.committed

    def test_consumer_handles_processing_errors(
        self, e2e_storage, e2e_cache, e2e_producer, e2e_consumer
    ):
        """
        E2E Test: Consumer handles errors without losing messages.

        Scenario:
        1. Consumer receives event for non-existent file
        2. Processing fails with FileNotFoundInLandingError
        3. Event is NOT committed (will be redelivered)
        4. DLQ handling can be triggered
        """
        # Arrange - event for non-existent file
        event = create_ingestion_event(
            tenant_id="tenant-x",
            file_path="gs://zorven-raw-assets/_landing/nonexistent.mp4",
        )
        e2e_consumer.events.append(event)

        service = IngestionService(
            storage=e2e_storage,
            cache=e2e_cache,
            producer=e2e_producer,
            output_topic="output",
            dlq_topic="dlq",
        )

        # Act
        consumed_event = e2e_consumer.consume_one()
        assert consumed_event is not None

        try:
            service.process_event(consumed_event)
            committed = True
        except (NonRetryableError, FileNotFoundInLandingError):
            committed = False
            # In real scenario, send to DLQ
            service.send_to_dlq(
                consumed_event.model_dump(),
                NonRetryableError("File not found"),
                "input-topic",
            )

        # Assert
        assert not committed
        assert len(e2e_producer.dlq_messages) == 1


# =============================================================================
# E2E Scenario: Deduplication and Idempotency
# =============================================================================


class TestE2EDeduplication:
    """E2E tests for deduplication across the pipeline."""

    def test_duplicate_prevention_across_retries(
        self, e2e_service, e2e_storage, e2e_cache, e2e_producer
    ):
        """
        E2E Test: Duplicate events are prevented even after retries.

        Scenario:
        1. Event is processed successfully
        2. Due to network issue, confirmation is lost
        3. Same event is retried
        4. Pipeline detects duplicate and skips
        """
        # Arrange
        event = create_ingestion_event(
            tenant_id="tenant-a",
            file_path="gs://zorven-raw-assets/_landing/frontend/tenant-a/profile_video.mp4",
        )

        # Act - first processing
        result1 = e2e_service.process_event(event)
        assert result1.status == ProcessingStatus.RAW_STORED
        first_publish_count = len(e2e_producer.published)

        # Simulate retry - re-add file and try again
        e2e_storage.add_file(event.file_path)

        # Create "retry" event with same event_id
        retry_event = IngestionEvent(
            event_id=event.event_id,  # Same event ID
            trace_id=uuid4(),  # Different trace
            tenant_id=event.tenant_id,
            file_path=event.file_path,
            file_type=event.file_type,
            timestamp=datetime.utcnow(),
            source=event.source,
        )

        # Assert - should raise duplicate error
        with pytest.raises(DuplicateEventError):
            e2e_service.process_event(retry_event)

        # No additional events published
        assert len(e2e_producer.published) == first_publish_count

    def test_process_with_retry_graceful_duplicate_handling(
        self, e2e_service, e2e_storage, e2e_cache
    ):
        """
        E2E Test: process_event_with_retry handles duplicates gracefully.

        Scenario:
        1. Event is processed successfully
        2. Same event_id is retried
        3. Returns None (not an error)
        """
        event = create_ingestion_event(
            tenant_id="tenant-a",
            file_path="gs://zorven-raw-assets/_landing/frontend/tenant-a/profile_video.mp4",
        )

        # First attempt
        result1 = e2e_service.process_event_with_retry(event)
        assert result1 is not None

        # Re-add file for retry
        e2e_storage.add_file(event.file_path)

        # Retry with same event_id
        retry_event = IngestionEvent(
            event_id=event.event_id,
            trace_id=uuid4(),
            tenant_id=event.tenant_id,
            file_path=event.file_path,
            file_type=event.file_type,
            timestamp=datetime.utcnow(),
            source=event.source,
        )

        # Should return None, not raise
        result2 = e2e_service.process_event_with_retry(retry_event)
        assert result2 is None


# =============================================================================
# E2E Scenario: Multi-Tenant Isolation
# =============================================================================


class TestE2EMultiTenantIsolation:
    """E2E tests for multi-tenant data isolation."""

    def test_tenant_data_isolation_in_storage(
        self, e2e_service, e2e_storage, e2e_cache, e2e_producer
    ):
        """
        E2E Test: Files are isolated by tenant in storage.

        Scenario:
        1. Multiple tenants upload files
        2. Each tenant's files go to separate paths
        3. No cross-tenant data access
        """
        # Arrange
        tenant_events = {
            "tenant-a": create_ingestion_event(
                tenant_id="tenant-a",
                file_path="gs://zorven-raw-assets/_landing/frontend/tenant-a/profile_video.mp4",
            ),
            "tenant-b": create_ingestion_event(
                tenant_id="tenant-b",
                file_path="gs://zorven-raw-assets/_landing/frontend/tenant-b/promo_video.mp4",
            ),
        }

        # Act
        results = {}
        for tenant_id, event in tenant_events.items():
            results[tenant_id] = e2e_service.process_event(event)

        # Assert - verify tenant isolation
        for tenant_id, result in results.items():
            # Each result should contain only its tenant's path
            assert tenant_id in result.destination_path

            # Other tenants should NOT be in path
            for other_tenant in tenant_events.keys():
                if other_tenant != tenant_id:
                    assert other_tenant not in result.destination_path

    def test_concurrent_tenant_processing(self, e2e_storage, e2e_cache, e2e_producer):
        """
        E2E Test: Multiple tenants can be processed concurrently.

        Scenario:
        1. Multiple services process different tenants
        2. No interference between tenant processing
        3. All outputs are correctly isolated
        """
        # Create separate services (simulating concurrent workers)
        service1 = IngestionService(
            storage=e2e_storage,
            cache=e2e_cache,
            producer=e2e_producer,
            output_topic="output",
            dlq_topic="dlq",
        )
        service2 = IngestionService(
            storage=e2e_storage,
            cache=e2e_cache,
            producer=e2e_producer,
            output_topic="output",
            dlq_topic="dlq",
        )

        # Arrange
        event_a = create_ingestion_event(
            tenant_id="tenant-a",
            file_path="gs://zorven-raw-assets/_landing/frontend/tenant-a/profile_video.mp4",
        )
        event_b = create_ingestion_event(
            tenant_id="tenant-b",
            file_path="gs://zorven-raw-assets/_landing/frontend/tenant-b/promo_video.mp4",
        )

        # Act - "concurrent" processing
        result_a = service1.process_event(event_a)
        result_b = service2.process_event(event_b)

        # Assert
        assert result_a.status == ProcessingStatus.RAW_STORED
        assert result_b.status == ProcessingStatus.RAW_STORED
        assert "tenant-a" in result_a.destination_path
        assert "tenant-b" in result_b.destination_path
        assert len(e2e_producer.published) == 2


# =============================================================================
# E2E Scenario: Error Handling and Recovery
# =============================================================================


class TestE2EErrorHandling:
    """E2E tests for error handling and recovery scenarios."""

    def test_missing_file_triggers_dlq(self, e2e_storage, e2e_cache, e2e_producer):
        """
        E2E Test: Missing file triggers DLQ flow.

        Scenario:
        1. Event received for file that doesn't exist
        2. Processing fails with FileNotFoundInLandingError
        3. Event is sent to DLQ
        4. Status is marked as FAILED
        """
        service = IngestionService(
            storage=e2e_storage,
            cache=e2e_cache,
            producer=e2e_producer,
            output_topic="output",
            dlq_topic="ingestion-dlq",
        )

        event = create_ingestion_event(
            tenant_id="tenant-x",
            file_path="gs://zorven-raw-assets/_landing/missing_file.mp4",
        )

        # Act
        try:
            service.process_event(event)
        except NonRetryableError as e:
            # Simulate DLQ send
            service.send_to_dlq(event.model_dump(), e, "raw-ingestion-topic")

        # Assert
        status = e2e_cache.get_status(str(event.trace_id))
        assert status is not None
        assert status["status"] == ProcessingStatus.FAILED.value

        # DLQ should have the message
        assert len(e2e_producer.dlq_messages) == 1
        dlq_msg = e2e_producer.dlq_messages[0]
        assert dlq_msg["source_topic"] == "raw-ingestion-topic"

    def test_storage_error_is_retryable(self, e2e_cache, e2e_producer):
        """
        E2E Test: Transient storage errors are retried.

        Scenario:
        1. GCS returns a temporary error
        2. Pipeline marks error as retryable
        3. Retry mechanism can be triggered
        """

        # Create storage that fails on move
        class FailingStorage(MockStoragePort):
            def __init__(self):
                super().__init__()
                self.attempt = 0

            def move_file(self, source_path, destination_path):
                self.attempt += 1
                if self.attempt < 3:
                    from data_ingestion.domain.exceptions import StorageOperationError

                    raise StorageOperationError(
                        operation="move_file",
                        path=source_path,
                        cause=Exception("Temporary network error"),
                        is_retryable=True,
                    )
                return super().move_file(source_path, destination_path)

        storage = FailingStorage()
        storage.add_file("gs://bucket/_landing/file.mp4")

        service = IngestionService(
            storage=storage,
            cache=e2e_cache,
            producer=e2e_producer,
            output_topic="output",
            dlq_topic="dlq",
        )

        event = create_ingestion_event(
            tenant_id="tenant-x",
            file_path="gs://bucket/_landing/file.mp4",
        )

        # Act & Assert - should raise RetryableError
        with pytest.raises(RetryableError):
            service.process_event(event)


# =============================================================================
# E2E Scenario: Status Tracking Throughout Pipeline
# =============================================================================


class TestE2EStatusTracking:
    """E2E tests for status tracking throughout the pipeline."""

    def test_status_progression_complete_flow(
        self, e2e_service, e2e_storage, e2e_cache
    ):
        """
        E2E Test: Status is tracked at each pipeline stage.

        Scenario:
        1. Event starts processing
        2. Status updates through stages
        3. Final status is RAW_STORED
        """
        event = create_ingestion_event(
            tenant_id="tenant-a",
            file_path="gs://zorven-raw-assets/_landing/frontend/tenant-a/profile_video.mp4",
        )

        # Act
        e2e_service.process_event(event)

        # Assert - final status
        status = e2e_cache.get_status(str(event.trace_id))
        assert status is not None
        assert status["status"] == ProcessingStatus.RAW_STORED.value

    def test_status_check_api(self, e2e_service, e2e_storage, e2e_cache):
        """
        E2E Test: Status can be queried after processing.

        Scenario:
        1. Event is processed
        2. Client queries status by trace_id
        3. Complete status info is returned
        """
        event = create_ingestion_event(
            tenant_id="tenant-a",
            file_path="gs://zorven-raw-assets/_landing/frontend/tenant-a/profile_video.mp4",
        )

        # Act
        e2e_service.process_event(event)

        # Query status
        status = e2e_cache.get_status(str(event.trace_id))

        # Assert
        assert status is not None
        assert "status" in status
        assert "updated_at" in status


# =============================================================================
# E2E Scenario: Special Characters and Edge Cases
# =============================================================================


class TestE2EEdgeCases:
    """E2E tests for edge cases and special scenarios."""

    def test_file_with_spaces_in_name(
        self, e2e_service, e2e_storage, e2e_cache, e2e_producer
    ):
        """
        E2E Test: Files with spaces in names are handled correctly.
        """
        event = create_ingestion_event(
            tenant_id="tenant-e",
            file_path="gs://zorven-raw-assets/_landing/special/tenant-e/file with spaces.mp4",
        )

        result = e2e_service.process_event(event)

        assert result.status == ProcessingStatus.RAW_STORED
        assert "file with spaces.mp4" in result.destination_path

    def test_file_with_unicode_name(
        self, e2e_service, e2e_storage, e2e_cache, e2e_producer
    ):
        """
        E2E Test: Files with unicode characters are handled correctly.
        """
        event = create_ingestion_event(
            tenant_id="tenant-e",
            file_path="gs://zorven-raw-assets/_landing/special/tenant-e/файл_unicode.mp4",
        )

        result = e2e_service.process_event(event)

        assert result.status == ProcessingStatus.RAW_STORED
        assert "файл_unicode.mp4" in result.destination_path

    def test_large_batch_processing(self, e2e_cache, e2e_producer):
        """
        E2E Test: Large batch of files can be processed.
        """
        storage = MockStoragePort()
        batch_size = 50

        # Add many files
        for i in range(batch_size):
            storage.add_file(f"gs://bucket/_landing/batch/file_{i}.mp4")

        service = IngestionService(
            storage=storage,
            cache=e2e_cache,
            producer=e2e_producer,
            output_topic="output",
            dlq_topic="dlq",
        )

        # Process all
        results = []
        for i in range(batch_size):
            event = create_ingestion_event(
                tenant_id="tenant-batch",
                file_path=f"gs://bucket/_landing/batch/file_{i}.mp4",
            )
            result = service.process_event(event)
            results.append(result)

        # Assert
        assert len(results) == batch_size
        assert all(r.status == ProcessingStatus.RAW_STORED for r in results)
        assert len(e2e_producer.published) == batch_size

    def test_different_file_types(self, e2e_storage, e2e_cache, e2e_producer):
        """
        E2E Test: Different file types are processed correctly.
        """
        # Add files of different types
        e2e_storage.add_file("gs://bucket/_landing/video.mp4", b"video")
        e2e_storage.add_file("gs://bucket/_landing/image.jpg", b"image")
        e2e_storage.add_file("gs://bucket/_landing/doc.pdf", b"document")

        service = IngestionService(
            storage=e2e_storage,
            cache=e2e_cache,
            producer=e2e_producer,
            output_topic="output",
            dlq_topic="dlq",
        )

        file_types = [
            ("gs://bucket/_landing/video.mp4", "video/mp4"),
            ("gs://bucket/_landing/image.jpg", "image/jpeg"),
            ("gs://bucket/_landing/doc.pdf", "application/pdf"),
        ]

        for file_path, file_type in file_types:
            event = create_ingestion_event(
                tenant_id="tenant-x",
                file_path=file_path,
                file_type=file_type,
            )
            result = service.process_event(event)
            assert result.status == ProcessingStatus.RAW_STORED


# =============================================================================
# E2E Scenario: Celery Task Integration
# =============================================================================


class TestE2ECeleryTasks:
    """E2E tests for Celery task execution."""

    @patch("data_ingestion.tasks.create_ingestion_service")
    def test_celery_task_complete_flow(self, mock_create_service):
        """
        E2E Test: Celery task processes event end-to-end.
        """
        # Setup mock service
        mock_storage = MockStoragePort()
        mock_storage.add_file("gs://bucket/_landing/file.mp4")
        mock_cache = MockCachePort()
        mock_producer = MockEventProducerPort()

        mock_service = IngestionService(
            storage=mock_storage,
            cache=mock_cache,
            producer=mock_producer,
            output_topic="output",
            dlq_topic="dlq",
        )
        mock_create_service.return_value = mock_service

        from data_ingestion.tasks import process_ingestion_event

        event_id = str(uuid4())
        trace_id = str(uuid4())

        # Execute task
        result = process_ingestion_event.apply(
            args=[],
            kwargs={
                "event_id": event_id,
                "tenant_id": "tenant-123",
                "file_path": "gs://bucket/_landing/file.mp4",
                "file_type": "video/mp4",
                "trace_id": trace_id,
            },
        ).get()

        assert result["status"] == "success"
        assert result["event_id"] == event_id
        assert len(mock_producer.published) == 1

    @patch("data_ingestion.tasks.create_ingestion_service")
    def test_celery_batch_task_complete_flow(self, mock_create_service):
        """
        E2E Test: Celery batch task processes multiple events.
        """
        mock_storage = MockStoragePort()
        for i in range(3):
            mock_storage.add_file(f"gs://bucket/_landing/file_{i}.mp4")

        mock_cache = MockCachePort()
        mock_producer = MockEventProducerPort()

        mock_service = IngestionService(
            storage=mock_storage,
            cache=mock_cache,
            producer=mock_producer,
            output_topic="output",
            dlq_topic="dlq",
        )
        mock_create_service.return_value = mock_service

        from data_ingestion.tasks import process_batch

        events = [
            {
                "event_id": str(uuid4()),
                "tenant_id": "tenant-123",
                "file_path": f"gs://bucket/_landing/file_{i}.mp4",
            }
            for i in range(3)
        ]

        result = process_batch.apply(args=[events]).get()

        assert result["total"] == 3
        assert result["success"] + result["skipped"] + result["failed"] == 3


# =============================================================================
# E2E Scenario: Full Pipeline Simulation
# =============================================================================


class TestE2EFullPipelineSimulation:
    """E2E tests simulating the complete pipeline from start to finish."""

    def test_simulate_real_world_upload_flow(
        self, e2e_storage, e2e_cache, e2e_producer
    ):
        """
        E2E Test: Simulate a real-world file upload flow.

        This test simulates:
        1. User uploads file via frontend
        2. Frontend stores file in landing zone
        3. Frontend publishes Kafka event
        4. Consumer picks up event
        5. Ingestion service processes
        6. Output event published for curation
        """
        # Step 1-2: Simulate frontend upload (file already in storage)
        file_path = (
            "gs://zorven-raw-assets/_landing/frontend/tenant-a/profile_video.mp4"
        )
        assert file_path in e2e_storage.files

        # Step 3: Frontend would publish Kafka event (we create it directly)
        kafka_event_payload = {
            "event_id": str(uuid4()),
            "trace_id": str(uuid4()),
            "tenant_id": "tenant-a",
            "file_path": file_path,
            "file_type": "video/mp4",
            "timestamp": datetime.utcnow().isoformat(),
            "source": "frontend-upload",
            "metadata": {
                "uploaded_by": "user-456",
                "original_filename": "my_video.mp4",
            },
        }

        # Step 4: Consumer deserializes event
        event = IngestionEvent(
            event_id=kafka_event_payload["event_id"],
            trace_id=kafka_event_payload["trace_id"],
            tenant_id=kafka_event_payload["tenant_id"],
            file_path=kafka_event_payload["file_path"],
            file_type=kafka_event_payload["file_type"],
            timestamp=datetime.fromisoformat(kafka_event_payload["timestamp"]),
            source=EventSource(kafka_event_payload["source"]),
            metadata=kafka_event_payload.get("metadata"),
        )

        # Step 5: Ingestion service processes
        service = IngestionService(
            storage=e2e_storage,
            cache=e2e_cache,
            producer=e2e_producer,
            output_topic="curation-needed-topic",
            dlq_topic="ingestion-dlq",
        )

        result = service.process_event(event)

        # Step 6: Verify output
        assert result.status == ProcessingStatus.RAW_STORED
        assert len(e2e_producer.published) == 1

        # Verify published event format
        topic, published_event = e2e_producer.published[0]
        assert topic == "curation-needed-topic"
        assert published_event.tenant_id == "tenant-a"
        assert "/raw/" in published_event.destination_path

        # Verify the event can be serialized for downstream
        output_payload = {
            "event_id": str(published_event.event_id),
            "trace_id": str(published_event.trace_id),
            "tenant_id": published_event.tenant_id,
            "source_path": published_event.source_path,
            "destination_path": published_event.destination_path,
            "status": published_event.status.value,
            "processing_duration_ms": published_event.processing_duration_ms,
        }

        # Can be JSON serialized
        json_output = json.dumps(output_payload)
        assert "tenant-a" in json_output
        assert "raw_stored" in json_output

    def test_pipeline_resilience_simulation(self, e2e_cache, e2e_producer):
        """
        E2E Test: Pipeline is resilient to various failure scenarios.
        """
        processed = 0
        failed = 0
        duplicates = 0

        storage = MockStoragePort()

        # Add some files, but not all (to test missing file handling)
        for i in range(10):
            if i % 3 != 0:  # Skip every 3rd file
                storage.add_file(f"gs://bucket/_landing/file_{i}.mp4")

        service = IngestionService(
            storage=storage,
            cache=e2e_cache,
            producer=e2e_producer,
            output_topic="output",
            dlq_topic="dlq",
        )

        # Process events including duplicates and missing files
        events = []
        for i in range(15):
            file_idx = i % 10  # Reuse some event IDs (creates duplicates)
            events.append(
                create_ingestion_event(
                    tenant_id="tenant-x",
                    file_path=f"gs://bucket/_landing/file_{file_idx}.mp4",
                )
            )

        # Make some events have duplicate IDs
        for i in range(3):
            events[10 + i] = IngestionEvent(
                event_id=events[i].event_id,  # Duplicate ID
                trace_id=uuid4(),
                tenant_id=events[i].tenant_id,
                file_path=events[i].file_path,
                file_type=events[i].file_type,
                timestamp=datetime.utcnow(),
                source=events[i].source,
            )

        for event in events:
            try:
                # Re-add file if it was moved
                if event.file_path not in storage.files:
                    if int(event.file_path.split("_")[-1].split(".")[0]) % 3 != 0:
                        storage.add_file(event.file_path)

                result = service.process_event(event)
                if result:
                    processed += 1
            except DuplicateEventError:
                duplicates += 1
            except NonRetryableError:
                failed += 1

        # Assert - pipeline handled all scenarios
        assert processed > 0
        assert (
            duplicates > 0 or failed > 0
        )  # Some should have failed or been duplicates
        total = processed + failed + duplicates
        assert total == len(events)
