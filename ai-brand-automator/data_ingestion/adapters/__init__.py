"""
Adapters package - Concrete implementations of ports.

This package contains the infrastructure adapters that implement
the abstract ports defined in the ports package.
"""

from data_ingestion.adapters.gcs_adapter import GCSAdapter
from data_ingestion.adapters.redis_adapter import RedisAdapter
from data_ingestion.adapters.kafka_adapter import (
    KafkaProducerAdapter,
    KafkaConsumerAdapter,
)


__all__ = [
    "GCSAdapter",
    "RedisAdapter",
    "KafkaProducerAdapter",
    "KafkaConsumerAdapter",
]
