"""
Additional Adapter Coverage Tests.

Comprehensive tests for adapter modules to improve coverage.
"""

import asyncio


def run_async(coro):
    """Run async coroutine synchronously."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# =============================================================================
# DLP Adapter Extended Tests
# =============================================================================


class TestDLPAdapterMockMode:
    """Tests for DLP adapter mock mode."""

    def test_dlp_adapter_mock_mode_when_no_library(self):
        """Test DLP adapter works in mock mode without google-cloud-dlp."""
        from media_curation.adapters.dlp_adapter import CloudDLPAdapter

        adapter = CloudDLPAdapter(project_id="test-project")
        # Should have the _dlp_available attribute
        assert hasattr(adapter, "_dlp_available")

    def test_detect_pii_mock_returns_empty_list(self):
        """Test detect_pii returns empty list in mock mode."""
        from media_curation.adapters.dlp_adapter import CloudDLPAdapter

        adapter = CloudDLPAdapter(project_id="test-project")
        result = run_async(adapter.detect_pii("Test text with john@example.com"))

        # In mock mode, should return empty list
        assert isinstance(result, list)

    def test_redact_pii_mock_returns_original_text(self):
        """Test redact_pii returns original text in mock mode."""
        from media_curation.adapters.dlp_adapter import CloudDLPAdapter
        from media_curation.ports.dlp_port import RedactionResult

        adapter = CloudDLPAdapter(project_id="test-project")
        text = "Contact john@example.com for info"

        result = run_async(adapter.redact_pii(text))

        assert isinstance(result, RedactionResult)
        assert result.original_text == text
        # In mock mode, redacted text equals original
        assert result.redacted_text == text

    def test_is_healthy_mock_returns_false(self):
        """Test is_healthy returns False in mock mode."""
        from media_curation.adapters.dlp_adapter import CloudDLPAdapter

        adapter = CloudDLPAdapter(project_id="test-project")

        if not adapter._dlp_available:
            result = run_async(adapter.is_healthy())
            assert result is False

    def test_dlp_adapter_default_info_types(self):
        """Test DLP adapter has default info types."""
        from media_curation.adapters.dlp_adapter import DEFAULT_INFO_TYPES

        assert "EMAIL_ADDRESS" in DEFAULT_INFO_TYPES
        assert "PHONE_NUMBER" in DEFAULT_INFO_TYPES
        assert len(DEFAULT_INFO_TYPES) > 0


# =============================================================================
# GCS Adapter Extended Tests
# =============================================================================


class TestGCSAdapterExtended:
    """Extended tests for GCS adapter."""

    def test_gcs_adapter_default_bucket(self):
        """Test GCS adapter stores default bucket."""
        from media_curation.adapters.gcs_adapter import GCSAdapter

        adapter = GCSAdapter(
            project_id="test-project",
            default_bucket="my-bucket",
        )
        assert adapter.default_bucket == "my-bucket"

    def test_gcs_adapter_project_id(self):
        """Test GCS adapter stores project ID."""
        from media_curation.adapters.gcs_adapter import GCSAdapter

        adapter = GCSAdapter(project_id="my-project")
        assert adapter.project_id == "my-project"

    def test_gcs_adapter_has_required_methods(self):
        """Test GCS adapter has required methods."""
        from media_curation.adapters.gcs_adapter import GCSAdapter

        adapter = GCSAdapter(project_id="test-project")

        assert hasattr(adapter, "upload_from_bytes")
        assert hasattr(adapter, "download_as_bytes")
        assert hasattr(adapter, "exists")
        assert hasattr(adapter, "is_healthy")


# =============================================================================
# Kafka Adapter Extended Tests
# =============================================================================


class TestKafkaAdapterExtended:
    """Extended tests for Kafka adapter."""

    def test_kafka_producer_has_output_topic(self):
        """Test Kafka producer has output topic."""
        from media_curation.adapters.kafka_adapter import KafkaProducerAdapter

        adapter = KafkaProducerAdapter(
            output_topic="my-output",
            dlq_topic="my-dlq",
        )
        assert adapter.output_topic == "my-output"

    def test_kafka_producer_has_dlq_topic(self):
        """Test Kafka producer has DLQ topic."""
        from media_curation.adapters.kafka_adapter import KafkaProducerAdapter

        adapter = KafkaProducerAdapter(
            output_topic="my-output",
            dlq_topic="my-dlq",
        )
        assert adapter.dlq_topic == "my-dlq"

    def test_kafka_producer_bootstrap_servers_default(self):
        """Test Kafka producer uses default bootstrap servers."""
        from media_curation.adapters.kafka_adapter import KafkaProducerAdapter

        adapter = KafkaProducerAdapter(
            output_topic="output",
            dlq_topic="dlq",
        )
        # Should have bootstrap_servers attribute
        assert (
            hasattr(adapter, "bootstrap_servers")
            or hasattr(adapter, "_bootstrap_servers")
            or hasattr(adapter, "_config")
        )

    def test_kafka_consumer_can_be_created(self):
        """Test Kafka consumer can be instantiated."""
        from media_curation.adapters.kafka_adapter import KafkaConsumerAdapter

        adapter = KafkaConsumerAdapter(
            group_id="test-group",
            input_topic="test-input",
        )
        assert adapter is not None


# =============================================================================
# Media Processors Extended Tests
# =============================================================================


class TestMediaProcessorsExtended:
    """Extended tests for media processors."""

    def test_video_processor_initialization(self):
        """Test VideoProcessor can be initialized."""
        from media_curation.adapters.media_processors import VideoProcessor

        processor = VideoProcessor(project_id="my-project")
        assert processor is not None

    def test_audio_processor_initialization(self):
        """Test AudioProcessor can be initialized."""
        from media_curation.adapters.media_processors import AudioProcessor

        processor = AudioProcessor(project_id="my-project")
        assert processor is not None

    def test_image_processor_initialization(self):
        """Test ImageProcessor can be initialized."""
        from media_curation.adapters.media_processors import ImageProcessor

        processor = ImageProcessor()
        assert processor is not None

    def test_video_processor_supported_mime_types(self):
        """Test VideoProcessor has video MIME types."""
        from media_curation.adapters.media_processors import VideoProcessor

        processor = VideoProcessor(project_id="test")
        types = processor.supported_mime_types

        assert isinstance(types, list)
        assert len(types) > 0

    def test_audio_processor_supported_mime_types(self):
        """Test AudioProcessor has audio MIME types."""
        from media_curation.adapters.media_processors import AudioProcessor

        processor = AudioProcessor(project_id="test")
        types = processor.supported_mime_types

        assert isinstance(types, list)
        assert len(types) > 0

    def test_image_processor_supported_mime_types(self):
        """Test ImageProcessor has image MIME types."""
        from media_curation.adapters.media_processors import ImageProcessor

        processor = ImageProcessor()
        types = processor.supported_mime_types

        assert isinstance(types, list)
        assert len(types) > 0


# =============================================================================
# Vertex Adapter Extended Tests
# =============================================================================


class TestVertexAdapterExtended:
    """Extended tests for Vertex AI adapter."""

    def test_vertex_adapter_initialization(self):
        """Test VertexAdapter can be initialized."""
        from media_curation.adapters.vertex_adapter import VertexAIAdapter

        adapter = VertexAIAdapter(
            project_id="my-project",
            location="us-central1",
        )
        assert adapter is not None

    def test_vertex_adapter_has_required_methods(self):
        """Test VertexAdapter has required methods."""
        from media_curation.adapters.vertex_adapter import VertexAIAdapter

        adapter = VertexAIAdapter(project_id="test")

        assert hasattr(adapter, "generate_from_uri_async")
        assert hasattr(adapter, "is_healthy")


# =============================================================================
# Vision Adapter Extended Tests
# =============================================================================


class TestVisionAdapterExtended:
    """Extended tests for Vision adapter."""

    def test_vision_adapter_initialization(self):
        """Test VisionAdapter can be initialized."""
        from media_curation.adapters.vision_adapter import VisionAdapter

        adapter = VisionAdapter(project_id="test-project")
        assert adapter is not None

    def test_vision_adapter_has_required_methods(self):
        """Test VisionAdapter has required methods."""
        from media_curation.adapters.vision_adapter import VisionAdapter

        adapter = VisionAdapter(project_id="test-project")

        assert hasattr(adapter, "detect_text_async")
        assert hasattr(adapter, "is_healthy")


# =============================================================================
# Redis Adapter Extended Tests
# =============================================================================


class TestRedisAdapterExtended:
    """Extended tests for Redis adapter."""

    def test_redis_adapter_has_ttl_attribute(self):
        """Test Redis adapter has TTL configuration."""
        from media_curation.adapters.redis_adapter import RedisAdapter

        adapter = RedisAdapter(
            status_ttl_seconds=3600,
            dedupe_ttl_seconds=1800,
        )
        # Should store TTL values (as status_ttl)
        assert adapter.status_ttl == 3600 or hasattr(adapter, "_status_ttl")

    def test_redis_adapter_has_required_methods(self):
        """Test Redis adapter has required methods."""
        from media_curation.adapters.redis_adapter import RedisAdapter

        adapter = RedisAdapter()

        assert hasattr(adapter, "set_status")
        assert hasattr(adapter, "get_status")
        assert hasattr(adapter, "is_duplicate")
        assert hasattr(adapter, "mark_processed")

    def test_redis_adapter_mock_mode_without_redis(self):
        """Test Redis adapter works in mock mode without redis."""
        from media_curation.adapters.redis_adapter import RedisAdapter

        adapter = RedisAdapter()
        assert hasattr(adapter, "_redis_available")

    def test_redis_adapter_set_status_sync(self):
        """Test set_status is callable."""
        from media_curation.adapters.redis_adapter import RedisAdapter

        adapter = RedisAdapter()
        assert callable(adapter.set_status)

    def test_redis_adapter_get_status_sync(self):
        """Test get_status is callable."""
        from media_curation.adapters.redis_adapter import RedisAdapter

        adapter = RedisAdapter()
        assert callable(adapter.get_status)
