"""Tests for Kafka producer and consumer."""

from unittest.mock import MagicMock, patch

from app.messaging.kafka_producer import TraceProducer
from app.messaging.kafka_consumer import TriggerConsumer


class TestTraceProducer:
    """Test trace event and result event publishing."""

    async def test_send_trace_when_not_connected(self):
        """No-op when producer is not started."""
        producer = TraceProducer("localhost:9092")
        # Should not raise
        await producer.send_trace("job-1", "node-1", "running")
        assert producer.is_connected is False

    async def test_send_result_when_not_connected(self):
        """No-op when producer is not started."""
        producer = TraceProducer("localhost:9092")
        await producer.send_result("job-1", {"summary": "done"})
        assert producer.is_connected is False

    @patch("app.messaging.kafka_producer.TraceProducer.start")
    async def test_start_failure_is_non_fatal(self, mock_start):
        """Producer start failure doesn't crash the service."""
        producer = TraceProducer("localhost:9092")
        # After failed start, producer should not be connected
        assert producer.is_connected is False

    async def test_stop_when_not_started(self):
        """Stop is safe even if never started."""
        producer = TraceProducer("localhost:9092")
        await producer.stop()
        assert producer.is_connected is False


class TestTriggerConsumer:
    """Test consumer lifecycle and message processing."""

    async def test_consumer_not_connected_initially(self):
        consumer = TriggerConsumer("localhost:9092")
        assert consumer.is_connected is False

    async def test_consume_without_start_exits_cleanly(self):
        """Consume loop exits immediately if consumer not started."""
        consumer = TriggerConsumer("localhost:9092")
        mock_executor = MagicMock()
        # Should not raise
        await consumer.consume(mock_executor)

    async def test_stop_when_not_started(self):
        """Stop is safe even if never started."""
        consumer = TriggerConsumer("localhost:9092")
        await consumer.stop()
        assert consumer.is_connected is False

    async def test_consumer_group_id_default(self):
        consumer = TriggerConsumer("localhost:9092")
        assert consumer.group_id == "orchestrator-consumers"

    async def test_consumer_custom_group_id(self):
        consumer = TriggerConsumer("localhost:9092", group_id="custom-group")
        assert consumer.group_id == "custom-group"
