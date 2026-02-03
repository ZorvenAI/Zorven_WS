"""
Domain Layer for RAG Index Service.

This module exports the core domain models, exceptions, and schemas
used throughout the service.
"""

from .models import (
    SyncAction,
    SyncEvent,
    SyncResult,
    SyncStatusRecord,
    RateLimitStatus,
)
from .exceptions import (
    # Base exceptions
    RAGIndexError,
    # Rate limiting
    RateLimitExceededError,
    # Vertex AI
    VertexAIError,
    DocumentUpsertError,
    DocumentDeleteError,
    DocumentNotFoundError,
    # GCS
    GCSError,
    GCSReadError,
    GCSNotFoundError,
    InvalidGCSURIError,
    # Kafka
    KafkaError,
    KafkaPublishError,
    KafkaConsumeError,
    InvalidEventError,
    # Redis
    RedisError,
    RedisConnectionError,
    StatusNotFoundError,
    # Validation
    ValidationError,
    ConfigurationError,
    # Retry
    RetryableError,
    NonRetryableError,
)
from .schemas import (
    CloudEventBase,
    RagSyncReadyEvent,
    RagSyncReadyEventData,
    RagSyncCompletedEvent,
    RagSyncCompletedEventData,
    RagSyncDLQEvent,
    RagSyncDLQEventData,
)

__all__ = [
    # Models
    "SyncAction",
    "SyncEvent",
    "SyncResult",
    "SyncStatusRecord",
    "RateLimitStatus",
    # Base exceptions
    "RAGIndexError",
    # Rate limiting
    "RateLimitExceededError",
    # Vertex AI
    "VertexAIError",
    "DocumentUpsertError",
    "DocumentDeleteError",
    "DocumentNotFoundError",
    # GCS
    "GCSError",
    "GCSReadError",
    "GCSNotFoundError",
    "InvalidGCSURIError",
    # Kafka
    "KafkaError",
    "KafkaPublishError",
    "KafkaConsumeError",
    "InvalidEventError",
    # Redis
    "RedisError",
    "RedisConnectionError",
    "StatusNotFoundError",
    # Validation
    "ValidationError",
    "ConfigurationError",
    # Retry
    "RetryableError",
    "NonRetryableError",
    # Schemas
    "CloudEventBase",
    "RagSyncReadyEvent",
    "RagSyncReadyEventData",
    "RagSyncCompletedEvent",
    "RagSyncCompletedEventData",
    "RagSyncDLQEvent",
    "RagSyncDLQEventData",
]
