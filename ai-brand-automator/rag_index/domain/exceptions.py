"""
Domain Exceptions for RAG Index Service.

Custom exception hierarchy for handling various error scenarios
throughout the service.
"""

from typing import Any, Optional


class RAGIndexError(Exception):
    """Base exception for all RAG Index service errors.

    All custom exceptions in this service inherit from this base class,
    allowing for easy catching of all service-related errors.
    """

    def __init__(self, message: str, details: Optional[dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def __str__(self) -> str:
        if self.details:
            return f"{self.message} - Details: {self.details}"
        return self.message

    def to_dict(self) -> dict[str, Any]:
        """Convert exception to dictionary for serialization."""
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "details": self.details,
        }


# ============================================================================
# Rate Limiting Exceptions
# ============================================================================


class RateLimitExceededError(RAGIndexError):
    """Raised when Vertex AI rate limit (600 req/min) is exceeded.

    This error indicates that the service should wait before retrying
    the operation. The retry_after_seconds attribute provides guidance
    on when to retry.
    """

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        retry_after_seconds: int = 60,
        current_count: int = 0,
        limit: int = 600,
    ):
        details = {
            "retry_after_seconds": retry_after_seconds,
            "current_count": current_count,
            "limit": limit,
        }
        super().__init__(message, details)
        self.retry_after_seconds = retry_after_seconds
        self.current_count = current_count
        self.limit = limit


# ============================================================================
# Vertex AI Exceptions
# ============================================================================


class VertexAIError(RAGIndexError):
    """Base exception for Vertex AI Discovery Engine errors."""

    def __init__(
        self,
        message: str,
        operation_id: Optional[str] = None,
        grpc_code: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ):
        error_details = details or {}
        if operation_id:
            error_details["operation_id"] = operation_id
        if grpc_code:
            error_details["grpc_code"] = grpc_code
        super().__init__(message, error_details)
        self.operation_id = operation_id
        self.grpc_code = grpc_code


class DocumentUpsertError(VertexAIError):
    """Raised when document upsert to Vertex AI fails."""

    def __init__(
        self,
        message: str = "Failed to upsert document",
        document_id: Optional[str] = None,
        operation_id: Optional[str] = None,
        grpc_code: Optional[str] = None,
    ):
        details = {}
        if document_id:
            details["document_id"] = document_id
        super().__init__(message, operation_id, grpc_code, details)
        self.document_id = document_id


class DocumentDeleteError(VertexAIError):
    """Raised when document deletion from Vertex AI fails."""

    def __init__(
        self,
        message: str = "Failed to delete document",
        document_id: Optional[str] = None,
        operation_id: Optional[str] = None,
        grpc_code: Optional[str] = None,
    ):
        details = {}
        if document_id:
            details["document_id"] = document_id
        super().__init__(message, operation_id, grpc_code, details)
        self.document_id = document_id


class DocumentNotFoundError(VertexAIError):
    """Raised when a document is not found in Vertex AI."""

    def __init__(
        self,
        message: str = "Document not found",
        document_id: Optional[str] = None,
    ):
        details = {}
        if document_id:
            details["document_id"] = document_id
        super().__init__(message, details=details)
        self.document_id = document_id


# ============================================================================
# GCS Exceptions
# ============================================================================


class GCSError(RAGIndexError):
    """Base exception for GCS-related errors."""

    def __init__(
        self,
        message: str,
        gcs_uri: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ):
        error_details = details or {}
        if gcs_uri:
            error_details["gcs_uri"] = gcs_uri
        super().__init__(message, error_details)
        self.gcs_uri = gcs_uri


class GCSReadError(GCSError):
    """Raised when reading from GCS fails."""

    def __init__(
        self,
        message: str = "Failed to read from GCS",
        gcs_uri: Optional[str] = None,
    ):
        super().__init__(message, gcs_uri)


class GCSNotFoundError(GCSError):
    """Raised when a GCS object is not found."""

    def __init__(
        self,
        message: str = "GCS object not found",
        gcs_uri: Optional[str] = None,
    ):
        super().__init__(message, gcs_uri)


class DocumentFetchError(GCSError):
    """Raised when fetching a document from GCS fails."""

    def __init__(
        self,
        message: str = "Failed to fetch document from GCS",
        gcs_uri: Optional[str] = None,
    ):
        super().__init__(message, gcs_uri)


class InvalidGCSURIError(GCSError):
    """Raised when a GCS URI is malformed."""

    def __init__(
        self,
        message: str = "Invalid GCS URI format",
        gcs_uri: Optional[str] = None,
    ):
        super().__init__(message, gcs_uri)


# ============================================================================
# Kafka Exceptions
# ============================================================================


