"""
Unit tests for IngestionService.

Tests the orchestration logic with mocked dependencies.
"""

import pytest
from uuid import uuid4

from data_ingestion.domain.services import IngestionService
from data_ingestion.domain.models import (
    ProcessedEvent,
    ProcessingStatus,
)
from data_ingestion.domain.exceptions import (
    DuplicateEventError,
    FileNotFoundInLandingError,
    NonRetryableError,
    RetryableError,
    StorageOperationError,
    CacheOperationError,
)

from data_ingestion.tests.conftest import (
    MockStoragePort,
    MockCachePort,
)


class TestIngestionServiceInit:
    """Tests for IngestionService initialization."""

    def test_service_initialization(self, mock_storage, mock_cache, mock_producer):
        """Test service initializes with all dependencies."""
        service = IngestionService(
            storage=mock_storage,
            cache=mock_cache,
            producer=mock_producer,
            output_topic="output-topic",
            dlq_topic="dlq-topic",
        )

        assert service.storage == mock_storage
        assert service.cache == mock_cache
        assert service.producer == mock_producer
        assert service.output_topic == "output-topic"
        assert service.dlq_topic == "dlq-topic"

    def test_default_configuration(self, mock_storage, mock_cache, mock_producer):
        """Test default configuration values."""
        service = IngestionService(
            storage=mock_storage,
            cache=mock_cache,
            producer=mock_producer,
            output_topic="output",
            dlq_topic="dlq",
        )

        assert service.dedupe_ttl_seconds == 3600
        assert service.status_ttl_seconds == 604800
        assert service.max_retries == 3
        assert service.retry_backoff_seconds == 1.0

    def test_custom_configuration(self, mock_storage, mock_cache, mock_producer):
        """Test custom configuration values."""
        service = IngestionService(
            storage=mock_storage,
            cache=mock_cache,
            producer=mock_producer,
            output_topic="output",
            dlq_topic="dlq",
            dedupe_ttl_seconds=7200,
            status_ttl_seconds=86400,
            max_retries=5,
            retry_backoff_seconds=2.0,
        )

        assert service.dedupe_ttl_seconds == 7200
        assert service.status_ttl_seconds == 86400
        assert service.max_retries == 5
        assert service.retry_backoff_seconds == 2.0


class TestProcessEvent:
    """Tests for process_event method."""

    def test_successful_processing(self, ingestion_service, mock_storage, sample_event):
        """Test successful event processing."""
        # Add file to mock storage
        mock_storage.add_file(sample_event.file_path)

        # Process event
        result = ingestion_service.process_event(sample_event)

        # Verify result
        assert isinstance(result, ProcessedEvent)
        assert result.event_id == sample_event.event_id
        assert result.status == ProcessingStatus.RAW_STORED
        assert result.processing_duration_ms >= 0  # May be 0 for fast operations
        assert "raw" in result.destination_path

    def test_duplicate_event_raises_error(
        self, ingestion_service, mock_cache, sample_event
    ):
        """Test that duplicate events raise DuplicateEventError."""
        # Mark event as already processed
        mock_cache.mark_processed(str(sample_event.event_id))

        # Should raise DuplicateEventError
        with pytest.raises(DuplicateEventError):
            ingestion_service.process_event(sample_event)

    def test_file_not_found_raises_error(self, ingestion_service, sample_event):
        """Test that missing files raise NonRetryableError."""
        # Don't add file to storage - it won't exist

        with pytest.raises(NonRetryableError) as exc_info:
            ingestion_service.process_event(sample_event)

        assert isinstance(exc_info.value.cause, FileNotFoundInLandingError)

    def test_publishes_to_output_topic(
        self, ingestion_service, mock_storage, mock_producer, sample_event
    ):
        """Test that successful processing publishes to output topic."""
        mock_storage.add_file(sample_event.file_path)

        ingestion_service.process_event(sample_event)

        # Verify publish was called
        assert len(mock_producer.published) == 1
        topic, event = mock_producer.published[0]
        assert topic == "curation-needed-topic"
        assert event.event_id == sample_event.event_id

    def test_updates_status_through_pipeline(
        self, ingestion_service, mock_storage, mock_cache, sample_event
    ):
        """Test that status is updated through the pipeline."""
        mock_storage.add_file(sample_event.file_path)

        ingestion_service.process_event(sample_event)

        # Verify final status
        trace_id = str(sample_event.trace_id)
        status = mock_cache.get_status(trace_id)
        assert status is not None
        assert status["status"] == ProcessingStatus.RAW_STORED.value

    def test_marks_event_as_processed(
        self, ingestion_service, mock_storage, mock_cache, sample_event
    ):
        """Test that event is marked as processed for deduplication."""
        mock_storage.add_file(sample_event.file_path)

        ingestion_service.process_event(sample_event)

        # Verify deduplication key is set
        assert mock_cache.is_duplicate(str(sample_event.event_id))

    def test_moves_file_to_raw_storage(
        self, ingestion_service, mock_storage, sample_event
    ):
        """Test that file is moved from landing to raw storage."""
        mock_storage.add_file(sample_event.file_path)

        result = ingestion_service.process_event(sample_event)

        # Verify move was called
        assert len(mock_storage.move_calls) == 1
        source, dest = mock_storage.move_calls[0]
        assert source == sample_event.file_path
        assert dest == result.destination_path

        # Original file should no longer exist
        assert sample_event.file_path not in mock_storage.files

        # Destination file should exist
        assert result.destination_path in mock_storage.files


