"""Tests for the skill router."""

from pathlib import Path

import pytest

from app.skills.loader import load_all_skills
from app.skills.registry import SkillRegistry
from app.skills.router import SkillRouter

FIXTURES_DIR = Path(__file__).parent / "skills"


@pytest.fixture
def router():
    """SkillRouter loaded from test fixtures."""
    skills = load_all_skills(FIXTURES_DIR)
    registry = SkillRegistry(skills)
    return SkillRouter(registry)


class TestSkillRouter:
    """Tests for SkillRouter."""

    def test_skill_count(self, router):
        assert router.skill_count == 3

    def test_resolves_skills_for_matching_node(self, router):
        result = router.resolve_skills_for_node("blog_author", "optimize seo for our blog")
        assert "skill_context" in result
        assert "skill_names" in result
        assert "test-seo-skill" in result["skill_names"]
        assert "## Additional Skill Context" in result["skill_context"]

    def test_returns_empty_for_no_match(self, router):
        result = router.resolve_skills_for_node("blog_author", "unrelated weather topic")
        assert result == {}

    def test_returns_empty_for_unknown_node(self, router):
        result = router.resolve_skills_for_node("unknown_node", "seo keyword optimization")
        assert result == {}

    def test_multiple_skills_can_match(self, router):
        result = router.resolve_skills_for_node(
            "blog_author", "write seo-optimized content with brand voice"
        )
        assert len(result["skill_names"]) >= 2
        assert "test-seo-skill" in result["skill_names"]
        assert "test-multi-agent-skill" in result["skill_names"]

    def test_respects_max_skills(self, router):
        result = router.resolve_skills_for_node(
            "blog_author", "seo brand keyword", max_skills=1
        )
        assert len(result["skill_names"]) == 1

    def test_social_promoter_gets_social_skills(self, router):
        result = router.resolve_skills_for_node(
            "social_promoter", "promote on social media"
        )
        assert "test-social-skill" in result["skill_names"]
        assert "test-seo-skill" not in result.get("skill_names", [])
