"""Tests for Kafka producers — trace and audit event emission."""

from unittest.mock import AsyncMock

from app.messaging.kafka_producer import AuditProducer, TraceProducer


class TestTraceProducer:
    """TraceProducer tests."""

    async def test_send_step_produces_to_correct_topic(self) -> None:
        producer = TraceProducer("localhost:9092")
        mock_kafka = AsyncMock()
        producer._producer = mock_kafka
        producer._connected = True

        await producer.send_step("job-1", "Searching...")
        mock_kafka.send_and_wait.assert_called_once()
        topic = mock_kafka.send_and_wait.call_args.args[0]
        assert topic == "agent-trace-topic"

    async def test_send_step_event_has_correct_fields(self) -> None:
        producer = TraceProducer("localhost:9092")
        mock_kafka = AsyncMock()
        producer._producer = mock_kafka
        producer._connected = True

        await producer.send_step(
            "job-1", "Scraping URL...", metadata={"url": "https://example.com"}
        )
        event = mock_kafka.send_and_wait.call_args.args[1]
        assert event["job_id"] == "job-1"
        assert event["node_id"] == "discovery_worker"
        assert event["status"] == "PROCESSING"
        assert event["message"] == "Scraping URL..."
        assert event["metadata"]["url"] == "https://example.com"
        assert "timestamp" in event

    async def test_send_step_graceful_when_not_connected(self) -> None:
        producer = TraceProducer("localhost:9092")
        # No _producer set — should not raise
        await producer.send_step("job-1", "test")

    async def test_send_step_graceful_on_send_error(self) -> None:
        producer = TraceProducer("localhost:9092")
        mock_kafka = AsyncMock()
        mock_kafka.send_and_wait = AsyncMock(side_effect=Exception("Kafka down"))
        producer._producer = mock_kafka

        await producer.send_step("job-1", "test")  # Should not raise

    async def test_is_connected_false_when_not_started(self) -> None:
        producer = TraceProducer("localhost:9092")
        assert producer.is_connected is False

    async def test_stop_closes_producer(self) -> None:
        producer = TraceProducer("localhost:9092")
        mock_kafka = AsyncMock()
        producer._producer = mock_kafka
        producer._connected = True

        await producer.stop()
        mock_kafka.stop.assert_called_once()
        assert producer._connected is False

    async def test_noop_when_bootstrap_empty(self) -> None:
        producer = TraceProducer("")
        await producer.start()
        assert not producer.is_connected


class TestAuditProducer:
    """AuditProducer tests."""

    async def test_send_audit_produces_to_correct_topic(self) -> None:
        producer = AuditProducer("localhost:9092")
        mock_kafka = AsyncMock()
        producer._producer = mock_kafka
        producer._connected = True

        await producer.send_audit(
            "job-1", "tenant-1", "https://example.com", "<h1>Hi</h1>", "# Hi"
        )
        topic = mock_kafka.send_and_wait.call_args.args[0]
        assert topic == "discovery-audit-topic"

    async def test_send_audit_includes_raw_and_cleaned(self) -> None:
        producer = AuditProducer("localhost:9092")
        mock_kafka = AsyncMock()
        producer._producer = mock_kafka
        producer._connected = True

        await producer.send_audit(
            "job-1", "tenant-1", "https://example.com", "<h1>Raw</h1>", "# Cleaned"
        )
        event = mock_kafka.send_and_wait.call_args.args[1]
        assert event["raw_html"] == "<h1>Raw</h1>"
        assert event["cleaned_markdown"] == "# Cleaned"
        assert event["url"] == "https://example.com"
        assert event["tenant_id"] == "tenant-1"

    async def test_send_audit_graceful_when_not_connected(self) -> None:
        producer = AuditProducer("localhost:9092")
        await producer.send_audit(
            "job-1", "tenant-1", "https://x.com", "html", "md"
        )  # Should not raise

    async def test_send_audit_graceful_on_error(self) -> None:
        producer = AuditProducer("localhost:9092")
        mock_kafka = AsyncMock()
        mock_kafka.send_and_wait = AsyncMock(side_effect=Exception("Kafka down"))
        producer._producer = mock_kafka

        await producer.send_audit(
            "job-1", "tenant-1", "https://x.com", "html", "md"
        )  # Should not raise
