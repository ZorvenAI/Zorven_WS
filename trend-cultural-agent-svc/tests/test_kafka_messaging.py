"""Tests for Kafka producers and consumer — trace, audit, alert, and scheduled scans."""

from unittest.mock import AsyncMock, MagicMock

from app.messaging.kafka_consumer import ScheduledScanConsumer
from app.messaging.kafka_producer import AlertProducer, AuditProducer, TraceProducer


# ===== TraceProducer =====


class TestTraceProducer:
    """Tests for TraceProducer (agent-trace-topic)."""

    async def test_stub_mode_no_bootstrap(self) -> None:
        """When no bootstrap servers, stub mode: start is no-op."""
        producer = TraceProducer("")
        await producer.start()
        assert not producer._connected

    async def test_send_step_serializes_correctly(self) -> None:
        producer = TraceProducer("localhost:9092")
        mock_kafka_producer = AsyncMock()
        mock_kafka_producer.send_and_wait = AsyncMock()
        producer._producer = mock_kafka_producer
        producer._connected = True

        await producer.send_step("job-1", "Processing trend data", "PROCESSING")
        mock_kafka_producer.send_and_wait.assert_awaited_once()
        call_args = mock_kafka_producer.send_and_wait.call_args
        assert call_args[0][0] == "agent-trace-topic"
        event = call_args[0][1]
        assert event["job_id"] == "job-1"
        assert event["agent"] == "trend-cultural-insights"
        assert event["message"] == "Processing trend data"
        assert event["status"] == "PROCESSING"
        assert "timestamp" in event

    async def test_send_trace_raw_event(self) -> None:
        producer = TraceProducer("localhost:9092")
        mock_kafka_producer = AsyncMock()
        mock_kafka_producer.send_and_wait = AsyncMock()
        producer._producer = mock_kafka_producer
        producer._connected = True

        event = {"job_id": "j1", "custom_field": "value"}
        await producer.send_trace(event)
        mock_kafka_producer.send_and_wait.assert_awaited_once()
        sent_event = mock_kafka_producer.send_and_wait.call_args[0][1]
        assert sent_event["custom_field"] == "value"

    async def test_send_step_not_connected_noop(self) -> None:
        producer = TraceProducer("")
        # Should not raise
        await producer.send_step("job-1", "test", "PROCESSING")

    async def test_send_step_error_swallowed(self) -> None:
        producer = TraceProducer("localhost:9092")
        mock_kafka_producer = AsyncMock()
        mock_kafka_producer.send_and_wait = AsyncMock(
            side_effect=Exception("Kafka down")
        )
        producer._producer = mock_kafka_producer
        producer._connected = True
        # Should not raise
        await producer.send_step("job-1", "test", "PROCESSING")

    async def test_stop_disconnects(self) -> None:
        producer = TraceProducer("localhost:9092")
        mock_kafka_producer = AsyncMock()
        mock_kafka_producer.stop = AsyncMock()
        producer._producer = mock_kafka_producer
        producer._connected = True

        await producer.stop()
        assert not producer._connected
        mock_kafka_producer.stop.assert_awaited_once()

    async def test_stop_when_not_connected(self) -> None:
        producer = TraceProducer("")
        await producer.stop()  # Should not raise


# ===== AuditProducer =====


class TestAuditProducer:
    """Tests for AuditProducer (tcia-trend-audit-topic)."""

    async def test_send_event_serializes(self) -> None:
        producer = AuditProducer("localhost:9092")
        mock_kafka_producer = AsyncMock()
        mock_kafka_producer.send_and_wait = AsyncMock()
        producer._producer = mock_kafka_producer
        producer._connected = True

        event = {
            "event_type": "analysis.completed",
            "job_id": "job-1",
            "tenant_id": "t1",
        }
        await producer.send_event(event)
        mock_kafka_producer.send_and_wait.assert_awaited_once()
        call_args = mock_kafka_producer.send_and_wait.call_args
        assert call_args[0][0] == "tcia-trend-audit-topic"

    async def test_send_event_not_connected_noop(self) -> None:
        producer = AuditProducer("")
        # Should not raise
        await producer.send_event({"event_type": "test"})

    async def test_send_event_error_swallowed(self) -> None:
        producer = AuditProducer("localhost:9092")
        mock_kafka_producer = AsyncMock()
        mock_kafka_producer.send_and_wait = AsyncMock(
            side_effect=Exception("Kafka down")
        )
        producer._producer = mock_kafka_producer
        producer._connected = True
        # Should not raise
        await producer.send_event({"event_type": "test"})


# ===== AlertProducer =====


