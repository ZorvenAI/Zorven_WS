# Data Ingestion App - Implementation Guide

> Hexagonal Architecture Django app for data ingestion pipeline within ai-brand-automator.

## Architecture

```
Kafka (raw-ingestion) ──► KafkaConsumer ──► IngestionService ──► Kafka (curation-needed)
                                                  │
                              ┌───────────────────┼───────────────────┐
                              ▼                   ▼                   ▼
                          RedisAdapter       GCSAdapter          KafkaProducer
                         (dedup/status)    (move files)         (output events)
```

**Design Pattern:** Hexagonal Architecture (Ports & Adapters)
- **Core Domain:** Business logic with no external dependencies
- **Ports:** Abstract interfaces (`StoragePort`, `CachePort`, `EventProducerPort`)
- **Adapters:** Concrete implementations (GCS, Redis, Kafka)

---

## Directory Structure

```
ai-brand-automator/
├── data_ingestion/              # Django App
│   ├── __init__.py
│   ├── apps.py                  # Django app config
│   ├── domain/                  # Pure Business Logic
│   │   ├── __init__.py
│   │   ├── models.py            # Pydantic Models (IngestionEvent, FileMetadata)
│   │   ├── services.py          # IngestionService (The Orchestrator)
│   │   ├── path_generator.py    # Landing → Raw path logic
│   │   └── exceptions.py        # Custom Exceptions
│   ├── ports/                   # Abstract Base Classes (ABCs)
│   │   ├── __init__.py
│   │   ├── storage_port.py      # Interface for GCS
│   │   ├── event_port.py        # Interface for Kafka
│   │   └── cache_port.py        # Interface for Redis
│   ├── adapters/                # Concrete Implementations
│   │   ├── __init__.py
│   │   ├── gcs_adapter.py
│   │   ├── kafka_adapter.py     # KafkaProducerAdapter + KafkaConsumerAdapter
│   │   └── redis_adapter.py
│   ├── management/
│   │   └── commands/
│   │       └── run_ingestion.py # Django management command
│   ├── tasks.py                 # Celery tasks for background processing
│   ├── docs/
│   │   └── copilot-instructions-dis.md
│   └── tests/
│       ├── __init__.py
│       ├── conftest.py          # Shared fixtures
│       ├── test_models.py       # Unit tests for domain models
│       ├── test_path_generator.py
│       ├── test_exceptions.py
│       ├── test_services.py
│       ├── test_properties.py   # Hypothesis property tests
│       ├── test_adapters.py     # Adapter tests (GCS, Redis, Kafka)
│       ├── test_integration.py  # Integration tests
│       └── test_e2e.py          # End-to-end tests
```

---

## Implementation Phases

### Phase 1: App Skeleton & Configuration ✅
- Django app structure with hexagonal architecture
- Settings in `brand_automator/settings.py`
- GCS credentials configuration

### Phase 2: Domain Layer
- `domain/models.py`: `IngestionEvent`, `FileMetadata`, `EventSource` enum
- `domain/exceptions.py`: Custom exceptions
- `domain/path_generator.py`: Path transformation logic

### Phase 3: Ports (Interfaces)
- `ports/storage_port.py`: `StoragePort` ABC
- `ports/cache_port.py`: `CachePort` ABC
- `ports/event_port.py`: `EventProducerPort` ABC

### Phase 4: Domain Service
- `domain/services.py`: `IngestionService` orchestrator
- Unit tests with mock ports

### Phase 5: Adapters
- `adapters/gcs_adapter.py`: GCS implementation
- `adapters/redis_adapter.py`: Redis dedup/status (reuses existing Redis)
- `adapters/kafka_consumer.py`: Consumer with retry/DLQ
- `adapters/kafka_producer.py`: Producer wrapper

### Phase 6: Integration
- `management/commands/run_ingestion.py`: Django command to start consumer
- `tasks.py`: Celery tasks for scheduled ingestion
- Integration with existing Celery worker

### Phase 7: Testing
Comprehensive testing following the existing project patterns.

