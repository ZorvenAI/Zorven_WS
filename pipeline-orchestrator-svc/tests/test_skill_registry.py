"""Tests for the skill registry."""

from pathlib import Path

import pytest

from app.skills.loader import load_all_skills
from app.skills.registry import SkillRegistry

FIXTURES_DIR = Path(__file__).parent / "skills"


@pytest.fixture
def registry():
    """Registry loaded from test fixtures."""
    skills = load_all_skills(FIXTURES_DIR)
    return SkillRegistry(skills)


class TestSkillRegistry:
    """Tests for SkillRegistry."""

    def test_skill_count(self, registry):
        assert registry.skill_count == 3  # seo, social, multi-agent

    def test_skills_for_agent_blog_author(self, registry):
        skills = registry.skills_for_agent("blog_author")
        names = [s.meta.name for s in skills]
        assert "test-seo-skill" in names
        assert "test-multi-agent-skill" in names
        assert "test-social-skill" not in names

    def test_skills_for_agent_social_promoter(self, registry):
        skills = registry.skills_for_agent("social_promoter")
        names = [s.meta.name for s in skills]
        assert "test-social-skill" in names
        assert "test-multi-agent-skill" in names
        assert "test-seo-skill" not in names

    def test_skills_for_unknown_agent(self, registry):
        assert registry.skills_for_agent("unknown_agent") == []

    def test_priority_ordering(self, registry):
        skills = registry.skills_for_agent("blog_author")
        # test-seo-skill (priority 10) should come before test-multi-agent (priority 8)
        seo_idx = next(i for i, s in enumerate(skills) if s.meta.name == "test-seo-skill")
        multi_idx = next(
            i for i, s in enumerate(skills) if s.meta.name == "test-multi-agent-skill"
        )
        assert seo_idx < multi_idx


class TestMatchSkills:
    """Tests for trigger matching."""

    def test_matches_on_trigger(self, registry):
        matched = registry.match_skills("blog_author", "Optimize SEO for our blog")
        names = [s.meta.name for s in matched]
        assert "test-seo-skill" in names

    def test_no_match_returns_empty(self, registry):
        matched = registry.match_skills("blog_author", "unrelated topic about weather")
        assert matched == []

    def test_case_insensitive_matching(self, registry):
        matched = registry.match_skills("blog_author", "improve KEYWORD density")
        names = [s.meta.name for s in matched]
        assert "test-seo-skill" in names

    def test_max_skills_limit(self, registry):
        # Both seo and brand triggers match
        matched = registry.match_skills(
            "blog_author", "seo brand keyword optimization", max_skills=1
        )
        assert len(matched) == 1

    def test_token_budget_enforcement(self, registry):
        # test-seo-skill is 200 tokens, test-multi-agent is 180 tokens
        # With budget of 250, only one should fit
        matched = registry.match_skills(
            "blog_author",
            "seo brand keyword optimization",
            max_total_tokens=250,
        )
        assert len(matched) == 1
        assert matched[0].meta.name == "test-seo-skill"  # higher priority

    def test_multiple_triggers_match_same_skill(self, registry):
        matched = registry.match_skills("social_promoter", "post on linkedin and social media")
        names = [s.meta.name for s in matched]
        assert "test-social-skill" in names
        # Should not duplicate
        assert names.count("test-social-skill") == 1


class TestFormatSkillContext:
    """Tests for format_skill_context()."""

    def test_empty_skills_returns_empty_string(self, registry):
        assert registry.format_skill_context([]) == ""

    def test_formats_single_skill(self, registry):
        skills = [s for s in registry.skills_for_agent("blog_author") if s.meta.name == "test-seo-skill"]
        result = registry.format_skill_context(skills)
        assert "## Additional Skill Context" in result
        assert "Test SEO skill" in result
        assert "keywords naturally" in result

    def test_formats_multiple_skills(self, registry):
        skills = registry.skills_for_agent("blog_author")
        result = registry.format_skill_context(skills)
        assert "## Additional Skill Context" in result
        assert "Test SEO skill" in result
        assert "Test skill targeting multiple agents" in result
