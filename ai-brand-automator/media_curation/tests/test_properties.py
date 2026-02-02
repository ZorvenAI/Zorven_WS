"""
Property-Based Tests for Media Curation Service.

Uses Hypothesis to generate test cases for robust validation.
"""

import pytest
from hypothesis import given, strategies as st, settings
from uuid import uuid4, UUID

from media_curation.domain.models import (
    CurationEvent,
    CuratedDocument,
    CurationStatus,
    ContentType,
    DocumentMetadata,
    CurationStatusRecord,
)
from media_curation.domain.exceptions import (
    CurationError,
    InvalidEventError,
    RetryableError,
)


# Custom strategies
uuid_strategy = st.uuids()
gcs_path_strategy = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N"), whitelist_characters="-_./"
    ),
    min_size=1,
    max_size=100,
).map(lambda s: f"gs://test-bucket/{s}")

mime_type_strategy = st.sampled_from(
    [
        "application/pdf",
        "image/jpeg",
        "image/png",
        "video/mp4",
        "audio/mpeg",
        "text/plain",
    ]
)

content_type_strategy = st.sampled_from(list(ContentType))
status_strategy = st.sampled_from(list(CurationStatus))


class TestCurationEventProperties:
    """Property-based tests for CurationEvent model."""

    @pytest.mark.property
    @given(
        tenant_id=uuid_strategy,
        file_id=uuid_strategy,
        mime_type=mime_type_strategy,
    )
    @settings(max_examples=20)
    def test_event_always_has_valid_ids(self, tenant_id, file_id, mime_type):
        """Property: CurationEvent always has valid UUIDs."""
        event = CurationEvent(
            tenant_id=tenant_id,
            file_id=file_id,
            raw_gcs_uri="gs://test-bucket/file.pdf",
            mime_type=mime_type,
        )

        assert isinstance(event.event_id, UUID)
        assert isinstance(event.trace_id, UUID)
        assert isinstance(event.tenant_id, UUID)
        assert isinstance(event.file_id, UUID)

    @pytest.mark.property
    @given(mime_type=mime_type_strategy)
    @settings(max_examples=10)
    def test_content_type_derivation(self, mime_type):
        """Property: Content type is correctly derived from MIME type."""
        event = CurationEvent(
            tenant_id=uuid4(),
            file_id=uuid4(),
            raw_gcs_uri="gs://test-bucket/file",
            mime_type=mime_type,
        )

        content_type = event.get_content_type()

        if mime_type.startswith("video/"):
            assert content_type == ContentType.VIDEO
        elif mime_type.startswith("audio/"):
            assert content_type == ContentType.AUDIO
        elif mime_type.startswith("image/"):
            assert content_type == ContentType.IMAGE
        elif mime_type == "application/pdf":
            assert content_type == ContentType.DOCUMENT
        elif mime_type.startswith("text/"):
            assert content_type == ContentType.TEXT

    @pytest.mark.property
    @given(path=st.text(min_size=1, max_size=50).filter(lambda x: "/" not in x[:1]))
    @settings(max_examples=10)
    def test_gcs_uri_validation(self, path):
        """Property: Only valid GCS URIs are accepted."""
        # Valid GCS URI should work
        event = CurationEvent(
            tenant_id=uuid4(),
            file_id=uuid4(),
            raw_gcs_uri=f"gs://bucket/{path}",
            mime_type="application/pdf",
        )
        assert event.raw_gcs_uri.startswith("gs://")

        # Invalid path should fail
        with pytest.raises(Exception):
            CurationEvent(
                tenant_id=uuid4(),
                file_id=uuid4(),
                raw_gcs_uri=f"/local/{path}",  # Not a GCS URI
                mime_type="application/pdf",
            )


