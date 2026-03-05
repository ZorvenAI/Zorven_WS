"""Prometheus-style metrics for Odoo MCP Server.

Lightweight in-memory counters and histograms for monitoring.
Can be exposed via /metrics endpoint if prometheus_client is installed.
"""

import logging
import time
from collections import defaultdict
from typing import Any

logger = logging.getLogger(__name__)


class Metrics:
    """In-memory metrics collector."""

    def __init__(self) -> None:
        self.tool_calls_total: dict[str, int] = defaultdict(int)
        self.tool_errors_total: dict[str, int] = defaultdict(int)
        self.tool_latency_sum: dict[str, float] = defaultdict(float)
        self.tool_latency_count: dict[str, int] = defaultdict(int)
        self.rbac_decisions: dict[str, int] = defaultdict(int)
        self.odoo_rpc_calls: int = 0
        self.odoo_rpc_latency_sum: float = 0.0
        self.odoo_rpc_errors: int = 0

    def record_tool_call(
        self, tool_name: str, duration_ms: float, success: bool = True
    ) -> None:
        """Record a tool invocation."""
        self.tool_calls_total[tool_name] += 1
        self.tool_latency_sum[tool_name] += duration_ms
        self.tool_latency_count[tool_name] += 1
        if not success:
            self.tool_errors_total[tool_name] += 1

    def record_rbac_decision(self, decision: str) -> None:
        """Record an RBAC policy decision."""
        self.rbac_decisions[decision] += 1

    def record_rpc_call(self, duration_ms: float, success: bool = True) -> None:
        """Record an Odoo RPC call."""
        self.odoo_rpc_calls += 1
        self.odoo_rpc_latency_sum += duration_ms
        if not success:
            self.odoo_rpc_errors += 1

    def get_summary(self) -> dict[str, Any]:
        """Return a summary of all metrics."""
        tool_avg = {}
        for name, count in self.tool_latency_count.items():
            if count > 0:
                tool_avg[name] = round(self.tool_latency_sum[name] / count, 2)

        return {
            "tool_calls_total": dict(self.tool_calls_total),
            "tool_errors_total": dict(self.tool_errors_total),
            "tool_avg_latency_ms": tool_avg,
            "rbac_decisions": dict(self.rbac_decisions),
            "odoo_rpc_calls": self.odoo_rpc_calls,
            "odoo_rpc_avg_latency_ms": round(
                self.odoo_rpc_latency_sum / max(self.odoo_rpc_calls, 1), 2
            ),
            "odoo_rpc_errors": self.odoo_rpc_errors,
        }


# Global metrics instance
metrics = Metrics()
