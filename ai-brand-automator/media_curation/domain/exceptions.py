"""
Media Curation Custom Exceptions.

Hierarchical exception structure for the curation pipeline:
- CurationError (base)
  - RetryableError (temporary failures, should retry)
  - NonRetryableError (permanent failures, send to DLQ)
"""

from typing import Optional, Any
from uuid import UUID


class CurationError(Exception):
    """Base exception for all media curation errors."""

    def __init__(
        self,
        message: str,
        trace_id: Optional[UUID] = None,
        event_id: Optional[UUID] = None,
        **context: Any,
    ):
        self.message = message
        self.trace_id = trace_id
        self.event_id = event_id
        self.context = context
        super().__init__(message)

    def _format_message(self) -> str:
        """Format exception message with context."""
        parts = []
        if self.trace_id:
            parts.append(f"[trace_id={self.trace_id}]")
        if self.event_id:
            parts.append(f"[event_id={self.event_id}]")
        parts.append(self.message)
        return " ".join(parts)


class RetryableError(CurationError):
    """
    Temporary error that should be retried.

    Examples:
    - API rate limits
    - Temporary network issues
    - Service unavailability
    """

    def __init__(
        self,
        message: str,
        retry_after_seconds: float = 1.0,
        attempt: int = 1,
        max_attempts: int = 3,
        **kwargs: Any,
    ):
        self.retry_after_seconds = retry_after_seconds
        self.attempt = attempt
        self.max_attempts = max_attempts
        super().__init__(message, **kwargs)


class NonRetryableError(CurationError):
    """
    Permanent error that should not be retried.

    Events with this error are sent to DLQ.

    Examples:
    - Invalid file format
    - Unsupported content type
    - Corrupt file data
    """

    pass


# Specific error types


class ProcessorNotFoundError(NonRetryableError):
    """No processor available for the given content type."""

    def __init__(self, message: str, content_type: str = None, **kwargs: Any):
        self.content_type = content_type
        super().__init__(message, content_type=content_type, **kwargs)


class InvalidEventError(NonRetryableError):
    """Event data is invalid or malformed."""

    def __init__(
        self,
        reason: str,
        raw_event: Optional[str] = None,
        **kwargs: Any,
    ):
        self.reason = reason
        self.raw_event = raw_event
        super().__init__(f"Invalid event: {reason}", **kwargs)


class StorageError(RetryableError):
    """Error for storage operations (typically retryable)."""

    def __init__(
        self,
        message: str,
        operation: str = None,
        path: str = None,
        cause: Optional[Exception] = None,
        **kwargs: Any,
    ):
        self.operation = operation
        self.path = path
        self.cause = cause
        super().__init__(message, **kwargs)


class StorageNotFoundError(NonRetryableError):
    """File not found in storage."""

    def __init__(self, path: str, **kwargs: Any):
        super().__init__(f"File not found: {path}", path=path, **kwargs)


class StoragePermissionError(NonRetryableError):
    """Permission denied for storage operation."""

    def __init__(self, path: str, **kwargs: Any):
        super().__init__(f"Permission denied: {path}", path=path, **kwargs)


class AIModelError(RetryableError):
    """Error for AI model operations (typically retryable)."""

    def __init__(
        self,
        message: str,
        model: str = None,
        operation: str = None,
        cause: Optional[Exception] = None,
        **kwargs: Any,
    ):
        self.model = model
        self.operation = operation
        self.cause = cause
        super().__init__(message, **kwargs)


class AIModelRateLimitError(RetryableError):
    """AI model rate limit exceeded."""

    def __init__(
        self,
        model: str,
        retry_after_seconds: float = 60.0,
        **kwargs: Any,
    ):
        super().__init__(
            f"Rate limit exceeded for model: {model}",
            retry_after_seconds=retry_after_seconds,
            model=model,
            **kwargs,
        )


class AIModelQuotaExceededError(NonRetryableError):
    """AI model quota exhausted."""

    def __init__(self, model: str, **kwargs: Any):
        super().__init__(
            f"Quota exceeded for model: {model}",
            model=model,
            **kwargs,
        )


class AIModelUnavailableError(RetryableError):
    """AI model temporarily unavailable."""

    def __init__(self, model: str, **kwargs: Any):
        super().__init__(
            f"Model temporarily unavailable: {model}",
            model=model,
            **kwargs,
        )


class DLPError(RetryableError):
    """Error during PII detection/redaction (typically retryable)."""

    def __init__(
        self,
        message: str,
        operation: str = None,
        cause: Optional[Exception] = None,
        **kwargs: Any,
    ):
        self.operation = operation
        self.cause = cause
        super().__init__(message, **kwargs)


class CacheError(RetryableError):
    """Error during cache operations (typically retryable)."""

    def __init__(
        self,
        message: str,
        operation: str = None,
        key: str = None,
        cause: Optional[Exception] = None,
        **kwargs: Any,
    ):
        self.operation = operation
        self.key = key
        self.cause = cause
        super().__init__(message, **kwargs)


class EventError(RetryableError):
    """Error during event operations (typically retryable)."""

    def __init__(
        self,
        message: str,
        topic: str = None,
        cause: Optional[Exception] = None,
        **kwargs: Any,
    ):
        self.topic = topic
        self.cause = cause
        super().__init__(message, **kwargs)


class ConfigurationError(NonRetryableError):
    """Service misconfiguration."""

    def __init__(
        self, message: str, setting: str = None, reason: str = None, **kwargs: Any
    ):
        self.setting = setting
        self.reason = reason
        super().__init__(message, setting=setting, **kwargs)


class EventPublishError(RetryableError):
    """Failed to publish event to Kafka."""

    def __init__(
        self,
        topic: str,
        cause: Optional[Exception] = None,
        **kwargs: Any,
    ):
        self.topic = topic
        self.cause = cause
        message = f"Failed to publish to topic: {topic}"
        if cause:
            message += f" - {cause}"
        super().__init__(message, topic=topic, **kwargs)


class DuplicateEventError(NonRetryableError):
    """Event has already been processed (deduplication)."""

    def __init__(self, event_id: UUID, **kwargs: Any):
        super().__init__(
            f"Duplicate event detected: {event_id}",
            event_id=event_id,
            **kwargs,
        )


# =============================================================================
# Simplified exception aliases for easier usage
# =============================================================================


class RateLimitError(RetryableError):
    """API rate limit exceeded (retryable)."""

    def __init__(self, message: str, retry_after_seconds: float = 60.0, **kwargs: Any):
        super().__init__(message, retry_after_seconds=retry_after_seconds, **kwargs)


class TimeoutError(RetryableError):
    """Operation timed out (retryable)."""

    def __init__(self, message: str, **kwargs: Any):
        super().__init__(message, **kwargs)


class QuotaExhaustedError(NonRetryableError):
    """Quota exhausted (non-retryable)."""

    def __init__(self, message: str, **kwargs: Any):
        super().__init__(message, **kwargs)
