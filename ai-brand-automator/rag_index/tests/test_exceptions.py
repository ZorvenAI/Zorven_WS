"""
Unit Tests for Domain Exceptions.

Tests for custom exception hierarchy in RAG Index Service.
"""


from rag_index.domain.exceptions import (
    # Base
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


# ============================================================================
# Base Exception Tests
# ============================================================================


class TestRAGIndexError:
    """Tests for base RAGIndexError."""

    def test_create_with_message(self):
        """Test creating exception with message."""
        error = RAGIndexError("Test error")
        assert str(error) == "Test error"
        assert error.message == "Test error"

    def test_create_with_details(self):
        """Test creating exception with details."""
        error = RAGIndexError("Test error", {"key": "value"})
        assert "Details: {'key': 'value'}" in str(error)
        assert error.details == {"key": "value"}

    def test_to_dict(self):
        """Test exception serialization to dict."""
        error = RAGIndexError("Test error", {"key": "value"})
        data = error.to_dict()
        assert data["error_type"] == "RAGIndexError"
        assert data["message"] == "Test error"
        assert data["details"] == {"key": "value"}


# ============================================================================
# Rate Limiting Exception Tests
# ============================================================================


class TestRateLimitExceededError:
    """Tests for RateLimitExceededError."""

    def test_create_with_defaults(self):
        """Test creating with default values."""
        error = RateLimitExceededError()
        assert error.retry_after_seconds == 60
        assert error.current_count == 0
        assert error.limit == 600

    def test_create_with_custom_values(self):
        """Test creating with custom values."""
        error = RateLimitExceededError(
            message="Custom rate limit message",
            retry_after_seconds=30,
            current_count=650,
            limit=600,
        )
        assert error.retry_after_seconds == 30
        assert error.current_count == 650
        assert error.limit == 600
        assert "Custom rate limit message" in str(error)

    def test_details_contain_rate_info(self):
        """Test that details contain rate limit info."""
        error = RateLimitExceededError(current_count=500, limit=600)
        assert error.details["current_count"] == 500
        assert error.details["limit"] == 600


# ============================================================================
# Vertex AI Exception Tests
# ============================================================================


class TestVertexAIError:
    """Tests for VertexAIError."""

    def test_create_with_operation_id(self):
        """Test creating with operation ID."""
        error = VertexAIError("API error", operation_id="op-123")
        assert error.operation_id == "op-123"
        assert error.details["operation_id"] == "op-123"

    def test_create_with_grpc_code(self):
        """Test creating with gRPC code."""
        error = VertexAIError("API error", grpc_code="UNAVAILABLE")
        assert error.grpc_code == "UNAVAILABLE"
        assert error.details["grpc_code"] == "UNAVAILABLE"


class TestDocumentUpsertError:
    """Tests for DocumentUpsertError."""

    def test_create_with_document_id(self):
        """Test creating with document ID."""
        error = DocumentUpsertError(document_id="doc-123")
        assert error.document_id == "doc-123"
        assert "doc-123" in str(error.details)

    def test_default_message(self):
        """Test default error message."""
        error = DocumentUpsertError()
        assert "upsert" in error.message.lower()


class TestDocumentDeleteError:
    """Tests for DocumentDeleteError."""

    def test_create_with_document_id(self):
        """Test creating with document ID."""
        error = DocumentDeleteError(document_id="doc-456")
        assert error.document_id == "doc-456"

    def test_default_message(self):
        """Test default error message."""
        error = DocumentDeleteError()
        assert "delete" in error.message.lower()


class TestDocumentNotFoundError:
    """Tests for DocumentNotFoundError."""

    def test_create_with_document_id(self):
        """Test creating with document ID."""
        error = DocumentNotFoundError(document_id="doc-789")
        assert error.document_id == "doc-789"


# ============================================================================
# GCS Exception Tests
# ============================================================================


class TestGCSError:
    """Tests for GCS-related errors."""

    def test_create_with_gcs_uri(self):
        """Test creating with GCS URI."""
        error = GCSError("GCS error", gcs_uri="gs://bucket/path")
        assert error.gcs_uri == "gs://bucket/path"
        assert error.details["gcs_uri"] == "gs://bucket/path"


class TestGCSReadError:
    """Tests for GCSReadError."""

    def test_default_message(self):
        """Test default error message."""
        error = GCSReadError()
        assert "read" in error.message.lower()


class TestGCSNotFoundError:
    """Tests for GCSNotFoundError."""

    def test_with_uri(self):
        """Test creating with GCS URI."""
        error = GCSNotFoundError(gcs_uri="gs://bucket/missing.json")
        assert error.gcs_uri == "gs://bucket/missing.json"


class TestInvalidGCSURIError:
    """Tests for InvalidGCSURIError."""

    def test_default_message(self):
        """Test default error message."""
        error = InvalidGCSURIError(gcs_uri="invalid://uri")
        assert "invalid" in error.message.lower()


# ============================================================================
# Kafka Exception Tests
# ============================================================================


class TestKafkaError:
    """Tests for Kafka-related errors."""

    def test_create_with_topic(self):
        """Test creating with topic."""
        error = KafkaError("Kafka error", topic="rag-sync-ready-topic")
        assert error.topic == "rag-sync-ready-topic"


class TestKafkaPublishError:
    """Tests for KafkaPublishError."""

    def test_with_event_id(self):
        """Test creating with event ID."""
        error = KafkaPublishError(event_id="event-123", topic="output-topic")
        assert error.event_id == "event-123"
        assert error.topic == "output-topic"


class TestKafkaConsumeError:
    """Tests for KafkaConsumeError."""

    def test_default_message(self):
        """Test default error message."""
        error = KafkaConsumeError()
        assert "consume" in error.message.lower()


class TestInvalidEventError:
    """Tests for InvalidEventError."""

    def test_with_validation_errors(self):
        """Test creating with validation errors."""
        error = InvalidEventError(
            validation_errors=["missing field: tenant_id", "invalid action"]
        )
        assert len(error.validation_errors) == 2


# ============================================================================
# Redis Exception Tests
# ============================================================================


class TestRedisConnectionError:
    """Tests for RedisConnectionError."""

    def test_with_host_and_port(self):
        """Test creating with host and port."""
        error = RedisConnectionError(host="localhost", port=6379)
        assert error.host == "localhost"
        assert error.port == 6379


class TestStatusNotFoundError:
    """Tests for StatusNotFoundError."""

    def test_with_event_id(self):
        """Test creating with event ID."""
        error = StatusNotFoundError(event_id="event-abc")
        assert error.event_id == "event-abc"


# ============================================================================
# Validation Exception Tests
# ============================================================================


class TestValidationError:
    """Tests for ValidationError."""

    def test_with_field_and_value(self):
        """Test creating with field and value."""
        error = ValidationError(field="tenant_id", value="")
        assert error.field == "tenant_id"
        assert error.value == ""


class TestConfigurationError:
    """Tests for ConfigurationError."""

    def test_with_missing_keys(self):
        """Test creating with missing keys."""
        error = ConfigurationError(missing_keys=["GOOGLE_API_KEY", "REDIS_URL"])
        assert len(error.missing_keys) == 2


# ============================================================================
# Retry Exception Tests
# ============================================================================


class TestRetryableError:
    """Tests for RetryableError."""

    def test_can_retry_true(self):
        """Test can_retry when retries available."""
        error = RetryableError("Retryable", retry_count=1, max_retries=3)
        assert error.can_retry is True

    def test_can_retry_false(self):
        """Test can_retry when retries exhausted."""
        error = RetryableError("Retryable", retry_count=3, max_retries=3)
        assert error.can_retry is False


class TestNonRetryableError:
    """Tests for NonRetryableError."""

    def test_is_rag_index_error(self):
        """Test that NonRetryableError is a RAGIndexError."""
        error = NonRetryableError("Non-retryable error")
        assert isinstance(error, RAGIndexError)


# ============================================================================
# Inheritance Tests
# ============================================================================


class TestExceptionHierarchy:
    """Tests for exception inheritance."""

    def test_all_exceptions_inherit_from_base(self):
        """Test all custom exceptions inherit from RAGIndexError."""
        exceptions = [
            RateLimitExceededError(),
            VertexAIError("test"),
            DocumentUpsertError(),
            GCSError("test"),
            KafkaError("test"),
            RedisError("test"),
            ValidationError(),
            RetryableError("test"),
            NonRetryableError("test"),
        ]
        for exc in exceptions:
            assert isinstance(exc, RAGIndexError)

    def test_vertex_ai_exceptions_hierarchy(self):
        """Test Vertex AI exception hierarchy."""
        assert issubclass(DocumentUpsertError, VertexAIError)
        assert issubclass(DocumentDeleteError, VertexAIError)
        assert issubclass(DocumentNotFoundError, VertexAIError)

    def test_gcs_exceptions_hierarchy(self):
        """Test GCS exception hierarchy."""
        assert issubclass(GCSReadError, GCSError)
        assert issubclass(GCSNotFoundError, GCSError)
        assert issubclass(InvalidGCSURIError, GCSError)

    def test_kafka_exceptions_hierarchy(self):
        """Test Kafka exception hierarchy."""
        assert issubclass(KafkaPublishError, KafkaError)
        assert issubclass(KafkaConsumeError, KafkaError)
        assert issubclass(InvalidEventError, KafkaError)

    def test_redis_exceptions_hierarchy(self):
        """Test Redis exception hierarchy."""
        assert issubclass(RedisConnectionError, RedisError)
        assert issubclass(StatusNotFoundError, RedisError)
