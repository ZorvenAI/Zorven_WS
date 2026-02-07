"""
Integration tests for adapters with mocked external services.

These tests verify adapter behavior without requiring actual external services.
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch
from uuid import uuid4

from data_ingestion.domain.models import ProcessedEvent, ProcessingStatus
from data_ingestion.domain.exceptions import (
    FileNotFoundInLandingError,
)


class TestGCSAdapterWithMock:
    """Tests for GCSAdapter with mocked GCS client."""

    @pytest.fixture
    def mock_gcs_client(self):
        """Create a mock GCS client."""
        with patch("data_ingestion.adapters.gcs_adapter.storage") as mock_storage:
            mock_client = MagicMock()
            mock_storage.Client.from_service_account_json.return_value = mock_client
            mock_storage.Client.return_value = mock_client
            yield mock_client

    @pytest.fixture
    def gcs_adapter(self, mock_gcs_client):
        """Create a GCSAdapter with mocked client."""
        from data_ingestion.adapters.gcs_adapter import GCSAdapter

        return GCSAdapter(
            project_id="test-project",
            credentials_path=None,
            default_bucket="test-bucket",
        )

    def test_check_exists_returns_true(self, gcs_adapter, mock_gcs_client):
        """Test check_exists returns True when file exists."""
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_blob.exists.return_value = True
        mock_bucket.blob.return_value = mock_blob
        mock_gcs_client.bucket.return_value = mock_bucket

        result = gcs_adapter.check_exists("gs://test-bucket/path/file.mp4")

        assert result is True
        mock_blob.exists.assert_called_once()

    def test_check_exists_returns_false(self, gcs_adapter, mock_gcs_client):
        """Test check_exists returns False when file doesn't exist."""
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_blob.exists.return_value = False
        mock_bucket.blob.return_value = mock_blob
        mock_gcs_client.bucket.return_value = mock_bucket

        result = gcs_adapter.check_exists("gs://test-bucket/path/file.mp4")

        assert result is False

    def test_move_file_success(self, gcs_adapter, mock_gcs_client):
        """Test successful file move."""
        mock_source_bucket = MagicMock()
        mock_source_blob = MagicMock()
        mock_source_blob.exists.return_value = True
        mock_source_bucket.blob.return_value = mock_source_blob
        mock_gcs_client.bucket.return_value = mock_source_bucket

        result = gcs_adapter.move_file(
            source_path="gs://test-bucket/_landing/file.mp4",
            destination_path="gs://test-bucket/tenant/raw/file.mp4",
        )

        assert result == "gs://test-bucket/tenant/raw/file.mp4"
        mock_source_bucket.copy_blob.assert_called_once()
        mock_source_blob.delete.assert_called_once()

    def test_move_file_source_not_found(self, gcs_adapter, mock_gcs_client):
        """Test move_file when source doesn't exist."""
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_blob.exists.return_value = False
        mock_bucket.blob.return_value = mock_blob
        mock_gcs_client.bucket.return_value = mock_bucket

        with pytest.raises(FileNotFoundInLandingError):
            gcs_adapter.move_file(
                source_path="gs://test-bucket/_landing/file.mp4",
                destination_path="gs://test-bucket/tenant/raw/file.mp4",
            )

    def test_move_file_same_source_and_dest_skips_move(
        self, gcs_adapter, mock_gcs_client
    ):
        """Test that move_file is a no-op when source == destination.

        This prevents the copy-then-delete pattern from destroying
        the file when retrying an already-ingested asset.
        """
        mock_bucket = MagicMock()
        mock_bucket.name = "test-bucket"
        mock_blob = MagicMock()
        mock_blob.exists.return_value = True
        mock_bucket.blob.return_value = mock_blob
        mock_gcs_client.bucket.return_value = mock_bucket

        same_path = "gs://test-bucket/1/raw/2026/02/07/abc_file.pdf"
        result = gcs_adapter.move_file(
            source_path=same_path,
            destination_path=same_path,
        )

        assert result == same_path
        # copy_blob and delete should NOT be called
        mock_bucket.copy_blob.assert_not_called()
        mock_blob.delete.assert_not_called()


