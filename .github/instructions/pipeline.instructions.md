---
applyTo: "ai-brand-automator/{data_ingestion,media_curation,rag_index}/**/*.py"
---

# Pipeline Instructions (Hexagonal Architecture)

## Architecture Overview

Pipeline apps (`data_ingestion`, `media_curation`, `rag_index`) follow **Hexagonal Architecture** (Ports & Adapters). This is fundamentally different from the rest of the Django project.

## Directory Structure

```
app_name/
├── domain/           → Pure Pydantic models (NO Django ORM)
│   └── models.py     → BaseModel subclasses with validation
├── ports/            → Abstract interfaces (ABCs)
│   ├── inbound.py    → Service interfaces (what the app exposes)
│   └── outbound.py   → Repository/adapter interfaces (what the app needs)
├── adapters/         → Concrete implementations
│   ├── gcs.py        → Google Cloud Storage adapter
│   ├── kafka.py      → Kafka producer/consumer adapter
│   └── db.py         → Django ORM adapter (only place ORM is used)
├── services/         → Business logic orchestration
│   └── service.py    → Implements inbound port, uses outbound ports
├── factory.py        → Dependency injection wiring
└── tests/            → Unit + integration tests
```

## Critical Rules

### Domain Models

```python
# ✅ CORRECT — Pure Pydantic BaseModel
from pydantic import BaseModel, Field

class IngestionRecord(BaseModel):
    file_name: str
    content_type: str
    file_size: int = Field(gt=0)
    status: str = "pending"

# ❌ WRONG — Django ORM in domain
from django.db import models
class IngestionRecord(models.Model):  # NEVER in domain/
    pass
```

### Ports (Interfaces)

```python
# ports/outbound.py
from abc import ABC, abstractmethod
from domain.models import IngestionRecord

class StoragePort(ABC):
    @abstractmethod
    def upload(self, record: IngestionRecord, data: bytes) -> str:
        """Upload file and return URL."""
        ...

    @abstractmethod
    def download(self, path: str) -> bytes:
        """Download file by path."""
        ...
```

### Adapters (Implementations)

```python
# adapters/gcs.py
from ports.outbound import StoragePort
from domain.models import IngestionRecord

class GCSStorageAdapter(StoragePort):
    def upload(self, record: IngestionRecord, data: bytes) -> str:
        # Concrete GCS implementation
        ...
```

### Factory (Wiring)

```python
# factory.py — Single place where adapters are instantiated
def create_ingestion_service():
    storage = GCSStorageAdapter()
    kafka = KafkaProducerAdapter()
    return IngestionService(storage=storage, kafka=kafka)
```

## Testing

- **Unit tests**: Test services with mock adapters (no I/O)
- **Integration tests**: Test adapters against real/emulated services
- **Domain tests**: Test Pydantic model validation
- Mock at the port boundary, not at individual function level
- Use `@pytest.mark.unit` and `@pytest.mark.integration` markers

## Kafka Events

Pipeline apps communicate via Kafka topics:

| Producer | Topic | Consumer |
|----------|-------|----------|
| `data_ingestion` | `curation-needed` | `media_curation` |
| `media_curation` | `rag-sync-ready` | `rag_index` |

Always handle `KafkaException` gracefully — Kafka is optional and may be disabled.
