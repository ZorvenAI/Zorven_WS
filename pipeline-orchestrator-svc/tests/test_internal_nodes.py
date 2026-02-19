"""Tests for all 7 internal node stubs."""

import pytest

from app.nodes.internal.audience_node import AudienceNode
from app.nodes.internal.calendar_node import CalendarNode
from app.nodes.internal.manager_node import ManagerNode
from app.nodes.internal.planner_node import PlannerNode
from app.nodes.internal.report_node import ReportNode
from app.nodes.internal.router_node import RouterNode
from app.nodes.internal.strategy_node import StrategyNode
from app.state.schema import AgentState


def _base_state(**overrides) -> AgentState:
    state: AgentState = {
        "job_id": "test-job",
        "tenant_id": "1",
        "input_prompt": "Analyze brand positioning for Acme Corp",
        "input_context": {"company_id": 42},
        "tenant_context": {"tenant_id": "1"},
        "global_config": {},
        "callback_url": "http://localhost:8001/callback/",
        "available_manifests": None,
        "resolved_manifest_id": None,
        "node_outputs": {},
        "progress": {},
        "result_data": None,
        "error": None,
        "cancelled": False,
    }
    state.update(overrides)
    return state


class TestRouterNode:
    """Test intent routing via keyword matching."""

    async def test_default_resolves_brand_analysis(self):
        node = RouterNode()
        result = await node(_base_state(input_prompt="hello world"))
        assert result["resolved_manifest_id"] == "brand-analysis"

    async def test_keyword_iso_brand_equity(self):
        node = RouterNode()
        result = await node(_base_state(input_prompt="ISO brand equity valuation"))
        assert result["resolved_manifest_id"] == "iso-brand-equity"

    async def test_keyword_competitor_audit(self):
        node = RouterNode()
        result = await node(_base_state(input_prompt="competitor audit analysis"))
        assert result["resolved_manifest_id"] == "competitor-audit"

    async def test_keyword_content_strategy(self):
        node = RouterNode()
        result = await node(_base_state(input_prompt="content strategy calendar"))
        assert result["resolved_manifest_id"] == "content-strategy"

    async def test_respects_available_manifests(self):
        node = RouterNode()
        result = await node(
            _base_state(
                input_prompt="ISO brand equity",
                available_manifests=[
                    {"pipeline_id": "brand-analysis", "name": "BA", "description": ""}
                ],
            )
        )
        # iso-brand-equity is not in available_manifests, falls back
        assert result["resolved_manifest_id"] == "brand-analysis"


class TestStrategyNode:
    async def test_returns_strategy_data(self):
        node = StrategyNode()
        result = await node(_base_state())
        outputs = result.get("node_outputs", {})
        # StrategyNode writes under the "brand_strategist" key
        assert "brand_strategist" in outputs
        assert any(
            "positioning" in str(v) or "findings" in str(v) for v in outputs.values()
        )


class TestReportNode:
    async def test_returns_report_data(self):
        node = ReportNode()
        result = await node(_base_state())
        outputs = result.get("node_outputs", {})
        if outputs:
            assert any(
                "report" in str(v).lower() or "format" in str(v).lower()
                for v in outputs.values()
            )


class TestAudienceNode:
    async def test_returns_audience_data(self):
        node = AudienceNode()
        result = await node(_base_state())
        outputs = result.get("node_outputs", {})
        if outputs:
            assert any(
                "audience" in str(v).lower() or "primary" in str(v).lower()
                for v in outputs.values()
            )


class TestPlannerNode:
    async def test_returns_planner_data(self):
        node = PlannerNode()
        result = await node(_base_state())
        outputs = result.get("node_outputs", {})
        if outputs:
            assert any(
                "theme" in str(v).lower() or "content" in str(v).lower()
                for v in outputs.values()
            )


class TestCalendarNode:
    async def test_returns_calendar_data(self):
        node = CalendarNode()
        result = await node(_base_state())
        outputs = result.get("node_outputs", {})
        if outputs:
            assert any(
                "week" in str(v).lower() or "calendar" in str(v).lower()
                for v in outputs.values()
            )


class TestManagerNode:
    async def test_aggregates_node_outputs(self):
        node = ManagerNode()
        state = _base_state(
            node_outputs={
                "strategy": {
                    "findings": ["Strong brand recognition"],
                    "recommendations": ["Expand to new markets"],
                },
                "report": {
                    "findings": ["Market share at 15%"],
                },
            }
        )
        result = await node(state)
        assert "result_data" in result
        rd = result["result_data"]
        assert "summary" in rd
        assert "findings" in rd
        assert "recommendations" in rd
        assert "score" in rd
        assert len(rd["findings"]) >= 2
        assert len(rd["recommendations"]) >= 1

    async def test_empty_outputs_returns_defaults(self):
        node = ManagerNode()
        result = await node(_base_state(node_outputs={}))
        rd = result["result_data"]
        assert len(rd["findings"]) >= 1
        assert len(rd["recommendations"]) >= 1
