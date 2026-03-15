"""Tests for ScheduledScanConsumer."""

import pytest
from unittest.mock import AsyncMock

from app.messaging.kafka_consumer import ScheduledScanConsumer


@pytest.mark.asyncio
@pytest.mark.unit
async def test_consumer_stub_mode():
    """Consumer in stub mode (no bootstrap servers) starts without error."""
    consumer = ScheduledScanConsumer(
        bootstrap_servers="",
        consumer_group="test-group",
        executor=AsyncMock(),
        redis_manager=AsyncMock(),
    )
    await consumer.start()
    # Consumer should not have a real consumer
    assert consumer._consumer is None
    await consumer.stop()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_handle_message_missing_tenant_id():
    """Message without tenant_id is skipped."""
    mock_executor = AsyncMock()
    mock_redis = AsyncMock()
    mock_redis.check_idempotency = AsyncMock(return_value=True)

    consumer = ScheduledScanConsumer(
        bootstrap_servers="",
        consumer_group="test-group",
        executor=mock_executor,
        redis_manager=mock_redis,
    )

    # Simulate handling a message with no tenant_id
    await consumer._handle_message(
        {"scan_type": "full", "payload": {"company_name": "TestCorp"}}
    )

    # Executor should NOT have been called
    mock_executor.execute.assert_not_called()
