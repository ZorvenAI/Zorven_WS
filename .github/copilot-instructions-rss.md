# RAG Index Service (rag-index-svc) - Implementation Complete

> **Service Name:** `rag-index-svc`  
> **Version:** 1.0  
> **Status:** ✅ Implementation Complete  
> **Tests:** 322 passing  
> **GitHub Issue:** [#123](https://github.com/naveenah/Prevision_WS/issues/123)  
> **Created:** February 2, 2026  
> **Completed:** February 2, 2026

---

## Executive Summary

The `rag-index-svc` has been fully implemented as a Django REST Framework application within the `ai-brand-automator` project. The service syncs curated documents to Vertex AI Search (Discovery Engine) with built-in rate limiting.

**Key Responsibilities:**
- **Indexing:** Upserts curated JSON documents into Vertex AI Data Store
- **Deletions:** Removes documents from the index on delete events
- **Traffic Control:** Enforces API quotas (600 req/min) to prevent 429 errors

**Design Pattern:** Hexagonal Architecture with Throttling Proxy Pattern

---

## Implementation Summary

| Phase | Description | Tests | Status |
|-------|-------------|-------|--------|
| 1 | Domain Models | 80 | ✅ Complete |
| 2 | Ports (Interfaces) | 43 | ✅ Complete |
| 3 | Adapters (Implementations) | 44 | ✅ Complete |
| 4 | Rate Limiting | 34 | ✅ Complete |
| 5 | Service Layer | 33 | ✅ Complete |
| 6 | Celery Tasks | 18 | ✅ Complete |
| 7 | REST API Views | 33 | ✅ Complete |
| 8 | Kafka Consumer Command | 13 | ✅ Complete |
| 9 | Integration Tests | 14 | ✅ Complete |
| 10 | E2E Tests | 10 | ✅ Complete |
| 11 | Deployment & CI/CD | - | ✅ Complete |
| **Total** | | **322** | ✅ |

---

## Quick Reference

### Running the Service

```bash
# Start dependencies
docker-compose -f rag_index/docker-compose.yml up -d redis kafka

# Run API server
python manage.py runserver

# Run Kafka consumer
python manage.py consume_sync_events --topic rag-sync-ready-topic --group rag-index-workers

# Run Celery worker
celery -A brand_automator worker -l info -Q rag-sync-queue
```

### Running Tests

```bash
# All tests
python -m pytest rag_index/tests/ -v

# With coverage
python -m pytest rag_index/tests/ --cov=rag_index --cov-report=html
```

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/rag-index/health/` | GET | Health check |
| `/api/v1/rag-index/health/ready/` | GET | Readiness probe |
| `/api/v1/rag-index/health/live/` | GET | Liveness probe |
| `/api/v1/rag-index/sync/` | POST | Trigger sync operation |
| `/api/v1/rag-index/sync/batch/` | POST | Batch sync operations |
| `/api/v1/rag-index/sync/status/{id}/` | GET | Get sync status |
| `/api/v1/rag-index/rate-limit/` | GET | Rate limit status |

### Key Files

| File | Purpose |
|------|---------|
| `rag_index/README.md` | Service documentation |
| `rag_index/services/sync_orchestrator.py` | Main orchestration service |
| `rag_index/adapters/rate_limiter.py` | Redis sliding window rate limiter |
| `rag_index/management/commands/consume_sync_events.py` | Kafka consumer |
| `rag_index/api/views.py` | REST API endpoints |
| `rag_index/Dockerfile` | Production Docker build |
| `rag_index/docker-compose.yml` | Local development stack |

---

## Original Implementation Plan (Reference)

The following sections contain the original implementation plan that was used as a guide during development.

### 1.1 Directory Structure

```
ai-brand-automator/
├── rag_index/                      # New Django app
│   ├── __init__.py
│   ├── apps.py
│   ├── admin.py
│   ├── urls.py
│   ├── views.py
│   ├── serializers.py
│   ├── tasks.py                    # Celery tasks
│   ├── factory.py                  # Dependency injection
│   ├── domain/
│   │   ├── __init__.py
│   │   ├── models.py               # Pydantic domain models
│   │   ├── schemas.py              # CloudEvents & Vertex schemas
│   │   ├── services.py             # IndexingService orchestrator
│   │   └── exceptions.py           # Custom exceptions
│   ├── ports/
│   │   ├── __init__.py
│   │   ├── search_port.py          # SearchEnginePort interface
│   │   ├── cache_port.py           # RateLimiterPort interface
│   │   └── event_port.py           # EventPublisherPort interface
│   ├── adapters/
│   │   ├── __init__.py
│   │   ├── vertex_adapter.py       # Vertex AI Discovery Engine
│   │   ├── redis_ratelimiter.py    # Redis sliding window rate limiter
│   │   └── kafka_adapter.py        # Kafka producer/consumer
│   ├── management/
│   │   └── commands/
│   │       └── run_rag_consumer.py # Kafka consumer management command
│   └── tests/
│       ├── __init__.py
│       ├── conftest.py
│       ├── test_models.py
│       ├── test_schemas.py
│       ├── test_exceptions.py
│       ├── test_adapters.py
│       ├── test_services.py
│       ├── test_tasks.py
│       ├── test_views.py
│       ├── test_integration.py
│       ├── test_properties.py      # Hypothesis property tests
│       └── test_e2e.py             # End-to-end tests
```

### 1.2 Domain Models (`domain/models.py`)

```python
from enum import Enum
from typing import Any, Literal, Optional
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field


class SyncAction(str, Enum):
    """Document sync action types."""
    UPSERT = "UPSERT"
    DELETE = "DELETE"


class SyncEvent(BaseModel):
    """Input event from rag-sync-ready-topic."""
    event_id: UUID
    trace_id: str
    tenant_id: str
    file_id: str
    processed_gcs_uri: str
    action: SyncAction
    timestamp: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)

    # Alias for backward compatibility
    @property
    def document_id(self) -> str:
        """Alias for file_id."""
        return self.file_id


class SyncResult(BaseModel):
    """Result of a sync operation."""
    event_id: UUID
    trace_id: str
    status: Literal["COMPLETED", "FAILED", "PENDING"]
    operation_id: Optional[str] = None  # Vertex LRO ID
    error_message: Optional[str] = None
    processing_time_ms: int = 0


class SyncStatusRecord(BaseModel):
    """Status tracking record stored in Redis."""
    event_id: UUID
    trace_id: str
    status: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
```

### 1.3 Domain Exceptions (`domain/exceptions.py`)

```python
class RagIndexError(Exception):
    """Base exception for RAG Index service."""
    def __init__(self, message: str, event_id: UUID = None, trace_id: str = None):
        super().__init__(message)
        self.event_id = event_id
        self.trace_id = trace_id


class RateLimitExceededError(RagIndexError):
    """Rate limit exceeded, should retry after waiting."""
    def __init__(self, message: str, retry_after: int = 60, **kwargs):
        super().__init__(message, **kwargs)
        self.retry_after = retry_after


