"""Tests for SKL-MRA-06: ResearchReportGenerator."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.skills.models import SkillContext
from app.skills.research_report_generator import ResearchReportGenerator


def _ctx() -> SkillContext:
    return SkillContext(session_id="s1", tenant_id="t1")


class TestResearchReportGenerator:
    async def test_stub_mode(self):
        skill = ResearchReportGenerator(anthropic_client=None)
        result = await skill.execute(
            {
                "findings": ["Finding 1", "Finding 2"],
                "analysis": "Test analysis",
                "prompt": "AI market",
            },
            _ctx(),
        )
        assert result.success
        assert "report_text" in result.data
        assert result.data["word_count"] > 0

    async def test_no_findings_fails(self):
        skill = ResearchReportGenerator(anthropic_client=None)
        result = await skill.execute(
            {"findings": [], "analysis": "", "prompt": "test"}, _ctx()
        )
        assert not result.success
        assert "No findings" in result.error

    async def test_meta_correct(self):
        skill = ResearchReportGenerator()
        assert skill.meta.skill_id == "SKL-MRA-06"
        assert "VIEWER" not in skill.meta.allowed_roles
