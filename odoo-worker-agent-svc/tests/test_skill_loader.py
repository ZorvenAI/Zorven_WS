"""Tests for skill loader."""

from pathlib import Path

from app.skills.loader import load_all_skills
from app.skills.models import LoadedSkill

SKILLS_DIR = Path(__file__).parent.parent / "skills"


def test_load_all_skills():
    """Should load all 22+ skill files."""
    skills = load_all_skills(SKILLS_DIR)
    assert len(skills) >= 22
    assert all(isinstance(s, LoadedSkill) for s in skills)


def test_skill_names_unique():
    """Each skill should have a unique name."""
    skills = load_all_skills(SKILLS_DIR)
    names = [s.meta.name for s in skills]
    assert len(names) == len(set(names))


def test_skill_required_fields():
    """Each skill should have all required fields populated."""
    skills = load_all_skills(SKILLS_DIR)
    for skill in skills:
        assert skill.meta.name, f"Skill missing name: {skill.file_path}"
        assert skill.meta.description, f"{skill.meta.name} missing description"
        assert skill.meta.target_personas, f"{skill.meta.name} missing target_personas"
        assert skill.meta.triggers, f"{skill.meta.name} missing triggers"
        assert skill.meta.mcp_tools, f"{skill.meta.name} missing mcp_tools"
        assert skill.body, f"{skill.meta.name} has empty body"


def test_skill_has_yaml_frontmatter():
    """Each skill file should start with YAML frontmatter."""
    skills = load_all_skills(SKILLS_DIR)
    for skill in skills:
        assert skill.meta.version, f"{skill.meta.name} missing version"


def test_load_nonexistent_dir():
    """Should return empty list for nonexistent directory."""
    skills = load_all_skills(Path("/nonexistent/path"))
    assert skills == []


def test_skill_priorities_valid():
    """Priorities should be reasonable integers."""
    skills = load_all_skills(SKILLS_DIR)
    for skill in skills:
        assert (
            0 <= skill.meta.priority <= 10
        ), f"{skill.meta.name} priority out of range: {skill.meta.priority}"
