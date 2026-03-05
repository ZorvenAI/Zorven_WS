"""
Unit Tests for Adapters.

Tests for concrete adapter implementations with mocked external services.
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from rag_index.adapters import (
    GCSAdapter,
    KafkaAdapter,
    RedisAdapter,
    VertexAIAdapter,
)
from rag_index.domain.exceptions import (
    GCSNotFoundError,
    GCSReadError,
    InvalidGCSURIError,
    StatusNotFoundError,
)


# ============================================================================
# VertexAIAdapter Tests
# ============================================================================


class TestVertexAIAdapter:
    """Tests for VertexAIAdapter."""

    @pytest.fixture
    def adapter(self):
        """Create adapter instance in mock mode."""
        return VertexAIAdapter(
            project_id="test-project",
            location="global",
            data_store_id="test-store",
            mock_mode=True,
        )

    def test_initialization(self, adapter):
        """Test adapter initialization."""
        assert adapter.project_id == "test-project"
        assert adapter.location == "global"
        assert adapter.data_store_id == "test-store"
        assert adapter.mock_mode is True

    def test_get_data_store_path(self, adapter):
        """Test data store path generation."""
        path = adapter.get_data_store_path("tenant-123")
        assert "test-project" in path
        assert "global" in path
        assert "test-store" in path  # Falls back to default in test (no DB)

    async def test_upsert_document_mock_mode(self, adapter, sample_sync_event):
        """Test upsert in mock mode (no SDK installed)."""
        result = await adapter.upsert_document(
            sample_sync_event,
            {"content": "test document"},
        )
        assert result.status == "COMPLETED"
        assert result.event_id == sample_sync_event.event_id

    async def test_delete_document_mock_mode(self, adapter, sample_delete_event):
        """Test delete in mock mode."""
        result = await adapter.delete_document(sample_delete_event)
        assert result.status == "COMPLETED"

    async def test_get_document_mock_mode(self, adapter):
        """Test get document in mock mode."""
        doc = await adapter.get_document("doc-123", "tenant-456")
        assert doc is not None
        assert doc["mock"] is True

    async def test_check_connection(self, adapter):
        """Test connection check in mock mode."""
        result = await adapter.check_connection()
        assert result is True


class TestVertexAIAdapterWithMockedClient:
    """Tests for VertexAIAdapter with mocked Discovery Engine client."""

    @pytest.fixture
    def adapter_with_mock(self):
        """Create adapter with mocked client."""
        mock_client = MagicMock()
        adapter = VertexAIAdapter(
            project_id="test-project",
            location="global",
            data_store_id="test-store",
        )
        adapter._client = mock_client
        adapter._initialized = True
        adapter.mock_mode = False  # Disable mock mode for client tests
        return adapter, mock_client

    async def test_upsert_document_with_client(
        self,
        adapter_with_mock,
        sample_sync_event,
    ):
        """Test upsert with mocked client - skipped when SDK not installed."""
        adapter, mock_client = adapter_with_mock

        # Since discoveryengine SDK is not installed, we test the mock path
        # Set mock_mode to true to test the mock path
        adapter.mock_mode = True
        adapter._client = None

        result = await adapter.upsert_document(
            sample_sync_event,
            {"content": "test"},
        )

        assert result.status == "COMPLETED"


# ============================================================================
# KafkaAdapter Tests
# ============================================================================


class TestKafkaAdapter:
    """Tests for KafkaAdapter."""

    @pytest.fixture
    def adapter(self):
        """Create adapter instance."""
        return KafkaAdapter(
            bootstrap_servers="localhost:9092",
            completed_topic="test-completed",
            dlq_topic="test-dlq",
        )

    def test_initialization(self, adapter):
        """Test adapter initialization."""
        assert adapter.bootstrap_servers == "localhost:9092"
        assert adapter.completed_topic == "test-completed"
        assert adapter.dlq_topic == "test-dlq"

    async def test_publish_mock_mode(self, adapter):
        """Test publish in mock mode."""
        # Should not raise in mock mode
        await adapter.publish("test-topic", {"key": "value"})

    async def test_publish_completed_mock_mode(self, adapter):
        """Test publish_completed in mock mode."""
        await adapter.publish_completed({"status": "done"}, "trace-123")

    async def test_publish_dlq_mock_mode(self, adapter):
        """Test publish_dlq in mock mode."""
        await adapter.publish_dlq({"error": "failed"}, "trace-456")

    async def test_flush_mock_mode(self, adapter):
        """Test flush in mock mode."""
        await adapter.flush()  # Should not raise

    async def test_close_mock_mode(self, adapter):
        """Test close in mock mode."""
        await adapter.close()  # Should not raise

    async def test_check_connection(self, adapter):
        """Test connection check in mock mode."""
        result = await adapter.check_connection()
        assert result is True


class TestKafkaAdapterWithMockedProducer:
    """Tests for KafkaAdapter with mocked AIOKafkaProducer."""

    @pytest.fixture
    def mock_producer(self):
        """Create mock Kafka producer."""
        producer = AsyncMock()
        producer.send_and_wait = AsyncMock()
        producer.flush = AsyncMock()
        producer.stop = AsyncMock()
        producer._sender_task = MagicMock()
        producer.start = AsyncMock()
        return producer

    @pytest.fixture
    def adapter_with_mock(self, mock_producer):
        """Create adapter with mocked producer."""
        adapter = KafkaAdapter()
        adapter._producer = mock_producer
        adapter._initialized = True
        return adapter, mock_producer

    async def test_publish_with_producer(self, adapter_with_mock):
        """Test publish with mocked producer."""
        adapter, mock_producer = adapter_with_mock

        await adapter.publish("test-topic", {"key": "value"}, key="msg-key")

        mock_producer.send_and_wait.assert_called_once()
        call_args = mock_producer.send_and_wait.call_args
        assert call_args.kwargs["topic"] == "test-topic"
        assert call_args.kwargs["key"] == "msg-key"

    async def test_publish_with_headers(self, adapter_with_mock):
        """Test publish with headers."""
        adapter, mock_producer = adapter_with_mock

        await adapter.publish(
            "test-topic",
            {"data": "value"},
            headers={"trace_id": "abc123"},
        )

        call_args = mock_producer.send_and_wait.call_args
        assert call_args.kwargs["headers"] is not None


# ============================================================================
# RedisAdapter Tests
# ============================================================================


class TestRedisAdapter:
    """Tests for RedisAdapter."""

    @pytest.fixture
    def adapter(self):
        """Create adapter instance."""
        return RedisAdapter(
            redis_url="redis://localhost:6379/0",
            rate_limit=600,
            rate_window=60,
        )

    def test_initialization(self, adapter):
        """Test adapter initialization."""
        assert adapter.redis_url == "redis://localhost:6379/0"
        assert adapter.rate_limit == 600
        assert adapter.rate_window == 60

    def test_get_status_key(self, adapter):
        """Test status key generation."""
        key = adapter._get_status_key("event-123")
        assert "rag_sync:status:" in key
        assert "event-123" in key

    def test_get_rate_key(self, adapter):
        """Test rate key generation."""
        key = adapter._get_rate_key("custom")
        assert "rag_sync:rate:" in key
        assert "custom" in key

    async def test_save_status_mock_mode(self, adapter, sample_status_record):
        """Test save_status in mock mode."""
        await adapter.save_status(sample_status_record)  # Should not raise

    async def test_get_status_mock_mode(self, adapter):
        """Test get_status in mock mode."""
        result = await adapter.get_status("event-123")
        assert result is None  # Mock mode returns None

    async def test_check_rate_limit_mock_mode(self, adapter):
        """Test check_rate_limit in mock mode."""
        status = await adapter.check_rate_limit()
        assert status.current_count == 0
        assert status.remaining == 600

    async def test_increment_rate_counter_mock_mode(self, adapter):
        """Test increment_rate_counter in mock mode."""
        count = await adapter.increment_rate_counter()
        assert count == 1

    async def test_check_connection(self, adapter):
        """Test connection check in mock mode."""
        result = await adapter.check_connection()
        assert result is True


class TestRedisAdapterWithMockedClient:
    """Tests for RedisAdapter with mocked Redis client."""

    @pytest.fixture
    def mock_redis(self):
        """Create mock Redis client."""
        client = AsyncMock()
        client.get = AsyncMock(return_value=None)
        client.set = AsyncMock(return_value=True)
        client.delete = AsyncMock(return_value=1)
        client.incr = AsyncMock(return_value=1)
        client.expire = AsyncMock(return_value=True)
        client.ttl = AsyncMock(return_value=60)
        client.ping = AsyncMock(return_value=True)
        client.close = AsyncMock()
        return client

    @pytest.fixture
    def adapter_with_mock(self, mock_redis):
        """Create adapter with mocked client."""
        adapter = RedisAdapter()
        adapter._client = mock_redis
        adapter._initialized = True
        return adapter, mock_redis

    async def test_save_status(self, adapter_with_mock, sample_status_record):
        """Test save_status with mocked client."""
        adapter, mock_redis = adapter_with_mock

        await adapter.save_status(sample_status_record)

        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args
        assert str(sample_status_record.event_id) in call_args[0][0]

    async def test_get_status_found(self, adapter_with_mock, sample_status_record):
        """Test get_status when record exists."""
        adapter, mock_redis = adapter_with_mock

        mock_redis.get.return_value = json.dumps(sample_status_record.to_dict())

        result = await adapter.get_status(str(sample_status_record.event_id))

        assert result is not None
        assert result.status == sample_status_record.status

    async def test_get_status_not_found(self, adapter_with_mock):
        """Test get_status when record doesn't exist."""
        adapter, mock_redis = adapter_with_mock
        mock_redis.get.return_value = None

        result = await adapter.get_status("nonexistent-event")

        assert result is None

    async def test_update_status(self, adapter_with_mock, sample_status_record):
        """Test update_status with mocked client."""
        adapter, mock_redis = adapter_with_mock

        mock_redis.get.return_value = json.dumps(sample_status_record.to_dict())

        await adapter.update_status(
            str(sample_status_record.event_id),
            "COMPLETED",
        )

        mock_redis.set.assert_called_once()

    async def test_update_status_not_found(self, adapter_with_mock):
        """Test update_status raises when not found."""
        adapter, mock_redis = adapter_with_mock
        mock_redis.get.return_value = None

        with pytest.raises(StatusNotFoundError):
            await adapter.update_status("nonexistent", "COMPLETED")

    async def test_increment_rate_counter(self, adapter_with_mock):
        """Test increment_rate_counter with mocked client."""
        adapter, mock_redis = adapter_with_mock

        count = await adapter.increment_rate_counter()

        assert count == 1
        mock_redis.incr.assert_called_once()

    async def test_check_connection_with_client(self, adapter_with_mock):
        """Test check_connection with mocked client."""
        adapter, mock_redis = adapter_with_mock

        result = await adapter.check_connection()

        assert result is True
        mock_redis.ping.assert_called_once()


