"""Tests for Kafka producer and consumer — maximise coverage.

Covers:
  - app/messaging/kafka_producer.py (KafkaProducer)
  - app/messaging/kafka_consumer.py (KafkaConsumer)
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.messaging.kafka_consumer import KafkaConsumer
from app.messaging.kafka_producer import KafkaProducer

# ── KafkaProducer ──────────────────────────────────────────────────


class TestKafkaProducerInit:
    """KafkaProducer.__init__ sets expected defaults."""

    def test_defaults(self):
        producer = KafkaProducer()
        assert producer._producer is None
        assert producer._connected is False

    def test_is_connected_default(self):
        producer = KafkaProducer()
        assert producer.is_connected is False


class TestKafkaProducerStart:
    """KafkaProducer.start() behaviour under various conditions."""

    async def test_start_no_bootstrap_servers(self):
        """When KAFKA_BOOTSTRAP_SERVERS is empty, start() returns early
        and producer remains disconnected."""
        producer = KafkaProducer()
        with patch("app.messaging.kafka_producer.settings") as mock_settings:
            mock_settings.KAFKA_BOOTSTRAP_SERVERS = ""
            await producer.start()

        assert not producer.is_connected
        assert producer._producer is None

    async def test_start_import_failure(self):
        """When aiokafka cannot be imported, start() catches the error
        and leaves producer disconnected."""
        producer = KafkaProducer()
        with patch("app.messaging.kafka_producer.settings") as mock_settings:
            mock_settings.KAFKA_BOOTSTRAP_SERVERS = "localhost:9092"
            # Force the import to fail by patching builtins.__import__
            original_import = (
                __builtins__.__import__
                if hasattr(__builtins__, "__import__")
                else __import__
            )
            with patch("builtins.__import__", side_effect=ImportError("no aiokafka")):
                await producer.start()

        assert not producer.is_connected
        assert producer._producer is None

    async def test_start_success(self):
        """When bootstrap servers are set and aiokafka works, producer
        connects successfully."""
        producer = KafkaProducer()

        mock_aio_producer = AsyncMock()
        mock_aio_producer.start = AsyncMock()

        mock_aiokafka = MagicMock()
        mock_aiokafka.AIOKafkaProducer.return_value = mock_aio_producer

        with patch("app.messaging.kafka_producer.settings") as mock_settings:
            mock_settings.KAFKA_BOOTSTRAP_SERVERS = "localhost:9092"
            with patch.dict("sys.modules", {"aiokafka": mock_aiokafka}):
                await producer.start()

        assert producer.is_connected is True
        assert producer._producer is mock_aio_producer
        mock_aio_producer.start.assert_awaited_once()

    async def test_start_producer_start_raises(self):
        """When the underlying producer.start() raises, the exception
        is caught and _connected stays False."""
        producer = KafkaProducer()

        mock_aio_producer = AsyncMock()
        mock_aio_producer.start = AsyncMock(
            side_effect=RuntimeError("broker unreachable")
        )

        mock_aiokafka = MagicMock()
        mock_aiokafka.AIOKafkaProducer.return_value = mock_aio_producer

        with patch("app.messaging.kafka_producer.settings") as mock_settings:
            mock_settings.KAFKA_BOOTSTRAP_SERVERS = "localhost:9092"
            with patch.dict("sys.modules", {"aiokafka": mock_aiokafka}):
                await producer.start()

        assert not producer.is_connected


class TestKafkaProducerStop:
    """KafkaProducer.stop() in various states."""

    async def test_stop_when_producer_is_none(self):
        """stop() with no producer does not raise."""
        producer = KafkaProducer()
        await producer.stop()
        assert not producer.is_connected

    async def test_stop_calls_producer_stop(self):
        """stop() calls _producer.stop() when connected."""
        producer = KafkaProducer()
        mock_inner = AsyncMock()
        producer._producer = mock_inner
        producer._connected = True

        await producer.stop()

        mock_inner.stop.assert_awaited_once()
        assert producer._producer is None
        assert not producer.is_connected

    async def test_stop_when_producer_stop_raises(self):
        """If the inner producer.stop() raises, state is still reset."""
        producer = KafkaProducer()
        mock_inner = AsyncMock()
        mock_inner.stop = AsyncMock(side_effect=RuntimeError("boom"))
        producer._producer = mock_inner
        producer._connected = True

        await producer.stop()

        assert producer._producer is None
        assert not producer.is_connected


class TestKafkaProducerPublish:
    """publish_audit / publish_tenant_event / _publish."""

    async def test_publish_audit_when_disconnected(self):
        """publish_audit() returns immediately when not connected."""
        producer = KafkaProducer()
        # Should not raise
        await producer.publish_audit({"tool": "test", "tenant": "t1"})

    async def test_publish_tenant_event_when_disconnected(self):
        """publish_tenant_event() returns immediately when not connected."""
        producer = KafkaProducer()
        await producer.publish_tenant_event({"event_type": "provision"})

    async def test_publish_audit_when_connected(self):
        """publish_audit() calls send_and_wait with AUDIT_TOPIC."""
        producer = KafkaProducer()
        mock_inner = AsyncMock()
        producer._producer = mock_inner
        producer._connected = True

        event = {"tool": "test", "tenant": "t1"}
        await producer.publish_audit(event)

        mock_inner.send_and_wait.assert_awaited_once_with(
            KafkaProducer.AUDIT_TOPIC, event
        )

    async def test_publish_tenant_event_when_connected(self):
        """publish_tenant_event() calls send_and_wait with
        TENANT_EVENTS_TOPIC."""
        producer = KafkaProducer()
        mock_inner = AsyncMock()
        producer._producer = mock_inner
        producer._connected = True

        event = {"event_type": "provision"}
        await producer.publish_tenant_event(event)

        mock_inner.send_and_wait.assert_awaited_once_with(
            KafkaProducer.TENANT_EVENTS_TOPIC, event
        )

    async def test_publish_send_and_wait_raises(self):
        """If send_and_wait raises, _publish logs warning but does not
        crash."""
        producer = KafkaProducer()
        mock_inner = AsyncMock()
        mock_inner.send_and_wait = AsyncMock(side_effect=RuntimeError("send failed"))
        producer._producer = mock_inner
        producer._connected = True

        # Should not raise
        await producer.publish_audit({"tool": "failing"})

    async def test_publish_returns_when_producer_none_but_connected_flag(self):
        """Edge case: _connected is True but _producer is None — returns
        early."""
        producer = KafkaProducer()
        producer._connected = True
        producer._producer = None

        # Should not raise
        await producer.publish_audit({"tool": "test"})


class TestKafkaProducerTopics:
    """Verify topic constants."""

    def test_audit_topic(self):
        assert KafkaProducer.AUDIT_TOPIC == "odoo-mcp-audit-topic"

    def test_tenant_events_topic(self):
        assert KafkaProducer.TENANT_EVENTS_TOPIC == "odoo-tenant-events-topic"


# ── KafkaConsumer ──────────────────────────────────────────────────


class TestKafkaConsumerInit:
    """KafkaConsumer.__init__ sets expected defaults."""

    def test_defaults(self):
        consumer = KafkaConsumer()
        assert consumer._consumer is None
        assert consumer._connected is False
        assert consumer._running is False
        assert consumer._on_tenant_provision is None

    def test_callback_stored(self):
        async def handler(event):
            pass

        consumer = KafkaConsumer(on_tenant_provision=handler)
        assert consumer._on_tenant_provision is handler

    def test_is_connected_default(self):
        consumer = KafkaConsumer()
        assert consumer.is_connected is False


class TestKafkaConsumerStart:
    """KafkaConsumer.start() under various conditions."""

    async def test_start_no_bootstrap_servers(self):
        """Returns early when no bootstrap servers configured."""
        consumer = KafkaConsumer()
        with patch("app.messaging.kafka_consumer.settings") as mock_settings:
            mock_settings.KAFKA_BOOTSTRAP_SERVERS = ""
            await consumer.start()

        assert not consumer.is_connected

    async def test_start_success(self):
        """Successful start with mocked aiokafka module."""
        consumer = KafkaConsumer()

        mock_aio_consumer = AsyncMock()
        mock_aio_consumer.start = AsyncMock()

        mock_aiokafka = MagicMock()
        mock_aiokafka.AIOKafkaConsumer.return_value = mock_aio_consumer

        with patch("app.messaging.kafka_consumer.settings") as mock_settings:
            mock_settings.KAFKA_BOOTSTRAP_SERVERS = "localhost:9092"
            with patch.dict("sys.modules", {"aiokafka": mock_aiokafka}):
                await consumer.start()

        assert consumer.is_connected is True
        assert consumer._consumer is mock_aio_consumer

    async def test_start_raises_exception(self):
        """If consumer start raises, _connected stays False."""
        consumer = KafkaConsumer()

        mock_aio_consumer = AsyncMock()
        mock_aio_consumer.start = AsyncMock(side_effect=RuntimeError("broker down"))

        mock_aiokafka = MagicMock()
        mock_aiokafka.AIOKafkaConsumer.return_value = mock_aio_consumer

        with patch("app.messaging.kafka_consumer.settings") as mock_settings:
            mock_settings.KAFKA_BOOTSTRAP_SERVERS = "localhost:9092"
            with patch.dict("sys.modules", {"aiokafka": mock_aiokafka}):
                await consumer.start()

        assert not consumer.is_connected


class TestKafkaConsumerStop:
    """KafkaConsumer.stop() in various states."""

    async def test_stop_when_consumer_is_none(self):
        """stop() with no consumer does not raise."""
        consumer = KafkaConsumer()
        await consumer.stop()
        assert not consumer.is_connected
        assert not consumer._running

    async def test_stop_calls_consumer_stop(self):
        """stop() calls _consumer.stop() and resets state."""
        consumer = KafkaConsumer()
        mock_inner = AsyncMock()
        consumer._consumer = mock_inner
        consumer._connected = True
        consumer._running = True

        await consumer.stop()

        mock_inner.stop.assert_awaited_once()
        assert consumer._consumer is None
        assert not consumer._connected
        assert not consumer._running

    async def test_stop_when_consumer_stop_raises(self):
        """If inner consumer.stop() raises, state is still reset."""
        consumer = KafkaConsumer()
        mock_inner = AsyncMock()
        mock_inner.stop = AsyncMock(side_effect=RuntimeError("stop failed"))
        consumer._consumer = mock_inner
        consumer._connected = True
        consumer._running = True

        await consumer.stop()

        assert consumer._consumer is None
        assert not consumer._connected
        assert not consumer._running


class TestKafkaConsumerConsumeLoop:
    """KafkaConsumer.consume_loop() message processing."""

    async def test_consume_loop_when_not_connected(self):
        """Returns immediately when consumer is not connected."""
        consumer = KafkaConsumer()
        await consumer.consume_loop()
        assert not consumer._running

    async def test_consume_loop_when_consumer_is_none(self):
        """Returns immediately when _consumer is None even if
        _connected is True."""
        consumer = KafkaConsumer()
        consumer._connected = True
        consumer._consumer = None
        await consumer.consume_loop()

    async def test_consume_loop_processes_messages(self):
        """Messages are processed and callback invoked."""
        callback = AsyncMock()
        consumer = KafkaConsumer(on_tenant_provision=callback)

        msg1 = MagicMock()
        msg1.value = {"event_type": "provision", "tenant_id": "t1"}
        msg2 = MagicMock()
        msg2.value = {"event_type": "provision", "tenant_id": "t2"}

        # Create an async iterator that yields messages then stops
        async def message_stream():
            yield msg1
            yield msg2
            consumer._running = False  # stop after processing

        mock_inner = MagicMock()
        mock_inner.__aiter__ = lambda self: message_stream()

        consumer._consumer = mock_inner
        consumer._connected = True

        await consumer.consume_loop()

        assert callback.await_count == 2
        callback.assert_any_await(msg1.value)
        callback.assert_any_await(msg2.value)

    async def test_consume_loop_without_callback(self):
        """Messages are consumed but no callback is invoked when
        on_tenant_provision is None."""
        consumer = KafkaConsumer(on_tenant_provision=None)

        msg = MagicMock()
        msg.value = {"event_type": "provision", "tenant_id": "t1"}

        async def message_stream():
            yield msg
            consumer._running = False

        mock_inner = MagicMock()
        mock_inner.__aiter__ = lambda self: message_stream()

        consumer._consumer = mock_inner
        consumer._connected = True

        # Should not raise even without a callback
        await consumer.consume_loop()

    async def test_consume_loop_callback_exception(self):
        """If the callback raises, the error is logged but processing
        continues."""
        callback = AsyncMock(side_effect=ValueError("handler broke"))
        consumer = KafkaConsumer(on_tenant_provision=callback)

        msg = MagicMock()
        msg.value = {"event_type": "provision", "tenant_id": "t1"}

        async def message_stream():
            yield msg
            consumer._running = False

        mock_inner = MagicMock()
        mock_inner.__aiter__ = lambda self: message_stream()

        consumer._consumer = mock_inner
        consumer._connected = True

        # Should not raise
        await consumer.consume_loop()

        callback.assert_awaited_once_with(msg.value)

    async def test_consume_loop_stops_when_running_false(self):
        """Loop breaks when _running is set to False mid-iteration."""
        callback = AsyncMock()
        consumer = KafkaConsumer(on_tenant_provision=callback)

        msg1 = MagicMock()
        msg1.value = {"event_type": "p", "tenant_id": "t1"}
        msg2 = MagicMock()
        msg2.value = {"event_type": "p", "tenant_id": "t2"}

        async def message_stream():
            yield msg1
            # After first message, stop running
            consumer._running = False
            yield msg2  # This should NOT be processed

        mock_inner = MagicMock()
        mock_inner.__aiter__ = lambda self: message_stream()

        consumer._consumer = mock_inner
        consumer._connected = True

        await consumer.consume_loop()

        # Only the first message's callback should fire
        assert callback.await_count == 1
        callback.assert_awaited_once_with(msg1.value)

    async def test_consume_loop_outer_exception(self):
        """If the async iterator itself raises, the outer except
        catches it and sets _running = False."""
        consumer = KafkaConsumer()

        async def broken_stream():
            raise RuntimeError("Kafka disconnected")
            yield  # pragma: no cover  # noqa: E501

        mock_inner = MagicMock()
        mock_inner.__aiter__ = lambda self: broken_stream()

        consumer._consumer = mock_inner
        consumer._connected = True

        await consumer.consume_loop()

        assert not consumer._running


class TestKafkaConsumerTopic:
    """Verify topic constant."""

    def test_provisioning_topic(self):
        assert KafkaConsumer.PROVISIONING_TOPIC == "tenant-provisioning-topic"
