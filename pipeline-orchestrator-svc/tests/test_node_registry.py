"""Tests for the node registry — handler name resolution."""

import pytest

from app.factory.node_registry import INTERNAL_HANDLERS, resolve_handler
from app.nodes.base import BaseNode
from app.nodes.internal.audience_node import AudienceNode
from app.nodes.internal.calendar_node import CalendarNode
from app.nodes.internal.default_agent_node import DefaultAgentNode
from app.nodes.internal.manager_node import ManagerNode
from app.nodes.internal.planner_node import PlannerNode
from app.nodes.internal.report_node import ReportNode
from app.nodes.internal.router_node import RouterNode
from app.nodes.internal.strategy_node import StrategyNode


class TestNodeRegistry:
    """Test handler name → class resolution."""

    @pytest.mark.parametrize(
        "name,expected_cls",
        [
            ("RouterNode", RouterNode),
            ("ManagerNode", ManagerNode),
            ("StrategyNode", StrategyNode),
            ("ReportNode", ReportNode),
            ("AudienceNode", AudienceNode),
            ("PlannerNode", PlannerNode),
            ("CalendarNode", CalendarNode),
            ("DefaultAgentNode", DefaultAgentNode),
        ],
    )
    def test_resolve_registered_handler(self, name, expected_cls):
        resolved = resolve_handler(name)
        assert resolved is expected_cls

    def test_resolve_unknown_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown handler"):
            resolve_handler("NonExistentNode")

    def test_all_handlers_are_base_node_subclasses(self):
        for name, cls in INTERNAL_HANDLERS.items():
            assert issubclass(cls, BaseNode), f"{name} is not a BaseNode subclass"

    def test_registry_has_eight_handlers(self):
        assert len(INTERNAL_HANDLERS) == 8
