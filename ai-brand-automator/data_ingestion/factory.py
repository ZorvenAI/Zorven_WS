"""
Factory module for creating configured adapter instances.

This module provides factory functions to create properly configured
adapters from Django settings, enabling dependency injection.
"""

import logging
from typing import Optional

from django.conf import settings

from data_ingestion.adapters.gcs_adapter import GCSAdapter
from data_ingestion.adapters.redis_adapter import RedisAdapter
from data_ingestion.adapters.kafka_adapter import (
    KafkaProducerAdapter,
    KafkaConsumerAdapter,
)
from data_ingestion.domain.services import IngestionService


logger = logging.getLogger(__name__)


def get_data_ingestion_config() -> dict:
    """Get data ingestion configuration from Django settings."""
    return getattr(settings, "DATA_INGESTION", {})


def create_gcs_adapter(config: Optional[dict] = None) -> GCSAdapter:
    """
    Create a GCS adapter from configuration.

    Args:
        config: Optional config dict (uses Django settings if not provided)

    Returns:
        Configured GCSAdapter instance
    """
    config = config or get_data_ingestion_config()
    # Support both nested GCS config and flat keys (GCP_PROJECT_ID, etc.)
    gcs_config = config.get("GCS", {})

    return GCSAdapter(
        project_id=gcs_config.get(
            "PROJECT_ID", config.get("GCP_PROJECT_ID", "brandsol")
        ),
        credentials_path=gcs_config.get(
            "CREDENTIALS_PATH", config.get("GCS_CREDENTIALS_PATH")
        ),
        default_bucket=gcs_config.get(
            "BUCKET_NAME", config.get("GCP_BUCKET_NAME", "onboarding-bucket1")
        ),
    )


def create_redis_adapter(config: Optional[dict] = None) -> RedisAdapter:
    """
    Create a Redis adapter from configuration.

    Args:
        config: Optional config dict (uses Django settings if not provided)

    Returns:
        Configured RedisAdapter instance
    """
    config = config or get_data_ingestion_config()
    redis_config = config.get("REDIS", {})

    # Fall back to CELERY_BROKER_URL if REDIS_URL not set
    redis_url = redis_config.get("URL") or getattr(
        settings, "CELERY_BROKER_URL", "redis://localhost:6379/0"
    )

    # TTLs can be configured either under REDIS or as top-level DATA_INGESTION keys
    dedupe_ttl_seconds = redis_config.get(
        "DEDUPE_TTL_SECONDS",
        config.get("DEDUPE_TTL_SECONDS", 3600),
    )
    status_ttl_seconds = redis_config.get(
        "STATUS_TTL_SECONDS",
        config.get("STATUS_TTL_SECONDS", 604800),
    )

    return RedisAdapter(
        redis_url=redis_url,
        dedupe_ttl_seconds=dedupe_ttl_seconds,
        status_ttl_seconds=status_ttl_seconds,
    )


