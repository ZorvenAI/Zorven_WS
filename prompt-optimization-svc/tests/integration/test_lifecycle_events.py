"""Integration tests for lifecycle events (US-036)."""

import json

from app.kafka.producer import LifecycleProducer
from app.kafka.schemas import PROMPT_PROMOTED, PromptLifecycleEvent


class TestLifecycleProducerNoKafka:
    """LifecycleProducer in no-op mode (no Kafka)."""

    def test_creates_without_kafka(self):
        producer = LifecycleProducer("")
        assert producer.is_connected is False

    def test_send_noop_without_kafka(self):
        producer = LifecycleProducer("")
        # Should not raise
        producer.send_lifecycle_event_sync(
            event_type=PROMPT_PROMOTED,
            prompt_name="test",
            version=1,
            from_state="CANARY",
            to_state="PRODUCTION",
        )

    def test_send_with_correlation_id(self):
        producer = LifecycleProducer("")
        # Should not raise even with correlation_id
        producer.send_lifecycle_event_sync(
            event_type=PROMPT_PROMOTED,
            prompt_name="test",
            version=1,
            from_state="CANARY",
            to_state="PRODUCTION",
            correlation_id="test-correlation-123",
        )


class TestEventSerialization:
    def test_full_event_round_trip(self):
        event = PromptLifecycleEvent(
            event_type=PROMPT_PROMOTED,
            prompt_name="zorven-wf3-cga-system",
            version=5,
            from_state="CANARY",
            to_state="PRODUCTION",
            agent_code="cga",
            correlation_id="corr-abc-123",
        )
        serialized = json.dumps(event.model_dump())
        deserialized = json.loads(serialized)
        assert deserialized["correlation_id"] == "corr-abc-123"
        assert deserialized["schema_version"] == "1.0"
        assert deserialized["agent_code"] == "cga"
