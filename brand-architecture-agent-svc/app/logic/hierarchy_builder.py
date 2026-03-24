"""SKL-BAA-07: Brand hierarchy tree builder (JSON for React Flow)."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class HierarchyBuilder:
    """Build brand hierarchy tree structure."""

    async def build(self, llm_result: dict[str, Any]) -> dict[str, Any]:
        """Extract and validate hierarchy from LLM result."""
        hierarchy = llm_result.get("hierarchy", {})
        root = hierarchy.get("root", {})

        # Calculate depth and node count
        depth = self._calculate_depth(root)
        nodes = self._count_nodes(root)

        return {
            "root": root,
            "total_depth": depth,
            "total_nodes": nodes,
        }

    def _calculate_depth(self, node: dict[str, Any], current: int = 1) -> int:
        """Calculate maximum depth of hierarchy tree."""
        if not node:
            return 0
        if not node.get("children"):
            return current
        return max(
            self._calculate_depth(child, current + 1) for child in node["children"]
        )

    def _count_nodes(self, node: dict[str, Any]) -> int:
        """Count total nodes in hierarchy tree."""
        if not node:
            return 0
        count = 1
        for child in node.get("children", []):
            count += self._count_nodes(child)
        return count