class TestAlertProducer:
    """Tests for AlertProducer (tcia-trend-alerts-topic)."""

    async def test_send_alert_to_correct_topic(self) -> None:
        producer = AlertProducer("localhost:9092")
        mock_kafka_producer = AsyncMock()
        mock_kafka_producer.send_and_wait = AsyncMock()
        producer._producer = mock_kafka_producer
        producer._connected = True

        alert = {
            "alert_id": "alert-001",
            "trend_slug": "ev-growth",
            "relevance_score": 85,
            "urgency": "this_week",
            "recommendation": "capitalize",
            "affected_personas": ["urban-commuter"],
            "expiry_estimate": "2026-04-01",
        }
        await producer.send_alert("t1", alert)
        mock_kafka_producer.send_and_wait.assert_awaited_once()
        call_args = mock_kafka_producer.send_and_wait.call_args
        assert call_args[0][0] == "tcia-trend-alerts-topic"
        event = call_args[0][1]
        assert event["event_type"] == "opportunity.alert"
        assert event["tenant_id"] == "t1"
        assert event["alert_id"] == "alert-001"
        assert event["trend_slug"] == "ev-growth"
        assert event["urgency"] == "this_week"
        assert "timestamp" in event

    async def test_send_alert_not_connected_noop(self) -> None:
        producer = AlertProducer("")
        # Should not raise
        await producer.send_alert("t1", {"alert_id": "a1"})

    async def test_send_alert_error_swallowed(self) -> None:
        producer = AlertProducer("localhost:9092")
        mock_kafka_producer = AsyncMock()
        mock_kafka_producer.send_and_wait = AsyncMock(
            side_effect=Exception("Kafka down")
        )
        producer._producer = mock_kafka_producer
        producer._connected = True
        # Should not raise
        await producer.send_alert("t1", {"alert_id": "a1"})


# ===== ScheduledScanConsumer =====


class TestScheduledScanConsumer:
    """Tests for the Kafka consumer that handles scheduled scan commands."""

    def setup_method(self) -> None:
        self.mock_executor = AsyncMock()
        self.mock_redis = AsyncMock()
        self.consumer = ScheduledScanConsumer(
            bootstrap_servers="",
            executor=self.mock_executor,
            redis_manager=self.mock_redis,
        )

    async def test_disabled_when_no_bootstrap(self) -> None:
        await self.consumer.start()
        assert not self.consumer._running

    async def test_stop_when_not_started(self) -> None:
        await self.consumer.stop()
        assert not self.consumer._running

    async def test_handles_valid_command(self) -> None:
        self.mock_redis.check_idempotency = AsyncMock(return_value=False)
        self.mock_redis.set_idempotency = AsyncMock()
        await self.consumer._handle_message(
            {
                "command_type": "scheduled_trend_scan",
                "tenant_id": "t1",
                "payload": {
                    "scan_type": "daily_scan",
                    "industry": "EV Charging",
                    "focus_areas": ["social", "cultural"],
                },
                "idempotency_key": "scan:t1:2026-03-13",
            }
        )
        self.mock_executor.execute.assert_awaited_once()

    async def test_skips_empty_tenant(self) -> None:
        await self.consumer._handle_message(
            {
                "command_type": "scheduled_trend_scan",
                "tenant_id": "",
            }
        )
        self.mock_executor.execute.assert_not_awaited()

    async def test_skips_missing_command_type(self) -> None:
        await self.consumer._handle_message(
            {
                "tenant_id": "t1",
            }
        )
        self.mock_executor.execute.assert_not_awaited()

    async def test_idempotency_dedup(self) -> None:
        self.mock_redis.check_idempotency = AsyncMock(return_value=True)
        await self.consumer._handle_message(
            {
                "command_type": "scheduled_trend_scan",
                "tenant_id": "t1",
                "idempotency_key": "scan:t1:2026-03-13",
            }
        )
        self.mock_executor.execute.assert_not_awaited()

    async def test_sets_idempotency_after_execution(self) -> None:
        self.mock_redis.check_idempotency = AsyncMock(return_value=False)
        self.mock_redis.set_idempotency = AsyncMock()
        await self.consumer._handle_message(
            {
                "command_type": "scheduled_trend_scan",
                "tenant_id": "t1",
                "payload": {"scan_type": "daily_scan", "industry": "EV"},
                "idempotency_key": "scan:t1:2026-03-13",
            }
        )
        self.mock_redis.set_idempotency.assert_awaited_once()

    async def test_no_idempotency_key_still_executes(self) -> None:
        await self.consumer._handle_message(
            {
                "command_type": "scheduled_trend_scan",
                "tenant_id": "t1",
                "payload": {"scan_type": "daily_scan"},
            }
        )
        self.mock_executor.execute.assert_awaited_once()

    async def test_handle_malformed_message(self) -> None:
        # Should not raise
        await self.consumer._handle_message({"bad": "data"})
        self.mock_executor.execute.assert_not_awaited()

    async def test_executor_exception_handled(self) -> None:
        self.mock_redis.check_idempotency = AsyncMock(return_value=False)
        self.mock_executor.execute = AsyncMock(
            side_effect=RuntimeError("Executor crashed")
        )
        # Should not raise
        await self.consumer._handle_message(
            {
                "command_type": "scheduled_trend_scan",
                "tenant_id": "t1",
                "payload": {},
            }
        )