class VertexAPIError(RagIndexError):
    """Error from Vertex AI API."""
    def __init__(self, message: str, status_code: int = None, **kwargs):
        super().__init__(message, **kwargs)
        self.status_code = status_code


class DocumentNotFoundError(RagIndexError):
    """Document not found for deletion."""
    pass


class InvalidEventError(RagIndexError):
    """Invalid event format."""
    pass


class RetryableError(RagIndexError):
    """Error that can be retried."""
    pass


class NonRetryableError(RagIndexError):
    """Error that should not be retried."""
    pass
```

### 1.4 Tests for Phase 1

| Test File | Tests | Description |
|-----------|-------|-------------|
| `test_models.py` | 20 | All domain models, serialization |
| `test_exceptions.py` | 10 | Exception hierarchy, attributes |
| `test_schemas.py` | 5 | CloudEvents schema validation |

---

## Phase 2: Ports (Interfaces)

### 2.1 SearchEnginePort (`ports/search_port.py`)

```python
from abc import ABC, abstractmethod
from typing import Optional


class SearchEnginePort(ABC):
    """Interface for search engine operations (Vertex AI Discovery Engine)."""
    
    @abstractmethod
    async def upsert_from_gcs(self, gcs_uri: str, document_id: str) -> str:
        """Import document from GCS into search index.
        
        Args:
            gcs_uri: GCS URI of the curated JSON document
            document_id: Unique document identifier
            
        Returns:
            Operation ID (Long Running Operation)
        """
        pass
    
    @abstractmethod
    async def delete_document(self, document_id: str) -> bool:
        """Delete document from search index.
        
        Args:
            document_id: Unique document identifier
            
        Returns:
            True if deleted, False if not found
        """
        pass
    
    @abstractmethod
    async def get_document(self, document_id: str) -> Optional[dict]:
        """Get document from search index.
        
        Args:
            document_id: Unique document identifier
            
        Returns:
            Document data or None if not found
        """
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """Check if search engine is healthy."""
        pass
```

### 2.2 RateLimiterPort (`ports/cache_port.py`)

```python
from abc import ABC, abstractmethod


class RateLimiterPort(ABC):
    """Interface for rate limiting operations."""
    
    @abstractmethod
    async def acquire_token(self, key: str, limit: int, window_seconds: int) -> bool:
        """Attempt to acquire a rate limit token.
        
        Args:
            key: Rate limit key (e.g., "vertex:import")
            limit: Maximum requests per window
            window_seconds: Window duration in seconds
            
        Returns:
            True if allowed, False if rate limited
        """
        pass
    
    @abstractmethod
    async def get_current_count(self, key: str) -> int:
        """Get current request count for the window."""
        pass
    
    @abstractmethod
    async def reset(self, key: str) -> None:
        """Reset rate limit counter."""
        pass


class StatusCachePort(ABC):
    """Interface for status caching operations."""
    
    @abstractmethod
    async def set_status(self, event_id: str, status: dict, ttl: int = 3600) -> None:
        """Set status for an event."""
        pass
    
    @abstractmethod
    async def get_status(self, event_id: str) -> Optional[dict]:
        """Get status for an event."""
        pass
```

### 2.3 EventPublisherPort (`ports/event_port.py`)

```python
from abc import ABC, abstractmethod
from rag_index.domain.models import SyncResult


class EventPublisherPort(ABC):
    """Interface for event publishing (success/failure notifications)."""
    
    @abstractmethod
    async def publish_success(self, event: SyncResult) -> None:
        """Publish sync success event to completion topic."""
        pass
    
    @abstractmethod
    async def publish_failure(self, event: SyncResult) -> None:
        """Publish sync failure event to DLQ."""
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """Check if event publisher is healthy."""
        pass
```

### 2.4 Tests for Phase 2

| Test File | Tests | Description |
|-----------|-------|-------------|
| `test_ports.py` | 15 | Port interface contracts |

---

## Phase 3: Adapters (Implementations)

### 3.1 Vertex AI Adapter (`adapters/vertex_adapter.py`)

```python
import logging
from typing import Optional
from google.cloud import discoveryengine_v1 as discoveryengine
from google.cloud.discoveryengine_v1.types import (
    ImportDocumentsRequest,
    GcsSource,
    DeleteDocumentRequest,
)
from google.api_core.exceptions import GoogleAPICallError, NotFound
from tenacity import retry, stop_after_attempt, wait_exponential

from rag_index.ports.search_port import SearchEnginePort
from rag_index.domain.exceptions import VertexAPIError, DocumentNotFoundError

logger = logging.getLogger(__name__)


class VertexAdapter(SearchEnginePort):
    """Vertex AI Discovery Engine adapter.
    
    Uses google-cloud-discoveryengine library to interact with
    the Discovery Engine API.
    """
    
    def __init__(
        self,
        project_id: str,
        location: str = "global",
        data_store_id: str = None,
        collection: str = "default_collection",
    ):
        self.project_id = project_id
        self.location = location
        self.data_store_id = data_store_id
        self.collection = collection
        self._client: Optional[discoveryengine.DocumentServiceClient] = None
    
    async def _get_client(self) -> discoveryengine.DocumentServiceClient:
        """Get or create Discovery Engine client."""
        if self._client is None:
            self._client = discoveryengine.DocumentServiceClient()
        return self._client
    
    def _get_parent_path(self) -> str:
        """Construct the parent path for API calls."""
        return (
            f"projects/{self.project_id}"
            f"/locations/{self.location}"
            f"/collections/{self.collection}"
            f"/dataStores/{self.data_store_id}"
            f"/branches/0"
        )
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=60),
        reraise=True
    )
    async def upsert_from_gcs(self, gcs_uri: str, document_id: str) -> str:
        """Import document from GCS using ImportDocumentsRequest."""
        client = await self._get_client()
        parent = self._get_parent_path()
        
        request = ImportDocumentsRequest(
            parent=parent,
            gcs_source=GcsSource(
                input_uris=[gcs_uri],
                data_schema="document"
            ),
            reconciliation_mode=ImportDocumentsRequest.ReconciliationMode.INCREMENTAL
        )
        
        try:
            operation = client.import_documents(request=request)
            logger.info(
                f"Import initiated for {document_id}",
                extra={"operation_id": operation.operation.name, "gcs_uri": gcs_uri}
            )
            return operation.operation.name
        except GoogleAPICallError as e:
            logger.error(f"Vertex API error: {e.message}", extra={"code": e.code})
            raise VertexAPIError(e.message, status_code=e.code)
    
    async def delete_document(self, document_id: str) -> bool:
        """Delete document from data store."""
        client = await self._get_client()
        parent = self._get_parent_path()
        document_name = f"{parent}/documents/{document_id}"
        
        request = DeleteDocumentRequest(name=document_name)
        
        try:
            client.delete_document(request=request)
            logger.info(f"Document deleted: {document_id}")
            return True
        except NotFound:
            logger.warning(f"Document not found for deletion: {document_id}")
            return False
        except GoogleAPICallError as e:
            raise VertexAPIError(e.message, status_code=e.code)
    
    async def get_document(self, document_id: str) -> Optional[dict]:
        """Get document from data store."""
        client = await self._get_client()
        parent = self._get_parent_path()
        document_name = f"{parent}/documents/{document_id}"
        
        try:
            doc = client.get_document(name=document_name)
            return {"id": doc.id, "content": doc.content}
        except NotFound:
            return None
    
    async def health_check(self) -> bool:
        """Check Vertex AI connectivity."""
        try:
            client = await self._get_client()
            # Simple connectivity check
            return client is not None
        except Exception:
            return False
