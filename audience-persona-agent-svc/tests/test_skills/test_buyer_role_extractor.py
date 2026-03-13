"""Tests for SKL-APA-04: Buyer Role Extractor."""

from unittest.mock import AsyncMock

from app.skills.buyer_role_extractor import BuyerRoleExtractor
from app.skills.models import SkillContext


def _ctx():
    return SkillContext(session_id="s", tenant_id="t", user_role="EDITOR")


class TestBuyerRoleExtractor:
    async def test_meta(self):
        skill = BuyerRoleExtractor(AsyncMock())
        assert skill.meta.skill_id == "SKL-APA-04"

    async def test_execute_success(self):
        tavily = AsyncMock()
        tavily.search = AsyncMock(
            return_value=[
                {
                    "title": "B2B buying committee",
                    "url": "https://example.com/buying",
                    "content": "The decision maker is typically the CTO. "
                    "The end user is the developer team. "
                    "Procurement acts as a gatekeeper.",
                }
            ]
        )
        skill = BuyerRoleExtractor(tavily)
        result = await skill.execute({"prompt": "DevOps tools"}, _ctx())
        assert result.success is True
        assert "buyer_roles" in result.data
        roles = [r["role"] for r in result.data["buyer_roles"]]
        assert len(roles) > 0

    async def test_execute_empty_prompt(self):
        skill = BuyerRoleExtractor(AsyncMock())
        result = await skill.execute({"prompt": ""}, _ctx())
        assert result.success is False
