"""MCP Server — registers tools, resources, and prompts.

Uses the `mcp` Python SDK to create a Model Context Protocol server
that exposes Odoo capabilities to AI agents.
"""

import logging
from typing import Any, Optional

from mcp.server import Server
from mcp.types import (
    GetPromptResult,
    Prompt,
    PromptArgument,
    PromptMessage,
    Resource,
    TextContent,
    Tool,
)

logger = logging.getLogger(__name__)

SERVER_NAME = "odoo-mcp-server"
SERVER_VERSION = "1.0.0"


def create_mcp_server(
    tool_registry: Optional[Any] = None,
    resource_registry: Optional[Any] = None,
    prompt_registry: Optional[Any] = None,
) -> Server:
    """Create and configure the MCP server with all Odoo tools/resources/prompts."""
    server = Server(SERVER_NAME)

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """Return all registered MCP tools."""
        if tool_registry is None:
            return []
        tools = []
        for tool_def in tool_registry.list_tools():
            tools.append(
                Tool(
                    name=tool_def["name"],
                    description=tool_def["description"],
                    inputSchema=tool_def.get("input_schema", {}),
                )
            )
        return tools

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        """Invoke an MCP tool by name."""
        if tool_registry is None:
            return [TextContent(type="text", text="Tool registry not initialized")]
        try:
            result = await tool_registry.dispatch(name, arguments)
            import json

            return [TextContent(type="text", text=json.dumps(result, default=str))]
        except Exception as exc:
            logger.error("Tool %s failed: %s", name, exc)
            return [TextContent(type="text", text=f"Error: {exc}")]

    @server.list_resources()
    async def list_resources() -> list[Resource]:
        """Return all registered MCP resources."""
        if resource_registry is None:
            return []
        return resource_registry.list_resources()

    @server.read_resource()
    async def read_resource(uri: str) -> str:
        """Read an MCP resource by URI."""
        if resource_registry is None:
            return "Resource registry not initialized"
        return await resource_registry.read(uri)

    @server.list_prompts()
    async def list_prompts() -> list[Prompt]:
        """Return all registered MCP prompts."""
        if prompt_registry is None:
            return []
        return prompt_registry.list_prompts()

    @server.get_prompt()
    async def get_prompt(
        name: str, arguments: Optional[dict[str, str]] = None
    ) -> GetPromptResult:
        """Get a specific MCP prompt."""
        if prompt_registry is None:
            return GetPromptResult(
                description="Not available",
                messages=[],
            )
        return await prompt_registry.get_prompt(name, arguments)

    return server
