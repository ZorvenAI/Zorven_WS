"""
Ports Layer for RAG Index Service.

Contains abstract interfaces (ports) that define the boundaries
between the domain and external systems.

These interfaces follow the Hexagonal Architecture pattern,
allowing the domain to be decoupled from infrastructure concerns.
"""

from .vertex_ai_port import VertexAIPort
from .kafka_port import KafkaPort
from .redis_port import RedisPort
from .gcs_port import GCSPort

__all__ = [
    "VertexAIPort",
    "KafkaPort",
    "RedisPort",
    "GCSPort",
]
