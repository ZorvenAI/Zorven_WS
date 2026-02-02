"""
Unit tests for media_curation exception hierarchy.

Tests the exception classes and their inheritance structure.
"""

import pytest

from media_curation.domain.exceptions import (
    CurationError,
    RetryableError,
    NonRetryableError,
    ProcessorNotFoundError,
    InvalidEventError,
    ConfigurationError,
    StorageError,
    AIModelError,
    DLPError,
    RateLimitError,
    TimeoutError,
    QuotaExhaustedError,
)


class TestCurationError:
    """Tests for base CurationError."""

    def test_basic_error(self):
        """Test creating a basic curation error."""
        error = CurationError("Something went wrong")
        assert str(error) == "Something went wrong"
        assert isinstance(error, Exception)

    def test_error_with_cause(self):
        """Test error with a cause exception."""
        cause = ValueError("Invalid value")
        error = CurationError("Curation failed")
        error.__cause__ = cause
        assert error.__cause__ is cause

    def test_error_inheritance(self):
        """Test CurationError is base for all domain exceptions."""
        error = CurationError("Base error")
        assert isinstance(error, Exception)


class TestRetryableError:
    """Tests for RetryableError."""

    def test_retryable_error(self):
        """Test creating a retryable error."""
        error = RetryableError("Temporary failure, please retry")
        assert str(error) == "Temporary failure, please retry"
        assert isinstance(error, CurationError)

    def test_retryable_error_is_curation_error(self):
        """Test RetryableError inherits from CurationError."""
        error = RetryableError("Retry me")
        assert isinstance(error, CurationError)

    def test_catching_as_curation_error(self):
        """Test catching RetryableError as CurationError."""
        with pytest.raises(CurationError):
            raise RetryableError("Should be caught as CurationError")


class TestNonRetryableError:
    """Tests for NonRetryableError."""

    def test_non_retryable_error(self):
        """Test creating a non-retryable error."""
        error = NonRetryableError("Permanent failure, do not retry")
        assert str(error) == "Permanent failure, do not retry"
        assert isinstance(error, CurationError)

    def test_non_retryable_error_is_curation_error(self):
        """Test NonRetryableError inherits from CurationError."""
        error = NonRetryableError("No retry")
        assert isinstance(error, CurationError)


class TestProcessorNotFoundError:
    """Tests for ProcessorNotFoundError."""

    def test_processor_not_found(self):
        """Test creating a processor not found error."""
        error = ProcessorNotFoundError("No processor for MIME type: video/unknown")
        assert "No processor" in str(error)
        assert isinstance(error, NonRetryableError)

    def test_is_non_retryable(self):
        """Test ProcessorNotFoundError is non-retryable."""
        error = ProcessorNotFoundError("Unknown MIME type")
        assert isinstance(error, NonRetryableError)
        assert isinstance(error, CurationError)

    def test_with_mime_type(self):
        """Test error message includes MIME type."""
        mime_type = "application/x-custom"
        error = ProcessorNotFoundError(f"No processor for MIME type: {mime_type}")
        assert mime_type in str(error)


class TestInvalidEventError:
    """Tests for InvalidEventError."""

    def test_invalid_event(self):
        """Test creating an invalid event error."""
        error = InvalidEventError("Event missing required field: tenant_id")
        assert "missing required" in str(error).lower()
        assert isinstance(error, NonRetryableError)

    def test_is_non_retryable(self):
        """Test InvalidEventError is non-retryable."""
        error = InvalidEventError("Invalid event format")
        assert isinstance(error, NonRetryableError)


class TestConfigurationError:
    """Tests for ConfigurationError."""

    def test_configuration_error(self):
        """Test creating a configuration error."""
        error = ConfigurationError("Missing GOOGLE_API_KEY")
        assert "GOOGLE_API_KEY" in str(error)
        assert isinstance(error, NonRetryableError)

    def test_is_non_retryable(self):
        """Test ConfigurationError is non-retryable."""
        error = ConfigurationError("Invalid config")
        assert isinstance(error, NonRetryableError)

    def test_missing_tenant_config(self):
        """Test error for missing tenant configuration."""
        tenant_id = "tenant-123"
        error = ConfigurationError(f"No configuration found for tenant: {tenant_id}")
        assert tenant_id in str(error)


class TestStorageError:
    """Tests for StorageError."""

    def test_storage_error(self):
        """Test creating a storage error."""
        error = StorageError("Failed to read from GCS: gs://bucket/file.pdf")
        assert "GCS" in str(error)
        assert isinstance(error, RetryableError)

    def test_is_retryable(self):
        """Test StorageError is retryable."""
        error = StorageError("Temporary GCS failure")
        assert isinstance(error, RetryableError)
        assert isinstance(error, CurationError)

    def test_gcs_read_failure(self):
        """Test GCS read failure error."""
        uri = "gs://test-bucket/file.pdf"
        error = StorageError(f"Failed to read file: {uri}")
        assert uri in str(error)

    def test_gcs_write_failure(self):
        """Test GCS write failure error."""
        uri = "gs://curated-bucket/output.json"
        error = StorageError(f"Failed to write file: {uri}")
        assert uri in str(error)


class TestAIModelError:
    """Tests for AIModelError."""

    def test_ai_model_error(self):
        """Test creating an AI model error."""
        error = AIModelError("Gemini API returned error: 500")
        assert "Gemini" in str(error)
        assert isinstance(error, RetryableError)

    def test_is_retryable(self):
        """Test AIModelError is retryable."""
        error = AIModelError("Model temporarily unavailable")
        assert isinstance(error, RetryableError)

    def test_model_response_error(self):
        """Test error for invalid model response."""
        error = AIModelError("Model returned empty response")
        assert "empty response" in str(error).lower()


