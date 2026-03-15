"""Tests for SKL-VoCA-12: VoC Strategy Bridge Synthesizer."""

import pytest

from app.skills.voc_strategy_bridge import VoCStrategyBridge
from app.skills.models import SkillContext


@pytest.fixture
def bridge_no_llm():
    """VoCStrategyBridge without Anthropic client (stub mode)."""
    return VoCStrategyBridge(anthropic_client=None)


@pytest.mark.unit
def test_meta_attributes(bridge_no_llm):
    """Skill meta has correct ID and name."""
    assert bridge_no_llm.meta.skill_id == "SKL-VoCA-12"
    assert bridge_no_llm.meta.name == "voc_strategy_bridge"
    assert "VIEWER" not in bridge_no_llm.meta.allowed_roles
    assert bridge_no_llm.meta.circuit_breaker_dependency == "llm"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_health_score_capped_external_only(bridge_no_llm):
    """External-only mode caps VoC health score at 70."""
    ctx = SkillContext(
        session_id="s1",
        tenant_id="t1",
        user_role="EDITOR",
        operating_mode="external_only",
    )
    result = await bridge_no_llm.execute(
        {
            "prompt": "Strategy bridge",
            "sentiment_data": {},
            "theme_data": {},
            "nps_data": {},
        },
        ctx,
    )
    assert result.success is True
    assert result.data["voc_health_score"] <= 70.0
    assert result.data["operating_mode"] == "external_only"
    assert result.data["odoo_onboarding_recommendation"] != ""
