"""Tests for Kafka producers lifecycle."""

from app.messaging.trace_producer import TraceProducer
from app.messaging.audit_producer import AuditProducer


async def test_trace_producer_disabled():
    """Trace producer should no-op when Kafka not configured."""
    producer = TraceProducer(bootstrap_servers="")
    await producer.start()  # Should not raise
    await producer.send_trace("tenant", "plan", 1, "test")  # Should not raise
    await producer.stop()  # Should not raise


async def test_audit_producer_disabled():
    """Audit producer should no-op when Kafka not configured."""
    producer = AuditProducer(bootstrap_servers="")
    await producer.start()
    await producer.send_audit("tenant", "odoo_search", {}, True)
    await producer.stop()


async def test_trace_producer_topic():
    """Trace producer should have correct topic."""
    assert TraceProducer.TOPIC == "agent-trace-topic"


async def test_audit_producer_topic():
    """Audit producer should have correct topic."""
    assert AuditProducer.TOPIC == "odoo-worker-audit-topic"
