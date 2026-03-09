"""RBAC pre-flight — validates permissions before MCP tool execution."""

import logging
from typing import Optional

from app.services.mcp_client import MCPClient

logger = logging.getLogger(__name__)


class RBACPreflight:
    """Pre-validates user permissions before executing MCP tools.

    Acts as an optimization to fail fast before the PAOR loop
    attempts a tool call that would be denied by the MCP server's
    RBAC engine.
    """

    def __init__(
        self,
        mcp_client: Optional[MCPClient] = None,
        enabled: bool = True,
    ) -> None:
        self._mcp_client = mcp_client
        self._enabled = enabled

    async def check(
        self,
        tool_name: str,
        tenant_id: str,
        user_roles: list[str],
    ) -> bool:
        """Check if the user has permission to execute the given tool.

        Returns True if allowed (or if RBAC is disabled).
        Fails open on errors to avoid blocking legitimate requests.
        """
        if not self._enabled:
            return True

        if not user_roles:
            # No roles provided — let MCP server handle enforcement
            return True

        try:
            # Delegate to MCP server's RBAC check if available
            if self._mcp_client:
                return await self._check_via_mcp(tool_name, tenant_id, user_roles)
            return True
        except Exception as exc:
            logger.warning(
                "RBAC pre-flight error for %s: %s — failing open",
                tool_name,
                exc,
            )
            return True  # fail open

    async def _check_via_mcp(
        self,
        tool_name: str,
        tenant_id: str,
        user_roles: list[str],
    ) -> bool:
        """Check permissions via the MCP server's RBAC endpoint."""
        try:
            client = await self._mcp_client._get_client()
            response = await client.post(
                "/rbac/check",
                json={
                    "tool_name": tool_name,
                    "user_roles": user_roles,
                },
                headers={"X-Tenant-ID": tenant_id},
            )
            if response.status_code == 200:
                data = response.json()
                return data.get("allowed", True)
            # Non-200 response — fail open
            return True
        except Exception as exc:
            logger.debug("MCP RBAC check failed: %s — failing open", exc)
            return True
