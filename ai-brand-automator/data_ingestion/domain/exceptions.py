"""
Custom Exceptions for Data Ingestion Pipeline.

Domain-specific exceptions that are independent of external libraries.
These exceptions carry semantic meaning about what went wrong in the pipeline.
"""

from typing import Optional
from uuid import UUID


class DataIngestionError(Exception):
    """Base exception for all data ingestion errors."""

    def __init__(self, message: str, trace_id: Optional[UUID] = None):
        self.message = message
        self.trace_id = trace_id
        super().__init__(self.message)

    def __str__(self) -> str:
        if self.trace_id:
            return f"[trace_id={self.trace_id}] {self.message}"
        return self.message


class DuplicateEventError(DataIngestionError):
    """
    Raised when an event has already been processed.

    This is not necessarily an error - it's expected during at-least-once delivery.
    The event should be skipped without being sent to DLQ.
    """

    def __init__(self, event_id: UUID, trace_id: Optional[UUID] = None):
        self.event_id = event_id
        message = f"Event {event_id} has already been processed (duplicate)"
        super().__init__(message, trace_id)


class FileNotFoundInLandingError(DataIngestionError):
    """
    Raised when the referenced file does not exist in the landing zone.

    This is a permanent error - the event should be sent to DLQ.
    """

    def __init__(
        self,
        file_path: str,
        trace_id: Optional[UUID] = None,
        bucket: Optional[str] = None,
    ):
        self.file_path = file_path
        self.bucket = bucket
        message = f"File not found in landing zone: {file_path}"
        if bucket:
            message += f" (bucket: {bucket})"
        super().__init__(message, trace_id)


class StorageOperationError(DataIngestionError):
    """
    Raised when a storage operation (GCS) fails.

    May be transient (network issues) or permanent (permissions).
    """

    def __init__(
        self,
        operation: str,
        path: str,
        trace_id: Optional[UUID] = None,
        cause: Optional[Exception] = None,
        is_retryable: bool = True,
    ):
        self.operation = operation
        self.path = path
        self.cause = cause
        self.is_retryable = is_retryable
        message = f"Storage operation '{operation}' failed for path: {path}"
        if cause:
            message += f" - {cause}"
        super().__init__(message, trace_id)


class CacheOperationError(DataIngestionError):
    """
    Raised when a cache operation (Redis) fails.

    Usually transient - should be retried.
    """

    def __init__(
        self,
        operation: str,
        key: str,
        trace_id: Optional[UUID] = None,
        cause: Optional[Exception] = None,
    ):
        self.operation = operation
        self.key = key
        self.cause = cause
        message = f"Cache operation '{operation}' failed for key: {key}"
        if cause:
            message += f" - {cause}"
        super().__init__(message, trace_id)


class EventPublishError(DataIngestionError):
    """
    Raised when publishing to Kafka fails.

    Usually transient - should be retried.
    """

    def __init__(
        self,
        topic: str,
        event_id: Optional[UUID] = None,
        trace_id: Optional[UUID] = None,
        cause: Optional[Exception] = None,
    ):
        self.topic = topic
        self.event_id = event_id
        self.cause = cause
        message = f"Failed to publish event to topic: {topic}"
        if event_id:
            message += f" (event_id: {event_id})"
        if cause:
            message += f" - {cause}"
        super().__init__(message, trace_id)


class EventConsumptionError(DataIngestionError):
    """
    Raised when consuming from Kafka fails.

    Usually transient - consumer should retry.
    """

    def __init__(
        self,
        topic: Optional[str] = None,
        trace_id: Optional[UUID] = None,
        cause: Optional[Exception] = None,
    ):
        self.topic = topic
        self.cause = cause
        message = "Failed to consume event"
        if topic:
            message += f" from topic: {topic}"
        if cause:
            message += f" - {cause}"
        super().__init__(message, trace_id)


class InvalidEventError(DataIngestionError):
    """
    Raised when an incoming event fails validation.

    This is a permanent error - the event should be sent to DLQ.
    """

    def __init__(
        self,
        reason: str,
        trace_id: Optional[UUID] = None,
        event_data: Optional[dict] = None,
        raw_event: Optional[str] = None,
    ):
        self.reason = reason
        self.event_data = event_data
        self.raw_event = raw_event
        message = f"Invalid event: {reason}"
        super().__init__(message, trace_id)


class PathGenerationError(DataIngestionError):
    """
    Raised when generating the destination path fails.

    This is usually a programming error or invalid input.
    """

    def __init__(
        self,
        reason: str,
        source_path: Optional[str] = None,
        tenant_id: Optional[str] = None,
        trace_id: Optional[UUID] = None,
    ):
        self.reason = reason
        self.source_path = source_path
        self.tenant_id = tenant_id
        message = f"Failed to generate destination path: {reason}"
        if source_path:
            message += f" (source: {source_path})"
        if tenant_id:
            message += f" (tenant: {tenant_id})"
        super().__init__(message, trace_id)


class RetryableError(DataIngestionError):
    """
    Wrapper exception indicating an error that should be retried.

    Used to signal to the consumer that the message should not be committed.
    """

    def __init__(
        self,
        cause: Exception,
        retry_count: int = 0,
        max_retries: int = 3,
        trace_id: Optional[UUID] = None,
    ):
        self.cause = cause
        self.retry_count = retry_count
        self.max_retries = max_retries
        self.should_retry = retry_count < max_retries
        message = f"Retryable error (attempt {retry_count + 1}/{max_retries}): {cause}"
        super().__init__(message, trace_id)


class NonRetryableError(DataIngestionError):
    """
    Wrapper exception indicating an error that should NOT be retried.

    The message should be sent to DLQ immediately.
    """

    def __init__(
        self,
        cause: Exception,
        reason: str = "Non-retryable error",
        trace_id: Optional[UUID] = None,
    ):
        self.cause = cause
        self.reason = reason
        message = f"{reason}: {cause}"
        super().__init__(message, trace_id)
