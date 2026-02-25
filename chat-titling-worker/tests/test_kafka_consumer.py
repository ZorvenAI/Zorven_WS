"""Tests for TitlingConsumer."""

from unittest.mock import AsyncMock, patch, MagicMock

from app.messaging.kafka_consumer import TitlingConsumer
from app.messaging.schemas import TitlingEvent


class TestTitlingConsumer:
    """Tests for the TitlingConsumer class."""

    def test_initial_state(self):
        """Consumer starts disconnected."""
        consumer = TitlingConsumer(
            bootstrap_servers="localhost:9092",
            group_id="test-group",
            topic="test-topic",
        )
        assert consumer.is_connected is False

    async def test_graceful_when_kafka_unavailable(self):
        """No crash when Kafka broker is unavailable."""
        consumer = TitlingConsumer(
            bootstrap_servers="nonexistent:9092",
            group_id="test-group",
            topic="test-topic",
        )

        # start() should catch the error and leave consumer disconnected
        await consumer.start()
        assert consumer.is_connected is False

    async def test_consume_skips_when_not_started(self):
        """Consume loop exits immediately when consumer not started."""
        consumer = TitlingConsumer(
            bootstrap_servers="localhost:9092",
            group_id="test-group",
            topic="test-topic",
        )

        handler = AsyncMock()
        await consumer.consume(handler)
        handler.assert_not_called()

    def test_deserializes_event(self):
        """JSON dict → TitlingEvent."""
        data = {
            "session_id": "abc-123",
            "session_pk": 42,
            "tenant_id": "tenant-1",
            "first_message": "Hello world",
        }
        event = TitlingEvent(**data)
        assert event.session_id == "abc-123"
        assert event.session_pk == 42
        assert event.tenant_id == "tenant-1"
        assert event.first_message == "Hello world"
        assert event.first_response == ""  # default

    def test_deserializes_event_with_response(self):
        """JSON dict with first_response → TitlingEvent."""
        data = {
            "session_id": "abc-123",
            "session_pk": 42,
            "tenant_id": "tenant-1",
            "first_message": "Hello world",
            "first_response": "Hi there!",
        }
        event = TitlingEvent(**data)
        assert event.first_response == "Hi there!"

    async def test_stop_when_not_started(self):
        """Stop is safe when consumer was never started."""
        consumer = TitlingConsumer(
            bootstrap_servers="localhost:9092",
            group_id="test-group",
            topic="test-topic",
        )
        await consumer.stop()  # Should not raise
        assert consumer.is_connected is False
