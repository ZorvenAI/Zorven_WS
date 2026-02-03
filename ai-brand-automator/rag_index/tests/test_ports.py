"""
Unit Tests for Port Interfaces.

Tests verify that port interfaces are properly defined
and can be subclassed with correct method signatures.
"""

from abc import ABC
from typing import Any, Optional

import pytest

from rag_index.domain.models import (
    RateLimitStatus,
    SyncEvent,
    SyncResult,
    SyncStatus,
    SyncStatusRecord,
)
from rag_index.ports import (
    GCSPort,
    KafkaPort,
    RedisPort,
    VertexAIPort,
)


# ============================================================================
# VertexAIPort Tests
# ============================================================================


class TestVertexAIPort:
    """Tests for VertexAIPort interface."""

    def test_is_abstract_class(self):
        """Test that VertexAIPort is an abstract class."""
        assert issubclass(VertexAIPort, ABC)

    def test_cannot_instantiate_directly(self):
        """Test that VertexAIPort cannot be instantiated directly."""
        with pytest.raises(TypeError):
            VertexAIPort()

    def test_has_upsert_document_method(self):
        """Test that upsert_document method is defined."""
        assert hasattr(VertexAIPort, "upsert_document")

    def test_has_delete_document_method(self):
        """Test that delete_document method is defined."""
        assert hasattr(VertexAIPort, "delete_document")

    def test_has_get_document_method(self):
        """Test that get_document method is defined."""
        assert hasattr(VertexAIPort, "get_document")

    def test_has_check_connection_method(self):
        """Test that check_connection method is defined."""
        assert hasattr(VertexAIPort, "check_connection")

    def test_has_get_data_store_path_method(self):
        """Test that get_data_store_path method is defined."""
        assert hasattr(VertexAIPort, "get_data_store_path")


class MockVertexAIAdapter(VertexAIPort):
    """Mock implementation of VertexAIPort for testing."""

    async def upsert_document(
        self,
        event: SyncEvent,
        document_content: dict[str, Any],
    ) -> SyncResult:
        return SyncResult(
            event_id=event.event_id,
            trace_id=event.trace_id,
            status="COMPLETED",
            operation_id="test-op-123",
        )

    async def delete_document(self, event: SyncEvent) -> SyncResult:
        return SyncResult(
            event_id=event.event_id,
            trace_id=event.trace_id,
            status="COMPLETED",
        )

    async def get_document(
        self,
        document_id: str,
        tenant_id: str,
    ) -> Optional[dict[str, Any]]:
        return {"id": document_id, "content": "test"}

    async def check_connection(self) -> bool:
        return True

    def get_data_store_path(self, tenant_id: str) -> str:
        return f"projects/test/locations/global/dataStores/{tenant_id}"


class TestMockVertexAIAdapter:
    """Tests for mock VertexAI adapter implementation."""

    @pytest.fixture
    def adapter(self):
        """Create mock adapter instance."""
        return MockVertexAIAdapter()

    @pytest.mark.asyncio
    async def test_upsert_document(self, adapter, sample_sync_event):
        """Test upsert_document implementation."""
        result = await adapter.upsert_document(sample_sync_event, {"content": "test"})
        assert result.status == "COMPLETED"
        assert result.event_id == sample_sync_event.event_id

    @pytest.mark.asyncio
    async def test_delete_document(self, adapter, sample_delete_event):
        """Test delete_document implementation."""
        result = await adapter.delete_document(sample_delete_event)
        assert result.status == "COMPLETED"

    @pytest.mark.asyncio
    async def test_get_document(self, adapter):
        """Test get_document implementation."""
        doc = await adapter.get_document("doc-123", "tenant-456")
        assert doc is not None
        assert doc["id"] == "doc-123"

    @pytest.mark.asyncio
    async def test_check_connection(self, adapter):
        """Test check_connection implementation."""
        result = await adapter.check_connection()
        assert result is True

    def test_get_data_store_path(self, adapter):
        """Test get_data_store_path implementation."""
        path = adapter.get_data_store_path("tenant-123")
        assert "tenant-123" in path


# ============================================================================
# KafkaPort Tests
# ============================================================================


class TestKafkaPort:
    """Tests for KafkaPort interface."""

    def test_is_abstract_class(self):
        """Test that KafkaPort is an abstract class."""
        assert issubclass(KafkaPort, ABC)

    def test_cannot_instantiate_directly(self):
        """Test that KafkaPort cannot be instantiated directly."""
        with pytest.raises(TypeError):
            KafkaPort()

    def test_has_publish_method(self):
        """Test that publish method is defined."""
        assert hasattr(KafkaPort, "publish")

    def test_has_publish_completed_method(self):
        """Test that publish_completed method is defined."""
        assert hasattr(KafkaPort, "publish_completed")

    def test_has_publish_dlq_method(self):
        """Test that publish_dlq method is defined."""
        assert hasattr(KafkaPort, "publish_dlq")

    def test_has_flush_method(self):
        """Test that flush method is defined."""
        assert hasattr(KafkaPort, "flush")

    def test_has_close_method(self):
        """Test that close method is defined."""
        assert hasattr(KafkaPort, "close")


