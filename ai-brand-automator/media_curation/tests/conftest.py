"""
Test fixtures for media_curation tests.

Provides mock adapters, sample events, and test utilities.
"""

import pytest
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

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
from media_curation.domain.schemas import (
    CurationNeededEvent,
    CurationCompletedEvent,
)

# Note: We don't inherit from these ABC ports in mocks to keep tests simpler
from media_curation.ports.dlp_port import PIIFinding


# =============================================================================
# Sample UUIDs for consistent testing
# =============================================================================

SAMPLE_TENANT_ID = "11111111-1111-1111-1111-111111111111"
SAMPLE_FILE_ID = UUID("22222222-2222-2222-2222-222222222222")
SAMPLE_TRACE_ID = UUID("33333333-3333-3333-3333-333333333333")
SAMPLE_EVENT_ID = UUID("44444444-4444-4444-4444-444444444444")
SAMPLE_DOC_ID = UUID("55555555-5555-5555-5555-555555555555")


# =============================================================================
# Sample Data Factories
# =============================================================================


@pytest.fixture
def sample_tenant_id() -> str:
    """Return a consistent sample tenant ID."""
    return SAMPLE_TENANT_ID


@pytest.fixture
def sample_file_id() -> UUID:
    """Return a consistent sample file ID."""
    return SAMPLE_FILE_ID


@pytest.fixture
def sample_trace_id() -> UUID:
    """Return a consistent sample trace ID."""
    return SAMPLE_TRACE_ID


@pytest.fixture
def sample_curation_event() -> CurationEvent:
    """Create a sample curation event for testing."""
    return CurationEvent(
        event_id=SAMPLE_EVENT_ID,
        trace_id=SAMPLE_TRACE_ID,
        tenant_id=SAMPLE_TENANT_ID,
        file_id=SAMPLE_FILE_ID,
        raw_gcs_uri="gs://test-bucket/_landing/tenant-1/file-1.pdf",
        mime_type="application/pdf",
        content_type=ContentType.DOCUMENT,
        source_service="data-ingestion-svc",
        timestamp=datetime.now(timezone.utc),
        metadata={"filename": "test-document.pdf", "file_size": 1024},
    )


@pytest.fixture
def sample_video_event() -> CurationEvent:
    """Create a sample video curation event."""
    return CurationEvent(
        event_id=uuid4(),
        trace_id=uuid4(),
        tenant_id=SAMPLE_TENANT_ID,
        file_id=uuid4(),
        raw_gcs_uri="gs://test-bucket/_landing/tenant-1/video.mp4",
        mime_type="video/mp4",
        content_type=ContentType.VIDEO,
        source_service="data-ingestion-svc",
        timestamp=datetime.now(timezone.utc),
        metadata={"filename": "test-video.mp4", "file_size": 10485760},
    )


@pytest.fixture
def sample_audio_event() -> CurationEvent:
    """Create a sample audio curation event."""
    return CurationEvent(
        event_id=uuid4(),
        trace_id=uuid4(),
        tenant_id=SAMPLE_TENANT_ID,
        file_id=uuid4(),
        raw_gcs_uri="gs://test-bucket/_landing/tenant-1/audio.mp3",
        mime_type="audio/mpeg",
        content_type=ContentType.AUDIO,
        source_service="data-ingestion-svc",
        timestamp=datetime.now(timezone.utc),
        metadata={"filename": "test-audio.mp3", "file_size": 5242880},
    )


@pytest.fixture
def sample_image_event() -> CurationEvent:
    """Create a sample image curation event."""
    return CurationEvent(
        event_id=uuid4(),
        trace_id=uuid4(),
        tenant_id=SAMPLE_TENANT_ID,
        file_id=uuid4(),
        raw_gcs_uri="gs://test-bucket/_landing/tenant-1/image.png",
        mime_type="image/png",
        content_type=ContentType.IMAGE,
        source_service="data-ingestion-svc",
        timestamp=datetime.now(timezone.utc),
        metadata={"filename": "test-image.png", "file_size": 2097152},
    )


