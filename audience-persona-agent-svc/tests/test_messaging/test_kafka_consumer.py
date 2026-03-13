"""Tests for ScheduledScanConsumer."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.messaging.kafka_consumer import ScheduledScanConsumer


class TestScheduledScanConsumer:
    def test_init(self):
        consumer = ScheduledScanConsumer(
            bootstrap_servers="localhost:9092",
            consumer_group="test-group",
        )
        assert consumer._bootstrap_servers == "localhost:9092"
        assert consumer._consumer_group == "test-group"
        assert consumer.is_connected is False

    async def test_start_no_bootstrap(self):
        consumer = ScheduledScanConsumer(bootstrap_servers="")
        await consumer.start()
        assert consumer.is_connected is False

    async def test_stop_not_started(self):
        consumer = ScheduledScanConsumer(bootstrap_servers="")
        await consumer.stop()
        assert consumer.is_connected is False

    async def test_handle_message_valid(self):
        mock_executor = AsyncMock()
        mock_redis = AsyncMock()
        mock_redis.check_idempotency = AsyncMock(return_value=True)

        consumer = ScheduledScanConsumer(
            bootstrap_servers="localhost:9092",
            executor=mock_executor,
            redis_manager=mock_redis,
        )

        message = {
            "command_id": "cmd-123",
            "command_type": "scheduled_persona_scan",
            "tenant_id": "tenant-1",
            "payload": {
                "brand_description": "SaaS product",
                "industry": "Technology",
                "scan_type": "full",
            },
            "idempotency_key": "key-1",
        }
        await consumer._handle_message(message)
        mock_executor.execute.assert_called_once()

    async def test_handle_message_duplicate(self):
        mock_executor = AsyncMock()
        mock_redis = AsyncMock()
        mock_redis.check_idempotency = AsyncMock(return_value=False)

        consumer = ScheduledScanConsumer(
            bootstrap_servers="localhost:9092",
            executor=mock_executor,
            redis_manager=mock_redis,
        )

        message = {
            "command_id": "cmd-123",
            "command_type": "scheduled_persona_scan",
            "tenant_id": "tenant-1",
            "payload": {},
            "idempotency_key": "key-dup",
        }
        await consumer._handle_message(message)
        mock_executor.execute.assert_not_called()

    async def test_handle_message_wrong_type(self):
        mock_executor = AsyncMock()
        consumer = ScheduledScanConsumer(
            bootstrap_servers="localhost:9092",
            executor=mock_executor,
        )

        message = {
            "command_id": "cmd-456",
            "command_type": "unknown_command",
            "tenant_id": "tenant-1",
        }
        await consumer._handle_message(message)
        mock_executor.execute.assert_not_called()

    async def test_handle_message_no_tenant(self):
        mock_executor = AsyncMock()
        consumer = ScheduledScanConsumer(
            bootstrap_servers="localhost:9092",
            executor=mock_executor,
        )

        message = {
            "command_id": "cmd-789",
            "command_type": "scheduled_persona_scan",
            "tenant_id": "",
        }
        await consumer._handle_message(message)
        mock_executor.execute.assert_not_called()

    async def test_handle_message_error_graceful(self):
        consumer = ScheduledScanConsumer(
            bootstrap_servers="localhost:9092",
        )
        # Invalid message should not raise
        await consumer._handle_message({"invalid": "data"})
