"""Tool registry — central registry for all MCP tools."""

import logging
from typing import Any, Optional

from app.tools.base import BaseTool

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Central registry for Odoo MCP tools."""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """Register a tool instance."""
        if tool.name in self._tools:
            logger.warning("Overwriting tool: %s", tool.name)
        self._tools[tool.name] = tool
        logger.debug("Registered tool: %s (%s)", tool.name, tool.domain)

    def get_tool(self, name: str) -> Optional[BaseTool]:
        """Get a tool by name."""
        return self._tools.get(name)

    def list_tools(self, domain: Optional[str] = None) -> list[dict[str, Any]]:
        """List all tools, optionally filtered by domain."""
        tools = self._tools.values()
        if domain:
            tools = [t for t in tools if t.domain == domain]
        return [t.to_mcp_dict() for t in tools]

    def list_domains(self) -> list[str]:
        """List all unique tool domains."""
        return sorted({t.domain for t in self._tools.values()})

    async def dispatch(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        context: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Dispatch a tool call by name."""
        tool = self._tools.get(tool_name)
        if tool is None:
            return {"error": f"Unknown tool: {tool_name}"}
        try:
            return await tool.execute(arguments, context)
        except Exception as exc:
            logger.error("Tool %s failed: %s", tool_name, exc)
            return {"error": str(exc)}

    @property
    def count(self) -> int:
        return len(self._tools)
