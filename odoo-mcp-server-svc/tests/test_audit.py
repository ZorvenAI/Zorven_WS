"""Tests for audit logging — maximise coverage of app/observability/audit.py.

Covers:
  - AuditLogger.log() with and without Kafka
  - AuditLogger.log_rbac()
  - AuditLogger.log_tenant_event() with and without Kafka
  - RuntimeError handling when no event loop is running
  - Entry format verification
"""

import asyncio
import json
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.observability.audit import AuditLogger
from app.observability.metrics import Metrics, metrics

# ── AuditLogger ────────────────────────────────────────────────────


class TestAuditLoggerLog:
    """AuditLogger.log() behaviour."""

    def test_log_without_kafka(self, caplog):
        """log() emits a structured log entry when no Kafka producer
        is configured."""
        logger = AuditLogger()
        with caplog.at_level(logging.INFO, logger="odoo_mcp.audit"):
            logger.log(
                tool_name="odoo_search",
                tenant_id="test",
                success=True,
                duration_ms=50.0,
                model="res.partner",
                operation="read",
            )

        # Verify the JSON entry was logged
        assert len(caplog.records) == 1
        entry = json.loads(caplog.records[0].message)
        assert entry["tool_name"] == "odoo_search"
        assert entry["tenant_id"] == "test"
        assert entry["success"] is True
        assert entry["duration_ms"] == 50.0
        assert entry["model"] == "res.partner"
        assert entry["operation"] == "read"
        assert entry["event_type"] == "tool_call"
        assert entry["service"] == "odoo-mcp-server"

    async def test_log_with_kafka(self):
        """log() creates an asyncio task for publish_audit when a Kafka
        producer is provided."""
        mock_producer = AsyncMock()
        logger = AuditLogger(kafka_producer=mock_producer)

        logger.log(
            tool_name="odoo_create",
            tenant_id="t1",
            success=True,
            duration_ms=25.0,
        )

        # Give the event loop a tick so create_task fires
        await asyncio.sleep(0)

        mock_producer.publish_audit.assert_awaited_once()
        entry = mock_producer.publish_audit.call_args[0][0]
        assert entry["tool_name"] == "odoo_create"
        assert entry["tenant_id"] == "t1"

    def test_log_with_all_optional_params(self, caplog):
        """log() includes all optional parameters in the entry."""
        logger = AuditLogger()
        with caplog.at_level(logging.INFO, logger="odoo_mcp.audit"):
            logger.log(
                tool_name="odoo_write",
                tenant_id="test",
                success=False,
                duration_ms=100.0,
                user_id="user-42",
                model="sale.order",
                operation="write",
                record_ids=[1, 2, 3],
                error="Permission denied",
                metadata={"fields": ["name", "amount"]},
            )

        entry = json.loads(caplog.records[0].message)
        assert entry["user_id"] == "user-42"
        assert entry["model"] == "sale.order"
        assert entry["operation"] == "write"
        assert entry["record_ids"] == [1, 2, 3]
        assert entry["error"] == "Permission denied"
        assert entry["metadata"] == {"fields": ["name", "amount"]}

    def test_log_with_error(self, caplog):
        """log() records error string when success is False."""
        logger = AuditLogger()
        with caplog.at_level(logging.INFO, logger="odoo_mcp.audit"):
            logger.log(
                tool_name="odoo_write",
                tenant_id="test",
                success=False,
                duration_ms=100.0,
                error="Access denied",
            )

        entry = json.loads(caplog.records[0].message)
        assert entry["success"] is False
        assert entry["error"] == "Access denied"

    def test_log_defaults(self, caplog):
        """log() uses correct defaults for optional params."""
        logger = AuditLogger()
        with caplog.at_level(logging.INFO, logger="odoo_mcp.audit"):
            logger.log(
                tool_name="odoo_search",
                tenant_id="test",
                success=True,
                duration_ms=10.0,
            )

        entry = json.loads(caplog.records[0].message)
        assert entry["user_id"] == ""
        assert entry["model"] == ""
        assert entry["operation"] == ""
        assert entry["record_ids"] == []
        assert entry["error"] == ""
        assert entry["metadata"] == {}

    def test_log_no_event_loop_does_not_crash(self):
        """When called with Kafka but outside an event loop,
        the RuntimeError is caught silently."""
        mock_producer = MagicMock()
        logger = AuditLogger(kafka_producer=mock_producer)

        # Patch asyncio.get_running_loop to raise RuntimeError
        with patch(
            "asyncio.get_running_loop",
            side_effect=RuntimeError("no running event loop"),
        ):
            # Should not raise
            logger.log(
                tool_name="test",
                tenant_id="t1",
                success=True,
                duration_ms=1.0,
            )

    def test_log_entry_has_timestamp(self, caplog):
        """Verify the entry contains an ISO-format timestamp."""
        logger = AuditLogger()
        with caplog.at_level(logging.INFO, logger="odoo_mcp.audit"):
            logger.log(
                tool_name="test",
                tenant_id="t1",
                success=True,
                duration_ms=1.0,
            )

        entry = json.loads(caplog.records[0].message)
        assert "timestamp" in entry
        # Should be parseable ISO format
        assert "T" in entry["timestamp"]

    def test_log_duration_ms_rounded(self, caplog):
        """duration_ms is rounded to 2 decimal places."""
        logger = AuditLogger()
        with caplog.at_level(logging.INFO, logger="odoo_mcp.audit"):
            logger.log(
                tool_name="test",
                tenant_id="t1",
                success=True,
                duration_ms=123.456789,
            )

        entry = json.loads(caplog.records[0].message)
        assert entry["duration_ms"] == 123.46


