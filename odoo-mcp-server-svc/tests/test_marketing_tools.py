"""Tests for Marketing domain tools."""

from unittest.mock import AsyncMock

from app.tools.marketing.tools import (
    ALL_MARKETING_TOOLS,
    CreateCampaign,
    SchedulePost,
    SendMailing,
)


def _mock_context():
    rpc = AsyncMock()
    return {"rpc_client": rpc, "tenant_id": "test"}


class TestCreateCampaign:
    async def test_create_returns_id(self):
        ctx = _mock_context()
        ctx["rpc_client"].create.return_value = 25
        tool = CreateCampaign()
        result = await tool.execute(
            {
                "subject": "Spring Sale",
                "mailing_model_id": 99,
                "body_html": "<p>Big discounts!</p>",
            },
            ctx,
        )
        assert result["id"] == 25
        assert result["model"] == "mailing.mailing"

    async def test_create_no_client(self):
        tool = CreateCampaign()
        result = await tool.execute(
            {
                "subject": "Spring Sale",
                "mailing_model_id": 99,
                "body_html": "<p>Big discounts!</p>",
            }
        )
        assert "error" in result


class TestSendMailing:
    async def test_send_returns_result(self):
        ctx = _mock_context()
        ctx["rpc_client"].execute_kw.return_value = True
        tool = SendMailing()
        result = await tool.execute({"mailing_id": 25}, ctx)
        assert result["id"] == 25
        assert result["model"] == "mailing.mailing"
        assert result["action"] == "action_send_mail"


class TestSchedulePost:
    async def test_schedule_returns_id(self):
        ctx = _mock_context()
        ctx["rpc_client"].create.return_value = 30
        tool = SchedulePost()
        result = await tool.execute(
            {
                "message": "Check out our new products!",
                "scheduled_date": "2026-04-01 10:00:00",
            },
            ctx,
        )
        assert result["id"] == 30
        assert result["model"] == "social.post"


class TestNoClient:
    """Test all tools return error when no RPC client."""

    async def test_send_mailing_no_client(self):
        tool = SendMailing()
        result = await tool.execute({"mailing_id": 1})
        assert "error" in result

    async def test_schedule_post_no_client(self):
        tool = SchedulePost()
        result = await tool.execute(
            {"message": "test", "scheduled_date": "2026-04-01 10:00:00"}
        )
        assert "error" in result


class TestAllMarketingTools:
    def test_all_tools_count(self):
        assert len(ALL_MARKETING_TOOLS) == 3

    def test_all_tools_have_names(self):
        for tool in ALL_MARKETING_TOOLS:
            assert tool.name != ""
            assert tool.domain == "marketing"
