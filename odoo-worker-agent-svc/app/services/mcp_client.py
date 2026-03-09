"""Async HTTP client for odoo-mcp-server-svc tool execution."""

import logging
from typing import Any, Optional

import httpx

from app.services.circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)


class ToolCallResponse:
    """Response from an MCP tool call."""

    def __init__(
        self,
        success: bool,
        data: dict[str, Any],
        error: Optional[str] = None,
        tool_name: str = "",
    ) -> None:
        self.success = success
        self.data = data
        self.error = error
        self.tool_name = tool_name

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "tool_name": self.tool_name,
        }


class MCPClient:
    """Async HTTP client for odoo-mcp-server-svc tool execution."""

    def __init__(
        self,
        base_url: str,
        timeout: float = 60.0,
        circuit_breaker: Optional[CircuitBreaker] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._circuit_breaker = circuit_breaker or CircuitBreaker()
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Return an HTTP client, creating one if needed."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self._timeout,
            )
        return self._client

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        tenant_id: str,
    ) -> ToolCallResponse:
        """Execute a single MCP tool via POST /execute on the MCP server."""
        if self._circuit_breaker.is_open:
            logger.warning("Circuit breaker OPEN — rejecting call to %s", tool_name)
            return ToolCallResponse(
                success=False,
                data={},
                error="Circuit breaker open — MCP server unavailable",
                tool_name=tool_name,
            )

        try:
            client = await self._get_client()
            payload = {
                "tool_name": tool_name,
                "arguments": arguments,
            }
            headers = {"X-Tenant-ID": tenant_id}

            response = await client.post(
                "/execute",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()

            data = response.json()
            self._circuit_breaker.record_success()

            return ToolCallResponse(
                success=True,
                data=data,
                tool_name=tool_name,
            )

        except httpx.TimeoutException:
            self._circuit_breaker.record_failure()
            logger.error("MCP tool call timed out: %s", tool_name)
            return ToolCallResponse(
                success=False,
                data={},
                error=f"Timeout calling MCP tool: {tool_name}",
                tool_name=tool_name,
            )
        except httpx.HTTPStatusError as exc:
            self._circuit_breaker.record_failure()
            logger.error(
                "MCP tool call HTTP error: %s → %d",
                tool_name,
                exc.response.status_code,
            )
            return ToolCallResponse(
                success=False,
                data={},
                error=f"HTTP {exc.response.status_code} from MCP: {tool_name}",
                tool_name=tool_name,
            )
        except Exception as exc:
            self._circuit_breaker.record_failure()
            logger.error("MCP tool call failed: %s — %s", tool_name, exc)
            return ToolCallResponse(
                success=False,
                data={},
                error=f"Failed to call MCP tool {tool_name}: {exc}",
                tool_name=tool_name,
            )

    async def list_tools(self, tenant_id: str) -> list[dict[str, Any]]:
        """List available tools from the MCP server."""
        try:
            client = await self._get_client()
            response = await client.get(
                "/tools",
                headers={"X-Tenant-ID": tenant_id},
            )
            response.raise_for_status()
            return response.json().get("tools", [])
        except Exception as exc:
            logger.warning("Failed to list MCP tools: %s", exc)
            return []

    async def health_check(self) -> bool:
        """Check MCP server health."""
        try:
            client = await self._get_client()
            response = await client.get("/health")
            return response.status_code == 200
        except Exception:
            return False

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