class TestProcessEventWithRetry:
    """Tests for process_event_with_retry method."""

    def test_successful_first_attempt(
        self, ingestion_service, mock_storage, sample_event
    ):
        """Test successful processing on first attempt."""
        mock_storage.add_file(sample_event.file_path)

        result = ingestion_service.process_event_with_retry(sample_event)

        assert result is not None
        assert result.status == ProcessingStatus.RAW_STORED

    def test_duplicate_returns_none(self, ingestion_service, mock_cache, sample_event):
        """Test that duplicate events return None."""
        mock_cache.mark_processed(str(sample_event.event_id))

        result = ingestion_service.process_event_with_retry(sample_event)

        assert result is None

    def test_non_retryable_error_raises_immediately(
        self, ingestion_service, sample_event
    ):
        """Test that non-retryable errors are raised immediately."""
        # File doesn't exist - non-retryable

        with pytest.raises(NonRetryableError):
            ingestion_service.process_event_with_retry(sample_event)


class TestSendToDlq:
    """Tests for send_to_dlq method."""

    def test_sends_to_dlq(self, ingestion_service, mock_producer):
        """Test that events are sent to DLQ."""
        original_event = {
            "event_id": str(uuid4()),
            "tenant_id": "tenant-123",
            "file_path": "gs://bucket/_landing/file.mp4",
        }
        error = Exception("Test error")

        ingestion_service.send_to_dlq(
            original_event=original_event,
            error=error,
            source_topic="raw-ingestion-topic",
        )

        assert len(mock_producer.dlq_messages) == 1
        dlq_msg = mock_producer.dlq_messages[0]
        assert dlq_msg["original_event"] == original_event
        assert "Test error" in dlq_msg["error"]
        assert dlq_msg["source_topic"] == "raw-ingestion-topic"


class TestErrorHandling:
    """Tests for error handling scenarios."""

    def test_storage_error_during_move(self, mock_cache, mock_producer, sample_event):
        """Test handling of storage errors during file move."""

        # Create a storage that fails on move
        class FailingStorage(MockStoragePort):
            def move_file(self, source_path, destination_path):
                raise StorageOperationError(
                    operation="move_file",
                    path=source_path,
                    cause=Exception("Network error"),
                    is_retryable=True,
                )

            def check_exists(self, path):
                return True

        storage = FailingStorage()
        service = IngestionService(
            storage=storage,
            cache=mock_cache,
            producer=mock_producer,
            output_topic="output",
            dlq_topic="dlq",
        )

        with pytest.raises(RetryableError):
            service.process_event(sample_event)

    def test_cache_error_during_status_update(
        self, mock_storage, mock_producer, sample_event
    ):
        """Test that cache errors during status update don't fail processing."""

        # Create a cache that fails on status update
        class FailingCache(MockCachePort):
            def update_status(self, trace_id, status, **kwargs):
                raise CacheOperationError(
                    operation="update_status",
                    key=trace_id,
                    cause=Exception("Redis error"),
                )

        cache = FailingCache()
        mock_storage.add_file(sample_event.file_path)

        service = IngestionService(
            storage=mock_storage,
            cache=cache,
            producer=mock_producer,
            output_topic="output",
            dlq_topic="dlq",
        )

        # Should succeed despite cache error (status is non-critical)
        result = service.process_event(sample_event)
        assert result.status == ProcessingStatus.RAW_STORED

    def test_cache_error_during_dedupe_check(
        self, mock_storage, mock_producer, sample_event
    ):
        """Test that cache errors during dedupe check allow processing to continue."""

        # Create a cache that fails on is_duplicate
        class FailingCache(MockCachePort):
            def is_duplicate(self, event_id):
                raise CacheOperationError(
                    operation="is_duplicate",
                    key=event_id,
                    cause=Exception("Redis error"),
                )

        cache = FailingCache()
        mock_storage.add_file(sample_event.file_path)

        service = IngestionService(
            storage=mock_storage,
            cache=cache,
            producer=mock_producer,
            output_topic="output",
            dlq_topic="dlq",
        )

        # Should succeed - better to potentially reprocess than fail
        result = service.process_event(sample_event)
        assert result.status == ProcessingStatus.RAW_STORED
