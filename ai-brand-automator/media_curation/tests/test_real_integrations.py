"""
Real Integration Tests for Redis and Kafka Adapters.

These tests connect to actual Redis and Kafka instances running in Docker.
Run with: pytest media_curation/tests/test_real_integrations.py -v

Prerequisites:
- Docker containers running: redis, kafka, zookeeper
- Redis: localhost:6379
- Kafka: localhost:9092
"""

import asyncio
import pytest
from datetime import datetime, timezone
from uuid import uuid4

# Skip all tests if services unavailable
pytestmark = pytest.mark.integration


def run_async(coro):
    """Run async coroutine synchronously."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# =============================================================================
# Redis Integration Tests
# =============================================================================


class TestRedisRealConnection:
    """Tests that connect to real Redis instance."""

    @pytest.fixture
    def redis_adapter(self):
        """Create Redis adapter connected to Docker Redis."""
        from media_curation.adapters.redis_adapter import RedisAdapter

        adapter = RedisAdapter(
            redis_url="redis://localhost:6379/0",
            status_ttl_seconds=60,
            dedupe_ttl_seconds=60,
        )
        return adapter

    def test_redis_connection_health(self, redis_adapter):
        """Test Redis connection is healthy."""
        result = run_async(redis_adapter.is_healthy())
        assert result is True, "Redis should be healthy and reachable"

    def test_redis_set_and_get_status(self, redis_adapter):
        """Test storing and retrieving status records."""
        from media_curation.domain.models import CurationStatusRecord, CurationStatus

        trace_id = uuid4()
        status_record = CurationStatusRecord(
            trace_id=trace_id,
            event_id=uuid4(),
            tenant_id=uuid4(),
            file_id=uuid4(),
            status=CurationStatus.PROCESSING,
            message="Test processing",
            updated_at=datetime.now(timezone.utc),
        )

        # Store status - API takes trace_id as string, status record
        run_async(redis_adapter.set_status(str(trace_id), status_record))

        # Retrieve status - API takes trace_id as string
        retrieved = run_async(redis_adapter.get_status(str(trace_id)))

        assert retrieved is not None
        assert retrieved.trace_id == trace_id
        assert retrieved.status == CurationStatus.PROCESSING

    def test_redis_deduplication(self, redis_adapter):
        """Test event deduplication functionality."""
        event_id = str(uuid4())  # API takes string

        # First check should return False (not a duplicate)
        is_dup_1 = run_async(redis_adapter.is_duplicate(event_id))
        assert is_dup_1 is False

        # Mark as processed
        run_async(redis_adapter.mark_processed(event_id))

        # Second check should return True (is a duplicate)
        is_dup_2 = run_async(redis_adapter.is_duplicate(event_id))
        assert is_dup_2 is True

    def test_redis_tenant_config(self, redis_adapter):
        """Test storing and retrieving tenant configuration."""
        from media_curation.domain.models import TenantConfig

        tenant_id = uuid4()
        config = TenantConfig(
            tenant_id=tenant_id,
            dlp_enabled=True,
            dlp_info_types=["EMAIL_ADDRESS", "PHONE_NUMBER"],
            max_file_size_bytes=50 * 1024 * 1024,
        )

        # Store config - API takes tenant_id as string, config
        run_async(redis_adapter.set_tenant_config(str(tenant_id), config))

        # Retrieve config - API takes tenant_id as string
        retrieved = run_async(redis_adapter.get_tenant_config(str(tenant_id)))

        assert retrieved is not None
        assert retrieved.tenant_id == tenant_id
        assert retrieved.dlp_enabled is True


# =============================================================================
# Kafka Integration Tests
# =============================================================================


class TestKafkaRealConnection:
    """Tests that connect to real Kafka instance."""

    @pytest.fixture
    def kafka_producer(self):
        """Create Kafka producer connected to Docker Kafka."""
        from media_curation.adapters.kafka_adapter import KafkaProducerAdapter

        adapter = KafkaProducerAdapter(
            bootstrap_servers="localhost:9192",
            dlq_topic="test-curation-dlq",
            output_topic="test-curation-output",
        )
        return adapter

    @pytest.fixture
    def kafka_consumer(self):
        """Create Kafka consumer connected to Docker Kafka."""
        from media_curation.adapters.kafka_adapter import KafkaConsumerAdapter

        adapter = KafkaConsumerAdapter(
            bootstrap_servers="localhost:9192",
            group_id=f"test-consumer-{uuid4().hex[:8]}",
            input_topic="test-curation-input",
        )
        return adapter

    def test_kafka_producer_available(self, kafka_producer):
        """Test Kafka producer is connected."""
        # Check that the producer was initialized (has the producer attribute)
        assert (
            kafka_producer._kafka_available is True
        ), "Kafka producer should be available"

    def test_kafka_publish_message(self, kafka_producer):
        """Test publishing a message to Kafka."""
        test_topic = f"test-topic-{uuid4().hex[:8]}"
        test_message = {
            "id": str(uuid4()),
            "type": "test.event.v1",
            "data": {
                "message": "Hello from integration test",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        }

        # Publish message
        run_async(
            kafka_producer.publish_raw(
                topic=test_topic,
                payload=test_message,
                key="test-key",
            )
        )

        # If we get here without exception, publish succeeded
        assert True

    def test_kafka_publish_curated_document(self, kafka_producer):
        """Test publishing a curated document event."""
        from media_curation.domain.models import CuratedDocument

        document = CuratedDocument(
            document_id=uuid4(),
            trace_id=uuid4(),
            tenant_id=uuid4(),
            file_id=uuid4(),
            source_gcs_uri="gs://test-bucket/input.pdf",  # Required field
            output_gcs_uri="gs://test-bucket/output.json",
            extracted_text="This is test content from the integration test",
            mime_type="application/pdf",
            pii_redacted=False,
            processing_time_ms=100,
        )

        # Publish to output topic
        test_topic = f"test-curated-{uuid4().hex[:8]}"
        run_async(kafka_producer.publish_curated_document(test_topic, document))

        assert True  # Success if no exception

    def test_kafka_publish_to_dlq(self, kafka_producer):
        """Test publishing failed event to DLQ."""
        from media_curation.domain.models import CurationEvent, ContentType

        event = CurationEvent(
            event_id=uuid4(),
            trace_id=uuid4(),
            tenant_id=uuid4(),
            file_id=uuid4(),
            raw_gcs_uri="gs://test-bucket/failed.pdf",
            mime_type="application/pdf",
            content_type=ContentType.DOCUMENT,
        )

        # publish_to_dlq takes event and error exception
        run_async(
            kafka_producer.publish_to_dlq(
                event=event,
                error=Exception("Test error for DLQ"),
                retry_count=0,
            )
        )

        assert True  # Success if no exception


# =============================================================================
# Combined Integration Tests
# =============================================================================


class TestCombinedRealServices:
    """Tests that use multiple real services together."""

    @pytest.fixture
    def real_adapters(self):
        """Create all real adapters."""
        from media_curation.adapters.redis_adapter import RedisAdapter
        from media_curation.adapters.kafka_adapter import KafkaProducerAdapter

        redis = RedisAdapter(
            redis_url="redis://localhost:6379/0",
            status_ttl_seconds=60,
        )

        kafka = KafkaProducerAdapter(
            bootstrap_servers="localhost:9192",
            dlq_topic="curation-dlq",
            output_topic="rag-sync-ready-topic",
        )

        return {"redis": redis, "kafka": kafka}

    def test_status_update_and_publish(self, real_adapters):
        """Test updating status in Redis and publishing event to Kafka."""
        from media_curation.domain.models import (
            CurationStatusRecord,
            CurationStatus,
            CuratedDocument,
        )

        trace_id = uuid4()
        tenant_id = uuid4()
        file_id = uuid4()
        event_id = uuid4()

        # 1. Set initial status in Redis
        status = CurationStatusRecord(
            trace_id=trace_id,
            event_id=event_id,
            tenant_id=tenant_id,
            file_id=file_id,
            status=CurationStatus.PROCESSING,
            message="Processing started",
            updated_at=datetime.now(timezone.utc),
        )
        run_async(real_adapters["redis"].set_status(str(trace_id), status))

        # 2. Verify status was stored
        retrieved = run_async(real_adapters["redis"].get_status(str(trace_id)))
        assert retrieved.status == CurationStatus.PROCESSING

        # 3. Publish completion event to Kafka
        doc = CuratedDocument(
            document_id=uuid4(),
            trace_id=trace_id,
            tenant_id=tenant_id,
            file_id=file_id,
            source_gcs_uri="gs://raw-bucket/input.pdf",
            output_gcs_uri="gs://curated/doc.json",
            extracted_text="Processed content",
            mime_type="application/pdf",
            pii_redacted=False,
        )
        test_topic = f"test-combined-{uuid4().hex[:8]}"
        run_async(real_adapters["kafka"].publish_curated_document(test_topic, doc))

        # 4. Update final status in Redis
        final_status = CurationStatusRecord(
            trace_id=trace_id,
            event_id=event_id,
            tenant_id=tenant_id,
            file_id=file_id,
            status=CurationStatus.CURATED,
            message="Processing complete",
            output_gcs_uri="gs://curated/doc.json",
            updated_at=datetime.now(timezone.utc),
        )
        run_async(real_adapters["redis"].set_status(str(trace_id), final_status))

        # 5. Verify final status
        final = run_async(real_adapters["redis"].get_status(str(trace_id)))
        assert final.status == CurationStatus.CURATED
        assert final.output_gcs_uri == "gs://curated/doc.json"


# =============================================================================
# Test Configuration
# =============================================================================


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers",
        "integration: marks tests as integration tests (require Docker services)",
    )
