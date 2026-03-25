"""
Graph builder — converts JSON manifests into LangGraph StateGraph objects.

Performs topological sort to determine execution order, resolves internal
handlers from the node registry, wraps external nodes with ExternalWrapper,
and wires edges into a compiled LangGraph.
"""

import logging
from collections import defaultdict, deque
from typing import Any

from langgraph.graph import END, StateGraph

from app.core.config import settings
from app.factory.node_registry import resolve_handler
from app.nodes.external_wrapper import ExternalWrapper
from app.nodes.tracked import TrackedNode
from app.services.callback_client import CallbackClient
from app.state.schema import AgentState

logger = logging.getLogger(__name__)

# Docker Compose service name → settings attribute mapping.
# Used to translate hardcoded manifest URLs to environment-configured URLs.
_SERVICE_URL_MAP: dict[str, str] = {
    "discovery-agent-svc:8020": settings.DISCOVERY_AGENT_URL,
    "intelligence-agent-svc:8030": settings.INTELLIGENCE_AGENT_URL,
    "content-agent-svc:8050": settings.CONTENT_AGENT_URL,
    "social-agent-svc:8060": settings.SOCIAL_AGENT_URL,
    "rag-uploader-agent-svc:8070": settings.RAG_UPLOADER_AGENT_URL,
    "odoo-worker-agent-svc:8100": settings.ODOO_WORKER_AGENT_URL,
    "market-research-agent-svc:8021": settings.MARKET_RESEARCH_AGENT_URL,
    "competitor-intel-agent-svc:8022": settings.COMPETITOR_INTEL_AGENT_URL,
    "audience-persona-agent-svc:8023": settings.AUDIENCE_PERSONA_AGENT_URL,
    "trend-cultural-agent-svc:8024": settings.TREND_CULTURAL_AGENT_URL,
    "brand-positioning-agent-svc:8031": settings.BRAND_POSITIONING_AGENT_URL,
    "brand-architecture-agent-svc:8032": settings.BRAND_ARCHITECTURE_AGENT_URL,
    "brand-personality-agent-svc:8033": settings.BRAND_PERSONALITY_AGENT_URL,
}


class GraphBuildError(Exception):
    """Raised when a manifest cannot be compiled into a valid graph."""


