"""MCP client for calling automation tools via SSE transport."""

from __future__ import annotations

import json
import logging
from typing import Any

try:
    from mcp.client.session import ClientSession
    from mcp.client.sse import sse_client
except ImportError:
    ClientSession = None  # type: ignore[assignment,misc]
    sse_client = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


class McpClient:
    """Client that connects to the MCP server via SSE and calls tools."""

    def __init__(self, mcp_url: str) -> None:
        self._url = mcp_url  # e.g. "http://mcp-server:8085/sse"

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Connect to MCP server via SSE and call a single tool."""
        if sse_client is None or ClientSession is None:
            return {"error": "mcp package not installed", "success": False}
        try:
            async with sse_client(url=self._url, timeout=10) as streams:
                async with ClientSession(*streams) as session:
                    await session.initialize()
                    result = await session.call_tool(
                        name=name, arguments=arguments
                    )
                    return self._parse_result(result)
        except Exception as exc:
            logger.error("MCP call_tool(%s) failed: %s", name, exc)
            return {"error": str(exc), "success": False}

    def _parse_result(self, result: Any) -> dict[str, Any]:
        """Parse MCP CallToolResult into a plain dict."""
        if hasattr(result, "isError") and result.isError:
            error_text = ""
            if hasattr(result, "content"):
                for item in result.content:
                    if hasattr(item, "text"):
                        error_text += item.text
            return {"error": error_text or "MCP tool error", "success": False}

        # Extract text content and try to parse as JSON
        text_parts: list[str] = []
        if hasattr(result, "content"):
            for item in result.content:
                if hasattr(item, "text"):
                    text_parts.append(item.text)

        combined = "\n".join(text_parts)
        try:
            return json.loads(combined)
        except (json.JSONDecodeError, ValueError):
            return {"result": combined, "success": True}

    async def create_scheduled_content(
        self,
        user_email: str,
        title: str,
        content: str,
        platforms: list[str],
        scheduled_date: str,
        tenant_id: str | None = None,
        media_urls: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a scheduled content entry via MCP."""
        args: dict[str, Any] = {
            "user_email": user_email,
            "title": title,
            "content": content,
            "platforms": platforms,
            "scheduled_date": scheduled_date,
        }
        if tenant_id:
            args["tenant_id"] = tenant_id
        if media_urls:
            args["media_urls"] = media_urls
        return await self.call_tool("create_scheduled_content", args)

    async def publish_content_now(self, content_id: int) -> dict[str, Any]:
        """Immediately publish a draft or scheduled content entry."""
        return await self.call_tool(
            "publish_content_now", {"content_id": content_id}
        )

    async def post_to_platform(
        self,
        platform: str,
        user_email: str,
        text: str,
        media_urls: list[str] | None = None,
    ) -> dict[str, Any]:
        """Post directly to a specific platform via MCP."""
        tool_name = f"post_to_{platform}"
        args: dict[str, Any] = {
            "user_email": user_email,
            "text": text,
        }
        if media_urls:
            args["media_urls"] = media_urls
        return await self.call_tool(tool_name, args)