class TestRedisAdapterWithMock:
    """Tests for RedisAdapter with mocked Redis client."""

    @pytest.fixture
    def mock_redis_client(self):
        """Create a mock Redis client."""
        with patch("data_ingestion.adapters.redis_adapter.redis") as mock_redis:
            mock_client = MagicMock()
            mock_redis.from_url.return_value = mock_client
            yield mock_client

    @pytest.fixture
    def redis_adapter(self, mock_redis_client):
        """Create a RedisAdapter with mocked client."""
        from data_ingestion.adapters.redis_adapter import RedisAdapter

        return RedisAdapter(
            redis_url="redis://localhost:6379/0",
            dedupe_ttl_seconds=3600,
            status_ttl_seconds=604800,
        )

    def test_is_duplicate_true(self, redis_adapter, mock_redis_client):
        """Test is_duplicate returns True for existing key."""
        mock_redis_client.exists.return_value = 1

        result = redis_adapter.is_duplicate("event-123")

        assert result is True
        mock_redis_client.exists.assert_called_once()

    def test_is_duplicate_false(self, redis_adapter, mock_redis_client):
        """Test is_duplicate returns False for non-existing key."""
        mock_redis_client.exists.return_value = 0

        result = redis_adapter.is_duplicate("event-123")

        assert result is False

    def test_mark_processed(self, redis_adapter, mock_redis_client):
        """Test mark_processed sets key with TTL."""
        redis_adapter.mark_processed("event-123", ttl_seconds=3600)

        mock_redis_client.setex.assert_called_once()
        call_args = mock_redis_client.setex.call_args
        assert call_args[0][0] == "ingestion:dedupe:event-123"
        assert call_args[0][1] == 3600

    def test_update_status(self, redis_adapter, mock_redis_client):
        """Test update_status sets hash with TTL."""
        redis_adapter.update_status(
            trace_id="trace-123",
            status="RAW_STORED",
            ttl_seconds=604800,
        )

        mock_redis_client.hset.assert_called_once()
        mock_redis_client.expire.assert_called_once()

    def test_get_status_found(self, redis_adapter, mock_redis_client):
        """Test get_status returns data when found."""
        import json

        status_data = {"status": "RAW_STORED", "updated_at": "2026-01-29T12:00:00"}
        mock_redis_client.hget.return_value = json.dumps(status_data)

        result = redis_adapter.get_status("trace-123")

        assert result["status"] == "RAW_STORED"

    def test_get_status_not_found(self, redis_adapter, mock_redis_client):
        """Test get_status returns None when not found."""
        mock_redis_client.hget.return_value = None

        result = redis_adapter.get_status("trace-123")

        assert result is None

    def test_health_check_success(self, redis_adapter, mock_redis_client):
        """Test health_check returns True on success."""
        mock_redis_client.ping.return_value = True

        result = redis_adapter.health_check()

        assert result is True


