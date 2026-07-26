"""
Test fixtures for data ingestion tests.

Provides mock implementations of ports and common test data.
"""

import pytest
from datetime import datetime
from typing import Optional
from uuid import uuid4

from data_ingestion.domain.models import (
    IngestionEvent,
    ProcessedEvent,
    ProcessingStatus,
    EventSource,
    FileMetadata,
)
from data_ingestion.ports.storage_port import StoragePort
from data_ingestion.ports.cache_port import CachePort
from data_ingestion.ports.event_port import EventProducerPort, EventConsumerPort


# =============================================================================
# Mock Port Implementations
# =============================================================================


class MockStoragePort(StoragePort):
    """Mock storage port for testing."""

    def __init__(self):
        self.files: dict[str, bytes] = {}
        self.metadata: dict[str, FileMetadata] = {}
        self.move_calls: list[tuple[str, str]] = []
        self.check_exists_calls: list[str] = []

    def check_exists(self, file_path: str) -> bool:
        self.check_exists_calls.append(file_path)
        return file_path in self.files

    def move_file(self, source_path: str, destination_path: str) -> str:
        self.move_calls.append((source_path, destination_path))
        if source_path not in self.files:
            from data_ingestion.domain.exceptions import FileNotFoundInLandingError

            raise FileNotFoundInLandingError(file_path=source_path)
        self.files[destination_path] = self.files.pop(source_path)
        return destination_path

    def copy_file(self, source_path: str, destination_path: str) -> str:
        if source_path not in self.files:
            from data_ingestion.domain.exceptions import FileNotFoundInLandingError

            raise FileNotFoundInLandingError(file_path=source_path)
        self.files[destination_path] = self.files[source_path]
        return destination_path

    def delete_file(self, file_path: str) -> bool:
        if file_path in self.files:
            del self.files[file_path]
            return True
        return False

    def get_metadata(self, file_path: str) -> Optional[FileMetadata]:
        if file_path not in self.metadata:
            return None
        return self.metadata[file_path]

    def list_files(self, prefix: str, max_results: int = 100) -> list[str]:
        """List files with the given prefix."""
        matching = [
            path
            for path in self.files.keys()
            if path.startswith(prefix) or prefix in path
        ]
        return matching[:max_results]

    def add_file(self, path: str, content: bytes = b"test content") -> None:
        """Helper to add a file to the mock storage."""
        # Parse bucket and object path
        if path.startswith("gs://"):
            parts = path[5:].split("/", 1)
            bucket = parts[0]
            obj_path = parts[1] if len(parts) > 1 else ""
        else:
            bucket = "test-bucket"
            obj_path = path

        self.files[path] = content
        self.metadata[path] = FileMetadata(
            bucket=bucket,
            path=obj_path,
            full_uri=path,
            size_bytes=len(content),
            content_type="application/octet-stream",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            md5_hash="abc123",
        )


class MockCachePort(CachePort):
    """Mock cache port for testing."""

    def __init__(self):
        self.processed: set[str] = set()
        self.statuses: dict[str, dict] = {}
        self.data: dict[str, str] = {}

    def is_duplicate(self, event_id: str, tenant_id: Optional[str] = None) -> bool:
        return event_id in self.processed

    def mark_processed(
        self,
        event_id: str,
        ttl_seconds: Optional[int] = None,
        tenant_id: Optional[str] = None,
    ) -> None:
        self.processed.add(event_id)

    def update_status(
        self,
        trace_id: str,
        status: str,
        ttl_seconds: Optional[int] = None,
        metadata: Optional[dict] = None,
        tenant_id: Optional[str] = None,
    ) -> None:
        self.statuses[trace_id] = {
            "status": status,
            "updated_at": datetime.utcnow().isoformat(),
            "metadata": metadata,
        }

    def get_status(
        self, trace_id: str, tenant_id: Optional[str] = None
    ) -> Optional[dict]:
        return self.statuses.get(trace_id)

    def get(self, key: str) -> Optional[str]:
        return self.data.get(key)

    def set(self, key: str, value: str, ttl_seconds: Optional[int] = None) -> None:
        self.data[key] = value

    def set_with_ttl(self, key: str, value: str, ttl_seconds: int) -> None:
        """Set a key-value pair with TTL (TTL is ignored in mock)."""
        self.data[key] = value

    def delete(self, key: str) -> bool:
        if key in self.data:
            del self.data[key]
            return True
        return False


