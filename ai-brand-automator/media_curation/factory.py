"""
Media Curation Factory.

Dependency injection and service creation for the curation pipeline.
Creates and configures all adapters and services.
"""

import logging
from typing import Optional

from django.conf import settings

from media_curation.domain.models import ContentType
from media_curation.processors.base import BaseProcessor


logger = logging.getLogger(__name__)


def get_media_curation_config() -> dict:
    """
    Get media curation configuration from Django settings.

    Returns:
        Configuration dictionary with defaults
    """
    defaults = {
        "GCP_PROJECT_ID": "brandsol",
        "VERTEX_MODEL_NAME": "gemini-1.5-pro",
        "VERTEX_LOCATION": "us-central1",
        "VISION_ENABLED": True,
        "DLP_ENABLED": True,
        "KAFKA": {
            "INPUT_TOPIC": "curation-needed-topic",
            "OUTPUT_TOPIC": "rag-sync-ready-topic",
            "DLQ_TOPIC": "curation-dlq",
            "CONSUMER_GROUP": "media-curation-consumers",
            "BOOTSTRAP_SERVERS": "kafka:9092",
        },
        "REDIS": {
            "STATUS_TTL_SECONDS": 604800,  # 7 days
            "CONFIG_KEY_PREFIX": "config:tenant:",
            "STATUS_KEY_PREFIX": "curation:status:",
            "DEDUPE_KEY_PREFIX": "curation:dedupe:",
            "URL": "redis://redis:6379/0",
        },
        "PROCESSING": {
            "MAX_RETRIES": 3,
            "RETRY_BACKOFF_SECONDS": 2.0,
            "TIMEOUT_SECONDS": 300,
        },
    }

    config = getattr(settings, "MEDIA_CURATION", {})

    # Deep merge with defaults
    result = defaults.copy()
    for key, value in config.items():
        if isinstance(value, dict) and key in result:
            result[key] = {**result[key], **value}
        else:
            result[key] = value

    return result


class ProcessorFactory:
    """
    Factory for creating content processors (Strategy pattern).

    Routes content to the appropriate processor based on MIME type.
    """

    def __init__(self):
        """Initialize the processor registry."""
        self._processors: dict[ContentType, BaseProcessor] = {}
        self._initialized = False

    def register(self, processor: BaseProcessor) -> None:
        """
        Register a processor for its content type.

        Args:
            processor: Processor instance to register
        """
        self._processors[processor.content_type] = processor
        logger.debug(
            "Registered processor",
            extra={
                "processor": processor.name,
                "content_type": processor.content_type.value,
                "mime_types": processor.supported_mime_types,
            },
        )

    def get_processor(self, mime_type: str) -> Optional[BaseProcessor]:
        """
        Get the appropriate processor for a MIME type.

        Args:
            mime_type: The MIME type (e.g., "video/mp4")

        Returns:
            Matching processor or None
        """
        for processor in self._processors.values():
            if processor.supports(mime_type):
                return processor
        return None

    def get_processor_for_content_type(
        self,
        content_type: ContentType,
    ) -> Optional[BaseProcessor]:
        """
        Get processor by content type directly.

        Args:
            content_type: The ContentType enum value

        Returns:
            Matching processor or None
        """
        return self._processors.get(content_type)

    async def initialize_all(self) -> None:
        """Initialize all registered processors."""
        if self._initialized:
            return

        for processor in self._processors.values():
            await processor.initialize()

        self._initialized = True
        logger.info(
            "Initialized %d processors" % len(self._processors),
            extra={"processors": list(p.name for p in self._processors.values())},
        )

    async def cleanup_all(self) -> None:
        """Cleanup all registered processors."""
        for processor in self._processors.values():
            await processor.cleanup()
        self._initialized = False


def create_processor_factory(
    config: Optional[dict] = None, tenant=None
) -> ProcessorFactory:
    """
    Create and configure a ProcessorFactory with all processors.

    Args:
        config: Optional configuration override
        tenant: Optional Tenant instance for per-tenant bucket resolution

    Returns:
        Configured ProcessorFactory
    """
    from media_curation.domain.services import (
        ProcessorFactory as DomainProcessorFactory,
    )
    from media_curation.adapters import (
        DocumentProcessor,
        VideoProcessor,
        AudioProcessor,
        ImageProcessor,
    )

    config = config or get_media_curation_config()

    # Create storage adapter for processors that need file access
    storage = create_storage_adapter(config, tenant=tenant)

    # Create processors
    processors = [
        DocumentProcessor(storage=storage),
        VideoProcessor(project_id=config.get("GCP_PROJECT_ID")),
        AudioProcessor(project_id=config.get("GCP_PROJECT_ID")),
        ImageProcessor(),
    ]

    factory = DomainProcessorFactory(processors=processors)
    logger.info(
        "ProcessorFactory created",
        extra={"processor_count": len(processors)},
    )

    return factory


def create_cache_adapter(config: Optional[dict] = None):
    """
    Create Redis cache adapter.

    Args:
        config: Optional configuration override

    Returns:
        CachePort implementation
    """
    from media_curation.adapters import RedisAdapter

    config = config or get_media_curation_config()
    redis_config = config.get("REDIS", {})

    adapter = RedisAdapter(
        redis_url=redis_config.get("URL", "redis://localhost:6379/0"),
        status_ttl_seconds=redis_config.get("STATUS_TTL_SECONDS", 604800),
        dedupe_ttl_seconds=redis_config.get("DEDUPE_TTL_SECONDS", 86400),
    )

    logger.info("Cache adapter created")
    return adapter


