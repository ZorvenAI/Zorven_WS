"""Structured audit logging for Odoo MCP Server.

Emits JSON-structured audit entries for tool calls, RBAC decisions,
and tenant operations. Optionally publishes to Kafka.
"""

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger("odoo_mcp.audit")


class AuditLogger:
    """Structured audit logger with optional Kafka publishing."""

    def __init__(self, kafka_producer: Optional[Any] = None) -> None:
        self.kafka_producer = kafka_producer

    def log(
        self,
        tool_name: str,
        tenant_id: str,
        success: bool,
        duration_ms: float,
        user_id: str = "",
        model: str = "",
        operation: str = "",
        record_ids: Optional[list[int]] = None,
        error: str = "",
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        """Emit a structured audit log entry."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "service": "odoo-mcp-server",
            "event_type": "tool_call",
            "tool_name": tool_name,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "model": model,
            "operation": operation,
            "record_ids": record_ids or [],
            "success": success,
            "duration_ms": round(duration_ms, 2),
            "error": error,
            "metadata": metadata or {},
        }

        # Structured log output
        logger.info(json.dumps(entry))

        # Publish to Kafka (fire-and-forget)
        if self.kafka_producer is not None:
            import asyncio

            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self.kafka_producer.publish_audit(entry))
            except RuntimeError:
                pass  # No event loop — skip Kafka

    def log_rbac(
        self,
        tenant_id: str,
        user_roles: list[str],
        tool_name: str,
        model: str,
        operation: str,
        decision: str,
        reason: str = "",
    ) -> None:
        """Emit an RBAC decision audit entry."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "service": "odoo-mcp-server",
            "event_type": "rbac_decision",
            "tenant_id": tenant_id,
            "user_roles": user_roles,
            "tool_name": tool_name,
            "model": model,
            "operation": operation,
            "decision": decision,
            "reason": reason,
        }
        logger.info(json.dumps(entry))

    def log_tenant_event(
        self,
        event_type: str,
        tenant_id: str,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        """Emit a tenant lifecycle event."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "service": "odoo-mcp-server",
            "event_type": f"tenant_{event_type}",
            "tenant_id": tenant_id,
            "details": details or {},
        }
        logger.info(json.dumps(entry))

        if self.kafka_producer is not None:
            import asyncio

            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self.kafka_producer.publish_tenant_event(entry))
            except RuntimeError:
                pass
