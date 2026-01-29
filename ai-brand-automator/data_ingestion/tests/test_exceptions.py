"""
Unit tests for domain exceptions.

Tests exception creation, messages, and attributes.
"""

from uuid import uuid4

from data_ingestion.domain.exceptions import (
    DataIngestionError,
    DuplicateEventError,
    FileNotFoundInLandingError,
    StorageOperationError,
    CacheOperationError,
    EventPublishError,
    EventConsumptionError,
    InvalidEventError,
    PathGenerationError,
    RetryableError,
    NonRetryableError,
)


class TestDataIngestionError:
    """Tests for base DataIngestionError."""

    def test_basic_error(self):
        """Test creating a basic error."""
        error = DataIngestionError("Test error")
        assert str(error) == "Test error"
        assert error.message == "Test error"
        assert error.trace_id is None

    def test_error_with_trace_id(self):
        """Test error with trace_id."""
        trace_id = uuid4()
        error = DataIngestionError("Test error", trace_id=trace_id)
        assert f"trace_id={trace_id}" in str(error)
        assert error.trace_id == trace_id


class TestDuplicateEventError:
    """Tests for DuplicateEventError."""

    def test_duplicate_error(self):
        """Test creating a duplicate event error."""
        event_id = uuid4()
        error = DuplicateEventError(event_id=event_id)

        assert str(event_id) in str(error)
        assert "duplicate" in str(error).lower()
        assert error.event_id == event_id

    def test_duplicate_error_with_trace_id(self):
        """Test duplicate error with trace_id."""
        event_id = uuid4()
        trace_id = uuid4()
        error = DuplicateEventError(event_id=event_id, trace_id=trace_id)

        assert error.trace_id == trace_id


class TestFileNotFoundInLandingError:
    """Tests for FileNotFoundInLandingError."""

    def test_file_not_found_error(self):
        """Test creating a file not found error."""
        error = FileNotFoundInLandingError(file_path="gs://bucket/file.mp4")

        assert "gs://bucket/file.mp4" in str(error)
        assert "not found" in str(error).lower()
        assert error.file_path == "gs://bucket/file.mp4"

    def test_file_not_found_with_bucket(self):
        """Test file not found error with bucket info."""
        error = FileNotFoundInLandingError(
            file_path="file.mp4",
            bucket="my-bucket",
        )

        assert "my-bucket" in str(error)


class TestStorageOperationError:
    """Tests for StorageOperationError."""

    def test_storage_error(self):
        """Test creating a storage error."""
        error = StorageOperationError(
            operation="move_file",
            path="gs://bucket/file.mp4",
        )

        assert "move_file" in str(error)
        assert "gs://bucket/file.mp4" in str(error)
        assert error.is_retryable is True

    def test_storage_error_with_cause(self):
        """Test storage error with cause."""
        cause = Exception("Network timeout")
        error = StorageOperationError(
            operation="copy_file",
            path="gs://bucket/file.mp4",
            cause=cause,
        )

        assert "Network timeout" in str(error)
        assert error.cause == cause

    def test_storage_error_non_retryable(self):
        """Test non-retryable storage error."""
        error = StorageOperationError(
            operation="delete_file",
            path="gs://bucket/file.mp4",
            is_retryable=False,
        )

        assert error.is_retryable is False


class TestCacheOperationError:
    """Tests for CacheOperationError."""

    def test_cache_error(self):
        """Test creating a cache error."""
        error = CacheOperationError(
            operation="set",
            key="my-key",
        )

        assert "set" in str(error)
        assert "my-key" in str(error)

    def test_cache_error_with_cause(self):
        """Test cache error with cause."""
        cause = Exception("Connection refused")
        error = CacheOperationError(
            operation="get",
            key="my-key",
            cause=cause,
        )

        assert "Connection refused" in str(error)


class TestEventPublishError:
    """Tests for EventPublishError."""

    def test_publish_error(self):
        """Test creating a publish error."""
        error = EventPublishError(topic="my-topic")

        assert "my-topic" in str(error)
        assert error.topic == "my-topic"

    def test_publish_error_with_event_id(self):
        """Test publish error with event_id."""
        event_id = uuid4()
        error = EventPublishError(topic="my-topic", event_id=event_id)

        assert str(event_id) in str(error)


class TestEventConsumptionError:
    """Tests for EventConsumptionError."""

    def test_consumption_error(self):
        """Test creating a consumption error."""
        error = EventConsumptionError(topic="my-topic")

        assert "my-topic" in str(error)

    def test_consumption_error_without_topic(self):
        """Test consumption error without topic."""
        error = EventConsumptionError()

        assert "consume" in str(error).lower()


class TestInvalidEventError:
    """Tests for InvalidEventError."""

    def test_invalid_event_error(self):
        """Test creating an invalid event error."""
        error = InvalidEventError(reason="Missing required field")

        assert "Missing required field" in str(error)
        assert error.reason == "Missing required field"

    def test_invalid_event_with_raw_event(self):
        """Test invalid event error with raw event data."""
        error = InvalidEventError(
            reason="Invalid JSON",
            raw_event='{"incomplete": ',
        )

        assert error.raw_event == '{"incomplete": '


class TestPathGenerationError:
    """Tests for PathGenerationError."""

    def test_path_generation_error(self):
        """Test creating a path generation error."""
        error = PathGenerationError(reason="Invalid bucket name")

        assert "Invalid bucket name" in str(error)

    def test_path_generation_with_context(self):
        """Test path generation error with context."""
        error = PathGenerationError(
            reason="Invalid path",
            source_path="gs://bucket/file.mp4",
            tenant_id="tenant-123",
        )

        assert "gs://bucket/file.mp4" in str(error)
        assert "tenant-123" in str(error)


class TestRetryableError:
    """Tests for RetryableError."""

    def test_retryable_error(self):
        """Test creating a retryable error."""
        cause = Exception("Temporary failure")
        error = RetryableError(cause=cause, retry_count=0, max_retries=3)

        assert error.cause == cause
        assert error.retry_count == 0
        assert error.max_retries == 3
        assert error.should_retry is True

    def test_retryable_error_at_max(self):
        """Test retryable error at max retries."""
        cause = Exception("Temporary failure")
        error = RetryableError(cause=cause, retry_count=3, max_retries=3)

        assert error.should_retry is False

    def test_retryable_error_message(self):
        """Test retryable error message format."""
        cause = Exception("Temporary failure")
        error = RetryableError(cause=cause, retry_count=1, max_retries=3)

        assert "attempt 2/3" in str(error)


class TestNonRetryableError:
    """Tests for NonRetryableError."""

    def test_non_retryable_error(self):
        """Test creating a non-retryable error."""
        cause = Exception("Permanent failure")
        error = NonRetryableError(cause=cause)

        assert error.cause == cause
        assert "Permanent failure" in str(error)

    def test_non_retryable_error_with_reason(self):
        """Test non-retryable error with custom reason."""
        cause = Exception("Auth failed")
        error = NonRetryableError(
            cause=cause,
            reason="Authentication error",
        )

        assert "Authentication error" in str(error)
        assert error.reason == "Authentication error"