class KafkaError(RAGIndexError):
    """Base exception for Kafka-related errors."""

    def __init__(
        self,
        message: str,
        topic: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ):
        error_details = details or {}
        if topic:
            error_details["topic"] = topic
        super().__init__(message, error_details)
        self.topic = topic


class KafkaPublishError(KafkaError):
    """Raised when publishing to Kafka fails."""

    def __init__(
        self,
        message: str = "Failed to publish to Kafka",
        topic: Optional[str] = None,
        event_id: Optional[str] = None,
    ):
        details = {}
        if event_id:
            details["event_id"] = event_id
        super().__init__(message, topic, details)
        self.event_id = event_id


class KafkaConsumeError(KafkaError):
    """Raised when consuming from Kafka fails."""

    def __init__(
        self,
        message: str = "Failed to consume from Kafka",
        topic: Optional[str] = None,
    ):
        super().__init__(message, topic)


class InvalidEventError(KafkaError):
    """Raised when a Kafka event payload is invalid."""

    def __init__(
        self,
        message: str = "Invalid event payload",
        topic: Optional[str] = None,
        validation_errors: Optional[list[str]] = None,
    ):
        details = {}
        if validation_errors:
            details["validation_errors"] = validation_errors
        super().__init__(message, topic, details)
        self.validation_errors = validation_errors or []


# ============================================================================
# Redis Exceptions
# ============================================================================


class RedisError(RAGIndexError):
    """Base exception for Redis-related errors."""


class RedisConnectionError(RedisError):
    """Raised when Redis connection fails."""

    def __init__(
        self,
        message: str = "Failed to connect to Redis",
        host: Optional[str] = None,
        port: Optional[int] = None,
    ):
        details = {}
        if host:
            details["host"] = host
        if port:
            details["port"] = port
        super().__init__(message, details)
        self.host = host
        self.port = port


class StatusNotFoundError(RedisError):
    """Raised when a sync status record is not found in Redis."""

    def __init__(
        self,
        message: str = "Status record not found",
        event_id: Optional[str] = None,
    ):
        details = {}
        if event_id:
            details["event_id"] = event_id
        super().__init__(message, details)
        self.event_id = event_id


# ============================================================================
# Validation Exceptions
# ============================================================================


class ValidationError(RAGIndexError):
    """Raised when input validation fails."""

    def __init__(
        self,
        message: str = "Validation failed",
        field: Optional[str] = None,
        value: Optional[Any] = None,
    ):
        details = {}
        if field:
            details["field"] = field
        if value is not None:
            details["value"] = str(value)
        super().__init__(message, details)
        self.field = field
        self.value = value


class ConfigurationError(RAGIndexError):
    """Raised when service configuration is invalid."""

    def __init__(
        self,
        message: str = "Configuration error",
        missing_keys: Optional[list[str]] = None,
    ):
        details = {}
        if missing_keys:
            details["missing_keys"] = missing_keys
        super().__init__(message, details)
        self.missing_keys = missing_keys or []


# ============================================================================
# Retry Exceptions
# ============================================================================


class RetryableError(RAGIndexError):
    """Base exception for errors that can be retried.

    Used to indicate that an operation failed but may succeed on retry.
    """

    def __init__(
        self,
        message: str,
        retry_count: int = 0,
        max_retries: int = 3,
        details: Optional[dict[str, Any]] = None,
    ):
        error_details = details or {}
        error_details["retry_count"] = retry_count
        error_details["max_retries"] = max_retries
        super().__init__(message, error_details)
        self.retry_count = retry_count
        self.max_retries = max_retries

    @property
    def can_retry(self) -> bool:
        """Check if more retries are available."""
        return self.retry_count < self.max_retries


class NonRetryableError(RAGIndexError):
    """Base exception for errors that should not be retried.

    These errors indicate permanent failures that won't be resolved
    by retrying (e.g., invalid input, authorization failures).
    """


# ============================================================================
# Sync Processing Exceptions
# ============================================================================


class SyncError(RAGIndexError):
    """Base exception for sync processing errors.

    Raised when a sync operation fails after all processing steps.
    """

    def __init__(
        self,
        message: str = "Sync processing failed",
        event_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ):
        error_details = details or {}
        if event_id:
            error_details["event_id"] = event_id
        if tenant_id:
            error_details["tenant_id"] = tenant_id
        super().__init__(message, error_details)
        self.event_id = event_id
        self.tenant_id = tenant_id


class SyncValidationError(SyncError):
    """Raised when sync event validation fails."""

    def __init__(
        self,
        message: str = "Sync event validation failed",
        field: Optional[str] = None,
        event_id: Optional[str] = None,
    ):
        details = {}
        if field:
            details["field"] = field
        super().__init__(message, event_id=event_id, details=details)
        self.field = field