class GraphBuilder:
    """Converts a manifest_data dict into a compiled LangGraph."""

    @staticmethod
    def build(
        manifest_data: dict[str, Any],
        checkpointer: Any = None,
        callback_client: CallbackClient | None = None,
    ) -> Any:
        """
        Build and compile a LangGraph StateGraph from manifest_data.

        Args:
            manifest_data: Dict with 'nodes', 'edges', and optional 'global_config'.
            checkpointer: Optional LangGraph checkpointer for state persistence.
            callback_client: Optional callback client for per-node progress
                tracking.  When provided, each node is wrapped with
                ``TrackedNode`` which sends HTTP progress callbacks and
                Kafka trace events before and after execution.

        Returns:
            Compiled LangGraph ready for execution.

        Raises:
            GraphBuildError: If the manifest is invalid (cyclic, missing nodes, etc.)
        """
        nodes = manifest_data.get("nodes", [])
        edges = manifest_data.get("edges", [])
        global_config = manifest_data.get("global_config", {})

        if not nodes:
            raise GraphBuildError("Manifest has no nodes")

        # --- Build adjacency and validate node IDs ---
        node_map = {}
        for node in nodes:
            node_id = node["id"]
            if node_id in node_map:
                raise GraphBuildError(f"Duplicate node ID: {node_id}")
            node_map[node_id] = node

        # Validate edges reference existing nodes
        in_degree: dict[str, int] = defaultdict(int)
        out_degree: dict[str, int] = defaultdict(int)
        adjacency: dict[str, list[str]] = defaultdict(list)

        for node_id in node_map:
            in_degree[node_id] = 0

        for edge in edges:
            if len(edge) != 2:
                raise GraphBuildError(f"Invalid edge (expected 2 elements): {edge}")
            src, dst = edge
            if src not in node_map:
                raise GraphBuildError(f"Edge references unknown source node: {src}")
            if dst not in node_map:
                raise GraphBuildError(
                    f"Edge references unknown destination node: {dst}"
                )
            adjacency[src].append(dst)
            in_degree[dst] += 1
            out_degree[src] += 1

        # --- Topological sort (Kahn's algorithm) for cycle detection ---
        sorted_nodes = GraphBuilder._topological_sort(node_map, in_degree, adjacency)

        # --- Identify entry and terminal nodes ---
        entry_nodes = [n for n in sorted_nodes if in_degree[n] == 0]
        terminal_nodes = [n for n in sorted_nodes if out_degree.get(n, 0) == 0]

        if not entry_nodes:
            raise GraphBuildError("No entry node found (all nodes have incoming edges)")

        if len(entry_nodes) > 1:
            logger.warning(
                "Multiple entry nodes found: %s. Using first: %s",
                entry_nodes,
                entry_nodes[0],
            )

        entry_node = entry_nodes[0]

        # --- Build the StateGraph ---
        graph = StateGraph(AgentState)

        for node_id in sorted_nodes:
            node_def = node_map[node_id]
            node_type = node_def.get("type", "internal")
            node_config = node_def.get("config", {})
            # Merge global_config into node config (node config takes precedence)
            merged_config = {**global_config, **node_config}

            if node_type == "internal":
                handler_name = node_def.get("handler")
                if not handler_name:
                    raise GraphBuildError(
                        f"Internal node '{node_id}' missing 'handler' field"
                    )
                handler_cls = resolve_handler(handler_name)
                handler_instance = handler_cls(config=merged_config)
            elif node_type == "external":
                url = node_def.get("url")
                if not url:
                    raise GraphBuildError(
                        f"External node '{node_id}' missing 'url' field"
                    )
                url = GraphBuilder._translate_url(url)
                handler_instance = ExternalWrapper(
                    url=url, node_id=node_id, config=merged_config
                )
            else:
                raise GraphBuildError(
                    f"Unknown node type '{node_type}' for node '{node_id}'"
                )

            # Wrap with progress tracking if callback_client provided
            if callback_client:
                handler_instance = TrackedNode(
                    node_id, handler_instance, callback_client
                )

            graph.add_node(node_id, handler_instance)

        # Set entry point
        graph.set_entry_point(entry_node)

        # Wire edges
        for src, destinations in adjacency.items():
            for dst in destinations:
                graph.add_edge(src, dst)

        # Terminal nodes → END
        for terminal in terminal_nodes:
            graph.add_edge(terminal, END)

        # Compile
        compile_kwargs: dict[str, Any] = {}
        if checkpointer is not None:
            compile_kwargs["checkpointer"] = checkpointer

        compiled = graph.compile(**compile_kwargs)
        logger.info(
            "Graph compiled: %d nodes, %d edges, entry=%s, terminals=%s",
            len(sorted_nodes),
            len(edges),
            entry_node,
            terminal_nodes,
        )
        return compiled

    @staticmethod
    def _translate_url(url: str) -> str:
        """Translate Docker Compose service URLs to environment-configured URLs.

        Manifest nodes may contain hardcoded Docker Compose hostnames
        (e.g. http://discovery-agent-svc:8020/v1/search). On Railway or
        other cloud deployments the internal DNS differs. This method
        replaces the host:port prefix with the value from settings,
        preserving the URL path.
        """
        for compose_host, settings_base in _SERVICE_URL_MAP.items():
            prefix = f"http://{compose_host}"
            if url.startswith(prefix):
                path = url[len(prefix) :]  # e.g. "/v1/search"
                translated = f"{settings_base}{path}"
                if translated != url:
                    logger.debug("Translated URL: %s → %s", url, translated)
                return translated
        return url

    @staticmethod
    def _topological_sort(
        node_map: dict[str, Any],
        in_degree: dict[str, int],
        adjacency: dict[str, list[str]],
    ) -> list[str]:
        """
        Kahn's algorithm — returns topologically sorted node IDs.

        Raises GraphBuildError if the graph contains a cycle.
        """
        queue: deque[str] = deque()
        in_deg = dict(in_degree)

        for node_id in node_map:
            if in_deg.get(node_id, 0) == 0:
                queue.append(node_id)

        sorted_nodes: list[str] = []

        while queue:
            node_id = queue.popleft()
            sorted_nodes.append(node_id)
            for neighbor in adjacency.get(node_id, []):
                in_deg[neighbor] -= 1
                if in_deg[neighbor] == 0:
                    queue.append(neighbor)

        if len(sorted_nodes) != len(node_map):
            visited = set(sorted_nodes)
            cyclic = [n for n in node_map if n not in visited]
            raise GraphBuildError(
                f"Manifest contains a cycle involving nodes: {cyclic}"
            )

        return sorted_nodes
