"""Tests for Communication domain tools."""

from unittest.mock import AsyncMock

from app.tools.comms.tools import (
    ALL_COMMS_TOOLS,
    CreateContact,
    CreateEvent,
    SendMessage,
)


def _mock_context():
    rpc = AsyncMock()
    return {"rpc_client": rpc, "tenant_id": "test"}


class TestSendMessage:
    async def test_send_returns_id(self):
        ctx = _mock_context()
        ctx["rpc_client"].create.return_value = 200
        tool = SendMessage()
        result = await tool.execute(
            {
                "model": "res.partner",
                "res_id": 1,
                "body": "<p>Hello!</p>",
            },
            ctx,
        )
        assert result["id"] == 200
        assert result["model"] == "mail.message"

    async def test_send_no_client(self):
        tool = SendMessage()
        result = await tool.execute(
            {
                "model": "res.partner",
                "res_id": 1,
                "body": "<p>Hello!</p>",
            }
        )
        assert "error" in result


class TestCreateEvent:
    async def test_create_returns_id(self):
        ctx = _mock_context()
        ctx["rpc_client"].create.return_value = 55
        tool = CreateEvent()
        result = await tool.execute(
            {
                "name": "Team Meeting",
                "start": "2026-04-01 10:00:00",
                "stop": "2026-04-01 11:00:00",
            },
            ctx,
        )
        assert result["id"] == 55
        assert result["model"] == "calendar.event"


class TestCreateContact:
    async def test_create_returns_id(self):
        ctx = _mock_context()
        ctx["rpc_client"].create.return_value = 300
        tool = CreateContact()
        result = await tool.execute({"name": "Acme Corp"}, ctx)
        assert result["id"] == 300
        assert result["model"] == "res.partner"


class TestNoClient:
    """Test all tools return error when no RPC client."""

    async def test_create_event_no_client(self):
        tool = CreateEvent()
        result = await tool.execute(
            {
                "name": "Meeting",
                "start": "2026-04-01 10:00:00",
                "stop": "2026-04-01 11:00:00",
            }
        )
        assert "error" in result

    async def test_create_contact_no_client(self):
        tool = CreateContact()
        result = await tool.execute({"name": "test"})
        assert "error" in result


class TestAllCommsTools:
    def test_all_tools_count(self):
        assert len(ALL_COMMS_TOOLS) == 3

    def test_all_tools_have_names(self):
        for tool in ALL_COMMS_TOOLS:
            assert tool.name != ""
            assert tool.domain == "comms"
