"""Tests for observability/metrics.py — in-memory metrics collector."""

from app.observability.metrics import Metrics


class TestMetrics:
    def test_record_tool_call_success(self):
        m = Metrics()
        m.record_tool_call("odoo_search", 12.5, success=True)
        assert m.tool_calls_total["odoo_search"] == 1
        assert m.tool_latency_sum["odoo_search"] == 12.5
        assert m.tool_latency_count["odoo_search"] == 1
        assert m.tool_errors_total["odoo_search"] == 0

    def test_record_tool_call_failure(self):
        m = Metrics()
        m.record_tool_call("odoo_search", 5.0, success=False)
        assert m.tool_calls_total["odoo_search"] == 1
        assert m.tool_errors_total["odoo_search"] == 1

    def test_record_rbac_decision(self):
        m = Metrics()
        m.record_rbac_decision("ALLOW")
        m.record_rbac_decision("DENY")
        m.record_rbac_decision("ALLOW")
        assert m.rbac_decisions["ALLOW"] == 2
        assert m.rbac_decisions["DENY"] == 1

    def test_record_rpc_call_success(self):
        m = Metrics()
        m.record_rpc_call(20.0, success=True)
        assert m.odoo_rpc_calls == 1
        assert m.odoo_rpc_latency_sum == 20.0
        assert m.odoo_rpc_errors == 0

    def test_record_rpc_call_failure(self):
        m = Metrics()
        m.record_rpc_call(100.0, success=False)
        assert m.odoo_rpc_calls == 1
        assert m.odoo_rpc_errors == 1

    def test_get_summary_empty(self):
        m = Metrics()
        summary = m.get_summary()
        assert summary["tool_calls_total"] == {}
        assert summary["odoo_rpc_calls"] == 0
        assert summary["odoo_rpc_avg_latency_ms"] == 0.0

    def test_get_summary_with_data(self):
        m = Metrics()
        m.record_tool_call("odoo_search", 10.0)
        m.record_tool_call("odoo_search", 20.0)
        m.record_rpc_call(50.0)
        m.record_rpc_call(150.0)
        m.record_rbac_decision("ALLOW")

        summary = m.get_summary()
        assert summary["tool_calls_total"]["odoo_search"] == 2
        assert summary["tool_avg_latency_ms"]["odoo_search"] == 15.0
        assert summary["odoo_rpc_calls"] == 2
        assert summary["odoo_rpc_avg_latency_ms"] == 100.0
        assert summary["rbac_decisions"]["ALLOW"] == 1

    def test_multiple_tools_tracked_separately(self):
        m = Metrics()
        m.record_tool_call("odoo_search", 10.0)
        m.record_tool_call("odoo_create", 5.0, success=False)
        summary = m.get_summary()
        assert len(summary["tool_calls_total"]) == 2
        assert summary["tool_errors_total"]["odoo_create"] == 1
        assert "odoo_search" not in summary["tool_errors_total"]
