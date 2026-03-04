"""Tests for app/main.py — lifespan and app creation."""

from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from app.main import app, lifespan
from app.api import routes
from app.mcp import transport


class TestLifespan:
    async def test_lifespan_initializes_redis_and_mcp(self) -> None:
        """Lifespan creates RedisManager, MCP server, and cleans up."""
        with (
            patch("app.main.RedisManager") as MockRedis,
            patch("app.main.setup_logging"),
            patch("app.main.transport") as mock_transport,
        ):
            mock_redis_instance = AsyncMock()
            MockRedis.return_value = mock_redis_instance

            async with lifespan(app):
                # Redis should be assigned
                assert routes.redis_manager is mock_redis_instance

            # After exit: cleanup
            mock_redis_instance.close.assert_awaited_once()
            assert routes.redis_manager is None
            assert mock_transport.mcp_server is None

    async def test_lifespan_continues_when_mcp_fails(self) -> None:
        """Lifespan continues even if MCP server creation fails."""
        with (
            patch("app.main.RedisManager") as MockRedis,
            patch("app.main.setup_logging"),
            patch(
                "app.mcp.server.create_mcp_server",
                side_effect=ImportError("no mcp"),
            ),
        ):
            mock_redis_instance = AsyncMock()
            MockRedis.return_value = mock_redis_instance

            async with lifespan(app):
                assert routes.redis_manager is mock_redis_instance

            mock_redis_instance.close.assert_awaited_once()


class TestAppCreation:
    def test_app_has_correct_title(self) -> None:
        assert app.title == "Odoo MCP Server"

    def test_app_has_routes(self) -> None:
        route_paths = [r.path for r in app.routes]
        assert "/health" in route_paths
