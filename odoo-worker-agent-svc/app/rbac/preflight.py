"""RBAC pre-flight — validates permissions before MCP tool execution."""

import logging
from typing import Optional

from app.services.mcp_client import MCPClient

logger = logging.getLogger(__name__)


class RBACPreflight:
    """Pre-validates user permissions before executing MCP tools.

    The MCP server's ToolDispatcher enforces RBAC at execution time.
    This pre-flight check is a fast-fail optimization: it verifies the
    requested tool exists in the MCP server's registry. If the tool is
    unknown, we skip the PAOR call entirely rather than waiting for a
    404/error from the MCP server.

    Full RBAC enforcement (role-based) is delegated to the MCP server
    itself, which evaluates tenant roles on every /tools/call request.
    """

    def __init__(
        self,
        mcp_client: Optional[MCPClient] = None,
        enabled: bool = True,
    ) -> None:
        self._mcp_client = mcp_client
        self._enabled = enabled
        self._known_tools: Optional[set[str]] = None

    async def check(
        self,
        tool_name: str,
        tenant_id: str,
        user_roles: list[str],
    ) -> bool:
        """Check if the tool exists in the MCP server's registry.

        Returns True if allowed (or if RBAC is disabled / tools unknown).
        Fails open on errors to avoid blocking legitimate requests.
        """
        if not self._enabled:
            return True

        try:
            if self._mcp_client and self._known_tools is None:
                await self._load_tools(tenant_id)

            if self._known_tools and tool_name not in self._known_tools:
                logger.warning(
                    "RBAC pre-flight: tool %s not in MCP registry", tool_name
                )
                return False

            return True
        except Exception as exc:
            logger.warning(
                "RBAC pre-flight error for %s: %s — failing open",
                tool_name,
                exc,
            )
            return True  # fail open

    async def _load_tools(self, tenant_id: str) -> None:
        """Cache the set of available tool names from the MCP server."""
        try:
            tools = await self._mcp_client.list_tools(tenant_id)
            self._known_tools = {t.get("name", "") for t in tools}
            logger.info("RBAC pre-flight: cached %d tool names", len(self._known_tools))
        except Exception as exc:
            logger.warning("Failed to load MCP tools for pre-flight: %s", exc)
            self._known_tools = None
