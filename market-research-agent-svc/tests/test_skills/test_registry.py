"""Tests for SkillRegistry."""

from unittest.mock import AsyncMock

import pytest

from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillMeta, SkillResult
from app.skills.registry import SkillRegistry


class _StubSkill(BaseSkill):
    meta = SkillMeta(
        skill_id="SKL-TEST-01",
        name="stub_skill",
        description="Test stub",
        allowed_roles=["OWNER", "ADMIN"],
    )

    async def execute(self, input_data, context):
        return SkillResult(skill_id=self.meta.skill_id, success=True)


class _ViewerSkill(BaseSkill):
    meta = SkillMeta(
        skill_id="SKL-TEST-02",
        name="viewer_skill",
        description="Viewer accessible",
        allowed_roles=["OWNER", "ADMIN", "EDITOR", "VIEWER"],
    )

    async def execute(self, input_data, context):
        return SkillResult(skill_id=self.meta.skill_id, success=True)


class TestSkillRegistry:
    def test_register_and_get_by_id(self):
        registry = SkillRegistry()
        skill = _StubSkill()
        registry.register(skill)
        assert registry.get_skill("SKL-TEST-01") is skill

    def test_get_by_name(self):
        registry = SkillRegistry()
        skill = _StubSkill()
        registry.register(skill)
        assert registry.get_skill("stub_skill") is skill

    def test_get_nonexistent_returns_none(self):
        registry = SkillRegistry()
        assert registry.get_skill("SKL-NONEXISTENT") is None

    def test_get_all_skills(self):
        registry = SkillRegistry()
        registry.register(_StubSkill())
        registry.register(_ViewerSkill())
        assert len(registry.get_all_skills()) == 2

    def test_skill_ids(self):
        registry = SkillRegistry()
        registry.register(_StubSkill())
        registry.register(_ViewerSkill())
        ids = registry.skill_ids()
        assert "SKL-TEST-01" in ids
        assert "SKL-TEST-02" in ids

    def test_skills_for_role_owner(self):
        registry = SkillRegistry()
        registry.register(_StubSkill())
        registry.register(_ViewerSkill())
        owner_skills = registry.skills_for_role("OWNER")
        assert len(owner_skills) == 2

    def test_skills_for_role_viewer(self):
        registry = SkillRegistry()
        registry.register(_StubSkill())
        registry.register(_ViewerSkill())
        viewer_skills = registry.skills_for_role("VIEWER")
        assert len(viewer_skills) == 1
        assert viewer_skills[0].meta.skill_id == "SKL-TEST-02"

    def test_skill_ids_for_role(self):
        registry = SkillRegistry()
        registry.register(_StubSkill())
        registry.register(_ViewerSkill())
        ids = registry.skill_ids_for_role("VIEWER")
        assert ids == ["SKL-TEST-02"]