@pytest.fixture
def sample_tenant_config() -> TenantConfig:
    """Create a sample tenant configuration."""
    return TenantConfig(
        tenant_id=SAMPLE_TENANT_ID,
        dlp_enabled=True,
        dlp_info_types=["EMAIL_ADDRESS", "PHONE_NUMBER", "US_SSN"],
        ai_model="gemini-2.0-flash",
        max_tokens=8192,
        temperature=0.1,
    )


@pytest.fixture
def sample_processor_result() -> ProcessorResult:
    """Create a sample processor result."""
    return ProcessorResult(
        extracted_text="This is extracted text from the document.",
        struct_data={"title": "Test Document", "pages": 5},
        confidence_score=0.95,
        processing_time_ms=1500,
        language_code="en",
    )


@pytest.fixture
def sample_curated_document() -> CuratedDocument:
    """Create a sample curated document."""
    return CuratedDocument(
        document_id=SAMPLE_DOC_ID,
        trace_id=SAMPLE_TRACE_ID,
        tenant_id=SAMPLE_TENANT_ID,
        file_id=SAMPLE_FILE_ID,
        source_gcs_uri="gs://test-bucket/_landing/tenant-1/file-1.pdf",
        output_gcs_uri="gs://curated-bucket/tenant-1/file-1/doc-1.json",
        mime_type="application/pdf",
        extracted_text="This is extracted text from the document.",
        struct_data={"title": "Test Document", "pages": 5},
        pii_redacted=False,
        processing_time_ms=1500,
        metadata=DocumentMetadata(
            original_filename="test-document.pdf",
            file_size_bytes=1024,
            content_type="application/pdf",
            word_count=8,
            language_code="en",
        ),
        created_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def sample_status_record() -> CurationStatusRecord:
    """Create a sample curation status record."""
    return CurationStatusRecord(
        trace_id=SAMPLE_TRACE_ID,
        event_id=SAMPLE_EVENT_ID,
        tenant_id=SAMPLE_TENANT_ID,
        file_id=SAMPLE_FILE_ID,
        status=CurationStatus.CURATED,
        message="Curation completed successfully",
        output_gcs_uri="gs://curated-bucket/tenant-1/file-1/doc-1.json",
        error_code=None,
        updated_at=datetime.now(timezone.utc),
    )


# =============================================================================
# Mock Adapters
# =============================================================================


class MockContentProcessor:
    """
    Mock content processor for testing.

    Implements async interface from ContentProcessorPort.
    """

    _SUPPORTED_MIME_TYPES = ["application/pdf", "text/plain"]

    def __init__(
        self,
        extracted_text: str = "Mock extracted text",
        should_fail: bool = False,
        failure_exception: Optional[Exception] = None,
    ):
        self._extracted_text = extracted_text
        self._should_fail = should_fail
        self._failure_exception = failure_exception
        self.process_calls = []

    @property
    def supported_mime_types(self) -> list[str]:
        return self._SUPPORTED_MIME_TYPES

    # Alias for backward compatibility
    SUPPORTED_MIME_TYPES = _SUPPORTED_MIME_TYPES

    def supports(self, mime_type: str) -> bool:
        return any(
            mime_type.startswith(t.rstrip("*")) for t in self._SUPPORTED_MIME_TYPES
        )

    async def process(
        self,
        event: CurationEvent,
        tenant_config: Optional[TenantConfig] = None,
    ) -> ProcessorResult:
        """Async process matching ContentProcessorPort interface."""
        self.process_calls.append({"event": event, "tenant_config": tenant_config})

        if self._should_fail:
            if self._failure_exception:
                raise self._failure_exception
            raise Exception("Mock processing failure")

        return ProcessorResult(
            extracted_text=self._extracted_text,
            struct_data={"source": "mock"},
            confidence_score=0.99,
            processing_time_ms=100,
            language_code="en",
        )


class MockVideoProcessor:
    """
    Mock video processor for testing.

    Implements async interface from ContentProcessorPort.
    """

    _SUPPORTED_MIME_TYPES = ["video/mp4", "video/webm", "video/*"]

    @property
    def supported_mime_types(self) -> list[str]:
        return self._SUPPORTED_MIME_TYPES

    # Alias for backward compatibility
    SUPPORTED_MIME_TYPES = _SUPPORTED_MIME_TYPES

    def supports(self, mime_type: str) -> bool:
        return mime_type.startswith("video/")

    async def process(
        self,
        event: CurationEvent,
        tenant_config: Optional[TenantConfig] = None,
    ) -> ProcessorResult:
        """Async process matching ContentProcessorPort interface."""
        return ProcessorResult(
            extracted_text="[Video transcript] This is a mock video transcript.",
            struct_data={"duration_seconds": 120, "has_audio": True},
            confidence_score=0.92,
            processing_time_ms=5000,
            language_code="en",
        )


class MockDLPAdapter:
    """Mock DLP adapter for testing (implements async interface from DLPPort)."""

    def __init__(
        self,
        should_redact: bool = True,
        should_fail: bool = False,
    ):
        self._should_redact = should_redact
        self._should_fail = should_fail
        self.redact_calls = []
        self.detect_calls = []

    async def redact_pii(
        self,
        text: str,
        tenant_config: Optional[TenantConfig] = None,
        replacement_token: str = "[REDACTED]",
    ):
        """Async redact_pii matching DLPPort interface."""
        from media_curation.ports.dlp_port import RedactionResult

        self.redact_calls.append({"text": text, "tenant_config": tenant_config})

        if self._should_fail:
            raise Exception("Mock DLP failure")

        if not self._should_redact:
            return RedactionResult(
                original_text=text,
                redacted_text=text,
                findings=[],
                findings_count=0,
                redaction_applied=False,
            )

        # Simple mock redaction
        redacted = text
        findings = []

        if "john@example.com" in text:
            redacted = redacted.replace("john@example.com", replacement_token)
            findings.append(
                PIIFinding(
                    info_type="EMAIL_ADDRESS",
                    quote="john@example.com",
                    likelihood="VERY_LIKELY",
                    start_offset=text.find("john@example.com"),
                    end_offset=text.find("john@example.com") + len("john@example.com"),
                )
            )
        if "555-123-4567" in text:
            redacted = redacted.replace("555-123-4567", replacement_token)
            findings.append(
                PIIFinding(
                    info_type="PHONE_NUMBER",
                    quote="555-123-4567",
                    likelihood="VERY_LIKELY",
                    start_offset=text.find("555-123-4567"),
                    end_offset=text.find("555-123-4567") + len("555-123-4567"),
                )
            )
        if "123-45-6789" in text:
            redacted = redacted.replace("123-45-6789", replacement_token)
            findings.append(
                PIIFinding(
                    info_type="US_SSN",
                    quote="123-45-6789",
                    likelihood="VERY_LIKELY",
                    start_offset=text.find("123-45-6789"),
                    end_offset=text.find("123-45-6789") + len("123-45-6789"),
                )
            )

        return RedactionResult(
            original_text=text,
            redacted_text=redacted,
            findings=findings,
            findings_count=len(findings),
            redaction_applied=len(findings) > 0,
        )

    async def detect_pii(
        self,
        text: str,
        tenant_config: Optional[TenantConfig] = None,
    ) -> list[PIIFinding]:
        """Async detect_pii matching DLPPort interface."""
        self.detect_calls.append({"text": text})

        findings = []
        if "john@example.com" in text:
            findings.append(
                PIIFinding(
                    info_type="EMAIL_ADDRESS",
                    quote="john@example.com",
                    likelihood="VERY_LIKELY",
                    start_offset=text.find("john@example.com"),
                    end_offset=text.find("john@example.com") + len("john@example.com"),
                )
            )
        return findings

    async def is_healthy(self) -> bool:
        """Check if DLP service is healthy."""
        return True


class MockStorageAdapter:
    """
    Mock storage adapter for testing.

    Implements async interface from StoragePort.
    """

    def __init__(self):
        self.saved_files = {}
        self.read_calls = []
        self.save_calls = []

    async def exists(self, path: str) -> bool:
        """Check if file exists."""
        return path in self.saved_files

    async def get_file_info(self, path: str):
        """Get file info."""
        from media_curation.ports.storage_port import FileInfo

        if path not in self.saved_files:
            raise Exception(f"File not found: {path}")
        content = self.saved_files[path]
        bucket, name = self._parse_gcs_uri(path)
        return FileInfo(
            path=path,
            bucket=bucket,
            name=name,
            size_bytes=len(content),
            content_type="application/octet-stream",
        )

    async def download_as_bytes(self, path: str) -> bytes:
        """Download file as bytes."""
        self.read_calls.append(path)
        return self.saved_files.get(path, b"mock file content")

    async def download_to_file(self, path: str, destination: str) -> str:
        """Download to local file."""
        content = await self.download_as_bytes(path)
        with open(destination, "wb") as f:
            f.write(content)
        return destination

    async def upload_from_bytes(
        self,
        content: bytes,
        destination_path: str,
        content_type: str = "application/octet-stream",
        metadata: Optional[dict] = None,
    ):
        """Upload bytes to storage."""
        from media_curation.ports.storage_port import FileInfo

        self.saved_files[destination_path] = content
        self.save_calls.append(
            {
                "destination_path": destination_path,
                "content": content,
                "content_type": content_type,
                "metadata": metadata,
            }
        )

        bucket, name = self._parse_gcs_uri(destination_path)
        return FileInfo(
            path=destination_path,
            bucket=bucket,
            name=name,
            size_bytes=len(content),
            content_type=content_type,
            metadata=metadata or {},
        )

    async def upload_from_file(
        self,
        source_path: str,
        destination_path: str,
        content_type: str = "application/octet-stream",
        metadata: Optional[dict] = None,
    ):
        """Upload local file to storage."""
        with open(source_path, "rb") as f:
            content = f.read()
        return await self.upload_from_bytes(
            content, destination_path, content_type, metadata
        )

    async def delete(self, path: str) -> bool:
        """Delete a file."""
        if path in self.saved_files:
            del self.saved_files[path]
            return True
        return False

    async def generate_signed_url(
        self,
        path: str,
        expiration_seconds: int = 3600,
        method: str = "GET",
    ) -> str:
        """Generate signed URL."""
        return (
            f"https://storage.googleapis.com/signed/{path}?expires={expiration_seconds}"
        )

    async def is_healthy(self) -> bool:
        """Check health."""
        return True

    def _parse_gcs_uri(self, uri: str) -> tuple[str, str]:
        """Parse gs://bucket/path into (bucket, path)."""
        if uri.startswith("gs://"):
            parts = uri[5:].split("/", 1)
            return parts[0], parts[1] if len(parts) > 1 else ""
        return "unknown-bucket", uri


class MockCacheAdapter:
    """Mock cache adapter for testing (implements async interface from CachePort)."""

    def __init__(self):
        self._cache = {}
        self._status_cache = {}
        self._tenant_config_cache = {}
        self._processed_events = set()
        self.get_calls = []
        self.set_calls = []

    async def get_status(
        self, trace_id: str, tenant_id: Optional[str] = None
    ) -> Optional[CurationStatusRecord]:
        """Get curation status by trace_id."""
        self.get_calls.append(f"status:{trace_id}")
        return self._status_cache.get(trace_id)

    async def set_status(
        self,
        trace_id: str,
        status: CurationStatusRecord,
        ttl_seconds: Optional[int] = None,
        tenant_id: Optional[str] = None,
    ) -> None:
        """Set curation status."""
        self.set_calls.append(
            {"trace_id": trace_id, "status": status, "ttl": ttl_seconds}
        )
        self._status_cache[trace_id] = status

    async def update_status(
        self,
        trace_id: str,
        status: CurationStatus,
        tenant_id: Optional[str] = None,
        **updates,
    ) -> None:
        """Update status fields."""
        existing = self._status_cache.get(trace_id)
        if existing:
            update_dict = {"status": status, **updates}
            self._status_cache[trace_id] = existing.model_copy(update=update_dict)

    async def get_tenant_config(self, tenant_id: str) -> Optional[TenantConfig]:
        """Get tenant configuration."""
        self.get_calls.append(f"config:{tenant_id}")
        return self._tenant_config_cache.get(tenant_id)

    async def set_tenant_config(
        self,
        tenant_id: str,
        config: TenantConfig,
        ttl_seconds: Optional[int] = None,
    ) -> None:
        """Set tenant configuration."""
        self.set_calls.append(
            {"tenant_id": tenant_id, "config": config, "ttl": ttl_seconds}
        )
        self._tenant_config_cache[tenant_id] = config

    async def is_duplicate(
        self, event_id: str, tenant_id: Optional[str] = None
    ) -> bool:
        """Check if event was already processed."""
        return event_id in self._processed_events

    async def mark_processed(
        self,
        event_id: str,
        ttl_seconds: Optional[int] = None,
        tenant_id: Optional[str] = None,
    ) -> None:
        """Mark event as processed."""
        self._processed_events.add(event_id)

    async def is_healthy(self) -> bool:
        """Check health."""
        return True

    # Legacy sync methods for backward compatibility
    def get(self, key: str) -> Optional[dict]:
        self.get_calls.append(key)
        return self._cache.get(key)

    def set(self, key: str, value: dict, ttl: int = None) -> bool:
        self.set_calls.append({"key": key, "value": value, "ttl": ttl})
        self._cache[key] = value
        return True

    def delete(self, key: str) -> bool:
        if key in self._cache:
            del self._cache[key]
            return True
        return False

    def exists(self, key: str) -> bool:
        return key in self._cache


class MockEventProducer:
    """
    Mock event producer for testing.

    Implements async interface from EventProducerPort.
    """

    def __init__(self):
        self.published_events = []
        self.dlq_events = []

    async def publish_curated_document(
        self,
        topic: str,
        document,
        key: Optional[str] = None,
    ) -> None:
        """Publish a curated document."""
        self.published_events.append(
            {
                "topic": topic,
                "key": key,
                "document": document,
            }
        )

    async def publish_to_dlq(
        self,
        event,
        error: Exception,
        retry_count: int = 0,
    ) -> None:
        """Publish to dead letter queue."""
        self.dlq_events.append(
            {
                "event": event,
                "error": str(error),
                "retry_count": retry_count,
            }
        )

    async def publish_raw(
        self,
        topic: str,
        payload: dict,
        key: Optional[str] = None,
    ) -> None:
        """Publish raw dict payload."""
        self.published_events.append(
            {
                "topic": topic,
                "key": key,
                "payload": payload,
            }
        )

    def flush(self, timeout: float = 10.0) -> int:
        """Flush pending messages."""
        return 0

    async def is_healthy(self) -> bool:
        """Check health."""
        return True

    # Legacy sync method for backward compatibility
    def publish(self, topic: str, key: str, value: dict) -> bool:
        self.published_events.append(
            {
                "topic": topic,
                "key": key,
                "value": value,
            }
        )
        return True


class MockEventConsumer:
    """Mock event consumer for testing (simplified, does not inherit ABC)."""

    def __init__(self, events: list[dict] = None):
        self._events = events or []
        self._position = 0

    def subscribe(self, topics: list[str]) -> None:
        pass

    def consume(self, timeout: float = 1.0) -> Optional[dict]:
        if self._position < len(self._events):
            event = self._events[self._position]
            self._position += 1
            return event
        return None

    def consume_batch(self, max_messages: int = 10, timeout: float = 1.0) -> list[dict]:
        batch = []
        for _ in range(max_messages):
            event = self.consume(timeout)
            if event:
                batch.append(event)
            else:
                break
        return batch

    def commit(self) -> None:
        pass

    def close(self) -> None:
        pass


# =============================================================================
# Fixtures for Mock Adapters
# =============================================================================


@pytest.fixture
def mock_content_processor() -> MockContentProcessor:
    """Create a mock content processor."""
    return MockContentProcessor()


@pytest.fixture
def mock_video_processor() -> MockVideoProcessor:
    """Create a mock video processor."""
    return MockVideoProcessor()


@pytest.fixture
def mock_dlp_adapter() -> MockDLPAdapter:
    """Create a mock DLP adapter."""
    return MockDLPAdapter()


@pytest.fixture
def mock_storage_adapter() -> MockStorageAdapter:
    """Create a mock storage adapter."""
    return MockStorageAdapter()


@pytest.fixture
def mock_cache_adapter() -> MockCacheAdapter:
    """Create a mock cache adapter."""
    return MockCacheAdapter()


@pytest.fixture
def mock_event_producer() -> MockEventProducer:
    """Create a mock event producer."""
    return MockEventProducer()


@pytest.fixture
def mock_event_consumer() -> MockEventConsumer:
    """Create a mock event consumer."""
    return MockEventConsumer()


# =============================================================================
# Service Fixtures
# =============================================================================


@pytest.fixture
def processor_factory(
    mock_content_processor: MockContentProcessor,
    mock_video_processor: MockVideoProcessor,
):
    """Create a ProcessorFactory with mock processors."""
    from media_curation.domain.services import ProcessorFactory

    return ProcessorFactory(processors=[mock_content_processor, mock_video_processor])


@pytest.fixture
def curation_service(
    processor_factory,
    mock_dlp_adapter: MockDLPAdapter,
    mock_storage_adapter: MockStorageAdapter,
    mock_cache_adapter: MockCacheAdapter,
    mock_event_producer: MockEventProducer,
):
    """Create a CurationService with mock dependencies."""
    from media_curation.domain.services import CurationService

    return CurationService(
        processor_factory=processor_factory,
        dlp=mock_dlp_adapter,
        storage=mock_storage_adapter,
        cache=mock_cache_adapter,
        producer=mock_event_producer,
        output_topic="rag-sync-ready-topic",
        dlq_topic="curation-dlq",
        output_bucket="curated-content",
    )


# =============================================================================
# CloudEvents Fixtures
# =============================================================================


@pytest.fixture
def sample_curation_needed_event() -> CurationNeededEvent:
    """Create a sample curation-needed CloudEvent."""
    return CurationNeededEvent(
        id=str(SAMPLE_EVENT_ID),
        source="data-ingestion-svc",
        type="brandsol.ingestion.completed.v1",
        datacontenttype="application/json",
        time=datetime.now(timezone.utc),
        subject=f"tenant:{SAMPLE_TENANT_ID}/file:{SAMPLE_FILE_ID}",
        traceid=str(SAMPLE_TRACE_ID),
        data={
            "trace_id": str(SAMPLE_TRACE_ID),
            "tenant_id": str(SAMPLE_TENANT_ID),
            "file_id": str(SAMPLE_FILE_ID),
            "raw_gcs_uri": "gs://test-bucket/_landing/tenant-1/file-1.pdf",
            "mime_type": "application/pdf",
            "metadata": {"filename": "test-document.pdf"},
        },
    )


@pytest.fixture
def sample_curation_completed_event() -> CurationCompletedEvent:
    """Create a sample curation-completed CloudEvent."""
    return CurationCompletedEvent(
        id=str(uuid4()),
        source="media-curation-svc",
        type="brandsol.curation.completed.v1",
        datacontenttype="application/json",
        time=datetime.now(timezone.utc),
        subject=f"tenant:{SAMPLE_TENANT_ID}/file:{SAMPLE_FILE_ID}",
        traceid=str(SAMPLE_TRACE_ID),
        data={
            "trace_id": str(SAMPLE_TRACE_ID),
            "tenant_id": str(SAMPLE_TENANT_ID),
            "file_id": str(SAMPLE_FILE_ID),
            "document_id": str(SAMPLE_DOC_ID),
            "curated_gcs_uri": "gs://curated-bucket/tenant-1/file-1/doc-1.json",
            "mime_type": "application/pdf",
            "pii_redacted": False,
        },
    )
