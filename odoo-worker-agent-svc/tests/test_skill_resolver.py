"""Tests for skill registry and router."""

from pathlib import Path

from app.skills.loader import load_all_skills
from app.skills.registry import SkillRegistry
from app.skills.router import SkillRouter

SKILLS_DIR = Path(__file__).parent.parent / "skills"


def _build_registry():
    skills = load_all_skills(SKILLS_DIR)
    return SkillRegistry(skills)


def test_registry_skill_count():
    """Registry should contain all loaded skills."""
    registry = _build_registry()
    assert registry.skill_count >= 22


def test_skills_for_persona():
    """Should return skills targeting a specific persona."""
    registry = _build_registry()
    sales_skills = registry.skills_for_persona("sales_manager")
    assert len(sales_skills) >= 1
    assert all("sales_manager" in s.meta.target_personas for s in sales_skills)


def test_skills_sorted_by_priority():
    """Skills for a persona should be sorted by priority (desc)."""
    registry = _build_registry()
    skills = registry.skills_for_persona("sales_manager")
    if len(skills) >= 2:
        priorities = [s.meta.priority for s in skills]
        assert priorities == sorted(priorities, reverse=True)


def test_match_skills_trigger():
    """Should match skills by trigger keywords."""
    registry = _build_registry()
    matched = registry.match_skills("sales_manager", "Create a sales order")
    assert len(matched) >= 1
    assert any("create-sales-order" == s.meta.name for s in matched)


def test_match_skills_max_budget():
    """Should respect max_total_tokens budget."""
    registry = _build_registry()
    matched = registry.match_skills(
        "general_assistant", "search and find records", max_total_tokens=100
    )
    total = sum(s.meta.max_tokens for s in matched)
    assert total <= 100


def test_match_skills_no_match():
    """Should return empty list for unmatched persona."""
    registry = _build_registry()
    matched = registry.match_skills("nonexistent_persona", "anything")
    assert matched == []


def test_format_skill_context():
    """Should format matched skills into markdown context."""
    registry = _build_registry()
    matched = registry.match_skills("sales_manager", "Create a sales order")
    context = registry.format_skill_context(matched)
    if matched:
        assert "## Additional Skill Context" in context


def test_router_resolve():
    """SkillRouter should resolve skills for a persona."""
    registry = _build_registry()
    router = SkillRouter(registry)
    result = router.resolve_skills_for_persona("sales_manager", "Create a sales order")
    assert "worker_skill_context" in result or result == {}


def test_router_empty_match():
    """SkillRouter should return empty dict for no matches."""
    registry = _build_registry()
    router = SkillRouter(registry)
    result = router.resolve_skills_for_persona("nonexistent_persona", "nothing")
    assert result == {}
