"""Tests for the MCP SSE client."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.mcp_client import McpClient


def _make_mcp_result(text: str, is_error: bool = False) -> MagicMock:
    """Build a mock MCP CallToolResult."""
    item = MagicMock()
    item.text = text

    result = MagicMock()
    result.isError = is_error
    result.content = [item]
    return result


class TestCallTool:
    async def test_successful_json_response(self):
        client = McpClient("http://mcp-server:8085/sse")
        response_data = {"content_id": 42, "status": "scheduled"}

        mock_session = AsyncMock()
        mock_session.initialize = AsyncMock()
        mock_session.call_tool = AsyncMock(
            return_value=_make_mcp_result(json.dumps(response_data))
        )

        with patch("app.services.mcp_client.sse_client") as mock_sse, \
             patch("app.services.mcp_client.ClientSession") as mock_cs:
            # Setup async context managers
            mock_sse_ctx = AsyncMock()
            mock_sse_ctx.__aenter__ = AsyncMock(return_value=("read", "write"))
            mock_sse_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_sse.return_value = mock_sse_ctx

            mock_cs_ctx = AsyncMock()
            mock_cs_ctx.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cs_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_cs.return_value = mock_cs_ctx

            result = await client.call_tool("create_scheduled_content", {"title": "test"})

        assert result == response_data
        mock_session.initialize.assert_called_once()
        mock_session.call_tool.assert_called_once_with(
            name="create_scheduled_content", arguments={"title": "test"}
        )

    async def test_mcp_error_response(self):
        client = McpClient("http://mcp-server:8085/sse")

        mock_session = AsyncMock()
        mock_session.initialize = AsyncMock()
        mock_session.call_tool = AsyncMock(
            return_value=_make_mcp_result("User not found", is_error=True)
        )

        with patch("app.services.mcp_client.sse_client") as mock_sse, \
             patch("app.services.mcp_client.ClientSession") as mock_cs:
            mock_sse_ctx = AsyncMock()
            mock_sse_ctx.__aenter__ = AsyncMock(return_value=("read", "write"))
            mock_sse_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_sse.return_value = mock_sse_ctx

            mock_cs_ctx = AsyncMock()
            mock_cs_ctx.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cs_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_cs.return_value = mock_cs_ctx

            result = await client.call_tool("create_scheduled_content", {"title": "test"})

        assert result["success"] is False
        assert "User not found" in result["error"]

    async def test_connection_error_returns_error_dict(self):
        client = McpClient("http://mcp-server:8085/sse")

        with patch("app.services.mcp_client.sse_client") as mock_sse:
            mock_sse_ctx = AsyncMock()
            mock_sse_ctx.__aenter__ = AsyncMock(
                side_effect=ConnectionError("Connection refused")
            )
            mock_sse_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_sse.return_value = mock_sse_ctx

            result = await client.call_tool("create_scheduled_content", {"title": "test"})

        assert result["success"] is False
        assert "error" in result

    async def test_non_json_response(self):
        client = McpClient("http://mcp-server:8085/sse")

        mock_session = AsyncMock()
        mock_session.initialize = AsyncMock()
        mock_session.call_tool = AsyncMock(
            return_value=_make_mcp_result("Content created successfully")
        )

        with patch("app.services.mcp_client.sse_client") as mock_sse, \
             patch("app.services.mcp_client.ClientSession") as mock_cs:
            mock_sse_ctx = AsyncMock()
            mock_sse_ctx.__aenter__ = AsyncMock(return_value=("read", "write"))
            mock_sse_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_sse.return_value = mock_sse_ctx

            mock_cs_ctx = AsyncMock()
            mock_cs_ctx.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cs_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_cs.return_value = mock_cs_ctx

            result = await client.call_tool("some_tool", {})

        assert result["success"] is True
        assert result["result"] == "Content created successfully"


class TestHelperMethods:
    async def test_create_scheduled_content(self):
        client = McpClient("http://mcp-server:8085/sse")
        client.call_tool = AsyncMock(
            return_value={"content_id": 10, "status": "scheduled"}
        )

        result = await client.create_scheduled_content(
            user_email="test@example.com",
            title="Social post - linkedin",
            content="Check out our blog!",
            platforms=["linkedin"],
            scheduled_date="2026-03-01T09:00:00+00:00",
            tenant_id="tenant-1",
        )

        assert result["content_id"] == 10
        client.call_tool.assert_called_once_with(
            "create_scheduled_content",
            {
                "user_email": "test@example.com",
                "title": "Social post - linkedin",
                "content": "Check out our blog!",
                "platforms": ["linkedin"],
                "scheduled_date": "2026-03-01T09:00:00+00:00",
                "tenant_id": "tenant-1",
            },
        )

    async def test_publish_content_now(self):
        client = McpClient("http://mcp-server:8085/sse")
        client.call_tool = AsyncMock(
            return_value={"status": "published", "post_url": "https://linkedin.com/post/123"}
        )

        result = await client.publish_content_now(42)

        assert result["status"] == "published"
        client.call_tool.assert_called_once_with(
            "publish_content_now", {"content_id": 42}
        )

    async def test_post_to_platform(self):
        client = McpClient("http://mcp-server:8085/sse")
        client.call_tool = AsyncMock(
            return_value={"status": "posted", "post_id": "abc123"}
        )

        result = await client.post_to_platform(
            platform="linkedin",
            user_email="test@example.com",
            text="Hello LinkedIn!",
        )

        assert result["status"] == "posted"
        client.call_tool.assert_called_once_with(
            "post_to_linkedin",
            {"user_email": "test@example.com", "text": "Hello LinkedIn!"},
        )

    async def test_create_scheduled_content_without_optional_params(self):
        client = McpClient("http://mcp-server:8085/sse")
        client.call_tool = AsyncMock(return_value={"content_id": 5})

        await client.create_scheduled_content(
            user_email="test@example.com",
            title="Test",
            content="Content",
            platforms=["twitter"],
            scheduled_date="2026-03-01T09:00:00+00:00",
        )

        # Should NOT include tenant_id or media_urls when not provided
        call_args = client.call_tool.call_args[0][1]
        assert "tenant_id" not in call_args
        assert "media_urls" not in call_args


class TestParseResult:
    def test_parse_error_result(self):
        client = McpClient("http://mcp-server:8085/sse")
        result = _make_mcp_result("Something went wrong", is_error=True)
        parsed = client._parse_result(result)
        assert parsed["success"] is False
        assert "Something went wrong" in parsed["error"]

    def test_parse_json_result(self):
        client = McpClient("http://mcp-server:8085/sse")
        data = {"content_id": 42, "status": "scheduled"}
        result = _make_mcp_result(json.dumps(data))
        parsed = client._parse_result(result)
        assert parsed == data

    def test_parse_non_json_result(self):
        client = McpClient("http://mcp-server:8085/sse")
        result = _make_mcp_result("Plain text response")
        parsed = client._parse_result(result)
        assert parsed["result"] == "Plain text response"
        assert parsed["success"] is True