class TestAuditLoggerLogRbac:
    """AuditLogger.log_rbac() behaviour."""

    def test_log_rbac(self, caplog):
        """log_rbac() emits an RBAC decision entry."""
        logger = AuditLogger()
        with caplog.at_level(logging.INFO, logger="odoo_mcp.audit"):
            logger.log_rbac(
                tenant_id="test",
                user_roles=["sales_user"],
                tool_name="odoo_create",
                model="crm.lead",
                operation="create",
                decision="allow",
            )

        entry = json.loads(caplog.records[0].message)
        assert entry["event_type"] == "rbac_decision"
        assert entry["tenant_id"] == "test"
        assert entry["user_roles"] == ["sales_user"]
        assert entry["tool_name"] == "odoo_create"
        assert entry["model"] == "crm.lead"
        assert entry["operation"] == "create"
        assert entry["decision"] == "allow"
        assert entry["reason"] == ""

    def test_log_rbac_with_reason(self, caplog):
        """log_rbac() includes the reason when provided."""
        logger = AuditLogger()
        with caplog.at_level(logging.INFO, logger="odoo_mcp.audit"):
            logger.log_rbac(
                tenant_id="test",
                user_roles=["viewer"],
                tool_name="odoo_delete",
                model="res.partner",
                operation="unlink",
                decision="deny",
                reason="Insufficient role",
            )

        entry = json.loads(caplog.records[0].message)
        assert entry["decision"] == "deny"
        assert entry["reason"] == "Insufficient role"

    def test_log_rbac_entry_format(self, caplog):
        """Verify the RBAC entry contains timestamp and service."""
        logger = AuditLogger()
        with caplog.at_level(logging.INFO, logger="odoo_mcp.audit"):
            logger.log_rbac(
                tenant_id="t1",
                user_roles=[],
                tool_name="test",
                model="m",
                operation="o",
                decision="allow",
            )

        entry = json.loads(caplog.records[0].message)
        assert "timestamp" in entry
        assert entry["service"] == "odoo-mcp-server"


class TestAuditLoggerLogTenantEvent:
    """AuditLogger.log_tenant_event() behaviour."""

    def test_log_tenant_event_without_kafka(self, caplog):
        """log_tenant_event() emits a structured entry when no Kafka
        producer is configured."""
        logger = AuditLogger()
        with caplog.at_level(logging.INFO, logger="odoo_mcp.audit"):
            logger.log_tenant_event(
                event_type="provision",
                tenant_id="new-tenant",
                details={"plan": "enterprise"},
            )

        entry = json.loads(caplog.records[0].message)
        assert entry["event_type"] == "tenant_provision"
        assert entry["tenant_id"] == "new-tenant"
        assert entry["details"] == {"plan": "enterprise"}

    async def test_log_tenant_event_with_kafka(self):
        """log_tenant_event() creates an asyncio task for
        publish_tenant_event when a Kafka producer is provided."""
        mock_producer = AsyncMock()
        logger = AuditLogger(kafka_producer=mock_producer)

        logger.log_tenant_event(
            event_type="provision",
            tenant_id="t1",
            details={"plan": "starter"},
        )

        await asyncio.sleep(0)

        mock_producer.publish_tenant_event.assert_awaited_once()
        entry = mock_producer.publish_tenant_event.call_args[0][0]
        assert entry["event_type"] == "tenant_provision"
        assert entry["tenant_id"] == "t1"

    def test_log_tenant_event_no_details(self, caplog):
        """log_tenant_event() uses empty dict when details is None."""
        logger = AuditLogger()
        with caplog.at_level(logging.INFO, logger="odoo_mcp.audit"):
            logger.log_tenant_event(
                event_type="deprovision",
                tenant_id="t1",
            )

        entry = json.loads(caplog.records[0].message)
        assert entry["details"] == {}

    def test_log_tenant_event_no_event_loop_does_not_crash(self):
        """When called with Kafka but outside an event loop,
        the RuntimeError is caught silently."""
        mock_producer = MagicMock()
        logger = AuditLogger(kafka_producer=mock_producer)

        with patch(
            "asyncio.get_running_loop",
            side_effect=RuntimeError("no running event loop"),
        ):
            # Should not raise
            logger.log_tenant_event(
                event_type="provision",
                tenant_id="t1",
            )

    def test_log_tenant_event_entry_format(self, caplog):
        """Verify the entry contains timestamp and service fields."""
        logger = AuditLogger()
        with caplog.at_level(logging.INFO, logger="odoo_mcp.audit"):
            logger.log_tenant_event(
                event_type="update",
                tenant_id="t1",
            )

        entry = json.loads(caplog.records[0].message)
        assert "timestamp" in entry
        assert entry["service"] == "odoo-mcp-server"


# ── Metrics (preserved from existing tests) ────────────────────────


class TestMetrics:
    def test_record_tool_call(self):
        m = Metrics()
        m.record_tool_call("odoo_search", 50.0)
        assert m.tool_calls_total["odoo_search"] == 1

    def test_record_rpc_call(self):
        m = Metrics()
        m.record_rpc_call(30.0)
        assert m.odoo_rpc_calls == 1

    def test_record_rbac_decision(self):
        m = Metrics()
        m.record_rbac_decision("allow")
        assert m.rbac_decisions["allow"] == 1

    def test_get_summary(self):
        m = Metrics()
        m.record_tool_call("test", 100.0)
        m.record_rpc_call(50.0)
        summary = m.get_summary()
        assert "tool_calls_total" in summary
        assert "odoo_rpc_calls" in summary

    def test_global_metrics_instance(self):
        assert metrics is not None
