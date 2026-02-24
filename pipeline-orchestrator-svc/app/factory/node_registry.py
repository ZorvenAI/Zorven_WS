"""
Node registry — maps handler name strings to Python node classes.

Handler names come from the manifest's internal node definitions
(e.g., "RouterNode", "ManagerNode") and are resolved to concrete
BaseNode subclasses for use in the LangGraph.
"""

from app.nodes.base import BaseNode
from app.nodes.internal.audience_node import AudienceNode
from app.nodes.internal.calendar_node import CalendarNode
from app.nodes.internal.default_agent_node import DefaultAgentNode
from app.nodes.internal.manager_node import ManagerNode
from app.nodes.internal.planner_node import PlannerNode
from app.nodes.internal.report_node import ReportNode
from app.nodes.internal.router_node import RouterNode
from app.nodes.internal.strategy_node import StrategyNode

INTERNAL_HANDLERS: dict[str, type[BaseNode]] = {
    "RouterNode": RouterNode,
    "ManagerNode": ManagerNode,
    "StrategyNode": StrategyNode,
    "ReportNode": ReportNode,
    "AudienceNode": AudienceNode,
    "PlannerNode": PlannerNode,
    "CalendarNode": CalendarNode,
    "DefaultAgentNode": DefaultAgentNode,
}


def resolve_handler(handler_name: str) -> type[BaseNode]:
    """
    Resolve a handler name string to a BaseNode subclass.

    Raises ValueError if the handler name is not registered.
    """
    if handler_name not in INTERNAL_HANDLERS:
        registered = ", ".join(sorted(INTERNAL_HANDLERS.keys()))
        raise ValueError(
            f"Unknown handler '{handler_name}'. " f"Registered handlers: {registered}"
        )
    return INTERNAL_HANDLERS[handler_name]