#### 7.1 Unit Tests (`tests/unit/`)
Pure logic tests with no external dependencies:
- `test_models.py`: Pydantic model validation, serialization/deserialization
- `test_path_generator.py`: Path transformation logic for all edge cases
- `test_exceptions.py`: Custom exception behavior
- `test_services.py`: IngestionService with **mock ports** (no real GCS/Redis/Kafka)

#### 7.2 Property Tests (`tests/test_properties.py`)
Hypothesis-based property testing (follows `onboarding/tests/test_properties.py` pattern):
- Path generator handles arbitrary tenant IDs and filenames
- Event model validates/rejects edge case inputs
- Deduplication logic is idempotent
- Use `@pytest.mark.property` marker

```python
@pytest.mark.property
@given(st.text(min_size=1, max_size=100, alphabet=st.characters(whitelist_categories=('L', 'N'))))
def test_path_generator_handles_any_tenant_id(tenant_id):
    # Property: path always contains tenant_id as prefix
    path = generate_raw_path(tenant_id, "file.mp4", datetime.now())
    assert path.startswith(f"{tenant_id}/raw/")
```

#### 7.3 Integration Tests (`tests/integration/`)
Tests with real (or emulated) external services:
- `test_gcs_adapter.py`: GCS operations with emulator or real bucket (test prefix)
- `test_redis_adapter.py`: Redis operations with `fakeredis` or real Redis
- `test_kafka_adapter.py`: Kafka producer/consumer with testcontainers or mock

```python
@pytest.fixture
def fake_redis():
    """Use fakeredis for integration tests without real Redis."""
    import fakeredis
    return fakeredis.FakeRedis()

def test_deduplication_prevents_reprocessing(fake_redis):
    adapter = RedisAdapter(client=fake_redis)
    assert adapter.is_duplicate("event-123") is False
    adapter.mark_processed("event-123", ttl=3600)
    assert adapter.is_duplicate("event-123") is True
```

#### 7.4 End-to-End Tests (`tests/e2e/`)
Full pipeline tests simulating real data flow:
- `test_ingestion_pipeline.py`: Complete flow from Kafka message to GCS file move
- Uses Docker Compose services (Kafka, Redis, GCS emulator) or mocks
- Validates output Kafka message is produced correctly

```python
@pytest.mark.e2e
def test_full_ingestion_pipeline(kafka_producer, gcs_client, redis_client):
    """
    E2E Test: Produce event → Consumer processes → File moved → Output event published
    """
    # 1. Upload test file to landing zone
    gcs_client.upload("_landing/test-file.mp4", b"test content")
    
    # 2. Produce ingestion event
    event = {"event_id": "...", "tenant_id": "customer-1", "file_path": "..."}
    kafka_producer.produce("raw-ingestion-topic", event)
    
    # 3. Run ingestion (or wait for consumer)
    run_ingestion_once()
    
    # 4. Assert file moved to raw path
    assert gcs_client.exists("customer-1/raw/2026/01/29/test-file.mp4")
    assert not gcs_client.exists("_landing/test-file.mp4")
    
    # 5. Assert output event published
    output_event = kafka_consumer.poll("curation-needed-topic")
    assert output_event["status"] == "RAW_STORED"
```

#### Test Directory Structure
```
data_ingestion/tests/
├── __init__.py
├── conftest.py              # Shared fixtures (mock ports, fake services)
├── unit/
│   ├── __init__.py
│   ├── test_models.py
│   ├── test_path_generator.py
│   ├── test_exceptions.py
│   └── test_services.py
├── test_properties.py       # Hypothesis property tests
├── integration/
│   ├── __init__.py
│   ├── test_gcs_adapter.py
│   ├── test_redis_adapter.py
│   └── test_kafka_adapter.py
└── e2e/
    ├── __init__.py
    └── test_ingestion_pipeline.py
```