class MockEventProducerPort(EventProducerPort):
    """Mock event producer port for testing."""

    def __init__(self):
        self.published: list[tuple[str, ProcessedEvent]] = []
        self.published_raw: list[tuple[str, dict]] = []
        self.dlq_messages: list[dict] = []

    def publish(
        self,
        topic: str,
        event: ProcessedEvent,
        key: Optional[str] = None,
    ) -> None:
        self.published.append((topic, event))

    def publish_raw(
        self,
        topic: str,
        payload: dict,
        key: Optional[str] = None,
    ) -> None:
        self.published_raw.append((topic, payload))

    def publish_to_dlq(
        self,
        original_event: dict,
        error: Exception,
        source_topic: str,
    ) -> None:
        self.dlq_messages.append(
            {
                "original_event": original_event,
                "error": str(error),
                "source_topic": source_topic,
            }
        )

    def flush(self, timeout: float = 10.0) -> int:
        return 0

    def close(self) -> None:
        pass


class MockEventConsumerPort(EventConsumerPort):
    """Mock event consumer port for testing."""

    def __init__(self):
        self.events: list[IngestionEvent] = []
        self.current_index = 0
        self.committed = False

    def subscribe(self, topics: Optional[list[str]] = None) -> None:
        pass

    def poll(self, timeout_seconds: float = 1.0) -> Optional[dict]:
        """Poll for the next message as a raw dict."""
        if self.current_index < len(self.events):
            event = self.events[self.current_index]
            self.current_index += 1
            return {
                "key": event.tenant_id,
                "value": event.model_dump(),
                "topic": "test-topic",
                "partition": 0,
                "offset": self.current_index - 1,
            }
        return None

    def seek_to_beginning(self) -> None:
        """Seek to the beginning of all partitions."""
        self.current_index = 0

    def consume_one(self, timeout: float = 1.0) -> Optional[IngestionEvent]:
        if self.current_index < len(self.events):
            event = self.events[self.current_index]
            self.current_index += 1
            return event
        return None

    def consume_batch(
        self,
        max_messages: int = 100,
        timeout: float = 1.0,
    ) -> list[IngestionEvent]:
        batch = self.events[self.current_index : self.current_index + max_messages]
        self.current_index += len(batch)
        return batch

    def commit(self, asynchronous: bool = False) -> None:
        self.committed = True

    def close(self) -> None:
        pass

    def add_event(self, event: IngestionEvent) -> None:
        """Helper to add an event to the mock consumer."""
        self.events.append(event)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_storage() -> MockStoragePort:
    """Create a mock storage port."""
    return MockStoragePort()


@pytest.fixture
def mock_cache() -> MockCachePort:
    """Create a mock cache port."""
    return MockCachePort()


@pytest.fixture
def mock_producer() -> MockEventProducerPort:
    """Create a mock event producer port."""
    return MockEventProducerPort()


@pytest.fixture
def mock_consumer() -> MockEventConsumerPort:
    """Create a mock event consumer port."""
    return MockEventConsumerPort()


@pytest.fixture
def sample_event() -> IngestionEvent:
    """Create a sample ingestion event for testing."""
    return IngestionEvent(
        event_id=uuid4(),
        trace_id=uuid4(),
        tenant_id="tenant-123",
        file_path="gs://zorven-raw-assets/_landing/test-video.mp4",
        file_type="video/mp4",
        timestamp=datetime(2026, 1, 29, 12, 0, 0),
        source=EventSource.FRONTEND_UPLOAD,
        metadata={"original_filename": "test-video.mp4"},
    )


@pytest.fixture
def sample_processed_event(sample_event: IngestionEvent) -> ProcessedEvent:
    """Create a sample processed event for testing."""
    return ProcessedEvent(
        event_id=sample_event.event_id,
        trace_id=sample_event.trace_id,
        timestamp=datetime.utcnow(),
        tenant_id=sample_event.tenant_id,
        source_path=sample_event.file_path,
        destination_path="gs://zorven-raw-assets/tenant-123/raw/2026/01/29/test-video.mp4",
        status=ProcessingStatus.RAW_STORED,
        processing_duration_ms=150,
    )


@pytest.fixture
def ingestion_service(mock_storage, mock_cache, mock_producer):
    """Create an IngestionService with mock dependencies."""
    from data_ingestion.domain.services import IngestionService

    return IngestionService(
        storage=mock_storage,
        cache=mock_cache,
        producer=mock_producer,
        output_topic="curation-needed-topic",
        dlq_topic="ingestion-dlq",
    )
