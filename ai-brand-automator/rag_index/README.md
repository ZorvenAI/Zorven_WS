# RAG Index Service

> **Version**: 1.0.0  
> **Status**: ✅ Implementation Complete  
> **Tests**: 322 passing  
> **Last Updated**: February 2, 2026

## Overview

The RAG Index Service (`rag-index-svc`) synchronizes curated documents from Google Cloud Storage to Vertex AI Discovery Engine (Search). It implements a Hexagonal Architecture pattern with robust rate limiting, status tracking, and event-driven processing.

## Key Features

- 🔍 **Document Indexing** - Upsert curated JSON documents into Vertex AI Data Store
- 🗑️ **Document Deletion** - Remove documents from the index on delete events
- ⏱️ **Rate Limiting** - Sliding window algorithm enforcing 600 req/min quota
- 📊 **Status Tracking** - Redis-based sync status with TTL
- 🔄 **Event-Driven** - Kafka consumer with CloudEvents format
- ⚡ **Celery Tasks** - Background processing with retry logic
- 🏗️ **Hexagonal Architecture** - Clean separation with Ports & Adapters pattern

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          RAG Index Service                               │
│                                                                          │
│  ┌──────────────┐    ┌────────────────────┐    ┌──────────────────────┐ │
│  │  REST API    │───►│  SyncOrchestrator  │───►│  Vertex AI Adapter   │ │
│  │  (Views)     │    │  (Domain Service)  │    │  (Discovery Engine)  │ │
│  └──────────────┘    └────────────────────┘    └──────────────────────┘ │
│         ▲                     │                          │               │
│         │                     ▼                          ▼               │
│  ┌──────────────┐    ┌────────────────────┐    ┌──────────────────────┐ │
│  │ Kafka        │    │  Rate Limiter      │    │  GCS Adapter         │ │
│  │ Consumer     │───►│  (Redis Sliding)   │    │  (Document Fetch)    │ │
│  └──────────────┘    └────────────────────┘    └──────────────────────┘ │
│                               │                                          │
│                               ▼                                          │
│                      ┌────────────────────┐                             │
│                      │  Redis Adapter     │                             │
│                      │  (Status Cache)    │                             │
│                      └────────────────────┘                             │
└─────────────────────────────────────────────────────────────────────────┘
```

## Directory Structure

```
rag_index/
├── __init__.py
├── apps.py
├── factory.py                    # Dependency injection
├── domain/
│   ├── __init__.py
│   ├── models.py                 # Pydantic domain models (SyncEvent, SyncResult)
│   ├── schemas.py                # CloudEvents & Vertex AI schemas
│   └── exceptions.py             # Custom exception hierarchy
├── ports/
│   ├── __init__.py
│   ├── gcs_port.py               # GCS interface
│   ├── vertex_ai_port.py         # Vertex AI interface
│   ├── redis_port.py             # Redis/status interface
│   └── kafka_port.py             # Kafka producer interface
├── adapters/
│   ├── __init__.py
│   ├── gcs_adapter.py            # Google Cloud Storage adapter
│   ├── vertex_ai_adapter.py      # Vertex AI Discovery Engine adapter
│   ├── redis_adapter.py          # Redis status tracking adapter
│   ├── kafka_adapter.py          # Kafka producer adapter
│   └── rate_limiter.py           # Redis sliding window rate limiter
├── services/
│   ├── __init__.py
│   └── sync_orchestrator.py      # Main orchestration service
├── tasks/
│   ├── __init__.py
│   └── sync_tasks.py             # Celery tasks
├── api/
│   ├── __init__.py
│   ├── views.py                  # DRF ViewSets
│   ├── serializers.py            # DRF serializers
│   └── urls.py                   # URL routing
├── management/
│   └── commands/
│       └── consume_sync_events.py  # Kafka consumer command
├── tests/
│   ├── __init__.py
│   ├── conftest.py               # Pytest fixtures
│   ├── test_models.py            # Domain model tests (80 tests)
│   ├── test_ports.py             # Port interface tests (43 tests)
│   ├── test_adapters.py          # Adapter tests (44 tests)
│   ├── test_rate_limiter.py      # Rate limiting tests (34 tests)
│   ├── test_sync_orchestrator.py # Service tests (33 tests)
│   ├── test_celery_tasks.py      # Celery task tests (18 tests)
│   ├── test_api.py               # REST API tests (33 tests)
│   ├── test_kafka_consumer.py    # Consumer command tests (13 tests)
│   ├── test_integration.py       # Integration tests (14 tests)
│   └── test_e2e.py               # E2E tests (10 tests)
├── Dockerfile                    # Multi-stage production build
├── docker-compose.yml            # Local development stack
├── railway.json                  # Railway deployment config
└── .env.example                  # Environment template
```

## Domain Models

### SyncEvent
Input event from the Kafka topic:
```python
SyncEvent(
    event_id=UUID,
    trace_id="trace-123",
    tenant_id="tenant-001",
    file_id="file-456",
    action=SyncAction.UPSERT,  # or DELETE
    processed_gcs_uri="gs://bucket/path/doc.json",
)
```

### SyncResult
Output result from processing:
```python
SyncResult(
    event_id=UUID,
    trace_id="trace-123",
    status="COMPLETED",  # or FAILED, PENDING
    operation_id="lro-789",
    processing_time_ms=150,
)
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/rag-index/health/` | GET | Health check |
| `/api/v1/rag-index/health/ready/` | GET | Readiness probe |
| `/api/v1/rag-index/health/live/` | GET | Liveness probe |
| `/api/v1/rag-index/sync/` | POST | Trigger sync operation |
| `/api/v1/rag-index/sync/batch/` | POST | Batch sync operations |
| `/api/v1/rag-index/sync/status/{id}/` | GET | Get sync status |
| `/api/v1/rag-index/rate-limit/` | GET | Rate limit status |

## Rate Limiting

The service implements a sliding window rate limiter with:
- **Limit**: 600 requests/minute (Vertex AI quota)
- **Algorithm**: Redis ZSET sliding window
- **Backpressure**: Automatic retry with exponential backoff

```python
# Rate limiter configuration
RateLimiterConfig(
    max_requests=600,
    window_seconds=60,
    redis_key_prefix="rag-index:rate-limit",
)
```

## Event Processing

### Kafka Consumer
```bash
# Start consumer
python manage.py consume_sync_events \
    --topic rag-sync-ready-topic \
    --group rag-index-workers \
    --bootstrap-servers kafka:9092
