"""
Unit tests for media_curation domain models.

Tests Pydantic validation for:
- CurationEvent
- TenantConfig
- ProcessorResult
- CuratedDocument
- CurationStatusRecord
"""

import pytest
from datetime import datetime, timezone
from uuid import UUID, uuid4

from pydantic import ValidationError

from media_curation.domain.models import (
    CurationEvent,
    TenantConfig,
    ProcessorResult,
    CuratedDocument,
    CurationStatusRecord,
    CurationStatus,
    ContentType,
    DocumentMetadata,
)


class TestCurationEvent:
    """Tests for CurationEvent model."""

    def test_valid_event_creation(self, sample_curation_event):
        """Test creating a valid curation event."""
        event = sample_curation_event
        assert isinstance(event.event_id, UUID)
        assert isinstance(event.trace_id, UUID)
        assert isinstance(event.tenant_id, str)
        assert event.mime_type == "application/pdf"
        assert event.content_type == ContentType.DOCUMENT

    def test_event_with_minimal_fields(self):
        """Test event with only required fields."""
        event = CurationEvent(
            event_id=uuid4(),
            trace_id=uuid4(),
            tenant_id=str(uuid4()),
            file_id=uuid4(),
            raw_gcs_uri="gs://bucket/file.pdf",
            mime_type="application/pdf",
            content_type=ContentType.DOCUMENT,
            source_service="test-svc",
            timestamp=datetime.now(timezone.utc),
        )
        assert event.metadata is None

    def test_event_missing_required_field_raises_error(self):
        """Test that missing required fields raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            CurationEvent(
                event_id=uuid4(),
                trace_id=uuid4(),
                # Missing tenant_id
                file_id=uuid4(),
                raw_gcs_uri="gs://bucket/file.pdf",
                mime_type="application/pdf",
                content_type=ContentType.DOCUMENT,
                source_service="test-svc",
                timestamp=datetime.now(timezone.utc),
            )
        assert "tenant_id" in str(exc_info.value)

    def test_event_invalid_gcs_uri_format(self):
        """Test validation of GCS URI format."""
        # Should accept valid gs:// URI
        event = CurationEvent(
            event_id=uuid4(),
            trace_id=uuid4(),
            tenant_id=str(uuid4()),
            file_id=uuid4(),
            raw_gcs_uri="gs://valid-bucket/path/to/file.pdf",
            mime_type="application/pdf",
            content_type=ContentType.DOCUMENT,
            source_service="test-svc",
            timestamp=datetime.now(timezone.utc),
        )
        assert event.raw_gcs_uri.startswith("gs://")

    def test_event_content_types(self):
        """Test all content type values."""
        for content_type in ContentType:
            event = CurationEvent(
                event_id=uuid4(),
                trace_id=uuid4(),
                tenant_id=str(uuid4()),
                file_id=uuid4(),
                raw_gcs_uri="gs://bucket/file",
                mime_type="text/plain",
                content_type=content_type,
                source_service="test-svc",
                timestamp=datetime.now(timezone.utc),
            )
            assert event.content_type == content_type

    def test_event_with_metadata(self):
        """Test event with metadata dictionary."""
        metadata = {
            "filename": "test.pdf",
            "file_size": 1024,
            "custom_field": "custom_value",
        }
        event = CurationEvent(
            event_id=uuid4(),
            trace_id=uuid4(),
            tenant_id=str(uuid4()),
            file_id=uuid4(),
            raw_gcs_uri="gs://bucket/file.pdf",
            mime_type="application/pdf",
            content_type=ContentType.DOCUMENT,
            source_service="test-svc",
            timestamp=datetime.now(timezone.utc),
            metadata=metadata,
        )
        assert event.metadata == metadata
        assert event.metadata["filename"] == "test.pdf"


class TestTenantConfig:
    """Tests for TenantConfig model."""

    def test_default_values(self, sample_tenant_id):
        """Test default tenant config values."""
        config = TenantConfig(tenant_id=sample_tenant_id)
        assert config.dlp_enabled is True
        assert config.ai_model == "gemini-3.5-flash"
        assert config.max_tokens == 8192
        assert config.temperature == 0.1

    def test_custom_dlp_info_types(self, sample_tenant_id):
        """Test custom DLP info types."""
        config = TenantConfig(
            tenant_id=sample_tenant_id,
            dlp_info_types=["EMAIL_ADDRESS", "PHONE_NUMBER"],
        )
        assert len(config.dlp_info_types) == 2
        assert "EMAIL_ADDRESS" in config.dlp_info_types

    def test_dlp_disabled(self, sample_tenant_id):
        """Test config with DLP disabled."""
        config = TenantConfig(
            tenant_id=sample_tenant_id,
            dlp_enabled=False,
        )
        assert config.dlp_enabled is False

    def test_custom_ai_model(self, sample_tenant_id):
        """Test custom AI model configuration."""
        config = TenantConfig(
            tenant_id=sample_tenant_id,
            ai_model="gemini-1.5-pro",
            max_tokens=16384,
            temperature=0.5,
        )
        assert config.ai_model == "gemini-1.5-pro"
        assert config.max_tokens == 16384
        assert config.temperature == 0.5

    def test_temperature_validation(self, sample_tenant_id):
        """Test temperature must be between 0 and 2."""
        # Valid temperatures
        config = TenantConfig(
            tenant_id=sample_tenant_id,
            temperature=0.0,
        )
        assert config.temperature == 0.0

        config = TenantConfig(
            tenant_id=sample_tenant_id,
            temperature=2.0,
        )
        assert config.temperature == 2.0


class TestProcessorResult:
    """Tests for ProcessorResult model."""

    def test_valid_result(self, sample_processor_result):
        """Test creating a valid processor result."""
        result = sample_processor_result
        assert result.extracted_text is not None
        assert result.confidence_score == 0.95
        assert result.processing_time_ms == 1500

    def test_result_with_empty_text(self):
        """Test result with empty extracted text."""
        result = ProcessorResult(
            extracted_text="",
            struct_data={},
            confidence_score=0.5,
            processing_time_ms=100,
        )
        assert result.extracted_text == ""

    def test_result_with_struct_data(self):
        """Test result with structured data."""
        struct_data = {
            "title": "Document Title",
            "author": "John Doe",
            "pages": 10,
            "tables": [{"rows": 5, "cols": 3}],
        }
        result = ProcessorResult(
            extracted_text="Sample text",
            struct_data=struct_data,
            confidence_score=0.9,
            processing_time_ms=200,
        )
        assert result.struct_data["title"] == "Document Title"
        assert len(result.struct_data["tables"]) == 1

    def test_confidence_score_bounds(self):
        """Test confidence score values."""
        result = ProcessorResult(
            extracted_text="text",
            struct_data={},
            confidence_score=0.0,
            processing_time_ms=100,
        )
        assert result.confidence_score == 0.0

        result = ProcessorResult(
            extracted_text="text",
            struct_data={},
            confidence_score=1.0,
            processing_time_ms=100,
        )
        assert result.confidence_score == 1.0

    def test_result_with_language_code(self):
        """Test result with language code."""
        result = ProcessorResult(
            extracted_text="Bonjour le monde",
            struct_data={},
            confidence_score=0.95,
            processing_time_ms=100,
            language_code="fr",
        )
        assert result.language_code == "fr"


class TestCuratedDocument:
    """Tests for CuratedDocument model."""

    def test_valid_document(self, sample_curated_document):
        """Test creating a valid curated document."""
        doc = sample_curated_document
        assert isinstance(doc.document_id, UUID)
        assert doc.mime_type == "application/pdf"
        assert doc.pii_redacted is False

    def test_document_with_pii_redaction(
        self,
        sample_tenant_id,
        sample_file_id,
        sample_trace_id,
    ):
        """Test document marked as PII redacted."""
        doc = CuratedDocument(
            document_id=uuid4(),
            trace_id=sample_trace_id,
            tenant_id=sample_tenant_id,
            file_id=sample_file_id,
            source_gcs_uri="gs://bucket/file.pdf",
            output_gcs_uri="gs://curated/doc.json",
            mime_type="application/pdf",
            extracted_text="Contact at [EMAIL REDACTED]",
            struct_data={},
            pii_redacted=True,
            processing_time_ms=1000,
            metadata=DocumentMetadata(
                content_type="application/pdf",
                word_count=4,
            ),
            created_at=datetime.now(timezone.utc),
        )
        assert doc.pii_redacted is True
        assert "[EMAIL REDACTED]" in doc.extracted_text

    def test_document_metadata(self, sample_curated_document):
        """Test document metadata fields."""
        doc = sample_curated_document
        assert doc.metadata.original_filename == "test-document.pdf"
        assert doc.metadata.file_size_bytes == 1024
        assert doc.metadata.word_count == 8

    def test_document_serialization(self, sample_curated_document):
        """Test document can be serialized to dict."""
        doc = sample_curated_document
        doc_dict = doc.model_dump()

        assert "document_id" in doc_dict
        assert "extracted_text" in doc_dict
        assert "metadata" in doc_dict

    def test_document_json_serialization(self, sample_curated_document):
        """Test document can be serialized to JSON."""
        doc = sample_curated_document
        doc_json = doc.model_dump_json()

        assert isinstance(doc_json, str)
        assert "document_id" in doc_json


class TestCurationStatusRecord:
    """Tests for CurationStatusRecord model."""

    def test_pending_status(
        self,
        sample_trace_id,
        sample_tenant_id,
        sample_file_id,
    ):
        """Test creating a pending status record."""
        status = CurationStatusRecord(
            trace_id=sample_trace_id,
            event_id=uuid4(),
            tenant_id=sample_tenant_id,
            file_id=sample_file_id,
            status=CurationStatus.PENDING,
            message="Waiting in queue",
            updated_at=datetime.now(timezone.utc),
        )
        assert status.status == CurationStatus.PENDING
        assert status.output_gcs_uri is None
        assert status.error_code is None

    def test_processing_status(
        self,
        sample_trace_id,
        sample_tenant_id,
        sample_file_id,
    ):
        """Test processing status."""
        status = CurationStatusRecord(
            trace_id=sample_trace_id,
            event_id=uuid4(),
            tenant_id=sample_tenant_id,
            file_id=sample_file_id,
            status=CurationStatus.PROCESSING,
            message="Extracting content",
            updated_at=datetime.now(timezone.utc),
        )
        assert status.status == CurationStatus.PROCESSING

    def test_curated_status_with_output(
        self,
        sample_trace_id,
        sample_tenant_id,
        sample_file_id,
    ):
        """Test curated status with output URI."""
        status = CurationStatusRecord(
            trace_id=sample_trace_id,
            event_id=uuid4(),
            tenant_id=sample_tenant_id,
            file_id=sample_file_id,
            status=CurationStatus.CURATED,
            message="Curation completed",
            output_gcs_uri="gs://curated/doc.json",
            updated_at=datetime.now(timezone.utc),
        )
        assert status.status == CurationStatus.CURATED
        assert status.output_gcs_uri is not None

    def test_failed_status_with_error(
        self,
        sample_trace_id,
        sample_tenant_id,
        sample_file_id,
    ):
        """Test failed status with error details."""
        status = CurationStatusRecord(
            trace_id=sample_trace_id,
            event_id=uuid4(),
            tenant_id=sample_tenant_id,
            file_id=sample_file_id,
            status=CurationStatus.FAILED,
            message="Processing failed: Invalid file format",
            error_code="ProcessingError",
            updated_at=datetime.now(timezone.utc),
        )
        assert status.status == CurationStatus.FAILED
        assert status.error_code == "ProcessingError"
        assert "Invalid file format" in status.message

    def test_all_status_values(
        self,
        sample_trace_id,
        sample_tenant_id,
        sample_file_id,
    ):
        """Test all curation status enum values."""
        for status_value in CurationStatus:
            status = CurationStatusRecord(
                trace_id=sample_trace_id,
                event_id=uuid4(),
                tenant_id=sample_tenant_id,
                file_id=sample_file_id,
                status=status_value,
                message=f"Status: {status_value.value}",
                updated_at=datetime.now(timezone.utc),
            )
            assert status.status == status_value


class TestDocumentMetadata:
    """Tests for DocumentMetadata model."""

    def test_minimal_metadata(self):
        """Test metadata with minimal fields."""
        metadata = DocumentMetadata(
            content_type="application/pdf",
            word_count=100,
        )
        assert metadata.content_type == "application/pdf"
        assert metadata.word_count == 100
        assert metadata.original_filename is None

    def test_full_metadata(self):
        """Test metadata with all fields."""
        metadata = DocumentMetadata(
            original_filename="report.pdf",
            file_size_bytes=1024000,
            content_type="application/pdf",
            word_count=5000,
            language_code="en",
        )
        assert metadata.original_filename == "report.pdf"
        assert metadata.file_size_bytes == 1024000
        assert metadata.language_code == "en"


class TestContentType:
    """Tests for ContentType enum."""

    def test_content_type_values(self):
        """Test all content type enum values."""
        assert ContentType.VIDEO.value == "video"
        assert ContentType.AUDIO.value == "audio"
        assert ContentType.IMAGE.value == "image"
        assert ContentType.DOCUMENT.value == "document"
        assert ContentType.TEXT.value == "text"

    def test_content_type_from_string(self):
        """Test creating content type from string value."""
        assert ContentType("video") == ContentType.VIDEO
        assert ContentType("document") == ContentType.DOCUMENT