def create_kafka_producer(config: Optional[dict] = None) -> KafkaProducerAdapter:
    """
    Create a Kafka producer from configuration.

    Args:
        config: Optional config dict (uses Django settings if not provided)

    Returns:
        Configured KafkaProducerAdapter instance
    """
    config = config or get_data_ingestion_config()
    kafka_config = config.get("KAFKA", {})

    # Support both nested KAFKA config and flat keys (KAFKA_BOOTSTRAP_SERVERS, etc.)
    # Also fall back to global KAFKA_BOOTSTRAP_SERVERS setting
    bootstrap_servers = kafka_config.get(
        "BOOTSTRAP_SERVERS",
        config.get(
            "KAFKA_BOOTSTRAP_SERVERS",
            getattr(settings, "KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
        ),
    )

    # Get SASL/SSL config from Django settings
    sasl_config = getattr(settings, "KAFKA_SASL_CONFIG", {})

    return KafkaProducerAdapter(
        bootstrap_servers=bootstrap_servers,
        client_id=kafka_config.get(
            "PRODUCER_CLIENT_ID",
            config.get("KAFKA_PRODUCER_CLIENT_ID", "ingestion-producer"),
        ),
        dlq_topic=kafka_config.get(
            "DLQ_TOPIC",
            config.get("KAFKA_DLQ_TOPIC", "ingestion-dlq"),
        ),
        sasl_config=sasl_config,
    )


def create_kafka_consumer(config: Optional[dict] = None) -> KafkaConsumerAdapter:
    """
    Create a Kafka consumer from configuration.

    Args:
        config: Optional config dict (uses Django settings if not provided)

    Returns:
        Configured KafkaConsumerAdapter instance
    """
    config = config or get_data_ingestion_config()
    kafka_config = config.get("KAFKA", {})

    # Support both nested KAFKA config and flat keys (KAFKA_INPUT_TOPIC, etc.)
    bootstrap_servers = kafka_config.get(
        "BOOTSTRAP_SERVERS",
        config.get(
            "KAFKA_BOOTSTRAP_SERVERS",
            getattr(settings, "KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
        ),
    )
    input_topic = kafka_config.get(
        "INPUT_TOPIC",
        config.get("KAFKA_INPUT_TOPIC", "raw-ingestion-topic"),
    )

    # Get SASL/SSL config from Django settings
    sasl_config = getattr(settings, "KAFKA_SASL_CONFIG", {})

    return KafkaConsumerAdapter(
        bootstrap_servers=bootstrap_servers,
        group_id=kafka_config.get(
            "CONSUMER_GROUP_ID",
            config.get("KAFKA_CONSUMER_GROUP_ID", "ingestion-consumer-group"),
        ),
        topics=[input_topic],
        client_id=kafka_config.get(
            "CONSUMER_CLIENT_ID",
            config.get("KAFKA_CONSUMER_CLIENT_ID", "ingestion-consumer"),
        ),
        auto_offset_reset=kafka_config.get(
            "AUTO_OFFSET_RESET",
            config.get("KAFKA_AUTO_OFFSET_RESET", "earliest"),
        ),
        enable_auto_commit=kafka_config.get(
            "ENABLE_AUTO_COMMIT",
            config.get("KAFKA_ENABLE_AUTO_COMMIT", False),
        ),
        sasl_config=sasl_config,
    )


def create_ingestion_service(config: Optional[dict] = None) -> IngestionService:
    """
    Create a fully configured IngestionService with all adapters.

    This is the main factory function for creating the service
    with all dependencies wired up.

    Args:
        config: Optional config dict (uses Django settings if not provided)

    Returns:
        Configured IngestionService instance
    """
    config = config or get_data_ingestion_config()
    kafka_config = config.get("KAFKA", {})
    redis_config = config.get("REDIS", {})

    # Create adapters
    storage = create_gcs_adapter(config)
    cache = create_redis_adapter(config)
    producer = create_kafka_producer(config)

    # Support both nested config and flat keys for Kafka topics
    output_topic = kafka_config.get(
        "OUTPUT_TOPIC",
        config.get("KAFKA_OUTPUT_TOPIC", "curation-needed-topic"),
    )
    dlq_topic = kafka_config.get(
        "DLQ_TOPIC",
        config.get("KAFKA_DLQ_TOPIC", "ingestion-dlq"),
    )

    # Support both nested config and flat keys for TTLs
    dedupe_ttl = redis_config.get(
        "DEDUPE_TTL_SECONDS",
        config.get("DEDUPE_TTL_SECONDS", 3600),
    )
    status_ttl = redis_config.get(
        "STATUS_TTL_SECONDS",
        config.get("STATUS_TTL_SECONDS", 604800),
    )

    # Create service
    service = IngestionService(
        storage=storage,
        cache=cache,
        producer=producer,
        output_topic=output_topic,
        dlq_topic=dlq_topic,
        dedupe_ttl_seconds=dedupe_ttl,
        status_ttl_seconds=status_ttl,
        max_retries=config.get("MAX_RETRIES", 3),
        retry_backoff_seconds=config.get("RETRY_BACKOFF_SECONDS", 1.0),
    )

    logger.info("IngestionService created with all adapters")
    return service


class IngestionServiceContainer:
    """
    Singleton container for the IngestionService.

    Ensures only one instance of the service and its adapters
    are created per process.
    """

    _instance: Optional[IngestionService] = None
    _consumer: Optional[KafkaConsumerAdapter] = None

    @classmethod
    def get_service(cls) -> IngestionService:
        """Get or create the singleton IngestionService instance."""
        if cls._instance is None:
            cls._instance = create_ingestion_service()
        return cls._instance

    @classmethod
    def get_consumer(cls) -> KafkaConsumerAdapter:
        """Get or create the singleton KafkaConsumer instance."""
        if cls._consumer is None:
            cls._consumer = create_kafka_consumer()
        return cls._consumer

    @classmethod
    def reset(cls) -> None:
        """Reset the container (useful for testing)."""
        if cls._consumer:
            cls._consumer.close()
        cls._instance = None
        cls._consumer = None
