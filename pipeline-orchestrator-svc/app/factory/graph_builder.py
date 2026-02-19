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

from app.factory.node_registry import resolve_handler
from app.nodes.external_wrapper import ExternalWrapper
from app.state.schema import AgentState

logger = logging.getLogger(__name__)


class GraphBuildError(Exception):
    """Raised when a manifest cannot be compiled into a valid graph."""


class GraphBuilder:
    """Converts a manifest_data dict into a compiled LangGraph."""

    @staticmethod
    def build(
        manifest_data: dict[str, Any],
        checkpointer: Any = None,
    ) -> Any:
        """
        Build and compile a LangGraph StateGraph from manifest_data.

        Args:
            manifest_data: Dict with 'nodes', 'edges', and optional 'global_config'.
            checkpointer: Optional LangGraph checkpointer for state persistence.

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
                graph.add_node(node_id, handler_instance)
            elif node_type == "external":
                url = node_def.get("url")
                if not url:
                    raise GraphBuildError(
                        f"External node '{node_id}' missing 'url' field"
                    )
                wrapper = ExternalWrapper(
                    url=url, node_id=node_id, config=merged_config
                )
                graph.add_node(node_id, wrapper)
            else:
                raise GraphBuildError(
                    f"Unknown node type '{node_type}' for node '{node_id}'"
                )

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
