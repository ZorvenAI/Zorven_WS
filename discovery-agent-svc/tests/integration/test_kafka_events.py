"""Integration test: Kafka trace + audit event emission.

Uses a capture fixture instead of a real Kafka broker.
"""

from unittest.mock import AsyncMock

import pytest

from app.messaging.kafka_producer import AuditProducer, TraceProducer

pytestmark = pytest.mark.integration


class TestTraceEventEmission:
    """Verify trace events are produced correctly."""

    async def test_trace_events_have_required_fields(self) -> None:
        producer = TraceProducer("localhost:9092")
        mock_kafka = AsyncMock()
        producer._producer = mock_kafka
        producer._connected = True

        await producer.send_step(
            "job-1",
            "Searching for brand analysis...",
            metadata={"query": "brand analysis"},
        )

        mock_kafka.send_and_wait.assert_called_once()
        topic, event = mock_kafka.send_and_wait.call_args.args
        assert topic == "agent-trace-topic"
        assert event["job_id"] == "job-1"
        assert event["node_id"] == "discovery_worker"
        assert event["status"] == "PROCESSING"
        assert event["message"] == "Searching for brand analysis..."
        assert "timestamp" in event

    async def test_no_events_when_kafka_disabled(self) -> None:
        producer = TraceProducer("")
        await producer.start()
        assert not producer.is_connected

        # This should not raise
        await producer.send_step("job-1", "test")


class TestAuditEventEmission:
    """Verify audit events contain raw and cleaned content."""

    async def test_audit_events_have_raw_and_cleaned(self) -> None:
        producer = AuditProducer("localhost:9092")
        mock_kafka = AsyncMock()
        producer._producer = mock_kafka
        producer._connected = True

        await producer.send_audit(
            "job-1",
            "tenant-1",
            "https://example.com",
            "<h1>Raw HTML</h1>",
            "# Raw HTML",
        )

        mock_kafka.send_and_wait.assert_called_once()
        topic, event = mock_kafka.send_and_wait.call_args.args
        assert topic == "discovery-audit-topic"
        assert event["raw_html"] == "<h1>Raw HTML</h1>"
        assert event["cleaned_markdown"] == "# Raw HTML"
        assert event["url"] == "https://example.com"
        assert event["tenant_id"] == "tenant-1"
        assert "timestamp" in event

    async def test_no_audit_when_kafka_disabled(self) -> None:
        producer = AuditProducer("")
        await producer.start()
        assert not producer.is_connected

        # Should not raise
        await producer.send_audit("job-1", "tenant-1", "https://x.com", "html", "md")
