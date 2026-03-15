"""Tests for SKL-VoCA-11: NPS Trend Analyzer."""

import pytest

from app.skills.nps_trend_analyzer import NPSTrendAnalyzer
from app.skills.models import SkillContext


@pytest.fixture
def analyzer_no_llm():
    """NPSTrendAnalyzer without Anthropic client (stub mode)."""
    return NPSTrendAnalyzer(anthropic_client=None)


@pytest.mark.unit
def test_meta_attributes(analyzer_no_llm):
    """Skill meta has correct ID and name."""
    assert analyzer_no_llm.meta.skill_id == "SKL-VoCA-11"
    assert analyzer_no_llm.meta.name == "nps_trend_analyzer"
    assert "VIEWER" not in analyzer_no_llm.meta.allowed_roles
    assert analyzer_no_llm.meta.circuit_breaker_dependency == "llm"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_external_only_proxy_nps(analyzer_no_llm):
    """External-only mode sets nps_available=False and returns proxy_nps."""
    ctx = SkillContext(
        session_id="s1",
        tenant_id="t1",
        user_role="EDITOR",
        operating_mode="external_only",
    )
    result = await analyzer_no_llm.execute(
        {
            "prompt": "NPS analysis",
            "survey_data": {},
            "review_data": {},
        },
        ctx,
    )
    assert result.success is True
    assert result.data["nps_available"] is False
    assert result.data["data_source"] == "review_proxy"
    assert result.data["proxy_nps"] is not None
    assert result.data["current_nps"]["nps_score"] == 0.0