#### Test Commands
```bash
# All data_ingestion tests
pytest data_ingestion/tests -v

# Unit tests only (fast, no external deps)
pytest data_ingestion/tests/unit -v

# Property tests only
pytest data_ingestion/tests -m property -v

# Integration tests (requires Redis, may need GCS emulator)
pytest data_ingestion/tests/integration -v

# E2E tests (requires full stack)
pytest data_ingestion/tests/e2e -v --tb=short

# With coverage
pytest data_ingestion/tests --cov=data_ingestion --cov-report=term-missing
```

---

## Critical Patterns

### GCS Path Logic
```python
# Input (Landing): gs://{bucket}/_landing/{uuid_filename}
# Output (Raw):    gs://{bucket}/{tenant_id}/raw/{YYYY}/{MM}/{DD}/{uuid_filename}
```

### Deduplication Pattern (Reuses existing Redis)
```python
# Redis SETNX pattern - key expires after 1 hour
key = f"pipeline:dedupe:{event_id}"
is_new = redis.set(key, "1", nx=True, ex=3600)
if not is_new:
    raise DuplicateEventError(event_id)
```

### Kafka Manual Commit
```python
# Only commit AFTER successful processing or DLQ routing
try:
    service.process_event(event)
    consumer.commit()
except FileNotFoundError:
    producer.send_to_dlq(event, error)
    consumer.commit()  # Still commit - don't reprocess
except TransientError:
    # Don't commit - will retry on next poll
    raise
```

---

## Configuration (in settings.py)

```python
# Data Ingestion Settings
DATA_INGESTION = {
    # Kafka
    "KAFKA_BOOTSTRAP_SERVERS": config("KAFKA_BOOTSTRAP_SERVERS", default="localhost:9092"),
    "KAFKA_INPUT_TOPIC": config("KAFKA_INPUT_TOPIC", default="raw-ingestion-topic"),
    "KAFKA_OUTPUT_TOPIC": config("KAFKA_OUTPUT_TOPIC", default="curation-needed-topic"),
    "KAFKA_DLQ_TOPIC": config("KAFKA_DLQ_TOPIC", default="ingestion-dlq"),
    "KAFKA_GROUP_ID": config("KAFKA_GROUP_ID", default="ingestion-svc-group"),
    
    # GCS
    "GCP_PROJECT_ID": config("GCP_PROJECT_ID", default="brandsol"),
    "GCP_BUCKET_NAME": config("GCP_BUCKET_NAME", default="onboarding-bucket1"),
    "GCS_LANDING_PREFIX": config("GCS_LANDING_PREFIX", default="_landing"),
    
    # Processing
    "MAX_RETRIES": config("INGESTION_MAX_RETRIES", default=3, cast=int),
    "RETRY_BACKOFF_SECONDS": config("INGESTION_RETRY_BACKOFF", default=1.0, cast=float),
    "DEDUPE_TTL_SECONDS": config("INGESTION_DEDUPE_TTL", default=3600, cast=int),
}
```

---

## Commands

```bash
# Run ingestion consumer (standalone)
python manage.py run_ingestion

# Run with Celery (background)
celery -A brand_automator worker -l info

# Tests
pytest data_ingestion/tests -v
```

---

## Key Files Reference

| Purpose | Location |
|---------|----------|
| Django app config | `data_ingestion/apps.py` |
| Domain models | `data_ingestion/domain/models.py` |
| Business logic | `data_ingestion/domain/services.py` |
| Path generation | `data_ingestion/domain/path_generator.py` |
| GCS adapter | `data_ingestion/adapters/gcs_adapter.py` |
| Redis adapter | `data_ingestion/adapters/redis_adapter.py` |
| Kafka consumer | `data_ingestion/adapters/kafka_consumer.py` |
| Management command | `data_ingestion/management/commands/run_ingestion.py` |
| Celery tasks | `data_ingestion/tasks.py` |
| Test fixtures | `data_ingestion/tests/conftest.py` |
| Property tests | `data_ingestion/tests/test_properties.py` |
| E2E tests | `data_ingestion/tests/e2e/test_ingestion_pipeline.py` |
