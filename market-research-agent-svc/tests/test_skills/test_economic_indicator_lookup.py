"""Tests for SKL-MRA-04: EconomicIndicatorLookup."""

from unittest.mock import AsyncMock

import pytest

from app.services.api_clients import WorldBankClient
from app.skills.economic_indicator_lookup import EconomicIndicatorLookup
from app.skills.models import SkillContext


def _make_skill(data=None) -> EconomicIndicatorLookup:
    wb = WorldBankClient("https://api.worldbank.org/v2")
    wb.get_multiple_indicators = AsyncMock(return_value=data or {})
    return EconomicIndicatorLookup(wb)


def _ctx() -> SkillContext:
    return SkillContext(session_id="s1", tenant_id="t1")


class TestEconomicIndicatorLookup:
    async def test_success(self):
        skill = _make_skill(
            {
                "gdp": [
                    {
                        "country": "World",
                        "date": "2023",
                        "value": 100e12,
                        "indicator": "GDP",
                    }
                ]
            }
        )
        result = await skill.execute({"indicators": ["gdp"], "country": "WLD"}, _ctx())
        assert result.success
        assert result.data["indicator_count"] == 1
        assert result.data["indicators"][0]["latest_value"] == 100e12

    async def test_empty_indicators_fails(self):
        skill = _make_skill()
        result = await skill.execute({"indicators": []}, _ctx())
        assert not result.success
        assert "No indicators" in result.error

    async def test_handles_api_failure(self):
        skill = _make_skill()
        skill.world_bank_client.get_multiple_indicators = AsyncMock(
            side_effect=Exception("API down")
        )
        result = await skill.execute({"indicators": ["gdp"]}, _ctx())
        assert not result.success

    async def test_meta_correct(self):
        skill = _make_skill()
        assert skill.meta.skill_id == "SKL-MRA-04"
        assert "VIEWER" in skill.meta.allowed_roles