```

### Celery Worker
```bash
# Start worker
celery -A brand_automator worker -l info -Q rag-sync-queue
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `VERTEX_AI_PROJECT_ID` | GCP Project ID | - |
| `VERTEX_AI_LOCATION` | Vertex AI location | `us-central1` |
| `VERTEX_AI_DATASTORE_ID` | Discovery Engine datastore | - |
| `REDIS_URL` | Redis connection URL | `redis://localhost:6379/0` |
| `KAFKA_BOOTSTRAP_SERVERS` | Kafka brokers | `localhost:9092` |
| `GOOGLE_APPLICATION_CREDENTIALS` | GCP service account key | - |
| `RAG_RATE_LIMIT_MAX_REQUESTS` | Rate limit max | `600` |
| `RAG_RATE_LIMIT_WINDOW_SECONDS` | Rate limit window | `60` |

## Development

### Running Tests
```bash
# All tests
python -m pytest rag_index/tests/ -v

# Specific test file
python -m pytest rag_index/tests/test_sync_orchestrator.py -v

# With coverage
python -m pytest rag_index/tests/ --cov=rag_index --cov-report=html
```

### Local Development
```bash
# Start dependencies
docker-compose -f rag_index/docker-compose.yml up -d redis kafka

# Run API server
python manage.py runserver

# Run consumer (separate terminal)
python manage.py consume_sync_events --mock-mode

# Run Celery worker (separate terminal)
celery -A brand_automator worker -l info
```

## Deployment

### Docker
```bash
# Build image
docker build -f rag_index/Dockerfile -t rag-index-svc .

# Run container
docker run -p 8000:8000 --env-file rag_index/.env rag-index-svc
```

### Docker Compose (Full Stack)
```bash
cd rag_index
docker-compose up -d
```

### Railway
The service is configured for Railway deployment via `railway.json`:
- Automatic health checks
- Restart on failure
- Environment variable injection

## Test Coverage

| Phase | Tests | Description |
|-------|-------|-------------|
| Phase 1 | 80 | Domain Models |
| Phase 2 | 43 | Port Interfaces |
| Phase 3 | 44 | Adapters |
| Phase 4 | 34 | Rate Limiting |
| Phase 5 | 33 | Service Layer |
| Phase 6 | 18 | Celery Tasks |
| Phase 7 | 33 | REST API |
| Phase 8 | 13 | Kafka Consumer |
| Phase 9 | 14 | Integration |
| Phase 10 | 10 | E2E |
| **Total** | **322** | - |

## Related Services

- **Media Curation Service** (`media_curation/`) - Upstream document processor
- **AI Services** (`ai_services/`) - Gemini AI integration
- **Kong Gateway** - API gateway with JWT offloading

## Troubleshooting

### Rate Limit Errors
```bash
# Check current rate limit status
curl http://localhost:8000/api/v1/rag-index/rate-limit/

# Reset rate limiter (development only)
redis-cli DEL "rag-index:rate-limit:vertex"
```

### Consumer Not Processing
```bash
# Check Kafka connectivity
kafka-console-consumer --bootstrap-server localhost:9092 \
    --topic rag-sync-ready-topic --from-beginning

# Verify consumer group
kafka-consumer-groups --bootstrap-server localhost:9092 \
    --describe --group rag-index-workers
```

### Celery Tasks Failing
```bash
# Check worker status
celery -A brand_automator inspect active

# Purge queue (development only)
celery -A brand_automator purge -Q rag-sync-queue
```
