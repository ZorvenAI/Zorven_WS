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

# Well-known external agent service endpoints.
# Used by PipelineComposer (auto-detect mode) to resolve agent names
# to HTTP URLs for ExternalWrapper.
EXTERNAL_ENDPOINTS: dict[str, str] = {
    "discovery": "http://discovery-agent-svc:8020/v1/execute",
    "intelligence": "http://intelligence-agent-svc:8030/v1/execute",
    "content": "http://content-agent-svc:8050/v1/execute",
    "social": "http://social-agent-svc:8060/v1/execute",
    "rag_uploader": "http://rag-uploader-agent-svc:8070/v1/execute",
    "odoo_mcp": "http://odoo-mcp-server:8095/execute",
    "odoo_worker": "http://odoo-worker-agent:8100/v1/execute",
    "market_research": "http://market-research-agent-svc:8021/v1/execute",
    "competitor_intelligence": "http://competitor-intel-agent-svc:8022/v1/execute",
    "audience_persona": "http://audience-persona-agent-svc:8023/v1/execute",
    "trend_cultural": "http://trend-cultural-agent-svc:8024/v1/execute",
    "voice_of_customer": "http://voc-agent-svc:8025/v1/execute",
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
