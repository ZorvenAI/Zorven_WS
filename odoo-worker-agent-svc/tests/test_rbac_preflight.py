"""Tests for RBAC pre-flight checks."""

from unittest.mock import AsyncMock, MagicMock

from app.rbac.preflight import RBACPreflight


async def test_disabled_always_allows():
    """Should allow all when RBAC is disabled."""
    preflight = RBACPreflight(enabled=False)
    assert await preflight.check("any_tool", "tenant", ["role"]) is True


async def test_no_mcp_client_allows():
    """Should allow when no MCP client available."""
    preflight = RBACPreflight(mcp_client=None, enabled=True)
    assert await preflight.check("tool", "tenant", ["role"]) is True


async def test_tool_exists_in_registry():
    """Should allow when tool exists in MCP registry."""
    mock_mcp = MagicMock()
    mock_mcp.list_tools = AsyncMock(
        return_value=[{"name": "odoo_search"}, {"name": "sales_create_order"}]
    )

    preflight = RBACPreflight(mcp_client=mock_mcp, enabled=True)
    assert await preflight.check("odoo_search", "tenant", ["sales_user"]) is True


async def test_tool_not_in_registry():
    """Should deny when tool does not exist in MCP registry."""
    mock_mcp = MagicMock()
    mock_mcp.list_tools = AsyncMock(
        return_value=[{"name": "odoo_search"}, {"name": "sales_create_order"}]
    )

    preflight = RBACPreflight(mcp_client=mock_mcp, enabled=True)
    assert await preflight.check("nonexistent_tool", "tenant", ["role"]) is False


async def test_tool_list_cached():
    """Should only call list_tools once (cache on first check)."""
    mock_mcp = MagicMock()
    mock_mcp.list_tools = AsyncMock(return_value=[{"name": "odoo_search"}])

    preflight = RBACPreflight(mcp_client=mock_mcp, enabled=True)
    await preflight.check("odoo_search", "tenant", ["role"])
    await preflight.check("odoo_search", "tenant", ["role"])

    mock_mcp.list_tools.assert_awaited_once()


async def test_list_tools_error_fails_open():
    """Should fail open when list_tools raises an error."""
    mock_mcp = MagicMock()
    mock_mcp.list_tools = AsyncMock(side_effect=Exception("connection error"))

    preflight = RBACPreflight(mcp_client=mock_mcp, enabled=True)
    assert await preflight.check("tool", "tenant", ["role"]) is True