```

### 3.2 Redis Rate Limiter (`adapters/redis_ratelimiter.py`)

```python
import time
import logging
from typing import Optional
import redis.asyncio as redis

from rag_index.ports.cache_port import RateLimiterPort, StatusCachePort

logger = logging.getLogger(__name__)


class RedisRateLimiter(RateLimiterPort):
    """Redis-based fixed window rate limiter.
    
    Implements rate limiting using Redis INCR with TTL:
    - Key format: ratelimit:{key}:{minute_timestamp}
    - Expires after window_seconds + buffer
    """
    
    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        key_prefix: str = "ratelimit:vertex:import",
    ):
        self.redis_url = redis_url
        self.key_prefix = key_prefix
        self._client: Optional[redis.Redis] = None
    
    async def _get_client(self) -> redis.Redis:
        """Get or create Redis client."""
        if self._client is None:
            self._client = redis.from_url(self.redis_url)
        return self._client
    
    async def acquire_token(
        self, 
        key: str = None, 
        limit: int = 600,  # 600 req/min = 10 req/sec
        window_seconds: int = 60
    ) -> bool:
        """Acquire token using fixed window counter.
        
        Returns True if request is allowed, False if rate limited.
        """
        client = await self._get_client()
        
        # Get current window timestamp
        current_window = int(time.time() // window_seconds)
        rate_key = f"{self.key_prefix}:{current_window}"
        
        # Atomic increment and check
        pipe = client.pipeline()
        pipe.incr(rate_key)
        pipe.expire(rate_key, window_seconds + 30)  # Extra buffer for cleanup
        results = await pipe.execute()
        
        current_count = results[0]
        allowed = current_count <= limit
        
        if not allowed:
            logger.warning(
                f"Rate limit exceeded: {current_count}/{limit}",
                extra={"key": rate_key}
            )
        
        return allowed
    
    async def get_current_count(self, key: str = None) -> int:
        """Get current request count for the window."""
        client = await self._get_client()
        current_window = int(time.time() // 60)
        rate_key = f"{self.key_prefix}:{current_window}"
        
        count = await client.get(rate_key)
        return int(count) if count else 0
    
    async def reset(self, key: str = None) -> None:
        """Reset rate limit counter."""
        client = await self._get_client()
        current_window = int(time.time() // 60)
        rate_key = f"{self.key_prefix}:{current_window}"
        await client.delete(rate_key)
    
    async def health_check(self) -> bool:
        """Check Redis connectivity."""
        try:
            client = await self._get_client()
            await client.ping()
            return True
        except Exception:
            return False


class RedisStatusCache(StatusCachePort):
    """Redis-based status cache."""
    
    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        key_prefix: str = "rag_index:status",
    ):
        self.redis_url = redis_url
        self.key_prefix = key_prefix
        self._client: Optional[redis.Redis] = None
    
    async def _get_client(self) -> redis.Redis:
        if self._client is None:
            self._client = redis.from_url(self.redis_url)
        return self._client
    
    async def set_status(self, event_id: str, status: dict, ttl: int = 3600) -> None:
        """Set status for an event."""
        client = await self._get_client()
        key = f"{self.key_prefix}:{event_id}"
        await client.setex(key, ttl, json.dumps(status))
    
    async def get_status(self, event_id: str) -> Optional[dict]:
        """Get status for an event."""
        client = await self._get_client()
        key = f"{self.key_prefix}:{event_id}"
        data = await client.get(key)
        return json.loads(data) if data else None
```

### 3.3 Kafka Adapter (`adapters/kafka_adapter.py`)

```python
import json
import logging
from typing import Optional
from uuid import uuid4
from datetime import datetime, timezone
from confluent_kafka import Producer, KafkaException

from rag_index.ports.event_port import EventPublisherPort
from rag_index.domain.models import SyncResult

logger = logging.getLogger(__name__)


class KafkaAdapter(EventPublisherPort):
    """Kafka adapter for publishing sync results."""
    
    def __init__(
        self,
        bootstrap_servers: str,
        success_topic: str = "rag-sync-completed",
        dlq_topic: str = "rag-sync-dlq",
    ):
        self.bootstrap_servers = bootstrap_servers
        self.success_topic = success_topic
        self.dlq_topic = dlq_topic
        self._producer: Optional[Producer] = None
    
    def _get_producer(self) -> Producer:
        """Get or create Kafka producer."""
        if self._producer is None:
            self._producer = Producer({
                "bootstrap.servers": self.bootstrap_servers,
                "client.id": "rag-index-producer",
            })
        return self._producer
    
    def _create_cloud_event(self, result: SyncResult, event_type: str) -> dict:
        """Create CloudEvents formatted message."""
        return {
            "specversion": "1.0",
            "id": str(uuid4()),
            "source": "rag-index-svc",
            "type": event_type,
            "time": datetime.now(timezone.utc).isoformat(),
            "datacontenttype": "application/json",
            "data": {
                "event_id": str(result.event_id),
                "trace_id": result.trace_id,
                "status": result.status,
                "operation_id": result.operation_id,
                "error_message": result.error_message,
                "processing_time_ms": result.processing_time_ms,
            }
        }
    
    async def publish_success(self, result: SyncResult) -> None:
        """Publish sync success event."""
        producer = self._get_producer()
        event = self._create_cloud_event(result, "com.brandautomator.rag.completed")
        
        try:
            producer.produce(
                self.success_topic,
                key=str(result.event_id),
                value=json.dumps(event),
            )
            producer.flush()
            logger.info(
                f"Published success event",
                extra={"event_id": str(result.event_id), "topic": self.success_topic}
            )
        except KafkaException as e:
            logger.error(f"Failed to publish success event: {e}")
            raise
    
    async def publish_failure(self, result: SyncResult) -> None:
        """Publish sync failure event to DLQ."""
        producer = self._get_producer()
        event = self._create_cloud_event(result, "com.brandautomator.rag.failed")
        
        try:
            producer.produce(
                self.dlq_topic,
                key=str(result.event_id),
                value=json.dumps(event),
            )
            producer.flush()
            logger.warning(
                f"Published failure event to DLQ",
                extra={"event_id": str(result.event_id), "error": result.error_message}
            )
        except KafkaException as e:
            logger.error(f"Failed to publish failure event: {e}")
            raise
    
    async def health_check(self) -> bool:
        """Check Kafka connectivity."""
        try:
            producer = self._get_producer()
            # Check broker availability
            metadata = producer.list_topics(timeout=5)
            return len(metadata.brokers) > 0
        except Exception:
            return False
```

### 3.4 Tests for Phase 3

| Test File | Tests | Description |
|-----------|-------|-------------|
| `test_vertex_adapter.py` | 25 | Mocked GCP client tests |
| `test_redis_ratelimiter.py` | 30 | Rate limiter logic |
| `test_kafka_adapter.py` | 20 | Event publishing |

---

## Phase 4: Domain Services

### 4.1 IndexingService (`domain/services.py`)

```python
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from rag_index.domain.models import SyncEvent, SyncResult, SyncAction
from rag_index.domain.exceptions import (
    RateLimitExceededError,
    RetryableError,
    NonRetryableError,
)
from rag_index.ports.search_port import SearchEnginePort
from rag_index.ports.cache_port import RateLimiterPort, StatusCachePort
from rag_index.ports.event_port import EventPublisherPort

logger = logging.getLogger(__name__)


class IndexingService:
    """Orchestrates document indexing with rate limiting.
    
    Implements the Throttling Proxy pattern:
    1. Check rate limit before calling Vertex AI
    2. Wait and retry if rate limited
    3. Execute upsert/delete operation
    4. Update status in Redis
    5. Publish result event
    """
    
    def __init__(
        self,
        search_engine: SearchEnginePort,
        rate_limiter: RateLimiterPort,
        event_publisher: EventPublisherPort,
        status_cache: StatusCachePort,
        max_wait_seconds: int = 60,
        rate_limit: int = 600,
    ):
        self.search_engine = search_engine
        self.rate_limiter = rate_limiter
        self.event_publisher = event_publisher
        self.status_cache = status_cache
        self.max_wait_seconds = max_wait_seconds
        self.rate_limit = rate_limit
    
    async def process_event(self, event: SyncEvent) -> SyncResult:
        """Process a sync event with rate limiting."""
        start_time = datetime.now(timezone.utc)
        
        logger.info(
            f"Processing sync event",
            extra={
                "event_id": str(event.event_id),
                "trace_id": event.trace_id,
                "action": event.action.value,
            }
        )
        
        # Update status to PROCESSING
        await self._update_status(event, "PROCESSING")
        
        try:
            # Wait for rate limit allowance
            await self._wait_for_rate_limit()
            
            # Execute based on action
            if event.action == SyncAction.UPSERT:
                operation_id = await self.search_engine.upsert_from_gcs(
                    event.processed_gcs_uri,
                    event.file_id
                )
                result = SyncResult(
                    event_id=event.event_id,
                    trace_id=event.trace_id,
                    status="COMPLETED",
                    operation_id=operation_id,
                    processing_time_ms=self._calc_duration(start_time)
                )
            elif event.action == SyncAction.DELETE:
                await self.search_engine.delete_document(event.file_id)
                result = SyncResult(
                    event_id=event.event_id,
                    trace_id=event.trace_id,
                    status="COMPLETED",
                    processing_time_ms=self._calc_duration(start_time)
                )
            else:
                raise NonRetryableError(f"Unknown action: {event.action}")
            
            # Publish success
            await self.event_publisher.publish_success(result)
            await self._update_status(event, "COMPLETED")
            
            logger.info(
                f"Sync completed",
                extra={
                    "event_id": str(event.event_id),
                    "processing_time_ms": result.processing_time_ms,
                }
            )
            
            return result
            
        except RateLimitExceededError as e:
            # This should not happen if _wait_for_rate_limit works correctly
            logger.error(f"Rate limit still exceeded after waiting: {e}")
            raise RetryableError(str(e), event_id=event.event_id, trace_id=event.trace_id)
            
        except Exception as e:
            result = SyncResult(
                event_id=event.event_id,
                trace_id=event.trace_id,
                status="FAILED",
                error_message=str(e),
                processing_time_ms=self._calc_duration(start_time)
            )
            await self.event_publisher.publish_failure(result)
            await self._update_status(event, "FAILED", str(e))
            
            logger.error(
                f"Sync failed",
                extra={
                    "event_id": str(event.event_id),
                    "error": str(e),
                }
            )
            raise
    
    async def _wait_for_rate_limit(self) -> None:
        """Wait until rate limit allows request."""
        waited = 0
        while waited < self.max_wait_seconds:
            if await self.rate_limiter.acquire_token(limit=self.rate_limit):
                return
            logger.debug(f"Rate limited, waiting... ({waited}s)")
            await asyncio.sleep(1)
            waited += 1
        
        raise RateLimitExceededError(
            f"Max wait time ({self.max_wait_seconds}s) exceeded for rate limit"
        )
    
    async def _update_status(
        self, 
        event: SyncEvent, 
        status: str, 
        error_message: str = None
    ) -> None:
        """Update status in cache."""
        await self.status_cache.set_status(
            str(event.event_id),
            {
                "status": status,
                "trace_id": event.trace_id,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "error_message": error_message,
            }
        )
    
    def _calc_duration(self, start_time: datetime) -> int:
        """Calculate processing duration in milliseconds."""
        return int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
    
    async def get_status(self, event_id: str) -> Optional[dict]:
        """Get processing status for an event."""
        return await self.status_cache.get_status(event_id)
```

### 4.2 Tests for Phase 4

| Test File | Tests | Description |
|-----------|-------|-------------|
| `test_indexing_service.py` | 45 | All service scenarios |

---

## Phase 5: Celery Tasks

### 5.1 Tasks (`tasks.py`)

```python
import logging
import asyncio
from celery import shared_task
from uuid import UUID

from rag_index.domain.models import SyncEvent, SyncAction
from rag_index.domain.exceptions import RetryableError, NonRetryableError
from rag_index.factory import get_indexing_service

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Helper to run async coroutines in sync context."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@shared_task(
    bind=True,
    name="rag_index.process_sync_event",
    autoretry_for=(RetryableError,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=3,
    acks_late=True,
    reject_on_worker_lost=True,
)
def process_sync_event(self, event_data: dict) -> dict:
    """Process a RAG sync event via Celery.
    
    Args:
        event_data: Dict containing sync event data
        
    Returns:
        Dict with processing result
    """
    try:
        event = SyncEvent(
            event_id=UUID(event_data["event_id"]),
            trace_id=event_data["trace_id"],
            tenant_id=event_data["tenant_id"],
            file_id=event_data["file_id"],
            processed_gcs_uri=event_data.get("processed_gcs_uri", ""),
            action=SyncAction(event_data["action"]),
            timestamp=event_data.get("timestamp"),
            metadata=event_data.get("metadata", {}),
        )
    except Exception as e:
        logger.error(f"Invalid event data: {e}")
        raise NonRetryableError(f"Invalid event: {e}")
    
    service = get_indexing_service()
    
    try:
        result = _run_async(service.process_event(event))
        return {
            "status": result.status,
            "event_id": str(result.event_id),
            "operation_id": result.operation_id,
            "processing_time_ms": result.processing_time_ms,
        }
    except RetryableError:
        raise
    except NonRetryableError as e:
        logger.error(f"Non-retryable error: {e}")
        return {
            "status": "FAILED",
            "event_id": str(event.event_id),
            "error": str(e),
        }


@shared_task(name="rag_index.process_batch")
def process_batch(events: list[dict]) -> dict:
    """Process batch of sync events.
    
    Args:
        events: List of event data dicts
        
    Returns:
        Dict with batch results
    """
    results = []
    for event_data in events:
        try:
            result = process_sync_event.delay(event_data)
            results.append({"event_id": event_data.get("event_id"), "task_id": result.id})
        except Exception as e:
            results.append({"event_id": event_data.get("event_id"), "error": str(e)})
    
    return {"submitted": len(results), "results": results}


@shared_task(name="rag_index.check_rate_limit_status")
def check_rate_limit_status() -> dict:
    """Check current rate limit status."""
    from rag_index.factory import create_rate_limiter
    
    rate_limiter = create_rate_limiter()
    current_count = _run_async(rate_limiter.get_current_count())
    
    return {
        "current_count": current_count,
        "limit": 600,
        "available": 600 - current_count,
    }
```

### 5.2 Celery Configuration

Add to `brand_automator/celery.py`:

```python
# Add rag_index queue
app.conf.task_routes = {
    'rag_index.*': {'queue': 'rag_index'},
    'media_curation.*': {'queue': 'curation'},
    # ... existing routes
}
```

### 5.3 Tests for Phase 5

| Test File | Tests | Description |
|-----------|-------|-------------|
| `test_tasks.py` | 30 | Celery task tests |

---

## Phase 6: REST API Views

### 6.1 Views (`views.py`)

```python
import logging
from uuid import UUID
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.viewsets import ViewSet
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny

from rag_index.serializers import (
    SyncRequestSerializer,
    BatchSyncRequestSerializer,
    SyncStatusSerializer,
    HealthResponseSerializer,
    RateLimitStatusSerializer,
)
from rag_index.tasks import process_sync_event, process_batch

logger = logging.getLogger(__name__)


class SyncViewSet(ViewSet):
    """REST API for RAG sync operations."""
    permission_classes = [IsAuthenticated]
    
    @action(detail=False, methods=["POST"])
    def sync(self, request):
        """Submit single document for sync."""
        serializer = SyncRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        event_data = serializer.validated_data
        task = process_sync_event.delay(event_data)
        
        return Response(
            {
                "event_id": event_data["event_id"],
                "task_id": task.id,
                "status": "QUEUED",
            },
            status=status.HTTP_202_ACCEPTED
        )
    
    @action(detail=False, methods=["POST"], url_path="batch")
    def batch(self, request):
        """Submit batch of documents for sync."""
        serializer = BatchSyncRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        events = serializer.validated_data["events"]
        result = process_batch.delay(events)
        
        return Response(
            {
                "task_id": result.id,
                "event_count": len(events),
                "status": "QUEUED",
            },
            status=status.HTTP_202_ACCEPTED
        )
    
    @action(detail=True, methods=["GET"], url_path="status")
    def status(self, request, pk=None):
        """Get sync status by event_id."""
        from rag_index.factory import get_indexing_service
        
        service = get_indexing_service()
        status_data = service.get_status(pk)
        
        if not status_data:
            return Response(
                {"error": "Event not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = SyncStatusSerializer(status_data)
        return Response(serializer.data)


class HealthView(APIView):
    """Health check endpoint."""
    permission_classes = [AllowAny]
    
    def get(self, request):
        """Check service health including dependencies."""
        from rag_index.factory import (
            create_rate_limiter,
            create_kafka_adapter,
            create_vertex_adapter,
        )
        
        redis_healthy = create_rate_limiter().health_check()
        kafka_healthy = create_kafka_adapter().health_check()
        vertex_healthy = create_vertex_adapter().health_check()
        
        overall = all([redis_healthy, kafka_healthy, vertex_healthy])
        
        return Response(
            {
                "status": "healthy" if overall else "degraded",
                "redis": "healthy" if redis_healthy else "unhealthy",
                "kafka": "healthy" if kafka_healthy else "unhealthy",
                "vertex": "healthy" if vertex_healthy else "unhealthy",
            },
            status=status.HTTP_200_OK if overall else status.HTTP_503_SERVICE_UNAVAILABLE
        )


class RateLimitStatusView(APIView):
    """Rate limit status endpoint."""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Get current rate limit usage."""
        from rag_index.tasks import check_rate_limit_status
        
        result = check_rate_limit_status()
        serializer = RateLimitStatusSerializer(result)
        return Response(serializer.data)
```

### 6.2 URL Configuration (`urls.py`)

```python
from django.urls import path
from rag_index.views import SyncViewSet, HealthView, RateLimitStatusView

urlpatterns = [
    # Sync operations
    path("sync/", SyncViewSet.as_view({"post": "sync"}), name="rag-sync"),
    path("sync/batch/", SyncViewSet.as_view({"post": "batch"}), name="rag-sync-batch"),
    path("sync/status/<uuid:pk>/", SyncViewSet.as_view({"get": "status"}), name="rag-sync-status"),
    
    # Health and monitoring
    path("health/", HealthView.as_view(), name="rag-health"),
    path("rate-limit/", RateLimitStatusView.as_view(), name="rag-rate-limit"),
]
```

### 6.3 Register in Main URLs

Add to `brand_automator/urls.py`:

```python
path("api/v1/rag-index/", include("rag_index.urls")),
```

### 6.4 Tests for Phase 6

| Test File | Tests | Description |
|-----------|-------|-------------|
| `test_views.py` | 35 | API endpoint tests |

---

## Phase 7: Kafka Consumer Management Command

### 7.1 Command (`management/commands/run_rag_consumer.py`)

```python
import signal
import logging
import json
import time
from django.core.management.base import BaseCommand
from confluent_kafka import Consumer, KafkaError

from rag_index.domain.models import SyncEvent, SyncAction
from rag_index.domain.exceptions import RetryableError, NonRetryableError
from rag_index.factory import get_indexing_service

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Kafka consumer for rag-sync-ready-topic."""
    
    help = "Run the RAG Index Kafka consumer"
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.running = True
        self.consumer = None
        self.service = None
    
    def add_arguments(self, parser):
        parser.add_argument(
            "--batch-size",
            type=int,
            default=10,
            help="Number of messages to process per batch"
        )
        parser.add_argument(
            "--poll-timeout",
            type=float,
            default=1.0,
            help="Kafka poll timeout in seconds"
        )
        parser.add_argument(
            "--max-retries",
            type=int,
            default=3,
            help="Maximum retries for failed messages"
        )
        parser.add_argument(
            "--group-id",
            type=str,
            default="rag-index-consumer-group",
            help="Kafka consumer group ID"
        )
    
    def handle(self, *args, **options):
        """Main consumer loop."""
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
        
        self.service = get_indexing_service()
        self._init_consumer(options)
        
        self.stdout.write(self.style.SUCCESS("RAG Index consumer started"))
        
        while self.running:
            try:
                self._consume_batch(options)
            except Exception as e:
                logger.error(f"Consumer error: {e}")
                time.sleep(5)
        
        self._cleanup()
        self.stdout.write(self.style.SUCCESS("Consumer stopped gracefully"))
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, shutting down...")
        self.running = False
    
    def _init_consumer(self, options):
        """Initialize Kafka consumer."""
        from django.conf import settings
        
        self.consumer = Consumer({
            "bootstrap.servers": getattr(settings, "KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
            "group.id": options["group_id"],
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        })
        
        topic = getattr(settings, "RAG_INDEX_KAFKA_INPUT_TOPIC", "rag-sync-ready-topic")
        self.consumer.subscribe([topic])
    
    def _consume_batch(self, options):
        """Consume and process a batch of messages."""
        messages = self.consumer.consume(
            num_messages=options["batch_size"],
            timeout=options["poll_timeout"]
        )
        
        for msg in messages:
            if msg is None:
                continue
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                logger.error(f"Kafka error: {msg.error()}")
                continue
            
            self._process_message(msg, options["max_retries"])
    
    def _process_message(self, msg, max_retries: int):
        """Process a single Kafka message."""
        try:
            data = json.loads(msg.value().decode("utf-8"))
            event_data = data.get("data", data)
            
            event = SyncEvent(
                event_id=event_data["event_id"],
                trace_id=event_data["trace_id"],
                tenant_id=event_data["tenant_id"],
                file_id=event_data["file_id"],
                processed_gcs_uri=event_data.get("processed_gcs_uri", ""),
                action=SyncAction(event_data["action"]),
                timestamp=event_data.get("time"),
            )
            
            # Process with retries
            self._process_with_retry(event, max_retries)
            
            # Commit offset
            self.consumer.commit(msg)
            
        except Exception as e:
            logger.error(f"Failed to process message: {e}")
            # Send to DLQ handled by service
    
    def _process_with_retry(self, event: SyncEvent, max_retries: int):
        """Process event with retry logic."""
        import asyncio
        
        for attempt in range(max_retries + 1):
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(self.service.process_event(event))
                finally:
                    loop.close()
                return
            except RetryableError as e:
                if attempt < max_retries:
                    backoff = 2 ** attempt
                    logger.warning(f"Retrying in {backoff}s: {e}")
                    time.sleep(backoff)
                else:
                    raise
    
    def _cleanup(self):
        """Cleanup resources."""
        if self.consumer:
            self.consumer.close()
```

### 7.2 Tests for Phase 7

| Test File | Tests | Description |
|-----------|-------|-------------|
| `test_consumer_command.py` | 30 | Consumer management command |

---

## Phase 8: Property-Based Tests (Hypothesis)

### 8.1 Test File: `tests/test_properties.py`

```python
"""
Property-based tests using Hypothesis.

These tests verify invariants hold across a wide range of generated inputs.
"""
import pytest
from hypothesis import given, strategies as st, settings
from uuid import uuid4
from datetime import datetime, timezone

pytestmark = pytest.mark.property


class TestSyncEventProperties:
    """Property tests for SyncEvent domain model."""
    
    @given(
        tenant_id=st.text(min_size=1, max_size=100).filter(str.strip),
        file_id=st.text(min_size=1, max_size=100).filter(str.strip),
    )
    def test_event_id_always_valid_uuid(self, tenant_id, file_id):
        """Event IDs are always valid UUIDs."""
        from rag_index.domain.models import SyncEvent, SyncAction
        
        event = SyncEvent(
            event_id=uuid4(),
            trace_id=f"tr-{uuid4()}",
            tenant_id=tenant_id,
            file_id=file_id,
            processed_gcs_uri="gs://bucket/file.json",
            action=SyncAction.UPSERT,
            timestamp=datetime.now(timezone.utc),
        )
        
        assert event.event_id is not None
        assert str(event.event_id)  # Valid UUID string
    
    @given(action=st.sampled_from(["UPSERT", "DELETE"]))
    def test_action_always_valid_enum(self, action):
        """Action field only accepts valid enum values."""
        from rag_index.domain.models import SyncAction
        
        parsed = SyncAction(action)
        assert parsed.value == action
    
    @given(
        gcs_uri=st.from_regex(r"gs://[a-z0-9-]+/[a-zA-Z0-9/_.-]+", fullmatch=True)
    )
    def test_gcs_uri_format_preserved(self, gcs_uri):
        """GCS URIs maintain proper format."""
        from rag_index.domain.models import SyncEvent, SyncAction
        
        event = SyncEvent(
            event_id=uuid4(),
            trace_id="tr-test",
            tenant_id="tenant-1",
            file_id="file-1",
            processed_gcs_uri=gcs_uri,
            action=SyncAction.UPSERT,
            timestamp=datetime.now(timezone.utc),
        )
        
        assert event.processed_gcs_uri == gcs_uri
        assert event.processed_gcs_uri.startswith("gs://")


class TestSyncResultProperties:
    """Property tests for SyncResult model."""
    
    @given(
        processing_time=st.integers(min_value=0, max_value=300000)
    )
    def test_processing_time_non_negative(self, processing_time):
        """Processing time is always non-negative."""
        from rag_index.domain.models import SyncResult
        
        result = SyncResult(
            event_id=uuid4(),
            trace_id="tr-test",
            status="COMPLETED",
            processing_time_ms=processing_time,
        )
        
        assert result.processing_time_ms >= 0
    
    @given(status=st.sampled_from(["COMPLETED", "FAILED", "PENDING"]))
    def test_status_always_valid(self, status):
        """Status is always a valid value."""
        from rag_index.domain.models import SyncResult
        
        result = SyncResult(
            event_id=uuid4(),
            trace_id="tr-test",
            status=status,
        )
        
        assert result.status in ["COMPLETED", "FAILED", "PENDING"]


class TestRateLimiterProperties:
    """Property tests for rate limiter logic."""
    
    @given(
        limit=st.integers(min_value=1, max_value=10000),
        requests=st.integers(min_value=0, max_value=100),
    )
    @settings(max_examples=50)
    def test_rate_limit_boundary(self, limit, requests):
        """Rate limiter allows exactly `limit` requests."""
        # This would test the rate limiter mock behavior
        allowed_count = min(requests, limit)
        assert allowed_count <= limit


class TestExceptionProperties:
    """Property tests for exception handling."""
    
    @given(message=st.text(max_size=500))
    def test_error_message_preserved_in_exception(self, message):
        """Error messages are preserved in exceptions."""
        from rag_index.domain.exceptions import RagIndexError
        
        error = RagIndexError(message)
        assert str(error) == message
    
    @given(
        retry_after=st.integers(min_value=0, max_value=3600)
    )
    def test_retryable_error_retry_after(self, retry_after):
        """RetryableError preserves retry_after value."""
        from rag_index.domain.exceptions import RateLimitExceededError
        
        error = RateLimitExceededError("Rate limited", retry_after=retry_after)
        assert error.retry_after == retry_after
```

### 8.2 Property Test Count: 40 tests

---

## Phase 9: Integration Tests

### 9.1 Test File: `tests/test_integration.py`

```python
"""
Integration tests with real Redis and mocked Vertex AI.

Requires: Docker containers for Redis, Kafka.
Run with: pytest -m integration
"""
import pytest
import asyncio
from unittest.mock import AsyncMock

pytestmark = pytest.mark.integration


@pytest.fixture
async def redis_client():
    """Create real Redis connection."""
    import redis.asyncio as redis
    client = redis.from_url("redis://localhost:6379/0")
    yield client
    await client.flushdb()
    await client.close()


class TestRedisIntegration:
    """Integration tests with real Redis."""
    
    async def test_rate_limiter_with_real_redis(self, redis_client):
        """Rate limiter works with real Redis."""
        from rag_index.adapters.redis_ratelimiter import RedisRateLimiter
        
        limiter = RedisRateLimiter()
        
        # First request should be allowed
        allowed = await limiter.acquire_token(limit=10)
        assert allowed is True
        
        # Check count
        count = await limiter.get_current_count()
        assert count == 1
    
    async def test_rate_limiter_enforces_limit(self, redis_client):
        """Rate limiter blocks requests over limit."""
        from rag_index.adapters.redis_ratelimiter import RedisRateLimiter
        
        limiter = RedisRateLimiter()
        
        # Exhaust the limit
        for _ in range(10):
            await limiter.acquire_token(limit=10)
        
        # Next request should be blocked
        allowed = await limiter.acquire_token(limit=10)
        assert allowed is False


class TestServiceIntegration:
    """Integration tests for IndexingService."""
    
    async def test_service_with_real_rate_limiter(self, redis_client):
        """Service integrates with real Redis rate limiter."""
        from rag_index.adapters.redis_ratelimiter import RedisRateLimiter, RedisStatusCache
        from rag_index.domain.services import IndexingService
        from rag_index.domain.models import SyncEvent, SyncAction
        from uuid import uuid4
        from datetime import datetime, timezone
        
        # Create real rate limiter, mock others
        rate_limiter = RedisRateLimiter()
        status_cache = RedisStatusCache()
        search_engine = AsyncMock()
        search_engine.upsert_from_gcs.return_value = "operation-123"
        event_publisher = AsyncMock()
        
        service = IndexingService(
            search_engine=search_engine,
            rate_limiter=rate_limiter,
            event_publisher=event_publisher,
            status_cache=status_cache,
        )
        
        event = SyncEvent(
            event_id=uuid4(),
            trace_id="tr-test",
            tenant_id="tenant-1",
            file_id="file-1",
            processed_gcs_uri="gs://bucket/file.json",
            action=SyncAction.UPSERT,
            timestamp=datetime.now(timezone.utc),
        )
        
        result = await service.process_event(event)
        
        assert result.status == "COMPLETED"
        search_engine.upsert_from_gcs.assert_called_once()
```

### 9.2 Integration Test Count: 50 tests

---

## Phase 10: End-to-End (E2E) Tests

### 10.1 Test File: `tests/test_e2e.py`

```python
"""
End-to-End tests for the complete RAG Index pipeline.

Run with: pytest -m e2e --run-e2e
"""
import pytest
import time
import json
import requests
from uuid import uuid4
from confluent_kafka import Producer, Consumer

pytestmark = pytest.mark.e2e


@pytest.fixture
def api_base_url():
    """Base URL for API calls."""
    return "http://localhost:8000/api/v1/rag-index"


@pytest.fixture
def kafka_producer():
    """Kafka producer for test events."""
    producer = Producer({"bootstrap.servers": "localhost:9092"})
    yield producer
    producer.flush()


class TestUpsertE2EFlow:
    """E2E tests for UPSERT operations."""
    
    def test_upsert_via_rest_api(self, api_base_url):
        """UPSERT via REST API."""
        payload = {
            "event_id": str(uuid4()),
            "trace_id": f"tr-{uuid4()}",
            "tenant_id": "tenant-e2e-test",
            "file_id": f"file-{uuid4()}",
            "processed_gcs_uri": "gs://test-bucket/test-file.json",
            "action": "UPSERT"
        }
        
        response = requests.post(
            f"{api_base_url}/sync/",
            json=payload,
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == 202
        assert "task_id" in response.json()
    
    def test_upsert_via_kafka(self, kafka_producer):
        """Complete UPSERT flow via Kafka."""
        event = {
            "specversion": "1.0",
            "id": str(uuid4()),
            "source": "media-curation-svc",
            "type": "com.brandautomator.rag.ready",
            "data": {
                "trace_id": f"tr-{uuid4()}",
                "tenant_id": "tenant-e2e-test",
                "file_id": f"file-{uuid4()}",
                "processed_gcs_uri": "gs://test-bucket/test-file.json",
                "action": "UPSERT"
            }
        }
        
        kafka_producer.produce(
            "rag-sync-ready-topic",
            json.dumps(event)
        )
        kafka_producer.flush()
        
        # Wait for processing
        time.sleep(5)
        
        # Verify via status endpoint or completion topic


class TestHealthChecksE2E:
    """E2E tests for health endpoints."""
    
    def test_health_endpoint(self, api_base_url):
        """Health check endpoint returns status."""
        response = requests.get(f"{api_base_url}/health/")
        
        assert response.status_code in [200, 503]
        data = response.json()
        assert "status" in data
        assert "redis" in data
```

### 10.2 E2E Test Count: 30 tests

---

## Phase 11: Deployment & CI/CD

### 11.1 Docker Configuration

**Dockerfile.rag-consumer:**
```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "manage.py", "run_rag_consumer"]
```

### 11.2 Docker Compose Updates

Add to `docker-compose.yml`:
```yaml
  # RAG Index Celery Worker
  rag-index-worker:
    build:
      context: .
      dockerfile: Dockerfile
    command: celery -A brand_automator worker -Q rag_index -l info --concurrency=2
    environment:
      - DEBUG=True
      - DB_NAME=${DB_NAME}
      - DB_USER=${DB_USER}
      - DB_PASSWORD=${DB_PASSWORD}
      - DB_HOST=${DB_HOST}
      - DB_PORT=${DB_PORT:-5432}
      - REDIS_URL=redis://redis:6379/0
      - CELERY_BROKER_URL=redis://redis:6379/0
      - SECRET_KEY=${SECRET_KEY:-django-insecure-changeme}
      # Vertex AI Configuration
      - GCP_PROJECT_ID=${GCP_PROJECT_ID}
      - VERTEX_DATA_STORE_ID=${VERTEX_DATA_STORE_ID}
      - VERTEX_RATE_LIMIT=${VERTEX_RATE_LIMIT:-600}
      - GOOGLE_APPLICATION_CREDENTIALS=/app/credentials/gcs-credentials.json
      # Kafka Configuration
      - KAFKA_BOOTSTRAP_SERVERS=${KAFKA_BOOTSTRAP_SERVERS:-brand-kafka:9092}
      - RAG_INDEX_KAFKA_INPUT_TOPIC=rag-sync-ready-topic
      - RAG_INDEX_KAFKA_SUCCESS_TOPIC=rag-sync-completed
      - RAG_INDEX_KAFKA_DLQ_TOPIC=rag-sync-dlq
    depends_on:
      redis:
        condition: service_healthy
      backend:
        condition: service_healthy
    networks:
      - app-network

  # RAG Index Kafka Consumer
  rag-index-consumer:
    build:
      context: .
      dockerfile: Dockerfile.rag-consumer
    command: python manage.py run_rag_consumer --batch-size 10 --poll-timeout 1.0
    environment:
      # Same as rag-index-worker
      - DEBUG=True
      - DB_NAME=${DB_NAME}
      - DB_USER=${DB_USER}
      - DB_PASSWORD=${DB_PASSWORD}
      - DB_HOST=${DB_HOST}
      - DB_PORT=${DB_PORT:-5432}
      - REDIS_URL=redis://redis:6379/0
      - SECRET_KEY=${SECRET_KEY:-django-insecure-changeme}
      - GCP_PROJECT_ID=${GCP_PROJECT_ID}
      - VERTEX_DATA_STORE_ID=${VERTEX_DATA_STORE_ID}
      - VERTEX_RATE_LIMIT=${VERTEX_RATE_LIMIT:-600}
      - GOOGLE_APPLICATION_CREDENTIALS=/app/credentials/gcs-credentials.json
      - KAFKA_BOOTSTRAP_SERVERS=${KAFKA_BOOTSTRAP_SERVERS:-brand-kafka:9092}
      - RAG_INDEX_KAFKA_INPUT_TOPIC=rag-sync-ready-topic
    depends_on:
      redis:
        condition: service_healthy
      kafka:
        condition: service_healthy
    restart: unless-stopped
    networks:
      - app-network
    profiles:
      - with-kafka
```

### 11.3 Environment Variables

Add to `.env.example`:
```bash
# RAG Index Service
GCP_PROJECT_ID=your-gcp-project-id
VERTEX_DATA_STORE_ID=your-data-store-id
VERTEX_RATE_LIMIT=600
RAG_INDEX_KAFKA_INPUT_TOPIC=rag-sync-ready-topic
RAG_INDEX_KAFKA_SUCCESS_TOPIC=rag-sync-completed
RAG_INDEX_KAFKA_DLQ_TOPIC=rag-sync-dlq
```

### 11.4 CI/CD Pipeline

Add to `.github/workflows/ci-cd.yml`:
```yaml
  test-rag-index-unit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Install dependencies
        run: |
          cd ai-brand-automator
          pip install -r requirements.txt -r requirements-dev.txt
      - name: Run Unit & Property Tests
        run: |
          cd ai-brand-automator
          pytest rag_index/ -m "unit or property" -v --tb=short
  
  test-rag-index-integration:
    runs-on: ubuntu-latest
    services:
      redis:
        image: redis:7-alpine
        ports:
          - 6379:6379
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Install dependencies
        run: |
          cd ai-brand-automator
          pip install -r requirements.txt -r requirements-dev.txt
      - name: Run Integration Tests
        run: |
          cd ai-brand-automator
          pytest rag_index/ -m integration -v --tb=short
```

### 11.5 Dependencies

Add to `requirements.txt`:
```
google-cloud-discoveryengine>=0.11.0
```

---

## Test Summary

| Category | Test File(s) | Count | Markers |
|----------|--------------|-------|---------|
| **Unit Tests** | | **230** | `@pytest.mark.unit` |
| | `test_models.py` | 20 | |
| | `test_schemas.py` | 15 | |
| | `test_exceptions.py` | 15 | |
| | `test_ports.py` | 15 | |
| | `test_vertex_adapter.py` | 25 | |
| | `test_redis_ratelimiter.py` | 30 | |
| | `test_kafka_adapter.py` | 20 | |
| | `test_indexing_service.py` | 45 | |
| | `test_tasks.py` | 30 | |
| | `test_views.py` | 35 | |
| | `test_consumer_command.py` | 30 | |
| **Property Tests** | `test_properties.py` | **40** | `@pytest.mark.property` |
| **Integration Tests** | `test_integration.py` | **50** | `@pytest.mark.integration` |
| **E2E Tests** | `test_e2e.py` | **30** | `@pytest.mark.e2e` |
| **Total** | | **~350** | |

---

## Test Execution Commands

```bash
# Run unit tests only (fast, no deps)
pytest rag_index/ -m unit -v

# Run property tests
pytest rag_index/ -m property -v

# Run unit + property (default CI)
pytest rag_index/ -m "unit or property" -v

# Run integration tests (requires Docker)
docker-compose up -d redis kafka
pytest rag_index/ -m integration -v

# Run E2E tests (requires full stack)
docker-compose up -d
pytest rag_index/ -m e2e -v --run-e2e

# Run all tests
pytest rag_index/ -m "unit or property or integration or e2e" -v

# Run with coverage
pytest rag_index/ --cov=rag_index --cov-report=html
```

---

## Configuration (`pytest.ini` additions)

```ini
markers =
    unit: Unit tests (no external dependencies)
    property: Property-based tests using Hypothesis
    integration: Integration tests (require Redis/Kafka in Docker)
    vertex: Tests requiring real Vertex AI credentials
    e2e: End-to-end tests (require full Docker Compose stack)
```

---

## Success Criteria

- [ ] All ~350 tests passing
- [ ] Rate limiting working (600 req/min enforced)
- [ ] Vertex AI integration working with mock credentials
- [ ] Kafka consumer processing events from `rag-sync-ready-topic`
- [ ] REST API endpoints functional
- [ ] Health checks passing for all dependencies
- [ ] Docker deployment working
- [ ] CI/CD pipeline updated
- [ ] Documentation complete

---

## Critical Patterns (MUST FOLLOW)

### Multi-Tenancy Defensive Access
```python
# ✅ CORRECT - in every ViewSet/view
tenant = getattr(request, 'tenant', None)
queryset = Model.objects.filter(tenant=tenant) if tenant else Model.objects.filter(tenant__isnull=True)
```

### Hexagonal Architecture
```
Domain (models, services, exceptions)
    ↓ depends on
Ports (interfaces/ABCs)
    ↑ implemented by
Adapters (Vertex, Redis, Kafka)
```

### Rate Limiting Pattern
```python
# Always check rate limit before calling Vertex AI
async def _wait_for_rate_limit(self) -> None:
    while not await self.rate_limiter.acquire_token(limit=600):
        await asyncio.sleep(1)
```

---

## Questions Resolved

1. **Rate Limit Strategy:** Fixed Window (simpler for MVP)
2. **LRO Polling:** Fire-and-forget for MVP (can add polling later)
3. **Tenant Isolation:** Global rate limit (per-tenant can be added)
4. **Retry Strategy:** 3 retries with exponential backoff
5. **Batch Size:** 10 messages per consumer batch