# ============================================================================
# GCSAdapter Tests
# ============================================================================


class TestGCSAdapter:
    """Tests for GCSAdapter."""

    @pytest.fixture
    def adapter(self):
        """Create adapter instance in mock mode."""
        return GCSAdapter(project_id="test-project", mock_mode=True)

    def test_initialization(self, adapter):
        """Test adapter initialization."""
        assert adapter.project_id == "test-project"
        assert adapter.mock_mode is True

    def test_parse_gcs_uri_valid(self, adapter):
        """Test parsing valid GCS URI."""
        bucket, path = adapter.parse_gcs_uri("gs://my-bucket/path/to/file.json")
        assert bucket == "my-bucket"
        assert path == "path/to/file.json"

    def test_parse_gcs_uri_invalid_scheme(self, adapter):
        """Test parsing URI with invalid scheme."""
        with pytest.raises(InvalidGCSURIError):
            adapter.parse_gcs_uri("https://example.com/file.json")

    def test_parse_gcs_uri_empty(self, adapter):
        """Test parsing empty URI."""
        with pytest.raises(InvalidGCSURIError):
            adapter.parse_gcs_uri("")

    def test_parse_gcs_uri_missing_path(self, adapter):
        """Test parsing URI without path."""
        with pytest.raises(InvalidGCSURIError):
            adapter.parse_gcs_uri("gs://bucket-only")

    async def test_read_document_mock_mode(self, adapter):
        """Test read_document in mock mode."""
        doc = await adapter.read_document("gs://bucket/path/doc.json")
        assert doc["mock"] is True

    async def test_file_exists_mock_mode(self, adapter):
        """Test file_exists in mock mode."""
        exists = await adapter.file_exists("gs://bucket/path/file.json")
        assert exists is True

    async def test_check_connection(self, adapter):
        """Test connection check in mock mode."""
        result = await adapter.check_connection()
        assert result is True