class MockKafkaAdapter(KafkaPort):
    """Mock implementation of KafkaPort for testing."""

    def __init__(self):
        self.published_messages = []

    async def publish(
        self,
        topic: str,
        message: dict[str, Any],
        key: Optional[str] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> None:
        self.published_messages.append(
            {
                "topic": topic,
                "message": message,
                "key": key,
                "headers": headers,
            }
        )

    async def publish_completed(
        self,
        message: dict[str, Any],
        trace_id: str,
    ) -> None:
        await self.publish("rag-sync-completed", message, key=trace_id)

    async def publish_dlq(
        self,
        message: dict[str, Any],
        trace_id: str,
    ) -> None:
        await self.publish("rag-sync-dlq", message, key=trace_id)

    async def flush(self) -> None:
        pass

    async def close(self) -> None:
        pass

    async def check_connection(self) -> bool:
        return True


class TestMockKafkaAdapter:
    """Tests for mock Kafka adapter implementation."""

    @pytest.fixture
    def adapter(self):
        """Create mock adapter instance."""
        return MockKafkaAdapter()

    @pytest.mark.asyncio
    async def test_publish(self, adapter):
        """Test publish implementation."""
        await adapter.publish("test-topic", {"key": "value"})
        assert len(adapter.published_messages) == 1
        assert adapter.published_messages[0]["topic"] == "test-topic"

    @pytest.mark.asyncio
    async def test_publish_completed(self, adapter):
        """Test publish_completed implementation."""
        await adapter.publish_completed({"status": "done"}, "trace-123")
        assert len(adapter.published_messages) == 1
        assert adapter.published_messages[0]["topic"] == "rag-sync-completed"

    @pytest.mark.asyncio
    async def test_publish_dlq(self, adapter):
        """Test publish_dlq implementation."""
        await adapter.publish_dlq({"error": "failed"}, "trace-456")
        assert len(adapter.published_messages) == 1
        assert adapter.published_messages[0]["topic"] == "rag-sync-dlq"


# ============================================================================
# RedisPort Tests
# ============================================================================


class TestRedisPort:
    """Tests for RedisPort interface."""

    def test_is_abstract_class(self):
        """Test that RedisPort is an abstract class."""
        assert issubclass(RedisPort, ABC)

    def test_cannot_instantiate_directly(self):
        """Test that RedisPort cannot be instantiated directly."""
        with pytest.raises(TypeError):
            RedisPort()

    def test_has_save_status_method(self):
        """Test that save_status method is defined."""
        assert hasattr(RedisPort, "save_status")

    def test_has_get_status_method(self):
        """Test that get_status method is defined."""
        assert hasattr(RedisPort, "get_status")

    def test_has_update_status_method(self):
        """Test that update_status method is defined."""
        assert hasattr(RedisPort, "update_status")

    def test_has_check_rate_limit_method(self):
        """Test that check_rate_limit method is defined."""
        assert hasattr(RedisPort, "check_rate_limit")

    def test_has_increment_rate_counter_method(self):
        """Test that increment_rate_counter method is defined."""
        assert hasattr(RedisPort, "increment_rate_counter")


class MockRedisAdapter(RedisPort):
    """Mock implementation of RedisPort for testing."""

    def __init__(self):
        self.status_store = {}
        self.rate_counters = {}

    async def save_status(
        self,
        record: SyncStatusRecord,
        ttl_seconds: int = 86400,
    ) -> None:
        self.status_store[str(record.event_id)] = record

    async def get_status(
        self,
        event_id: str,
    ) -> Optional[SyncStatusRecord]:
        return self.status_store.get(event_id)

    async def update_status(
        self,
        event_id: str,
        status: str,
        error_message: Optional[str] = None,
    ) -> None:
        if event_id in self.status_store:
            record = self.status_store[event_id]
            # Create updated record preserving all required fields
            new_status = SyncStatus(status) if isinstance(status, str) else status
            self.status_store[event_id] = SyncStatusRecord(
                event_id=record.event_id,
                trace_id=record.trace_id,
                tenant_id=record.tenant_id,
                file_id=record.file_id,
                action=record.action,
                status=new_status,
                error_message=error_message,
            )

    async def delete_status(self, event_id: str) -> bool:
        if event_id in self.status_store:
            del self.status_store[event_id]
            return True
        return False

    async def check_rate_limit(
        self,
        key: str = "rag_sync_rate",
        limit: int = 600,
        window_seconds: int = 60,
    ) -> RateLimitStatus:
        count = self.rate_counters.get(key, 0)
        return RateLimitStatus(
            current_count=count,
            limit=limit,
            remaining=max(0, limit - count),
        )

    async def increment_rate_counter(
        self,
        key: str = "rag_sync_rate",
        window_seconds: int = 60,
    ) -> int:
        self.rate_counters[key] = self.rate_counters.get(key, 0) + 1
        return self.rate_counters[key]

    async def get_rate_limit_remaining(
        self,
        key: str = "rag_sync_rate",
        limit: int = 600,
    ) -> int:
        count = self.rate_counters.get(key, 0)
        return max(0, limit - count)

    async def check_connection(self) -> bool:
        return True

    async def close(self) -> None:
        pass


class TestMockRedisAdapter:
    """Tests for mock Redis adapter implementation."""

    @pytest.fixture
    def adapter(self):
        """Create mock adapter instance."""
        return MockRedisAdapter()

    @pytest.mark.asyncio
    async def test_save_and_get_status(self, adapter, sample_status_record):
        """Test save and get status."""
        await adapter.save_status(sample_status_record)
        result = await adapter.get_status(str(sample_status_record.event_id))
        assert result is not None
        assert result.status == SyncStatus.IN_PROGRESS

    @pytest.mark.asyncio
    async def test_update_status(self, adapter, sample_status_record):
        """Test update status."""
        await adapter.save_status(sample_status_record)
        await adapter.update_status(
            str(sample_status_record.event_id),
            "COMPLETED",
        )
        result = await adapter.get_status(str(sample_status_record.event_id))
        assert result.status == SyncStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_check_rate_limit(self, adapter):
        """Test check rate limit."""
        status = await adapter.check_rate_limit()
        assert status.current_count == 0
        assert status.remaining == 600

    @pytest.mark.asyncio
    async def test_increment_rate_counter(self, adapter):
        """Test increment rate counter."""
        count = await adapter.increment_rate_counter()
        assert count == 1
        count = await adapter.increment_rate_counter()
        assert count == 2


# ============================================================================
# GCSPort Tests
# ============================================================================


class TestGCSPort:
    """Tests for GCSPort interface."""

    def test_is_abstract_class(self):
        """Test that GCSPort is an abstract class."""
        assert issubclass(GCSPort, ABC)

    def test_cannot_instantiate_directly(self):
        """Test that GCSPort cannot be instantiated directly."""
        with pytest.raises(TypeError):
            GCSPort()

    def test_has_read_document_method(self):
        """Test that read_document method is defined."""
        assert hasattr(GCSPort, "read_document")

    def test_has_file_exists_method(self):
        """Test that file_exists method is defined."""
        assert hasattr(GCSPort, "file_exists")

    def test_has_parse_gcs_uri_method(self):
        """Test that parse_gcs_uri method is defined."""
        assert hasattr(GCSPort, "parse_gcs_uri")


class MockGCSAdapter(GCSPort):
    """Mock implementation of GCSPort for testing."""

    def __init__(self):
        self.files = {}

    async def read_document(self, gcs_uri: str) -> dict[str, Any]:
        bucket, path = self.parse_gcs_uri(gcs_uri)
        key = f"{bucket}/{path}"
        if key in self.files:
            return self.files[key]
        raise FileNotFoundError(f"File not found: {gcs_uri}")

    async def file_exists(self, gcs_uri: str) -> bool:
        bucket, path = self.parse_gcs_uri(gcs_uri)
        key = f"{bucket}/{path}"
        return key in self.files

    def parse_gcs_uri(self, gcs_uri: str) -> tuple[str, str]:
        if not gcs_uri.startswith("gs://"):
            raise ValueError(f"Invalid GCS URI: {gcs_uri}")
        path = gcs_uri[5:]  # Remove "gs://"
        parts = path.split("/", 1)
        if len(parts) < 2:
            raise ValueError(f"Invalid GCS URI: {gcs_uri}")
        return parts[0], parts[1]

    async def check_connection(self) -> bool:
        return True

    async def close(self) -> None:
        pass


class TestMockGCSAdapter:
    """Tests for mock GCS adapter implementation."""

    @pytest.fixture
    def adapter(self):
        """Create mock adapter instance."""
        adapter = MockGCSAdapter()
        adapter.files["test-bucket/path/file.json"] = {"content": "test data"}
        return adapter

    @pytest.mark.asyncio
    async def test_read_document(self, adapter):
        """Test read_document implementation."""
        doc = await adapter.read_document("gs://test-bucket/path/file.json")
        assert doc["content"] == "test data"

    @pytest.mark.asyncio
    async def test_file_exists(self, adapter):
        """Test file_exists implementation."""
        exists = await adapter.file_exists("gs://test-bucket/path/file.json")
        assert exists is True

    @pytest.mark.asyncio
    async def test_file_not_exists(self, adapter):
        """Test file_exists returns false for missing file."""
        exists = await adapter.file_exists("gs://test-bucket/missing.json")
        assert exists is False

    def test_parse_gcs_uri(self, adapter):
        """Test parse_gcs_uri implementation."""
        bucket, path = adapter.parse_gcs_uri("gs://my-bucket/some/path/file.json")
        assert bucket == "my-bucket"
        assert path == "some/path/file.json"

    def test_parse_invalid_gcs_uri(self, adapter):
        """Test parse_gcs_uri raises error for invalid URI."""
        with pytest.raises(ValueError):
            adapter.parse_gcs_uri("https://invalid-uri")
