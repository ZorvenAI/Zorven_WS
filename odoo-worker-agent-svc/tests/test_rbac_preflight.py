"""Tests for RBAC pre-flight checks."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.rbac.preflight import RBACPreflight


async def test_disabled_always_allows():
    """Should allow all when RBAC is disabled."""
    preflight = RBACPreflight(enabled=False)
    assert await preflight.check("any_tool", "tenant", ["role"]) is True


async def test_no_roles_allows():
    """Should allow when no user roles provided."""
    preflight = RBACPreflight(enabled=True)
    assert await preflight.check("any_tool", "tenant", []) is True


async def test_no_mcp_client_allows():
    """Should allow when no MCP client available."""
    preflight = RBACPreflight(mcp_client=None, enabled=True)
    assert await preflight.check("tool", "tenant", ["role"]) is True


async def test_mcp_check_allowed():
    """Should return True when MCP RBAC allows."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"allowed": True}

    mock_http = AsyncMock()
    mock_http.post = AsyncMock(return_value=mock_response)

    mock_mcp = MagicMock()
    mock_mcp._get_client = AsyncMock(return_value=mock_http)

    preflight = RBACPreflight(mcp_client=mock_mcp, enabled=True)
    assert await preflight.check("odoo_search", "tenant", ["sales_user"]) is True


async def test_mcp_check_denied():
    """Should return False when MCP RBAC denies."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"allowed": False}

    mock_http = AsyncMock()
    mock_http.post = AsyncMock(return_value=mock_response)

    mock_mcp = MagicMock()
    mock_mcp._get_client = AsyncMock(return_value=mock_http)

    preflight = RBACPreflight(mcp_client=mock_mcp, enabled=True)
    assert await preflight.check("admin_tool", "tenant", ["basic_user"]) is False


async def test_mcp_check_error_fails_open():
    """Should fail open on MCP errors."""
    mock_mcp = MagicMock()
    mock_mcp._get_client = AsyncMock(side_effect=Exception("connection error"))

    preflight = RBACPreflight(mcp_client=mock_mcp, enabled=True)
    assert await preflight.check("tool", "tenant", ["role"]) is True
