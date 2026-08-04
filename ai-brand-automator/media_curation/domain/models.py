"""
Media Curation Domain Models.

Pydantic models for the media curation pipeline:
- CurationEvent: Input event from Kafka (curation-needed-topic)
- TenantConfig: Redis-stored tenant configuration
- ProcessorResult: Output from ContentProcessor implementations
- CuratedDocument: Final output structure for RAG indexing
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator


class CurationStatus(str, Enum):
    """Processing status for curation events."""

    PENDING = "pending"
    PROCESSING = "processing"
    CURATED = "curated"
    FAILED = "failed"
    SKIPPED = "skipped"


class ContentType(str, Enum):
    """Supported content types for curation."""

    VIDEO = "video"
    AUDIO = "audio"
    IMAGE = "image"
    DOCUMENT = "document"
    TEXT = "text"
    UNKNOWN = "unknown"


class DocumentMetadata(BaseModel):
    """Metadata for a curated document."""

    original_filename: Optional[str] = None
    file_size_bytes: Optional[int] = None
    content_type: str = ""
    word_count: int = 0
    language_code: Optional[str] = None
    page_count: Optional[int] = None
    duration_seconds: Optional[float] = None


class CurationEvent(BaseModel):
    """
    Input event received from Kafka curation-needed-topic.

    This event is produced by the data_ingestion service after
    successfully ingesting a file to GCS.
    """

    event_id: UUID = Field(default_factory=uuid4)
    trace_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    tenant_id: str
    file_id: UUID
    raw_gcs_uri: str  # GCS path: gs://bucket/_raw/tenant/file
    mime_type: str  # MIME type: video/mp4, image/jpeg, etc.
    content_type: ContentType = ContentType.UNKNOWN
    source_service: str = "data-ingestion-svc"
    metadata: Optional[dict[str, Any]] = None
    curated_bucket: Optional[str] = Field(
        default=None,
        description="Per-tenant curated bucket override "
        "(from upstream event payload)",
    )

    # Legacy field aliases for backward compatibility
    @property
    def source_path(self) -> str:
        """Alias for raw_gcs_uri."""
        return self.raw_gcs_uri

    @property
    def file_type(self) -> str:
        """Alias for mime_type."""
        return self.mime_type

    @field_validator("raw_gcs_uri")
    @classmethod
    def validate_gcs_path(cls, v: str) -> str:
        """Ensure raw_gcs_uri is a valid GCS URI."""
        if not v.startswith("gs://"):
            raise ValueError("raw_gcs_uri must be a GCS URI (gs://...)")
        return v

    def get_content_type(self) -> ContentType:
        """Determine ContentType from MIME type."""
        if self.mime_type.startswith("video/"):
            return ContentType.VIDEO
        elif self.mime_type.startswith("audio/"):
            return ContentType.AUDIO
        elif self.mime_type.startswith("image/"):
            return ContentType.IMAGE
        elif self.mime_type in ("application/pdf",):
            return ContentType.DOCUMENT
        elif self.mime_type.startswith("text/"):
            return ContentType.TEXT
        return ContentType.UNKNOWN


class TenantConfig(BaseModel):
    """
    Tenant-specific configuration stored in Redis.

    Controls behavior like PII redaction rules, model preferences, etc.
    """

    tenant_id: str
    dlp_enabled: bool = True
    dlp_info_types: list[str] = Field(
        default_factory=lambda: [
            "EMAIL_ADDRESS",
            "PHONE_NUMBER",
            "CREDIT_CARD_NUMBER",
            "US_SOCIAL_SECURITY_NUMBER",
            "PERSON_NAME",
        ]
    )
    custom_pii_patterns: list[dict[str, str]] = Field(default_factory=list)
    ai_model: str = "gemini-3.5-flash"
    max_tokens: int = 8192
    temperature: float = 0.1
    preferred_language: str = "en"
    max_video_duration_seconds: int = 3600  # 1 hour
    enable_speaker_diarization: bool = False
    confidence_threshold: float = 0.7
    metadata: dict[str, Any] = Field(default_factory=dict)

    # Legacy field aliases
    @property
    def pii_redaction_enabled(self) -> bool:
        """Alias for dlp_enabled."""
        return self.dlp_enabled

    @property
    def pii_info_types(self) -> list[str]:
        """Alias for dlp_info_types."""
        return self.dlp_info_types


class ProcessorResult(BaseModel):
    """
    Result from a ContentProcessor implementation.

    Contains extracted text, structured data, and processing metadata.
    """

    extracted_text: str = ""
    struct_data: dict[str, Any] = Field(default_factory=dict)
    confidence_score: float = 0.0
    processing_time_ms: int = 0
    language_code: Optional[str] = None
    error_message: Optional[str] = None

    # Legacy fields for backward compatibility
    event_id: Optional[UUID] = None
    trace_id: Optional[UUID] = None
    content_type: Optional[ContentType] = None
    extracted_entities: list[dict[str, Any]] = Field(default_factory=list)
    summary: Optional[str] = None
    duration_seconds: Optional[float] = None
    page_count: Optional[int] = None
    dimensions: Optional[dict[str, int]] = None
    raw_response: Optional[dict[str, Any]] = None

    @property
    def is_successful(self) -> bool:
        """Check if processing was successful."""
        return self.error_message is None and len(self.extracted_text) > 0

    @property
    def language_detected(self) -> str:
        """Alias for language_code."""
        return self.language_code or "en"

    @property
    def processing_duration_ms(self) -> int:
        """Alias for processing_time_ms."""
        return self.processing_time_ms


class CuratedDocument(BaseModel):
    """
    Final curated document ready for RAG indexing.

    This is the output sent to the rag-sync-ready-topic.
    """

    # Identifiers
    document_id: UUID = Field(default_factory=uuid4)
    trace_id: UUID
    tenant_id: str
    file_id: UUID

    # Source information
    source_gcs_uri: str
    output_gcs_uri: Optional[str] = None
    mime_type: str

    # Curated content
    extracted_text: str = ""
    struct_data: dict[str, Any] = Field(default_factory=dict)

    # Processing metadata
    pii_redacted: bool = False
    processing_time_ms: int = 0
    metadata: DocumentMetadata = Field(default_factory=DocumentMetadata)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # What the uploader said this asset *is* (B-02, Design §10.1). Carried
    # from the ingestion event rather than read from the database: this is a
    # hexagonal app and must not import the Django ORM.
    #
    # ocr_text is deliberately NOT carried here. OCR runs after upload, so at
    # event time the column is always null — threading it now would ship null
    # on every document while looking wired. H-03 owns it, and re-syncs the
    # document once redaction has actually run (Design §5.2 PG-08).
    usage_tag: Optional[str] = None

    # Legacy fields for backward compatibility
    event_id: Optional[UUID] = None
    brand_id: Optional[str] = None
    title: Optional[str] = None
    summary: Optional[str] = None
    entities: list[dict[str, Any]] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    language: str = "en"
    status: CurationStatus = CurationStatus.CURATED
    confidence_score: float = 0.0
    pii_findings_count: int = 0

    # Aliases for backward compatibility
    @property
    def source_path(self) -> str:
        """Alias for source_gcs_uri."""
        return self.source_gcs_uri

    @property
    def destination_path(self) -> Optional[str]:
        """Alias for output_gcs_uri."""
        return self.output_gcs_uri

    @property
    def file_type(self) -> str:
        """Alias for mime_type."""
        return self.mime_type

    @property
    def content(self) -> str:
        """Alias for extracted_text."""
        return self.extracted_text

    @property
    def content_type(self) -> ContentType:
        """Determine ContentType from MIME type."""
        if self.mime_type.startswith("video/"):
            return ContentType.VIDEO
        elif self.mime_type.startswith("audio/"):
            return ContentType.AUDIO
        elif self.mime_type.startswith("image/"):
            return ContentType.IMAGE
        elif self.mime_type in ("application/pdf",):
            return ContentType.DOCUMENT
        elif self.mime_type.startswith("text/"):
            return ContentType.TEXT
        return ContentType.UNKNOWN

    def to_rag_document(self) -> dict[str, Any]:
        """Convert to RAG indexer document format."""
        metadata: dict[str, Any] = {
            "file_id": str(self.file_id),
            "trace_id": str(self.trace_id),
            "pii_redacted": self.pii_redacted,
            "confidence_score": self.confidence_score,
            **self.struct_data,
        }
        # Only when present, so documents uploaded before B-02 — and every
        # asset that carries no tag — keep exactly the payload they had.
        if self.usage_tag:
            metadata["usage_tag"] = self.usage_tag

        return {
            "id": str(self.document_id),
            "tenant_id": self.tenant_id,
            "brand_id": self.brand_id,
            "content": self.extracted_text,
            "title": self.title,
            "summary": self.summary,
            "entities": self.entities,
            "keywords": self.keywords,
            "language": self.language,
            "source_path": self.source_gcs_uri,
            "file_type": self.mime_type,
            "content_type": self.content_type.value,
            "created_at": self.created_at.isoformat(),
            "metadata": metadata,
        }


class CurationStatusRecord(BaseModel):
    """
    Status record stored in Redis for tracking curation progress.
    """

    trace_id: UUID
    event_id: UUID
    tenant_id: str
    file_id: UUID
    status: CurationStatus
    message: str = ""
    output_gcs_uri: Optional[str] = None
    error_code: Optional[str] = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Legacy fields
    content_type: Optional[ContentType] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    processing_duration_ms: int = 0
    retry_count: int = 0

    @property
    def destination_path(self) -> Optional[str]:
        """Alias for output_gcs_uri."""
        return self.output_gcs_uri

    @property
    def error_message(self) -> Optional[str]:
        """Alias for message when status is FAILED."""
        return self.message if self.status == CurationStatus.FAILED else None
