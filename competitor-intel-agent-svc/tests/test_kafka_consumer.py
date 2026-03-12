"""Tests for Kafka consumer — scheduled competitive scans."""

from unittest.mock import AsyncMock, MagicMock, patch

from app.messaging.kafka_consumer import ScheduledScanConsumer
from app.messaging.command_schemas import ScheduledScanCommand, ScheduledScanPayload


class TestScheduledScanConsumer:
    def setup_method(self):
        self.mock_executor = AsyncMock()
        self.mock_redis = AsyncMock()
        self.consumer = ScheduledScanConsumer(
            bootstrap_servers="",
            executor=self.mock_executor,
            redis_manager=self.mock_redis,
        )

    async def test_disabled_when_no_bootstrap(self):
        await self.consumer.start()
        assert not self.consumer.is_connected

    async def test_stop_when_not_started(self):
        await self.consumer.stop()
        assert not self.consumer.is_connected

    async def test_handle_valid_command(self):
        self.mock_redis.check_idempotency = AsyncMock(return_value=False)
        self.mock_redis.set_idempotency = AsyncMock()
        await self.consumer._handle_message({
            "command_id": "cmd-1",
            "command_type": "scheduled_competitive_scan",
            "tenant_id": "t1",
            "payload": {
                "brand_description": "Acme Corp",
                "industry": "SaaS",
                "max_competitors": 5,
                "scan_type": "full",
            },
            "idempotency_key": "schedule:1:2026-01-01",
        })
        self.mock_executor.execute.assert_awaited_once()

    async def test_ignores_unknown_command_type(self):
        await self.consumer._handle_message({
            "command_id": "cmd-2",
            "command_type": "unknown_command",
            "tenant_id": "t1",
        })
        self.mock_executor.execute.assert_not_awaited()

    async def test_skips_empty_tenant(self):
        await self.consumer._handle_message({
            "command_id": "cmd-3",
            "command_type": "scheduled_competitive_scan",
            "tenant_id": "",
        })
        self.mock_executor.execute.assert_not_awaited()

    async def test_idempotency_dedup(self):
        self.mock_redis.check_idempotency = AsyncMock(return_value=True)
        await self.consumer._handle_message({
            "command_id": "cmd-4",
            "command_type": "scheduled_competitive_scan",
            "tenant_id": "t1",
            "idempotency_key": "schedule:1:2026-01-01",
        })
        self.mock_executor.execute.assert_not_awaited()

    async def test_idempotency_redis_failure_continues(self):
        self.mock_redis.check_idempotency = AsyncMock(
            side_effect=Exception("Redis down")
        )
        await self.consumer._handle_message({
            "command_id": "cmd-5",
            "command_type": "scheduled_competitive_scan",
            "tenant_id": "t1",
            "idempotency_key": "schedule:1:2026-01-01",
        })
        # Should still execute despite Redis failure
        self.mock_executor.execute.assert_awaited_once()

    async def test_handle_malformed_message(self):
        # Should not raise
        await self.consumer._handle_message({"bad": "data"})
        self.mock_executor.execute.assert_not_awaited()

    async def test_no_executor_no_crash(self):
        consumer = ScheduledScanConsumer(
            bootstrap_servers="",
            executor=None,
            redis_manager=self.mock_redis,
        )
        self.mock_redis.check_idempotency = AsyncMock(return_value=False)
        self.mock_redis.set_idempotency = AsyncMock()
        # Should not raise even without executor
        await consumer._handle_message({
            "command_id": "cmd-6",
            "command_type": "scheduled_competitive_scan",
            "tenant_id": "t1",
        })


class TestCommandSchemas:
    def test_scan_command_defaults(self):
        cmd = ScheduledScanCommand(command_id="cmd-1", tenant_id="t1")
        assert cmd.command_type == "scheduled_competitive_scan"
        assert cmd.payload.scan_type == "incremental"
        assert cmd.payload.max_competitors == 10
        assert cmd.idempotency_key == ""

    def test_scan_command_full(self):
        cmd = ScheduledScanCommand(
            command_id="cmd-2",
            tenant_id="t1",
            payload=ScheduledScanPayload(
                brand_description="Acme",
                industry="SaaS",
                geography="US",
                max_competitors=15,
                scan_type="full",
            ),
            idempotency_key="schedule:1:2026-01-01",
        )
        assert cmd.payload.brand_description == "Acme"
        assert cmd.payload.scan_type == "full"
        assert cmd.idempotency_key == "schedule:1:2026-01-01"