class TestKafkaProducerAdapterWithMock:
    """Tests for KafkaProducerAdapter with mocked Kafka client."""

    @pytest.fixture
    def mock_kafka_producer(self):
        """Create a mock Kafka producer."""
        with patch("data_ingestion.adapters.kafka_adapter.Producer") as MockProducer:
            mock_producer = MagicMock()
            MockProducer.return_value = mock_producer
            yield mock_producer

    @pytest.fixture
    def kafka_producer(self, mock_kafka_producer):
        """Create a KafkaProducerAdapter with mocked producer."""
        from data_ingestion.adapters.kafka_adapter import KafkaProducerAdapter

        return KafkaProducerAdapter(
            bootstrap_servers="localhost:9092",
            client_id="test-producer",
            dlq_topic="test-dlq",
        )

    def test_publish_event(self, kafka_producer, mock_kafka_producer):
        """Test publishing an event."""
        event = ProcessedEvent(
            event_id=uuid4(),
            trace_id=uuid4(),
            timestamp=datetime.utcnow(),
            tenant_id="tenant-123",
            source_path="gs://bucket/_landing/file.mp4",
            destination_path="gs://bucket/tenant-123/raw/file.mp4",
            status=ProcessingStatus.RAW_STORED,
            processing_duration_ms=100,
        )

        kafka_producer.publish(topic="output-topic", event=event)

        mock_kafka_producer.produce.assert_called_once()
        call_kwargs = mock_kafka_producer.produce.call_args[1]
        assert call_kwargs["topic"] == "output-topic"

    def test_publish_to_dlq(self, kafka_producer, mock_kafka_producer):
        """Test publishing to DLQ."""
        original_event = {"event_id": "123", "tenant_id": "tenant-123"}
        error = Exception("Test error")

        kafka_producer.publish_to_dlq(
            original_event=original_event,
            error=error,
            source_topic="input-topic",
        )

        mock_kafka_producer.produce.assert_called_once()
        call_kwargs = mock_kafka_producer.produce.call_args[1]
        assert call_kwargs["topic"] == "test-dlq"

    def test_flush(self, kafka_producer, mock_kafka_producer):
        """Test flush waits for all messages."""
        mock_kafka_producer.flush.return_value = 0

        result = kafka_producer.flush(timeout=5.0)

        assert result == 0
        mock_kafka_producer.flush.assert_called_once_with(5.0)


class TestKafkaConsumerAdapterWithMock:
    """Tests for KafkaConsumerAdapter with mocked Kafka client."""

    @pytest.fixture
    def mock_kafka_consumer(self):
        """Create a mock Kafka consumer."""
        with patch("data_ingestion.adapters.kafka_adapter.Consumer") as MockConsumer:
            mock_consumer = MagicMock()
            MockConsumer.return_value = mock_consumer
            yield mock_consumer

    @pytest.fixture
    def kafka_consumer(self, mock_kafka_consumer):
        """Create a KafkaConsumerAdapter with mocked consumer."""
        from data_ingestion.adapters.kafka_adapter import KafkaConsumerAdapter

        return KafkaConsumerAdapter(
            bootstrap_servers="localhost:9092",
            group_id="test-group",
            topics=["test-topic"],
        )

    def test_subscribe(self, kafka_consumer, mock_kafka_consumer):
        """Test subscribing to topics."""
        kafka_consumer.subscribe(["topic-1", "topic-2"])

        mock_kafka_consumer.subscribe.assert_called_once_with(["topic-1", "topic-2"])

    def test_consume_one_returns_event(self, kafka_consumer, mock_kafka_consumer):
        """Test consuming a single message."""
        import json

        event_data = {
            "event_id": str(uuid4()),
            "trace_id": str(uuid4()),
            "tenant_id": "tenant-123",
            "file_path": "gs://bucket/_landing/file.mp4",
            "file_type": "video/mp4",
            "timestamp": "2026-01-29T12:00:00",
            "source": "frontend-upload",
        }

        mock_msg = MagicMock()
        mock_msg.error.return_value = None
        mock_msg.value.return_value = json.dumps(event_data).encode("utf-8")
        mock_msg.topic.return_value = "test-topic"
        mock_msg.partition.return_value = 0
        mock_msg.offset.return_value = 100
        mock_kafka_consumer.poll.return_value = mock_msg

        result = kafka_consumer.consume_one(timeout=1.0)

        assert result is not None
        assert result.tenant_id == "tenant-123"

    def test_consume_one_timeout(self, kafka_consumer, mock_kafka_consumer):
        """Test consume_one returns None on timeout."""
        mock_kafka_consumer.poll.return_value = None

        result = kafka_consumer.consume_one(timeout=1.0)

        assert result is None

    def test_commit(self, kafka_consumer, mock_kafka_consumer):
        """Test committing offsets."""
        kafka_consumer.commit()

        mock_kafka_consumer.commit.assert_called_once_with(asynchronous=False)

    def test_close(self, kafka_consumer, mock_kafka_consumer):
        """Test closing the consumer."""
        kafka_consumer.close()

        mock_kafka_consumer.close.assert_called_once()