class TestCuratedDocumentProperties:
    """Property-based tests for CuratedDocument model."""

    @pytest.mark.property
    @given(
        text=st.text(min_size=0, max_size=1000),
        confidence=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    )
    @settings(max_examples=20)
    def test_document_accepts_any_text(self, text, confidence):
        """Property: CuratedDocument accepts any valid text content."""
        doc = CuratedDocument(
            document_id=uuid4(),
            trace_id=uuid4(),
            tenant_id=uuid4(),
            file_id=uuid4(),
            source_gcs_uri="gs://bucket/file",
            mime_type="application/pdf",
            extracted_text=text,
            confidence_score=confidence,
            status=CurationStatus.CURATED,
        )

        assert doc.extracted_text == text
        assert 0.0 <= doc.confidence_score <= 1.0

    @pytest.mark.property
    @given(
        keywords=st.lists(st.text(min_size=1, max_size=50), max_size=20),
    )
    @settings(max_examples=10)
    def test_document_keywords_preserved(self, keywords):
        """Property: Keywords list is preserved exactly."""
        doc = CuratedDocument(
            document_id=uuid4(),
            trace_id=uuid4(),
            tenant_id=uuid4(),
            file_id=uuid4(),
            source_gcs_uri="gs://bucket/file",
            mime_type="application/pdf",
            extracted_text="test",
            keywords=keywords,
            status=CurationStatus.CURATED,
        )

        assert doc.keywords == keywords
        assert len(doc.keywords) == len(keywords)

    @pytest.mark.property
    @given(status=status_strategy)
    @settings(max_examples=10)
    def test_document_status_values(self, status):
        """Property: All status values are valid."""
        doc = CuratedDocument(
            document_id=uuid4(),
            trace_id=uuid4(),
            tenant_id=uuid4(),
            file_id=uuid4(),
            source_gcs_uri="gs://bucket/file",
            mime_type="application/pdf",
            extracted_text="test",
            status=status,
        )

        assert doc.status in CurationStatus
        assert doc.status.value in [
            "pending",
            "processing",
            "curated",
            "failed",
            "skipped",
        ]


class TestCurationStatusRecordProperties:
    """Property-based tests for CurationStatusRecord model."""

    @pytest.mark.property
    @given(
        status=status_strategy,
        message=st.text(max_size=500),
    )
    @settings(max_examples=10)
    def test_status_record_message_preserved(self, status, message):
        """Property: Status record message is preserved."""
        record = CurationStatusRecord(
            trace_id=uuid4(),
            event_id=uuid4(),
            tenant_id=uuid4(),
            file_id=uuid4(),
            status=status,
            message=message,
        )

        assert record.message == message
        assert record.status == status


class TestExceptionProperties:
    """Property-based tests for exception classes."""

    @pytest.mark.property
    @given(
        message=st.text(min_size=1, max_size=200),
    )
    @settings(max_examples=10)
    def test_curation_error_preserves_message(self, message):
        """Property: CurationError preserves message."""
        error = CurationError(message=message)

        assert message in str(error)
        assert error.message == message

    @pytest.mark.property
    @given(
        reason=st.text(min_size=1, max_size=200),
    )
    @settings(max_examples=10)
    def test_invalid_event_error_properties(self, reason):
        """Property: InvalidEventError preserves reason."""
        error = InvalidEventError(reason=reason)

        assert error.reason == reason
        assert "Invalid event" in str(error)

    @pytest.mark.property
    @given(
        message=st.text(min_size=1, max_size=200),
        retry_after=st.floats(min_value=0.1, max_value=3600.0, allow_nan=False),
    )
    @settings(max_examples=10)
    def test_retryable_error_retry_after(self, message, retry_after):
        """Property: RetryableError respects retry_after_seconds."""
        error = RetryableError(message=message, retry_after_seconds=retry_after)

        assert error.retry_after_seconds == retry_after
        assert error.message == message


class TestMetadataProperties:
    """Property-based tests for metadata handling."""

    @pytest.mark.property
    @given(
        metadata=st.dictionaries(
            keys=st.text(min_size=1, max_size=20).filter(lambda x: x.isalnum()),
            values=st.one_of(
                st.text(max_size=100),
                st.integers(),
                st.floats(allow_nan=False, allow_infinity=False),
                st.booleans(),
            ),
            max_size=10,
        )
    )
    @settings(max_examples=15)
    def test_event_metadata_preserved(self, metadata):
        """Property: Event metadata is preserved."""
        event = CurationEvent(
            tenant_id=uuid4(),
            file_id=uuid4(),
            raw_gcs_uri="gs://bucket/file",
            mime_type="application/pdf",
            metadata=metadata,
        )

        assert event.metadata == metadata

    @pytest.mark.property
    @given(
        filename=st.text(min_size=1, max_size=100).filter(lambda x: "/" not in x),
        size=st.integers(min_value=0, max_value=10**10),
        word_count=st.integers(min_value=0, max_value=10**7),
    )
    @settings(max_examples=10)
    def test_document_metadata_values(self, filename, size, word_count):
        """Property: DocumentMetadata accepts valid values."""
        meta = DocumentMetadata(
            original_filename=filename,
            file_size_bytes=size,
            word_count=word_count,
        )

        assert meta.original_filename == filename
        assert meta.file_size_bytes == size
        assert meta.word_count == word_count
