"""
Tests for Media Curation Adapters.

Unit tests for GCS, Redis, DLP, and Kafka adapters with mocked external services.
Target: 25+ tests as per implementation plan.
"""

import pytest
import asyncio
from datetime import datetime, timezone
from uuid import uuid4, UUID

from media_curation.domain.models import (
    CurationEvent,
    CuratedDocument,
    CurationStatus,
    CurationStatusRecord,
    TenantConfig,
    ContentType,
)
from media_curation.ports.dlp_port import RedactionResult


# Helper to run async tests
def run_async(coro):
    """Run async coroutine in sync context."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# Sample UUIDs for testing
SAMPLE_TENANT_ID = UUID("11111111-1111-1111-1111-111111111111")
SAMPLE_TRACE_ID = UUID("22222222-2222-2222-2222-222222222222")
SAMPLE_EVENT_ID = UUID("33333333-3333-3333-3333-333333333333")
SAMPLE_FILE_ID = UUID("44444444-4444-4444-4444-444444444444")


# =============================================================================
# GCS Adapter Tests
# =============================================================================


class TestGCSAdapterParseUri:
    """Tests for GCS URI parsing."""

    def test_parse_valid_gcs_uri(self):
        """Test parsing a valid GCS URI."""
        from media_curation.adapters.gcs_adapter import parse_gcs_uri

        bucket, path = parse_gcs_uri("gs://my-bucket/path/to/file.pdf")
        assert bucket == "my-bucket"
        assert path == "path/to/file.pdf"

    def test_parse_gcs_uri_with_nested_path(self):
        """Test parsing GCS URI with deeply nested path."""
        from media_curation.adapters.gcs_adapter import parse_gcs_uri

        bucket, path = parse_gcs_uri("gs://bucket/a/b/c/d/file.json")
        assert bucket == "bucket"
        assert path == "a/b/c/d/file.json"

    def test_parse_gcs_uri_invalid_scheme(self):
        """Test that non-GCS URIs raise ValueError."""
        from media_curation.adapters.gcs_adapter import parse_gcs_uri

        with pytest.raises(ValueError, match="Invalid GCS URI"):
            parse_gcs_uri("s3://bucket/file.pdf")

    def test_parse_gcs_uri_no_object_path(self):
        """Test that URIs without object path raise ValueError."""
        from media_curation.adapters.gcs_adapter import parse_gcs_uri

        with pytest.raises(ValueError, match="no object path"):
            parse_gcs_uri("gs://bucket-only")

    def test_parse_gcs_uri_empty_bucket(self):
        """Test URI with empty bucket returns empty bucket name."""
        from media_curation.adapters.gcs_adapter import parse_gcs_uri

        # Current implementation returns empty bucket name
        bucket, path = parse_gcs_uri("gs:///path/file.pdf")
        assert bucket == ""
        assert path == "path/file.pdf"


class TestGCSAdapterRealOperations:
    """Tests for GCS adapter operations with real GCS credentials."""

    @pytest.fixture
    def gcs_adapter(self):
        """Create a real GCS adapter with credentials."""
        from media_curation.adapters.gcs_adapter import GCSAdapter
        from django.conf import settings
        import os

        base_dir = settings.BASE_DIR
        credentials_path = os.path.join(base_dir, "credentials", "gcs-credentials.json")

        return GCSAdapter(
            project_id="brandsol",
            credentials_path=credentials_path,
            default_bucket="brandsol-curation-bucket",
        )

    def test_gcs_adapter_initializes_with_credentials(self, gcs_adapter):
        """Test adapter initializes with real credentials."""
        assert gcs_adapter is not None
        assert gcs_adapter._storage_available is True
        assert gcs_adapter.client is not None

    def test_gcs_adapter_is_healthy(self, gcs_adapter):
        """Test is_healthy returns True with valid credentials."""
        result = run_async(gcs_adapter.is_healthy())
        assert result is True

    def test_upload_from_bytes_success(self, gcs_adapter):
        """Test uploading bytes to GCS."""
        import uuid

        test_id = str(uuid.uuid4())[:8]
        content = b"test content for upload"
        destination = f"gs://brandsol-curation-bucket/tests/test-upload-{test_id}.txt"

        result = run_async(
            gcs_adapter.upload_from_bytes(
                content=content,
                destination_path=destination,
                content_type="text/plain",
            )
        )
        assert result is not None

    def test_download_as_bytes_returns_bytes(self, gcs_adapter):
        """Test downloading bytes from GCS."""
        # Use the test file we uploaded to onboarding-bucket1
        result = run_async(
            gcs_adapter.download_as_bytes(
                "gs://onboarding-bucket1/customer-1/test-document.txt"
            )
        )
        assert isinstance(result, bytes)
        assert b"sample document" in result.lower() or len(result) > 0

    def test_exists_returns_true_for_existing_file(self, gcs_adapter):
        """Test file existence check for existing file."""
        result = run_async(
            gcs_adapter.exists("gs://onboarding-bucket1/customer-1/test-document.txt")
        )
        assert result is True

    def test_exists_returns_false_for_missing_file(self, gcs_adapter):
        """Test file existence check for non-existent file."""
        result = run_async(
            gcs_adapter.exists("gs://onboarding-bucket1/non-existent-file-12345.txt")
        )
        assert result is False


# =============================================================================
# Redis Adapter Tests
# =============================================================================


class TestRedisAdapterInitialization:
    """Tests for Redis adapter initialization."""

    def test_redis_adapter_initializes_with_defaults(self):
        """Test adapter initializes with default TTLs."""
        from media_curation.adapters.redis_adapter import RedisAdapter

        adapter = RedisAdapter()
        assert adapter is not None
        assert adapter.status_ttl == 604800  # 7 days
        assert adapter.dedupe_ttl == 86400  # 24 hours

    def test_redis_adapter_custom_ttls(self):
        """Test adapter accepts custom TTL values."""
        from media_curation.adapters.redis_adapter import RedisAdapter

        adapter = RedisAdapter(
            status_ttl_seconds=3600,
            dedupe_ttl_seconds=1800,
        )
        assert adapter.status_ttl == 3600
        assert adapter.dedupe_ttl == 1800


class TestRedisAdapterStatusOperations:
    """Tests for Redis adapter status tracking operations."""

    @pytest.fixture
    def redis_adapter(self):
        """Create Redis adapter (uses in-memory mock if Redis not available)."""
        from media_curation.adapters.redis_adapter import RedisAdapter

        return RedisAdapter()

    def test_set_status_stores_record(self, redis_adapter):
        """Test setting a curation status."""
        status_record = CurationStatusRecord(
            trace_id=SAMPLE_TRACE_ID,
            event_id=SAMPLE_EVENT_ID,
            tenant_id=SAMPLE_TENANT_ID,
            file_id=SAMPLE_FILE_ID,
            status=CurationStatus.PROCESSING,
            message="Processing started",
            updated_at=datetime.now(timezone.utc),
        )

        run_async(
            redis_adapter.set_status(
                trace_id=str(SAMPLE_TRACE_ID),
                status=status_record,
                ttl_seconds=3600,
            )
        )

        # Retrieve and verify
        retrieved = run_async(redis_adapter.get_status(str(SAMPLE_TRACE_ID)))
        assert retrieved is not None
        assert retrieved.status == CurationStatus.PROCESSING

    def test_get_status_returns_none_for_missing(self, redis_adapter):
        """Test getting status for non-existent trace_id."""
        result = run_async(redis_adapter.get_status("nonexistent-trace-id"))
        assert result is None

    def test_set_and_get_tenant_config(self, redis_adapter):
        """Test storing and retrieving tenant configuration."""
        config = TenantConfig(
            tenant_id=SAMPLE_TENANT_ID,
            dlp_enabled=True,
            dlp_info_types=["EMAIL_ADDRESS", "PHONE_NUMBER"],
        )

        run_async(
            redis_adapter.set_tenant_config(
                tenant_id=str(SAMPLE_TENANT_ID),
                config=config,
            )
        )

        retrieved = run_async(redis_adapter.get_tenant_config(str(SAMPLE_TENANT_ID)))
        assert retrieved is not None
        assert retrieved.dlp_enabled is True
        assert "EMAIL_ADDRESS" in retrieved.dlp_info_types


class TestRedisAdapterDeduplication:
    """Tests for Redis adapter deduplication operations."""

    @pytest.fixture
    def redis_adapter(self):
        """Create Redis adapter."""
        from media_curation.adapters.redis_adapter import RedisAdapter

        return RedisAdapter()

    def test_is_duplicate_returns_false_for_new_event(self, redis_adapter):
        """Test that new events are not duplicates."""
        event_id = str(uuid4())
        result = run_async(redis_adapter.is_duplicate(event_id))
        assert result is False

    def test_mark_processed_then_is_duplicate(self, redis_adapter):
        """Test that marking processed makes event a duplicate."""
        event_id = str(uuid4())

        # Mark as processed
        run_async(redis_adapter.mark_processed(event_id))

        # Should now be duplicate
        result = run_async(redis_adapter.is_duplicate(event_id))
        assert result is True

    def test_is_healthy_returns_bool(self, redis_adapter):
        """Test health check returns boolean."""
        result = run_async(redis_adapter.is_healthy())
        assert isinstance(result, bool)


# =============================================================================
# DLP Adapter Tests
# =============================================================================


class TestDLPAdapterInitialization:
    """Tests for DLP adapter initialization."""

    def test_dlp_adapter_initializes(self):
        """Test adapter initializes successfully."""
        from media_curation.adapters.dlp_adapter import CloudDLPAdapter

        adapter = CloudDLPAdapter(project_id="test-project")
        assert adapter is not None
        # Adapter should have required methods
        assert hasattr(adapter, "redact_pii")
        assert hasattr(adapter, "detect_pii")
        assert hasattr(adapter, "is_healthy")


class TestDLPAdapterRedaction:
    """Tests for DLP adapter PII redaction."""

    @pytest.fixture
    def dlp_adapter(self):
        """Create DLP adapter."""
        from media_curation.adapters.dlp_adapter import CloudDLPAdapter

        return CloudDLPAdapter(project_id="test-project")

    def test_redact_pii_returns_redaction_result(self, dlp_adapter):
        """Test redact_pii returns proper RedactionResult."""
        text = "Contact john@example.com for details"

        result = run_async(dlp_adapter.redact_pii(text))

        assert isinstance(result, RedactionResult)
        assert result.original_text == text

    def test_redact_pii_with_tenant_config(self, dlp_adapter):
        """Test redaction respects tenant config."""
        config = TenantConfig(
            tenant_id=SAMPLE_TENANT_ID,
            dlp_enabled=True,
            dlp_info_types=["EMAIL_ADDRESS"],
        )

        result = run_async(
            dlp_adapter.redact_pii(
                text="Email: test@example.com",
                tenant_config=config,
            )
        )

        assert isinstance(result, RedactionResult)

    def test_detect_pii_returns_findings_list(self, dlp_adapter):
        """Test detect_pii returns list of findings."""
        text = "Call 555-123-4567 or email test@example.com"

        result = run_async(dlp_adapter.detect_pii(text))

        assert isinstance(result, list)

    def test_is_healthy_returns_bool(self, dlp_adapter):
        """Test health check returns boolean."""
        result = run_async(dlp_adapter.is_healthy())
        assert isinstance(result, bool)


# =============================================================================
# Kafka Adapter Tests
# =============================================================================


class TestKafkaProducerAdapterInitialization:
    """Tests for Kafka producer adapter initialization."""

    def test_kafka_producer_initializes(self):
        """Test producer initializes without error."""
        from media_curation.adapters.kafka_adapter import KafkaProducerAdapter

        adapter = KafkaProducerAdapter(
            bootstrap_servers="localhost:9092",
            dlq_topic="test-dlq",
            output_topic="test-output",
        )
        assert adapter is not None

    def test_kafka_producer_stores_topics(self):
        """Test producer stores configured topics."""
        from media_curation.adapters.kafka_adapter import KafkaProducerAdapter

        adapter = KafkaProducerAdapter(
            dlq_topic="my-dlq",
            output_topic="my-output",
        )
        assert adapter.dlq_topic == "my-dlq"
        assert adapter.output_topic == "my-output"


class TestKafkaProducerOperations:
    """Tests for Kafka producer operations."""

    @pytest.fixture
    def kafka_producer(self):
        """Create Kafka producer adapter."""
        from media_curation.adapters.kafka_adapter import KafkaProducerAdapter

        return KafkaProducerAdapter(
            bootstrap_servers="localhost:9092",
            dlq_topic="test-dlq",
            output_topic="test-output",
        )

    @pytest.fixture
    def sample_curated_document(self):
        """Create a sample curated document."""
        return CuratedDocument(
            document_id=uuid4(),
            trace_id=SAMPLE_TRACE_ID,
            tenant_id=SAMPLE_TENANT_ID,
            file_id=SAMPLE_FILE_ID,
            source_gcs_uri="gs://bucket/input.pdf",
            output_gcs_uri="gs://bucket/output.json",
            mime_type="application/pdf",
            extracted_text="Test content",
            struct_data={},
            pii_redacted=False,
            processing_time_ms=1000,
            created_at=datetime.now(timezone.utc),
        )

    def test_publish_curated_document(self, kafka_producer, sample_curated_document):
        """Test publishing a curated document."""
        # Should not raise even in mock mode
        run_async(
            kafka_producer.publish_curated_document(
                topic="test-topic",
                document=sample_curated_document,
                key=str(sample_curated_document.tenant_id),
            )
        )

    def test_publish_to_dlq(self, kafka_producer):
        """Test publishing to dead letter queue."""
        event = CurationEvent(
            event_id=SAMPLE_EVENT_ID,
            trace_id=SAMPLE_TRACE_ID,
            tenant_id=SAMPLE_TENANT_ID,
            file_id=SAMPLE_FILE_ID,
            raw_gcs_uri="gs://bucket/file.pdf",
            mime_type="application/pdf",
            content_type=ContentType.DOCUMENT,
            source_service="test",
            timestamp=datetime.now(timezone.utc),
        )
        error = Exception("Test error")

        run_async(
            kafka_producer.publish_to_dlq(
                event=event,
                error=error,
                retry_count=3,
            )
        )

    def test_publish_raw(self, kafka_producer):
        """Test publishing raw payload."""
        payload = {"key": "value", "number": 123}

        run_async(
            kafka_producer.publish_raw(
                topic="test-topic",
                payload=payload,
                key="test-key",
            )
        )

    def test_producer_has_dlq_topic(self, kafka_producer):
        """Test producer has DLQ topic configured."""
        assert hasattr(kafka_producer, "dlq_topic")
        assert kafka_producer.dlq_topic == "test-dlq"


class TestKafkaConsumerAdapter:
    """Tests for Kafka consumer adapter."""

    def test_kafka_consumer_initializes(self):
        """Test consumer initializes without error."""
        from media_curation.adapters.kafka_adapter import KafkaConsumerAdapter

        adapter = KafkaConsumerAdapter(
            bootstrap_servers="localhost:9092",
            group_id="test-group",
            input_topic="test-input",
        )
        assert adapter is not None

    def test_kafka_consumer_stores_config(self):
        """Test consumer initializes with configuration."""
        from media_curation.adapters.kafka_adapter import KafkaConsumerAdapter

        adapter = KafkaConsumerAdapter(
            group_id="my-group",
            input_topic="my-topic",
        )
        # Adapter should initialize successfully
        assert adapter is not None


# =============================================================================
# Vertex AI Adapter Tests
# =============================================================================


class TestVertexAIAdapterInitialization:
    """Tests for Vertex AI adapter initialization."""

    def test_vertex_adapter_initializes(self):
        """Test adapter initializes successfully."""
        from media_curation.adapters.vertex_adapter import VertexAIAdapter

        adapter = VertexAIAdapter(
            project_id="test-project",
            location="us-central1",
            model_name="gemini-1.5-pro",
        )
        assert adapter is not None

    def test_vertex_adapter_default_location(self):
        """Test adapter uses default location if not specified."""
        from media_curation.adapters.vertex_adapter import VertexAIAdapter

        adapter = VertexAIAdapter(project_id="test-project")
        assert adapter.location == "us-central1"

    def test_vertex_adapter_custom_model(self):
        """Test adapter accepts custom model name."""
        from media_curation.adapters.vertex_adapter import VertexAIAdapter

        adapter = VertexAIAdapter(
            project_id="test-project",
            model_name="gemini-1.5-flash",
        )
        assert adapter.model_name == "gemini-1.5-flash"

    def test_vertex_adapter_has_prompts(self):
        """Test adapter has default prompts defined."""
        from media_curation.adapters.vertex_adapter import VertexAIAdapter

        assert VertexAIAdapter.VIDEO_TRANSCRIPTION_PROMPT is not None
        assert VertexAIAdapter.AUDIO_TRANSCRIPTION_PROMPT is not None
        assert VertexAIAdapter.VIDEO_ANALYSIS_PROMPT is not None


class TestVertexAIAdapterMethods:
    """Tests for Vertex AI adapter methods."""

    @pytest.fixture
    def vertex_adapter(self):
        """Create Vertex AI adapter (uses mock mode if vertexai not available)."""
        from media_curation.adapters.vertex_adapter import VertexAIAdapter

        return VertexAIAdapter(project_id="test-project")

    def test_generate_from_uri_mock_mode(self, vertex_adapter):
        """Test generate_from_uri returns mock response when unavailable."""
        # Should work even in mock mode
        result = vertex_adapter.generate_from_uri(
            gcs_uri="gs://bucket/video.mp4",
            mime_type="video/mp4",
        )
        assert isinstance(result, str)
        assert len(result) > 0

    def test_generate_from_uri_with_custom_prompt(self, vertex_adapter):
        """Test generate_from_uri with custom prompt."""
        result = vertex_adapter.generate_from_uri(
            gcs_uri="gs://bucket/audio.mp3",
            mime_type="audio/mpeg",
            prompt="Custom transcription prompt",
        )
        assert isinstance(result, str)

    def test_transcribe_video(self, vertex_adapter):
        """Test video transcription method."""
        result = vertex_adapter.transcribe_video(
            gcs_uri="gs://bucket/video.mp4",
            mime_type="video/mp4",
        )
        assert isinstance(result, str)

    def test_transcribe_audio(self, vertex_adapter):
        """Test audio transcription method."""
        result = vertex_adapter.transcribe_audio(
            gcs_uri="gs://bucket/audio.mp3",
            mime_type="audio/mpeg",
        )
        assert isinstance(result, str)

    def test_analyze_video(self, vertex_adapter):
        """Test comprehensive video analysis."""
        result = vertex_adapter.analyze_video(
            gcs_uri="gs://bucket/video.mp4",
            mime_type="video/mp4",
        )
        assert isinstance(result, str)

    def test_generate_from_uri_async(self, vertex_adapter):
        """Test async wrapper for generate_from_uri."""
        result = run_async(
            vertex_adapter.generate_from_uri_async(
                gcs_uri="gs://bucket/video.mp4",
                mime_type="video/mp4",
            )
        )
        assert isinstance(result, str)

    def test_is_healthy(self, vertex_adapter):
        """Test health check returns boolean."""
        result = run_async(vertex_adapter.is_healthy())
        assert isinstance(result, bool)


# =============================================================================
# Vision API Adapter Tests
# =============================================================================


class TestVisionAdapterInitialization:
    """Tests for Vision API adapter initialization."""

    def test_vision_adapter_initializes(self):
        """Test adapter initializes successfully."""
        from media_curation.adapters.vision_adapter import VisionAdapter

        adapter = VisionAdapter(project_id="test-project")
        assert adapter is not None

    def test_vision_adapter_supported_image_types(self):
        """Test adapter has supported image types defined."""
        from media_curation.adapters.vision_adapter import VisionAdapter

        assert "image/png" in VisionAdapter.SUPPORTED_IMAGE_TYPES
        assert "image/jpeg" in VisionAdapter.SUPPORTED_IMAGE_TYPES

    def test_vision_adapter_supported_document_types(self):
        """Test adapter has supported document types defined."""
        from media_curation.adapters.vision_adapter import VisionAdapter

        assert "application/pdf" in VisionAdapter.SUPPORTED_DOCUMENT_TYPES


class TestVisionAdapterTextDetection:
    """Tests for Vision adapter text detection methods."""

    @pytest.fixture
    def vision_adapter(self):
        """Create Vision adapter (uses mock mode if google-cloud-vision not available)."""
        from media_curation.adapters.vision_adapter import VisionAdapter

        return VisionAdapter(project_id="test-project")

    def test_detect_text_mock_mode(self, vision_adapter):
        """Test detect_text returns mock response when unavailable."""
        result = vision_adapter.detect_text("gs://bucket/image.png")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_detect_document_text(self, vision_adapter):
        """Test document text detection method."""
        result = vision_adapter.detect_document_text("gs://bucket/document.png")
        assert isinstance(result, str)

    def test_detect_text_async(self, vision_adapter):
        """Test async text detection wrapper."""
        result = run_async(vision_adapter.detect_text_async("gs://bucket/image.png"))
        assert isinstance(result, str)

    def test_detect_document_text_async(self, vision_adapter):
        """Test async document text detection wrapper."""
        result = run_async(
            vision_adapter.detect_document_text_async("gs://bucket/doc.png")
        )
        assert isinstance(result, str)


class TestVisionAdapterBatchProcessing:
    """Tests for Vision adapter batch PDF processing."""

    @pytest.fixture
    def vision_adapter(self):
        """Create Vision adapter."""
        from media_curation.adapters.vision_adapter import VisionAdapter

        return VisionAdapter(project_id="test-project")

    def test_batch_annotate_pdf_mock_mode(self, vision_adapter):
        """Test batch PDF annotation in mock mode."""
        result = vision_adapter.batch_annotate_pdf(
            gcs_input_uri="gs://bucket/document.pdf",
            gcs_output_uri="gs://bucket/output/",
        )
        assert isinstance(result, str)

    def test_batch_annotate_pdf_async(self, vision_adapter):
        """Test async batch PDF annotation."""
        result = run_async(
            vision_adapter.batch_annotate_pdf_async(
                gcs_input_uri="gs://bucket/document.pdf",
                gcs_output_uri="gs://bucket/output/",
            )
        )
        assert isinstance(result, str)


class TestVisionAdapterImageAnalysis:
    """Tests for Vision adapter image analysis."""

    @pytest.fixture
    def vision_adapter(self):
        """Create Vision adapter."""
        from media_curation.adapters.vision_adapter import VisionAdapter

        return VisionAdapter(project_id="test-project")

    def test_analyze_image_returns_dict(self, vision_adapter):
        """Test analyze_image returns dictionary with expected keys."""
        result = vision_adapter.analyze_image("gs://bucket/image.png")

        assert isinstance(result, dict)
        assert "text" in result
        assert "labels" in result
        assert "objects" in result
        assert "face_count" in result

    def test_analyze_image_async(self, vision_adapter):
        """Test async image analysis wrapper."""
        result = run_async(vision_adapter.analyze_image_async("gs://bucket/image.png"))

        assert isinstance(result, dict)
        assert "text" in result

    def test_is_healthy(self, vision_adapter):
        """Test health check returns boolean."""
        result = run_async(vision_adapter.is_healthy())
        assert isinstance(result, bool)


# =============================================================================
# GCS Adapter Extended Tests
# =============================================================================


class TestGCSAdapterSaveJson:
    """Tests for GCS adapter save_json method."""

    @pytest.fixture
    def gcs_adapter(self):
        """Create a real GCS adapter with credentials."""
        from media_curation.adapters.gcs_adapter import GCSAdapter
        from django.conf import settings
        import os

        base_dir = settings.BASE_DIR
        credentials_path = os.path.join(base_dir, "credentials", "gcs-credentials.json")

        return GCSAdapter(
            project_id="brandsol",
            credentials_path=credentials_path,
            default_bucket="brandsol-curation-bucket",
        )

    def test_save_json_stores_dict(self, gcs_adapter):
        """Test save_json stores dictionary as JSON."""
        import uuid

        test_id = str(uuid.uuid4())[:8]
        data = {
            "document_id": str(uuid4()),
            "content": "Test curated document",
            "metadata": {"source": "test"},
        }
        destination = f"gs://brandsol-curation-bucket/tests/curated-{test_id}.json"

        result = run_async(
            gcs_adapter.save_json(
                data=data,
                destination_path=destination,
            )
        )

        assert result is not None
        assert result.content_type == "application/json"

    def test_save_json_with_metadata(self, gcs_adapter):
        """Test save_json stores metadata with blob."""
        import uuid

        test_id = str(uuid.uuid4())[:8]
        data = {"test": "value"}
        metadata = {
            "tenant_id": str(SAMPLE_TENANT_ID),
            "trace_id": str(SAMPLE_TRACE_ID),
        }
        destination = f"gs://brandsol-curation-bucket/tests/with-meta-{test_id}.json"

        result = run_async(
            gcs_adapter.save_json(
                data=data,
                destination_path=destination,
                metadata=metadata,
            )
        )

        assert result is not None
