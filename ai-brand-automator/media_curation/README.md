# Media Curation Service

AI-powered media processing pipeline for extracting, enriching, and normalizing content for RAG indexing.

> **Status:** Production Ready | **Tests:** 443 passing | **Coverage:** 86%

## Table of Contents

- [Architecture](#architecture)
- [Features](#features)
- [Quick Start](#quick-start)
- [API Reference](#api-reference)
- [Configuration](#configuration)
- [Running the Consumer](#running-the-consumer)
- [Integration with Data Ingestion](#integration-with-data-ingestion)
- [Project Structure](#project-structure)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              Media Curation Service                              │
└─────────────────────────────────────────────────────────────────────────────────┘

data-ingestion-svc ─► Kafka (curation-needed-topic) ─► CurationService ─► Kafka (rag-sync-ready-topic)
                                                              │
                                                              ▼
                                                    ┌─────────────────┐
                                                    │ ProcessorFactory│
                                                    └────────┬────────┘
                                         ┌───────────┬───────┴───────┬───────────┐
                                         ▼           ▼               ▼           ▼
                                   ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
                                   │ Document │ │  Video   │ │  Audio   │ │  Image   │
                                   │Processor │ │Processor │ │Processor │ │Processor │
                                   └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘
                                        │            │            │            │
                                        └────────────┴─────┬──────┴────────────┘
                                                           ▼
                                              ┌────────────────────────┐
                                              │   External Services    │
                                              ├────────────────────────┤
                                              │ • Redis (status/cache) │
                                              │ • GCS (storage)        │
                                              │ • Cloud DLP (PII)      │
                                              │ • Vertex AI (LLM)      │
                                              │ • Vision API (OCR)     │
                                              │ • Video Intelligence   │
                                              └────────────────────────┘
```

### Hexagonal Architecture

The service follows [Hexagonal Architecture](https://alistair.cockburn.us/hexagonal-architecture/) (Ports & Adapters):

- **Domain Layer** (`domain/`): Core business logic, models, and services
- **Ports** (`ports/`): Abstract interfaces defining required capabilities
- **Adapters** (`adapters/`): Concrete implementations of ports (Redis, GCS, Kafka, etc.)
- **Factory** (`factory.py`): Dependency injection and configuration

## Features

| Feature | Description |
|---------|-------------|
| **Content Type Routing** | Automatically routes to appropriate processor based on MIME type |
| **Text Extraction** | OCR for images/PDFs, Speech-to-Text for audio/video |
| **PII Redaction** | Configurable per-tenant DLP integration with Cloud DLP |
| **AI Enrichment** | Entity extraction, summarization, keyword generation via Gemini |
| **Structured Output** | Normalized JSON for downstream RAG indexing |
| **Status Tracking** | Real-time processing status via Redis |
| **Retry & DLQ** | Automatic retry with exponential backoff and dead letter queue |
| **Multi-tenant** | Tenant-specific configuration and isolation |
| **Health Monitoring** | Component-level health checks including consumer status |

## Quick Start

### Prerequisites

- Python 3.12+
- Redis (for caching and status)
- Kafka (for event streaming)
- Google Cloud credentials (for AI services)

### Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Apply migrations (if using Django models)
python manage.py migrate

# Run the development server
python manage.py runserver
```

### Submit a Curation Request

```bash
# Submit a single document for curation
curl -X POST http://localhost:8000/api/v1/curation/ \
  -H "Authorization: Bearer <your-jwt-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "123e4567-e89b-12d3-a456-426614174000",
    "file_id": "789e0123-e45b-67c8-d901-234567890abc",
    "raw_gcs_uri": "gs://my-bucket/_raw/tenant/file.pdf",
    "mime_type": "application/pdf",
    "metadata": {
      "filename": "quarterly-report.pdf",
      "uploaded_by": "user@example.com"
    }
  }'
```

**Response:**
```json
{
  "trace_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "message": "Curation request accepted"
}
```

### Check Processing Status

```bash
curl http://localhost:8000/api/v1/curation/status/550e8400-e29b-41d4-a716-446655440000/ \
  -H "Authorization: Bearer <your-jwt-token>"
```

**Response:**
```json
{
  "trace_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "document_id": "doc-12345",
  "output_gcs_uri": "gs://my-bucket/_curated/tenant/doc-12345.json",
  "processing_time_ms": 2345,
  "completed_at": "2026-02-02T12:00:00Z"
}
```

## API Reference

### Endpoints

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/api/v1/curation/` | JWT | Submit single curation request |
| POST | `/api/v1/curation/batch/` | JWT | Submit batch curation request (up to 100) |
| GET | `/api/v1/curation/status/{trace_id}/` | JWT | Check processing status |
| GET | `/api/v1/curation/health/` | None | Health check (public) |
| GET | `/api/v1/curation/config/` | JWT | Get tenant configuration |
| PUT | `/api/v1/curation/config/` | JWT | Update tenant configuration |

### POST /api/v1/curation/

Submit a single file for curation processing.

**Request Body:**
```json
{
  "tenant_id": "uuid (required)",
  "file_id": "uuid (required)",
  "raw_gcs_uri": "gs://bucket/path (required)",
  "mime_type": "string (required)",
  "metadata": {
    "filename": "string (optional)",
    "custom_key": "any value (optional)"
  }
}
```

**Response (202 Accepted):**
```json
{
  "trace_id": "uuid",
  "status": "pending",
  "message": "Curation request accepted"
}
```

### POST /api/v1/curation/batch/

Submit multiple files for curation (max 100).

**Request Body:**
```json
{
  "items": [
    {
      "tenant_id": "uuid",
      "file_id": "uuid",
      "raw_gcs_uri": "gs://bucket/file1.pdf",
      "mime_type": "application/pdf"
    },
    {
      "tenant_id": "uuid",
      "file_id": "uuid",
      "raw_gcs_uri": "gs://bucket/file2.mp4",
      "mime_type": "video/mp4"
    }
  ]
}
```

**Response (202 Accepted):**
```json
{
  "batch_id": "uuid",
  "accepted": 2,
  "items": [
    {"trace_id": "uuid-1", "status": "pending"},
    {"trace_id": "uuid-2", "status": "pending"}
  ]
}
```

### GET /api/v1/curation/status/{trace_id}/

Check the processing status of a curation request.

**Response (200 OK):**
```json
{
  "trace_id": "uuid",
  "status": "completed | processing | pending | failed",
  "document_id": "string (if completed)",
  "output_gcs_uri": "gs://... (if completed)",
  "error": "string (if failed)",
  "processing_time_ms": 1234,
  "started_at": "2026-02-02T12:00:00Z",
  "completed_at": "2026-02-02T12:00:02Z"
}
```

### GET /api/v1/curation/health/

Public health check endpoint for load balancers and monitoring.

**Response (200 OK):**
```json
{
  "status": "healthy | degraded | unhealthy",
  "timestamp": "2026-02-02T12:00:00Z",
  "components": {
    "redis": {"status": "healthy"},
    "kafka": {"status": "healthy"},
    "gcs": {"status": "healthy"},
    "ai_model": {"status": "healthy", "model": "gemini-2.0-flash"},
    "consumers": {
      "status": "healthy",
      "active_count": 2,
      "total_events_processed": 1500
    }
  }
}
```

## Configuration

### Django Settings

Add to your `settings.py`:

```python
MEDIA_CURATION = {
    # Google Cloud Project
    "GCP_PROJECT_ID": os.getenv("GCP_PROJECT_ID", "your-project-id"),
    
    # AI Model Configuration
    "AI_MODEL": {
        "MODEL": os.getenv("VERTEX_MODEL_NAME", "gemini-2.0-flash"),
        "LOCATION": os.getenv("VERTEX_LOCATION", "us-central1"),
    },
    
    # Kafka Configuration
    "KAFKA": {
        "BOOTSTRAP_SERVERS": os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
        "INPUT_TOPIC": "curation-needed-topic",
        "OUTPUT_TOPIC": "rag-sync-ready-topic",
        "DLQ_TOPIC": "curation-dlq",
        "CONSUMER_GROUP": "media-curation-consumers",
    },
    
    # Redis Configuration
    "REDIS": {
        "URL": os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        "STATUS_TTL_SECONDS": 604800,  # 7 days
        "CONFIG_TTL_SECONDS": 3600,    # 1 hour
    },
    
    # GCS Configuration
    "GCS": {
        "RAW_BUCKET": os.getenv("GCS_RAW_BUCKET", "brand-automator-raw"),
        "CURATED_BUCKET": os.getenv("GCS_CURATED_BUCKET", "brand-automator-curated"),
    },
    
    # DLP Configuration
    "DLP": {
        "ENABLED": True,
        "INFO_TYPES": [
            "EMAIL_ADDRESS",
            "PHONE_NUMBER",
            "CREDIT_CARD_NUMBER",
            "US_SOCIAL_SECURITY_NUMBER",
        ],
    },
    
    # Processing Configuration
    "PROCESSING": {
        "MAX_FILE_SIZE_MB": 100,
        "MAX_BATCH_SIZE": 100,
        "DEFAULT_RETRIES": 3,
    },
}
```

### Environment Variables

```bash
# Required
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
export GCP_PROJECT_ID=your-gcp-project

# Kafka
export KAFKA_BOOTSTRAP_SERVERS=localhost:9092

# Redis
export REDIS_URL=redis://localhost:6379/0

# GCS Buckets
export GCS_RAW_BUCKET=brand-automator-raw
export GCS_CURATED_BUCKET=brand-automator-curated

# AI Model (optional)
export VERTEX_MODEL_NAME=gemini-2.0-flash
export VERTEX_LOCATION=us-central1
```

## Running the Consumer

The Kafka consumer processes events from `curation-needed-topic`:

### Via Management Command

```bash
# Basic usage
python manage.py run_curation_consumer

# With options
python manage.py run_curation_consumer \
  --batch-size 20 \
  --poll-timeout 2.0 \
  --max-retries 5
```

### Via Celery (Recommended for Production)

```bash
# Start Celery worker for curation queue
celery -A brand_automator worker -Q curation -l info

# With concurrency
celery -A brand_automator worker -Q curation -l info -c 4
```

### Consumer Health Monitoring

The consumer reports its health to Redis, visible via the health endpoint:

```bash
curl http://localhost:8000/api/v1/curation/health/ | jq '.components.consumers'
```

```json
{
  "status": "healthy",
  "active_count": 2,
  "stale_count": 0,
  "error_count": 0,
  "total_events_processed": 1523,
  "total_events_failed": 12,
  "instances": [
    {
      "instance_id": "consumer-12345-abc",
      "status": "running",
      "events_processed": 800,
      "uptime_seconds": 3600
    }
  ]
}
```

## Integration with Data Ingestion

### Event Flow

```
┌─────────────────┐     ┌─────────────────────┐     ┌─────────────────┐
│ data-ingestion  │────►│ curation-needed-topic│────►│ media-curation  │
│     service     │     │      (Kafka)        │     │     service     │
└─────────────────┘     └─────────────────────┘     └────────┬────────┘
                                                              │
                                                              ▼
                                                    ┌─────────────────────┐
                                                    │ rag-sync-ready-topic│
                                                    │      (Kafka)        │
                                                    └──────────┬──────────┘
                                                               │
                                                               ▼
                                                    ┌─────────────────┐
                                                    │   RAG Indexer   │
                                                    └─────────────────┘
```

### Input Event Schema (curation-needed-topic)

CloudEvents format:

```json
{
  "specversion": "1.0",
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "source": "data-ingestion-svc",
  "type": "com.brandautomator.curation.needed",
  "time": "2026-02-02T12:00:00Z",
  "datacontenttype": "application/json",
  "data": {
    "event_id": "uuid",
    "trace_id": "uuid",
    "tenant_id": "uuid",
    "file_id": "uuid",
    "raw_gcs_uri": "gs://bucket/_raw/tenant/file.pdf",
    "mime_type": "application/pdf",
    "metadata": {
      "filename": "document.pdf",
      "size_bytes": 1234567
    }
  }
}
```

### Output Event Schema (rag-sync-ready-topic)

```json
{
  "specversion": "1.0",
  "id": "660e8400-e29b-41d4-a716-446655440001",
  "source": "media-curation-svc",
  "type": "com.brandautomator.rag.ready",
  "time": "2026-02-02T12:00:02Z",
  "datacontenttype": "application/json",
  "data": {
    "document_id": "uuid",
    "trace_id": "uuid",
    "tenant_id": "uuid",
    "source_gcs_uri": "gs://bucket/_raw/tenant/file.pdf",
    "output_gcs_uri": "gs://bucket/_curated/tenant/doc.json",
    "mime_type": "application/pdf",
    "content_type": "document",
    "extracted_text": "Full extracted text...",
    "struct_data": {
      "title": "Quarterly Report Q4 2025",
      "summary": "Financial summary...",
      "entities": ["Company Inc.", "John Doe"],
      "keywords": ["revenue", "growth", "forecast"]
    },
    "pii_redacted": true,
    "processing_time_ms": 2345,
    "created_at": "2026-02-02T12:00:02Z"
  }
}
```

### Publishing from Data Ingestion

Example Python code for the data ingestion service:

```python
from confluent_kafka import Producer
import json
from datetime import datetime, timezone
from uuid import uuid4

def publish_curation_event(
    producer: Producer,
    tenant_id: str,
    file_id: str,
    gcs_uri: str,
    mime_type: str,
    metadata: dict = None,
):
    """Publish a curation-needed event to Kafka."""
    
    event_id = str(uuid4())
    trace_id = str(uuid4())
    
    cloud_event = {
        "specversion": "1.0",
        "id": event_id,
        "source": "data-ingestion-svc",
        "type": "com.brandautomator.curation.needed",
        "time": datetime.now(timezone.utc).isoformat(),
        "datacontenttype": "application/json",
        "data": {
            "event_id": event_id,
            "trace_id": trace_id,
            "tenant_id": tenant_id,
            "file_id": file_id,
            "raw_gcs_uri": gcs_uri,
            "mime_type": mime_type,
            "metadata": metadata or {},
        }
    }
    
    producer.produce(
        topic="curation-needed-topic",
        key=trace_id.encode(),
        value=json.dumps(cloud_event).encode(),
        headers=[("trace-id", trace_id.encode())],
    )
    producer.flush()
    
    return trace_id
```

## Project Structure

```
media_curation/
├── domain/                    # Core domain models and services
│   ├── models.py              # Pydantic models (CurationEvent, CuratedDocument)
│   ├── schemas.py             # CloudEvents schemas
│   ├── services.py            # CurationService, ProcessorFactory
│   └── exceptions.py          # Domain exceptions (RetryableError, etc.)
├── ports/                     # Abstract interfaces (Hexagonal Architecture)
│   ├── cache_port.py          # Cache operations interface
│   ├── storage_port.py        # Storage operations interface
│   ├── dlp_port.py            # DLP operations interface
│   └── event_ports.py         # Event consumer/producer interfaces
├── adapters/                  # Concrete implementations
│   ├── redis_adapter.py       # Redis cache implementation
│   ├── gcs_adapter.py         # Google Cloud Storage implementation
│   ├── dlp_adapter.py         # Cloud DLP implementation
│   ├── kafka_adapter.py       # Kafka consumer/producer implementation
│   ├── vertex_adapter.py      # Vertex AI/Gemini implementation
│   └── vision_adapter.py      # Vision API implementation
├── processors/                # Content type processors
│   ├── base.py                # BaseContentProcessor abstract class
│   ├── document_processor.py  # PDF, Word, text processing
│   ├── video_processor.py     # Video transcription
│   ├── audio_processor.py     # Audio transcription
│   └── image_processor.py     # Image OCR and analysis
├── management/
│   └── commands/
│       └── run_curation_consumer.py  # Kafka consumer command
├── tests/                     # Test suite (443 tests)
│   ├── conftest.py            # Pytest fixtures
│   ├── test_models.py         # Domain model tests
│   ├── test_adapters.py       # Adapter tests
│   ├── test_services.py       # Service tests
│   ├── test_tasks.py          # Celery task tests
│   ├── test_views.py          # API view tests
│   ├── test_e2e.py            # End-to-end tests
│   ├── test_properties.py     # Property-based tests (Hypothesis)
│   └── test_consumer_command.py  # Consumer command tests
├── docs/
│   └── copilot-instructions-mcs.md  # Implementation guide
├── consumer_health.py         # Consumer health tracking
├── factory.py                 # Dependency injection
├── tasks.py                   # Celery tasks
├── views.py                   # DRF views
├── serializers.py             # DRF serializers
├── urls.py                    # URL routing
└── README.md                  # This file
```

## Testing

### Run All Tests

```bash
# All media_curation tests
pytest media_curation/tests/ -v

# With coverage report
pytest media_curation/tests/ --cov=media_curation --cov-report=html
```

### Run Specific Test Categories

```bash
# Domain models
pytest media_curation/tests/test_models.py -v

# Adapters
pytest media_curation/tests/test_adapters.py -v

# Services
pytest media_curation/tests/test_services.py -v

# API views
pytest media_curation/tests/test_views.py -v

# End-to-end
pytest media_curation/tests/test_e2e.py -v

# Property-based (Hypothesis)
pytest media_curation/tests/test_properties.py -v

# Consumer command
pytest media_curation/tests/test_consumer_command.py -v

# Real integrations (requires Docker)
pytest media_curation/tests/test_real_integrations.py -v
```

### Test Statistics

| Test File | Tests | Coverage Focus |
|-----------|-------|----------------|
| test_models.py | 54 | Domain models, validation |
| test_adapters.py | 31 | Redis, GCS, Kafka, DLP adapters |
| test_services.py | 22 | CurationService, ProcessorFactory |
| test_tasks.py | 14 | Celery tasks |
| test_views.py | 12 | API endpoints |
| test_integration.py | 35 | Integration flows |
| test_e2e.py | 20 | Full pipeline |
| test_properties.py | 25 | Property-based tests |
| test_consumer_command.py | 28 | Management command |
| **Total** | **443** | **86% coverage** |

## Troubleshooting

### Common Issues

#### 1. "Kafka not available - running in mock mode"

**Cause:** Kafka broker is not reachable.

**Solution:**
```bash
# Check if Kafka is running
docker ps | grep kafka

# Start Kafka with Docker Compose
docker compose up -d kafka zookeeper
```

#### 2. "Redis connection refused"

**Cause:** Redis server is not running.

**Solution:**
```bash
# Start Redis
docker compose up -d redis

# Or install locally
brew install redis && brew services start redis
```

#### 3. "GCS credentials not found"

**Cause:** Google Cloud credentials not configured.

**Solution:**
```bash
# Set credentials path
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json

# Verify credentials
gcloud auth application-default print-access-token
```

#### 4. "DLP API quota exceeded"

**Cause:** Cloud DLP rate limits hit.

**Solution:**
- Enable quota increase in Google Cloud Console
- Or disable DLP temporarily:
```python
MEDIA_CURATION = {
    "DLP": {"ENABLED": False}
}
```

#### 5. Consumer not processing events

**Cause:** Consumer group offset issues or topic not subscribed.

**Solution:**
```bash
# Check consumer group status
kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
  --group media-curation-consumers --describe

# Reset consumer group offset
kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
  --group media-curation-consumers --topic curation-needed-topic \
  --reset-offsets --to-earliest --execute
```

### Debugging Tips

1. **Enable debug logging:**
```python
LOGGING = {
    'loggers': {
        'media_curation': {'level': 'DEBUG'},
    }
}
```

2. **Check health endpoint:**
```bash
curl http://localhost:8000/api/v1/curation/health/ | jq
```

3. **Monitor Kafka topics:**
```bash
# List topics
kafka-topics.sh --bootstrap-server localhost:9092 --list

# Consume from topic
kafka-console-consumer.sh --bootstrap-server localhost:9092 \
  --topic curation-needed-topic --from-beginning
```

4. **Check Redis status cache:**
```bash
redis-cli KEYS "curation:status:*"
redis-cli GET "curation:status:<trace-id>"
```

## Supported Content Types

| Type | MIME Types | Processor | AI Services |
|------|------------|-----------|-------------|
| Document | application/pdf, text/*, application/msword, etc. | DocumentProcessor | Vision API (OCR), Gemini (extraction) |
| Video | video/* | VideoProcessor | Video Intelligence, Speech-to-Text, Gemini |
| Audio | audio/* | AudioProcessor | Speech-to-Text, Gemini |
| Image | image/* | ImageProcessor | Vision API, Gemini |

## License

Proprietary - AI Brand Automator © 2026
