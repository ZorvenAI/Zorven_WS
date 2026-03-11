"""Tests for Kafka producers — lifecycle and message emission."""

from unittest.mock import AsyncMock, MagicMock, patch

from app.messaging.kafka_producer import AuditProducer, TraceProducer


class TestTraceProducer:
    async def test_start_no_bootstrap_servers(self):
        producer = TraceProducer("")
        await producer.start()
        assert not producer.is_connected

    async def test_stop_when_not_connected(self):
        producer = TraceProducer("")
        await producer.stop()  # Should not raise
        assert not producer.is_connected

    async def test_send_step_when_not_connected(self):
        producer = TraceProducer("")
        # Should not raise
        await producer.send_step(
            job_id="job-1",
            message="test message",
        )

    async def test_send_step_with_metadata(self):
        producer = TraceProducer("")
        # Not connected, should no-op gracefully
        await producer.send_step(
            job_id="job-1",
            message="test",
            metadata={"action": "search"},
            status="COMPLETED",
        )

    async def test_send_step_uses_correct_topic(self):
        producer = TraceProducer("localhost:9092")
        mock_kafka_producer = AsyncMock()
        producer._producer = mock_kafka_producer
        producer._connected = True

        await producer.send_step(job_id="job-1", message="test")

        mock_kafka_producer.send_and_wait.assert_awaited_once()
        call_args = mock_kafka_producer.send_and_wait.call_args
        assert call_args.args[0] == "agent-trace-topic"

    async def test_send_step_error_silent(self):
        producer = TraceProducer("localhost:9092")
        mock_kafka_producer = AsyncMock()
        mock_kafka_producer.send_and_wait.side_effect = Exception("Kafka down")
        producer._producer = mock_kafka_producer
        producer._connected = True

        # Should not raise
        await producer.send_step(job_id="job-1", message="test")


class TestAuditProducer:
    async def test_start_no_bootstrap_servers(self):
        producer = AuditProducer("")
        await producer.start()
        assert not producer.is_connected

    async def test_send_audit_when_not_connected(self):
        producer = AuditProducer("")
        await producer.send_audit(
            job_id="job-1",
            tenant_id="t-1",
            query="test query",
        )

    async def test_send_audit_uses_correct_topic(self):
        producer = AuditProducer("localhost:9092")
        mock_kafka_producer = AsyncMock()
        producer._producer = mock_kafka_producer
        producer._connected = True

        await producer.send_audit(
            job_id="job-1",
            tenant_id="t-1",
            query="test",
            sources_count=5,
            findings_count=3,
            confidence_score=0.8,
            data_sources_used=["tavily", "world_bank"],
        )

        mock_kafka_producer.send_and_wait.assert_awaited_once()
        call_args = mock_kafka_producer.send_and_wait.call_args
        assert call_args.args[0] == "market-research-audit-topic"

    async def test_send_audit_error_silent(self):
        producer = AuditProducer("localhost:9092")
        mock_kafka_producer = AsyncMock()
        mock_kafka_producer.send_and_wait.side_effect = Exception("Kafka down")
        producer._producer = mock_kafka_producer
        producer._connected = True

        # Should not raise
        await producer.send_audit(job_id="job-1", tenant_id="t-1", query="test")