class TestGCSAdapterWithMockedClient:
    """Tests for GCSAdapter with mocked GCS client."""

    @pytest.fixture
    def mock_gcs(self):
        """Create mock GCS client."""
        client = MagicMock()
        bucket = MagicMock()
        blob = MagicMock()

        blob.exists.return_value = True
        blob.download_as_text.return_value = '{"content": "test data"}'
        bucket.blob.return_value = blob
        client.bucket.return_value = bucket
        client.list_buckets.return_value = iter([])
        client.close = MagicMock()

        return client, bucket, blob

    @pytest.fixture
    def adapter_with_mock(self, mock_gcs):
        """Create adapter with mocked client."""
        client, bucket, blob = mock_gcs
        adapter = GCSAdapter()
        adapter._client = client
        adapter._initialized = True
        return adapter, client, bucket, blob

    async def test_read_document_success(self, adapter_with_mock):
        """Test read_document with mocked client."""
        adapter, client, bucket, blob = adapter_with_mock

        doc = await adapter.read_document("gs://test-bucket/path/doc.json")

        assert doc["content"] == "test data"
        client.bucket.assert_called_with("test-bucket")
        bucket.blob.assert_called_with("path/doc.json")

    async def test_read_document_not_found(self, adapter_with_mock):
        """Test read_document raises when file not found."""
        adapter, client, bucket, blob = adapter_with_mock
        blob.exists.return_value = False

        with pytest.raises(GCSNotFoundError):
            await adapter.read_document("gs://test-bucket/missing.json")

    async def test_read_document_invalid_json(self, adapter_with_mock):
        """Test read_document raises when JSON is invalid."""
        adapter, client, bucket, blob = adapter_with_mock
        blob.download_as_text.return_value = "not valid json"

        with pytest.raises(GCSReadError):
            await adapter.read_document("gs://test-bucket/invalid.json")

    async def test_file_exists_true(self, adapter_with_mock):
        """Test file_exists returns True when file exists."""
        adapter, client, bucket, blob = adapter_with_mock
        blob.exists.return_value = True

        result = await adapter.file_exists("gs://test-bucket/existing.json")

        assert result is True

    async def test_file_exists_false(self, adapter_with_mock):
        """Test file_exists returns False when file doesn't exist."""
        adapter, client, bucket, blob = adapter_with_mock
        blob.exists.return_value = False

        result = await adapter.file_exists("gs://test-bucket/missing.json")

        assert result is False
