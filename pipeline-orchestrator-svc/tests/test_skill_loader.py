"""Tests for the skill file loader."""

from pathlib import Path

import pytest

from app.skills.loader import load_all_skills, _parse_skill_file

FIXTURES_DIR = Path(__file__).parent / "skills"


class TestLoadAllSkills:
    """Tests for load_all_skills()."""

    def test_loads_valid_skills_from_fixture_dir(self):
        skills = load_all_skills(FIXTURES_DIR)
        names = {s.meta.name for s in skills}
        assert "test-seo-skill" in names
        assert "test-social-skill" in names
        assert "test-multi-agent-skill" in names

    def test_skips_malformed_files(self):
        skills = load_all_skills(FIXTURES_DIR)
        names = {s.meta.name for s in skills}
        # Malformed file (no frontmatter) should be skipped
        assert "test-malformed" not in names

    def test_skips_files_missing_name(self):
        skills = load_all_skills(FIXTURES_DIR)
        names = {s.meta.name for s in skills}
        # File without 'name' in frontmatter should be skipped
        assert len([s for s in skills if "missing" in s.meta.description.lower()]) == 0

    def test_returns_empty_for_nonexistent_dir(self):
        skills = load_all_skills(Path("/nonexistent/path"))
        assert skills == []

    def test_returns_empty_for_empty_dir(self, tmp_path):
        skills = load_all_skills(tmp_path)
        assert skills == []

    def test_loads_correct_metadata(self):
        skills = load_all_skills(FIXTURES_DIR)
        seo = next(s for s in skills if s.meta.name == "test-seo-skill")
        assert seo.meta.version == "1.0"
        assert seo.meta.target_agents == ["blog_author"]
        assert "seo" in seo.meta.triggers
        assert seo.meta.priority == 10
        assert seo.meta.max_tokens == 200

    def test_loads_body_content(self):
        skills = load_all_skills(FIXTURES_DIR)
        seo = next(s for s in skills if s.meta.name == "test-seo-skill")
        assert "keywords naturally" in seo.body

    def test_multi_agent_skill_has_multiple_targets(self):
        skills = load_all_skills(FIXTURES_DIR)
        multi = next(s for s in skills if s.meta.name == "test-multi-agent-skill")
        assert "blog_author" in multi.meta.target_agents
        assert "social_promoter" in multi.meta.target_agents


class TestParseSkillFile:
    """Tests for _parse_skill_file()."""

    def test_returns_none_for_no_frontmatter(self):
        path = FIXTURES_DIR / "test-malformed.md"
        assert _parse_skill_file(path) is None

    def test_returns_none_for_missing_name(self):
        path = FIXTURES_DIR / "test-no-name.md"
        assert _parse_skill_file(path) is None

    def test_parses_valid_file(self):
        path = FIXTURES_DIR / "test-seo-skill.md"
        skill = _parse_skill_file(path)
        assert skill is not None
        assert skill.meta.name == "test-seo-skill"
        assert skill.file_path == str(path)
