"""Tests for SKL-VoCA-10: Theme Cluster Builder."""

import pytest

from app.skills.theme_cluster_builder import ThemeClusterBuilder
from app.skills.models import SkillContext


@pytest.fixture
def builder_no_llm():
    """ThemeClusterBuilder without Anthropic client (stub mode)."""
    return ThemeClusterBuilder(anthropic_client=None)


@pytest.mark.unit
def test_meta_attributes(builder_no_llm):
    """Skill meta has correct ID and name."""
    assert builder_no_llm.meta.skill_id == "SKL-VoCA-10"
    assert builder_no_llm.meta.name == "theme_cluster_builder"
    assert "VIEWER" not in builder_no_llm.meta.allowed_roles
    assert builder_no_llm.meta.circuit_breaker_dependency == "llm"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_stub_mode_no_anthropic(builder_no_llm, basic_skill_context):
    """When Anthropic client is None, stub theme data is returned."""
    result = await builder_no_llm.execute(
        {"prompt": "Cluster themes", "feedback_data": {}},
        basic_skill_context,
    )
    assert result.success is True
    assert result.skill_id == "SKL-VoCA-10"
    assert result.data["themes"] == []
    assert result.data["total_feedback_analyzed"] == 0
    assert result.data["clustering_method"] == "stub"
