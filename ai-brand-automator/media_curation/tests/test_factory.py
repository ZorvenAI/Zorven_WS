"""
Factory Module Tests.

Comprehensive tests for the media_curation.factory module.
"""

import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

from media_curation.domain.models import ContentType


def run_async(coro):
    """Run async coroutine synchronously."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TestGetMediaCurationConfig:
    """Tests for get_media_curation_config function."""

    def test_returns_defaults_when_no_settings(self):
        """Test default config when MEDIA_CURATION not in settings."""
        from media_curation.factory import get_media_curation_config

        with patch("media_curation.factory.settings") as mock_settings:
            mock_settings.MEDIA_CURATION = {}

            config = get_media_curation_config()

            assert "GCP_PROJECT_ID" in config
            assert "KAFKA" in config
            assert "REDIS" in config
            assert "PROCESSING" in config

    def test_merges_custom_settings(self):
        """Test config merges custom settings with defaults."""
        from media_curation.factory import get_media_curation_config

        with patch("media_curation.factory.settings") as mock_settings:
            mock_settings.MEDIA_CURATION = {
                "GCP_PROJECT_ID": "custom-project",
                "KAFKA": {"BOOTSTRAP_SERVERS": "custom-kafka:9092"},
            }

            config = get_media_curation_config()

            assert config["GCP_PROJECT_ID"] == "custom-project"
            assert config["KAFKA"]["BOOTSTRAP_SERVERS"] == "custom-kafka:9092"
            # Default keys should still exist
            assert "INPUT_TOPIC" in config["KAFKA"]


class TestProcessorFactory:
    """Tests for ProcessorFactory class."""

    def test_register_processor(self):
        """Test processor registration."""
        from media_curation.factory import ProcessorFactory

        mock_processor = MagicMock()
        mock_processor.content_type = ContentType.DOCUMENT
        mock_processor.name = "test-processor"
        mock_processor.supported_mime_types = ["application/pdf"]

        factory = ProcessorFactory()
        factory.register(mock_processor)

        assert ContentType.DOCUMENT in factory._processors
        assert factory._processors[ContentType.DOCUMENT] == mock_processor

    def test_get_processor_by_mime_type(self):
        """Test getting processor by MIME type."""
        from media_curation.factory import ProcessorFactory

        mock_processor = MagicMock()
        mock_processor.content_type = ContentType.DOCUMENT
        mock_processor.supports = MagicMock(return_value=True)

        factory = ProcessorFactory()
        factory.register(mock_processor)

        result = factory.get_processor("application/pdf")
        assert result == mock_processor

    def test_get_processor_returns_none_for_unknown(self):
        """Test returns None for unknown MIME type."""
        from media_curation.factory import ProcessorFactory

        factory = ProcessorFactory()
        result = factory.get_processor("application/unknown")

        assert result is None

    def test_get_processor_for_content_type(self):
        """Test getting processor by content type."""
        from media_curation.factory import ProcessorFactory

        mock_processor = MagicMock()
        mock_processor.content_type = ContentType.VIDEO

        factory = ProcessorFactory()
        factory.register(mock_processor)

        result = factory.get_processor_for_content_type(ContentType.VIDEO)
        assert result == mock_processor

    def test_initialize_all_processors(self):
        """Test initializing all processors."""
        from media_curation.factory import ProcessorFactory

        mock_processor = MagicMock()
        mock_processor.content_type = ContentType.DOCUMENT
        mock_processor.initialize = AsyncMock()
        mock_processor.name = "test"

        factory = ProcessorFactory()
        factory.register(mock_processor)

        run_async(factory.initialize_all())

        mock_processor.initialize.assert_called_once()
        assert factory._initialized is True

    def test_initialize_all_idempotent(self):
        """Test initialize_all only runs once."""
        from media_curation.factory import ProcessorFactory

        mock_processor = MagicMock()
        mock_processor.content_type = ContentType.DOCUMENT
        mock_processor.initialize = AsyncMock()
        mock_processor.name = "test"

        factory = ProcessorFactory()
        factory.register(mock_processor)

        run_async(factory.initialize_all())
        run_async(factory.initialize_all())  # Second call

        # Should only be called once
        assert mock_processor.initialize.call_count == 1

    def test_cleanup_all_processors(self):
        """Test cleaning up all processors."""
        from media_curation.factory import ProcessorFactory

        mock_processor = MagicMock()
        mock_processor.content_type = ContentType.DOCUMENT
        mock_processor.cleanup = AsyncMock()

        factory = ProcessorFactory()
        factory.register(mock_processor)
        factory._initialized = True

        run_async(factory.cleanup_all())

        mock_processor.cleanup.assert_called_once()
        assert factory._initialized is False


class TestCreateProcessorFactory:
    """Tests for create_processor_factory function."""

    def test_creates_factory_with_default_config(self):
        """Test factory creation with default config."""
        from media_curation.factory import create_processor_factory

        with patch("media_curation.factory.create_storage_adapter") as mock_storage:
            mock_storage.return_value = MagicMock()

            factory = create_processor_factory()

            assert factory is not None
            mock_storage.assert_called_once()

    def test_creates_factory_with_custom_config(self):
        """Test factory creation with custom config."""
        from media_curation.factory import create_processor_factory

        custom_config = {"GCP_PROJECT_ID": "test-project"}

        with patch("media_curation.factory.create_storage_adapter") as mock_storage:
            mock_storage.return_value = MagicMock()

            factory = create_processor_factory(config=custom_config)

            assert factory is not None


class TestCreateCacheAdapter:
    """Tests for create_cache_adapter function."""

    def test_creates_redis_adapter(self):
        """Test Redis adapter creation."""
        from media_curation.factory import create_cache_adapter

        adapter = create_cache_adapter()

        assert adapter is not None
        assert hasattr(adapter, "set_status")
        assert hasattr(adapter, "get_status")

    def test_uses_custom_config(self):
        """Test uses custom Redis config."""
        from media_curation.factory import create_cache_adapter

        custom_config = {
            "REDIS": {
                "URL": "redis://custom-host:6380/1",
                "STATUS_TTL_SECONDS": 3600,
            }
        }

        adapter = create_cache_adapter(config=custom_config)
        assert adapter is not None


class TestCreateStorageAdapter:
    """Tests for create_storage_adapter function."""

    def test_creates_gcs_adapter(self):
        """Test GCS adapter creation."""
        from media_curation.factory import create_storage_adapter

        adapter = create_storage_adapter()

        assert adapter is not None
        assert hasattr(adapter, "upload_from_bytes")
        assert hasattr(adapter, "download_as_bytes")


class TestCreateKafkaProducer:
    """Tests for create_kafka_producer function."""

    def test_creates_kafka_producer(self):
        """Test Kafka producer creation."""
        from media_curation.factory import create_kafka_producer

        adapter = create_kafka_producer()

        assert adapter is not None
        assert hasattr(adapter, "publish_raw")

    def test_uses_custom_topics(self):
        """Test uses custom Kafka topics."""
        from media_curation.factory import create_kafka_producer

        custom_config = {
            "KAFKA": {
                "DLQ_TOPIC": "custom-dlq",
                "OUTPUT_TOPIC": "custom-output",
            }
        }

        adapter = create_kafka_producer(config=custom_config)
        assert adapter.dlq_topic == "custom-dlq"
        assert adapter.output_topic == "custom-output"


class TestCreateKafkaConsumer:
    """Tests for create_kafka_consumer function."""

    def test_creates_kafka_consumer(self):
        """Test Kafka consumer creation."""
        from media_curation.factory import create_kafka_consumer

        adapter = create_kafka_consumer()

        assert adapter is not None


class TestCreateDLPAdapter:
    """Tests for create_dlp_adapter function."""

    def test_creates_dlp_adapter(self):
        """Test DLP adapter creation."""
        from media_curation.factory import create_dlp_adapter

        adapter = create_dlp_adapter()

        assert adapter is not None

    def test_returns_none_when_disabled(self):
        """Test returns None when DLP is disabled."""
        from media_curation.factory import create_dlp_adapter

        config = {"DLP": {"ENABLED": False}}
        adapter = create_dlp_adapter(config=config)

        assert adapter is None


class TestCreateCurationService:
    """Tests for create_curation_service function."""

    def test_creates_curation_service(self):
        """Test CurationService creation."""
        from media_curation.factory import create_curation_service

        with patch("media_curation.factory.create_processor_factory") as mock_pf:
            with patch("media_curation.factory.create_cache_adapter") as mock_cache:
                with patch(
                    "media_curation.factory.create_storage_adapter"
                ) as mock_storage:
                    with patch(
                        "media_curation.factory.create_kafka_producer"
                    ) as mock_kafka:
                        with patch(
                            "media_curation.factory.create_dlp_adapter"
                        ) as mock_dlp:
                            mock_pf.return_value = MagicMock()
                            mock_cache.return_value = MagicMock()
                            mock_storage.return_value = MagicMock()
                            mock_kafka.return_value = MagicMock()
                            mock_dlp.return_value = MagicMock()

                            service = create_curation_service()

                            assert service is not None


class TestGetCurationService:
    """Tests for get_curation_service singleton function."""

    def test_returns_same_instance(self):
        """Test returns singleton instance."""
        from media_curation import factory

        # Reset singleton
        factory._curation_service = None

        with patch.object(factory, "create_curation_service") as mock_create:
            mock_service = MagicMock()
            mock_create.return_value = mock_service

            service1 = factory.get_curation_service()
            service2 = factory.get_curation_service()

            assert service1 is service2
            mock_create.assert_called_once()

        # Reset for other tests
        factory._curation_service = None

    def test_creates_new_instance_when_none(self):
        """Test creates new instance when singleton is None."""
        from media_curation import factory

        # Reset singleton
        factory._curation_service = None

        with patch.object(factory, "create_curation_service") as mock_create:
            mock_service = MagicMock()
            mock_create.return_value = mock_service

            service = factory.get_curation_service()

            assert service is mock_service
            mock_create.assert_called_once()

        # Reset for other tests
        factory._curation_service = None