def create_storage_adapter(config: Optional[dict] = None, tenant=None):
    """
    Create GCS storage adapter.

    Args:
        config: Optional configuration override
        tenant: Optional Tenant instance for per-tenant bucket resolution

    Returns:
        StoragePort implementation
    """
    from media_curation.adapters import GCSAdapter

    config = config or get_media_curation_config()
    storage_config = config.get("STORAGE", {})

    # Resolve bucket: per-tenant curated bucket takes priority
    if tenant is not None and hasattr(tenant, "get_curated_bucket"):
        default_bucket = tenant.get_curated_bucket()
    else:
        default_bucket = storage_config.get(
            "CURATED_BUCKET", "brandsol-curation-bucket"
        )

    adapter = GCSAdapter(
        project_id=storage_config.get("GCP_PROJECT_ID", config.get("GCP_PROJECT_ID")),
        default_bucket=default_bucket,
        credentials_path=storage_config.get("CREDENTIALS_PATH"),
    )

    logger.info(
        "Storage adapter created",
        extra={
            "project_id": adapter.project_id,
            "default_bucket": adapter.default_bucket,
        },
    )
    return adapter


def create_kafka_producer(config: Optional[dict] = None):
    """
    Create Kafka producer adapter.

    Args:
        config: Optional configuration override

    Returns:
        EventProducerPort implementation
    """
    from media_curation.adapters import KafkaProducerAdapter

    config = config or get_media_curation_config()
    kafka_config = config.get("KAFKA", {})

    # Get SASL/SSL config from Django settings
    sasl_config = getattr(settings, "KAFKA_SASL_CONFIG", {})

    adapter = KafkaProducerAdapter(
        bootstrap_servers=kafka_config.get("BOOTSTRAP_SERVERS", "localhost:9092"),
        dlq_topic=kafka_config.get("DLQ_TOPIC", "curation-dlq"),
        output_topic=kafka_config.get("OUTPUT_TOPIC", "curation-completed"),
        sasl_config=sasl_config,
    )

    logger.info("Kafka producer created")
    return adapter


def create_kafka_consumer(config: Optional[dict] = None):
    """
    Create Kafka consumer adapter.

    Args:
        config: Optional configuration override

    Returns:
        EventConsumerPort implementation
    """
    from media_curation.adapters import KafkaConsumerAdapter

    config = config or get_media_curation_config()
    kafka_config = config.get("KAFKA", {})

    # Get SASL/SSL config from Django settings
    sasl_config = getattr(settings, "KAFKA_SASL_CONFIG", {})

    adapter = KafkaConsumerAdapter(
        bootstrap_servers=kafka_config.get("BOOTSTRAP_SERVERS", "localhost:9092"),
        group_id=kafka_config.get("CONSUMER_GROUP", "media-curation-consumers"),
        input_topic=kafka_config.get("INPUT_TOPIC", "curation-needed"),
        sasl_config=sasl_config,
    )

    logger.info("Kafka consumer created")
    return adapter


def create_dlp_adapter(config: Optional[dict] = None):
    """
    Create DLP adapter for PII redaction.

    Args:
        config: Optional configuration override

    Returns:
        DLPPort implementation
    """
    from media_curation.adapters import CloudDLPAdapter

    config = config or get_media_curation_config()
    dlp_config = config.get("DLP", {})

    if not dlp_config.get("ENABLED", True):
        logger.info("DLP disabled in configuration")
        return None

    adapter = CloudDLPAdapter(
        project_id=config.get("GCP_PROJECT_ID"),
        default_info_types=dlp_config.get("INFO_TYPES"),
    )

    logger.info("DLP adapter created")
    return adapter


def create_curation_service(config: Optional[dict] = None, tenant=None):
    """
    Create fully configured CurationService.

    This is the main entry point for the curation pipeline.

    Args:
        config: Optional configuration override
        tenant: Optional Tenant instance for per-tenant bucket resolution

    Returns:
        Configured CurationService
    """
    from media_curation.domain.services import CurationService

    config = config or get_media_curation_config()

    # Get Kafka topic and bucket configuration
    kafka_config = config.get("KAFKA", {})
    storage_config = config.get("STORAGE", {})  # Match settings.MEDIA_CURATION key

    # Resolve curated bucket: per-tenant takes priority
    if tenant is not None and hasattr(tenant, "get_curated_bucket"):
        output_bucket = tenant.get_curated_bucket()
    else:
        output_bucket = storage_config.get("CURATED_BUCKET", "curated-documents")

    service = CurationService(
        processor_factory=create_processor_factory(config, tenant=tenant),
        cache=create_cache_adapter(config),
        storage=create_storage_adapter(config, tenant=tenant),
        producer=create_kafka_producer(config),
        dlp=create_dlp_adapter(config),
        output_topic=kafka_config.get("OUTPUT_TOPIC", "rag-sync-ready"),
        dlq_topic=kafka_config.get("DLQ_TOPIC", "curation-dlq"),
        output_bucket=output_bucket,
    )

    logger.info("CurationService created and configured")
    return service


# Singleton instances for reuse
_curation_service = None


def get_curation_service(config: Optional[dict] = None):
    """
    Get or create the CurationService singleton.

    Args:
        config: Optional configuration override

    Returns:
        Configured CurationService
    """
    global _curation_service
    if _curation_service is None:
        _curation_service = create_curation_service(config)
    return _curation_service