class TestDLPError:
    """Tests for DLPError."""

    def test_dlp_error(self):
        """Test creating a DLP error."""
        error = DLPError("DLP API failed to redact PII")
        assert "DLP" in str(error)
        assert isinstance(error, RetryableError)

    def test_is_retryable(self):
        """Test DLPError is retryable."""
        error = DLPError("DLP service unavailable")
        assert isinstance(error, RetryableError)

    def test_pii_redaction_failure(self):
        """Test PII redaction failure error."""
        error = DLPError("Failed to redact EMAIL_ADDRESS from text")
        assert "EMAIL_ADDRESS" in str(error)


class TestRateLimitError:
    """Tests for RateLimitError."""

    def test_rate_limit_error(self):
        """Test creating a rate limit error."""
        error = RateLimitError("API rate limit exceeded, retry after 60s")
        assert "rate limit" in str(error).lower()
        assert isinstance(error, RetryableError)

    def test_is_retryable(self):
        """Test RateLimitError is retryable."""
        error = RateLimitError("Rate limited")
        assert isinstance(error, RetryableError)

    def test_with_retry_after(self):
        """Test error with retry-after information."""
        retry_after = 30
        error = RateLimitError(f"Rate limited, retry after {retry_after} seconds")
        assert str(retry_after) in str(error)


class TestTimeoutError:
    """Tests for TimeoutError."""

    def test_timeout_error(self):
        """Test creating a timeout error."""
        error = TimeoutError("Request timed out after 300 seconds")
        assert "timed out" in str(error).lower()
        assert isinstance(error, RetryableError)

    def test_is_retryable(self):
        """Test TimeoutError is retryable."""
        error = TimeoutError("Operation timed out")
        assert isinstance(error, RetryableError)

    def test_with_duration(self):
        """Test error with timeout duration."""
        duration = 60
        error = TimeoutError(f"Processing timed out after {duration}s")
        assert str(duration) in str(error)


class TestQuotaExhaustedError:
    """Tests for QuotaExhaustedError."""

    def test_quota_exhausted_error(self):
        """Test creating a quota exhausted error."""
        error = QuotaExhaustedError("Daily API quota exceeded")
        assert "quota" in str(error).lower()
        assert isinstance(error, NonRetryableError)

    def test_is_non_retryable(self):
        """Test QuotaExhaustedError is non-retryable."""
        error = QuotaExhaustedError("Quota exceeded")
        assert isinstance(error, NonRetryableError)
        # Quota errors shouldn't be retried immediately
        assert not isinstance(error, RetryableError)


class TestExceptionHierarchy:
    """Tests for the exception hierarchy structure."""

    def test_all_inherit_from_curation_error(self):
        """Test all domain exceptions inherit from CurationError."""
        exceptions = [
            RetryableError("retryable"),
            NonRetryableError("non-retryable"),
            ProcessorNotFoundError("no processor"),
            InvalidEventError("invalid"),
            ConfigurationError("config error"),
            StorageError("storage error"),
            AIModelError("ai error"),
            DLPError("dlp error"),
            RateLimitError("rate limit"),
            TimeoutError("timeout"),
            QuotaExhaustedError("quota"),
        ]
        for exc in exceptions:
            assert isinstance(
                exc, CurationError
            ), f"{type(exc).__name__} should inherit from CurationError"

    def test_retryable_exceptions(self):
        """Test which exceptions are retryable."""
        retryable = [
            StorageError("storage"),
            AIModelError("ai"),
            DLPError("dlp"),
            RateLimitError("rate"),
            TimeoutError("timeout"),
        ]
        for exc in retryable:
            assert isinstance(
                exc, RetryableError
            ), f"{type(exc).__name__} should be retryable"

    def test_non_retryable_exceptions(self):
        """Test which exceptions are non-retryable."""
        non_retryable = [
            ProcessorNotFoundError("no processor"),
            InvalidEventError("invalid"),
            ConfigurationError("config"),
            QuotaExhaustedError("quota"),
        ]
        for exc in non_retryable:
            assert isinstance(
                exc, NonRetryableError
            ), f"{type(exc).__name__} should be non-retryable"

    def test_exception_handling_pattern(self):
        """Test typical exception handling pattern."""

        def process_with_retry(should_fail: bool, error_type: str):
            if should_fail:
                if error_type == "retryable":
                    raise StorageError("Temporary failure")
                elif error_type == "non_retryable":
                    raise ProcessorNotFoundError("No processor")
                else:
                    raise CurationError("Generic error")
            return "success"

        # Test retryable error handling
        with pytest.raises(RetryableError):
            process_with_retry(True, "retryable")

        # Test non-retryable error handling
        with pytest.raises(NonRetryableError):
            process_with_retry(True, "non_retryable")

        # Test generic error handling
        with pytest.raises(CurationError):
            process_with_retry(True, "generic")

    def test_catching_by_base_class(self):
        """Test catching exceptions by base class."""
        errors_caught = []

        try:
            raise StorageError("GCS failure")
        except RetryableError as e:
            errors_caught.append(("retryable", str(e)))

        try:
            raise ProcessorNotFoundError("No processor")
        except NonRetryableError as e:
            errors_caught.append(("non_retryable", str(e)))

        try:
            raise AIModelError("Model error")
        except CurationError as e:
            errors_caught.append(("curation", str(e)))

        assert len(errors_caught) == 3
        assert errors_caught[0][0] == "retryable"
        assert errors_caught[1][0] == "non_retryable"
        assert errors_caught[2][0] == "curation"
