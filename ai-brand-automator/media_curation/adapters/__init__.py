"""
Adapters Package - Concrete implementations of port interfaces.

This package provides the concrete adapter implementations for:
- GCS Storage (Google Cloud Storage)
- Cloud DLP (Data Loss Prevention for PII redaction)
- Redis (Caching and status tracking)
- Kafka (Event streaming)
- AI Processors (Document, Video, Audio, Image)
- Vertex AI (Gemini multimodal processing)
- Vision API (OCR and image analysis)
"""

from media_curation.adapters.gcs_adapter import GCSAdapter
from media_curation.adapters.dlp_adapter import CloudDLPAdapter
from media_curation.adapters.redis_adapter import RedisAdapter
from media_curation.adapters.kafka_adapter import (
    KafkaProducerAdapter,
    KafkaConsumerAdapter,
)
from media_curation.adapters.document_processor import DocumentProcessor
from media_curation.adapters.media_processors import (
    VideoProcessor,
    AudioProcessor,
    ImageProcessor,
)
from media_curation.adapters.vertex_adapter import VertexAIAdapter
from media_curation.adapters.vision_adapter import VisionAdapter


__all__ = [
    # Storage
    "GCSAdapter",
    # DLP
    "CloudDLPAdapter",
    # Cache
    "RedisAdapter",
    # Events
    "KafkaProducerAdapter",
    "KafkaConsumerAdapter",
    # AI Processors
    "DocumentProcessor",
    "VideoProcessor",
    "AudioProcessor",
    "ImageProcessor",
    # AI Adapters
    "VertexAIAdapter",
    "VisionAdapter",
]
