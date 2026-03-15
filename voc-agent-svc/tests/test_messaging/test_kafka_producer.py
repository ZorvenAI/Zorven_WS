"""Tests for Kafka producers (TraceProducer, AuditProducer, AlertProducer)."""

import pytest

from app.messaging.kafka_producer import (
    AlertProducer,
    AuditProducer,
    TraceProducer,
)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_trace_producer_stub_mode():
    """TraceProducer in stub mode (no bootstrap servers) sends without error."""
    producer = TraceProducer(bootstrap_servers="")
    await producer.start()
    # Should not raise, just log debug
    await producer.send_trace(
        job_id="job-001",
        status="started",
        message="Test trace",
    )
    await producer.send_step(job_id="job-001", step="collecting reviews")
    await producer.stop()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_audit_producer_stub_mode():
    """AuditProducer in stub mode sends events without error."""
    producer = AuditProducer(bootstrap_servers="")
    await producer.start()
    await producer.send_event(
        event_type="VOC_ANALYSIS_COMPLETED",
        event_name="voc_analysis_completed",
        tenant_id="t1",
        session_id="s1",
        data={"test": True},
    )
    await producer.stop()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_alert_producer_stub_mode():
    """AlertProducer in stub mode sends alerts without error."""
    producer = AlertProducer(bootstrap_servers="")
    await producer.start()
    await producer.send_alert(
        tenant_id="t1",
        alert_id="alert-001",
        alert_type="critical_negative_sentiment",
        severity="critical",
        title="Test Alert",
        description="Test alert description",
        recommendation="Take action",
    )
    await producer.stop()
