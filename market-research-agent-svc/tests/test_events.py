"""Tests for event catalog and emitter."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.events.catalog import EventCatalog, EventEmitter
from app.messaging.kafka_producer import AuditProducer


class TestEventCatalog:
    def test_all_14_events_defined(self):
        assert EventCatalog.SESSION_STARTED == "EVT-001"
        assert EventCatalog.SESSION_COMPLETED == "EVT-011"
        assert EventCatalog.RBAC_DECISION == "EVT-014"
        assert len(EventCatalog.DESCRIPTIONS) == 14

    def test_descriptions_match_events(self):
        assert EventCatalog.DESCRIPTIONS["EVT-001"] == "agent.session.started"
        assert EventCatalog.DESCRIPTIONS["EVT-005"] == "agent.tool.called"
        assert EventCatalog.DESCRIPTIONS["EVT-012"] == "circuit_breaker.opened"


class TestEventEmitter:
    async def test_emit_logs_event(self, caplog):
        import logging

        emitter = EventEmitter(audit_producer=None)
        with caplog.at_level(logging.INFO):
            await emitter.emit(
                EventCatalog.SESSION_STARTED,
                tenant_id="t1",
                session_id="s1",
                payload={"test": True},
            )
        assert "EVT-001" in caplog.text
        assert "agent.session.started" in caplog.text

    async def test_emit_sends_to_kafka(self):
        producer = MagicMock(spec=AuditProducer)
        producer.send_audit = AsyncMock()
        emitter = EventEmitter(audit_producer=producer)
        await emitter.emit(
            EventCatalog.TOOL_CALLED,
            tenant_id="t1",
            session_id="s1",
        )
        producer.send_audit.assert_awaited_once()

    async def test_emit_handles_kafka_failure(self):
        producer = MagicMock(spec=AuditProducer)
        producer.send_audit = AsyncMock(side_effect=Exception("Kafka down"))
        emitter = EventEmitter(audit_producer=producer)
        # Should not raise
        await emitter.emit(
            EventCatalog.TOOL_CALLED,
            tenant_id="t1",
            session_id="s1",
        )

    async def test_emit_without_producer(self):
        emitter = EventEmitter(audit_producer=None)
        # Should not raise
        await emitter.emit(
            EventCatalog.SESSION_COMPLETED,
            tenant_id="t1",
            session_id="s1",
        )
