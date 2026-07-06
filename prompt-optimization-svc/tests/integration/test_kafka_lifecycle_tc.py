"""Integration tests for Kafka publish/consume via testcontainers (US-059).

Tests LifecycleProducer and AuditProducer against a real Kafka container.
"""

import json
import os

import pytest

from app.kafka.producer import AuditProducer, LifecycleProducer
from app.kafka.schemas import PROMPT_PROMOTED


@pytest.mark.integration
class TestKafkaLifecycleTC:
    """Kafka publish/consume via testcontainers."""

    @pytest.fixture
    async def lifecycle_producer(self):
        bootstrap = os.environ.get("POI_KAFKA_BOOTSTRAP_SERVERS", "")
        producer = LifecycleProducer(bootstrap)
        await producer.start()
        yield producer
        await producer.stop()

    @pytest.fixture
    async def audit_producer(self):
        bootstrap = os.environ.get("POI_KAFKA_BOOTSTRAP_SERVERS", "")
        producer = AuditProducer(bootstrap)
        await producer.start()
        yield producer
        await producer.stop()

    @pytest.fixture
    async def lifecycle_consumer(self):
        from aiokafka import AIOKafkaConsumer

        bootstrap = os.environ.get("POI_KAFKA_BOOTSTRAP_SERVERS", "")
        consumer = AIOKafkaConsumer(
            LifecycleProducer.TOPIC,
            bootstrap_servers=bootstrap,
            auto_offset_reset="earliest",
            value_deserializer=lambda v: json.loads(v.decode("utf-8")),
            consumer_timeout_ms=10000,
            group_id="tc-test-lifecycle",
        )
        await consumer.start()
        yield consumer
        await consumer.stop()

    @pytest.fixture
    async def audit_consumer(self):
        from aiokafka import AIOKafkaConsumer

        bootstrap = os.environ.get("POI_KAFKA_BOOTSTRAP_SERVERS", "")
        consumer = AIOKafkaConsumer(
            AuditProducer.TOPIC,
            bootstrap_servers=bootstrap,
            auto_offset_reset="earliest",
            value_deserializer=lambda v: json.loads(v.decode("utf-8")),
            consumer_timeout_ms=10000,
            group_id="tc-test-audit",
        )
        await consumer.start()
        yield consumer
        await consumer.stop()

    async def test_lifecycle_producer_connects(self, lifecycle_producer):
        """LifecycleProducer connects to real Kafka."""
        assert lifecycle_producer.is_connected is True

    async def test_audit_producer_connects(self, audit_producer):
        """AuditProducer connects to real Kafka."""
        assert audit_producer.is_connected is True

    async def test_publish_and_consume_lifecycle_event(
        self, lifecycle_producer, lifecycle_consumer
    ):
        """Send PROMPT_PROMOTED event, consume it, verify fields."""
        lifecycle_producer.send_lifecycle_event_sync(
            event_type=PROMPT_PROMOTED,
            prompt_name="__tc-kafka-test",
            version=1,
            from_state="CANARY",
            to_state="PRODUCTION",
            agent_code="mra",
            correlation_id="tc-corr-001",
        )

        found = False
        async for msg in lifecycle_consumer:
            if msg.value.get("prompt_name") == "__tc-kafka-test":
                assert msg.value["event_type"] == PROMPT_PROMOTED
                assert msg.value["version"] == 1
                assert msg.value["from_state"] == "CANARY"
                assert msg.value["to_state"] == "PRODUCTION"
                found = True
                break

        assert found, "Lifecycle event not consumed from Kafka"

    async def test_audit_producer_publish_and_consume(
        self, audit_producer, audit_consumer
    ):
        """Send audit event, consume and verify."""
        await audit_producer.send_audit(
            job_id="tc-job-001",
            tenant_id="tc-tenant",
            action="TEST_ACTION",
            details={"key": "value"},
        )

        found = False
        async for msg in audit_consumer:
            if msg.value.get("job_id") == "tc-job-001":
                assert msg.value["tenant_id"] == "tc-tenant"
                assert msg.value["action"] == "TEST_ACTION"
                found = True
                break

        assert found, "Audit event not consumed from Kafka"

    async def test_correlation_id_as_message_key(
        self, lifecycle_producer, lifecycle_consumer
    ):
        """Verify Kafka message key equals the correlation_id."""
        lifecycle_producer.send_lifecycle_event_sync(
            event_type=PROMPT_PROMOTED,
            prompt_name="__tc-kafka-key-test",
            version=2,
            from_state="DRAFT",
            to_state="CANARY",
            correlation_id="tc-key-check-001",
        )

        async for msg in lifecycle_consumer:
            if msg.value.get("prompt_name") == "__tc-kafka-key-test":
                assert msg.key is not None
                assert msg.key.decode("utf-8") == "tc-key-check-001"
                break

    async def test_schema_version_header(self, lifecycle_producer, lifecycle_consumer):
        """Verify schema_version header is '1.0' on consumed message."""
        lifecycle_producer.send_lifecycle_event_sync(
            event_type=PROMPT_PROMOTED,
            prompt_name="__tc-kafka-header-test",
            version=3,
            from_state="DRAFT",
            to_state="PRODUCTION",
            correlation_id="tc-header-check-001",
        )

        async for msg in lifecycle_consumer:
            if msg.value.get("prompt_name") == "__tc-kafka-header-test":
                headers = dict(msg.headers) if msg.headers else {}
                assert b"schema_version" in headers or "schema_version" in headers
                sv = headers.get("schema_version", headers.get(b"schema_version", b""))
                if isinstance(sv, bytes):
                    sv = sv.decode("utf-8")
                assert sv == "1.0"
                break
