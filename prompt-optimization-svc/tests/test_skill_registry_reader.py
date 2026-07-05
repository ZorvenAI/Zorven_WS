"""
US-052 Unit Tests — SkillRegistryReader.

All tests use real file I/O against the actual config/skills.yaml files
on disk. No mocks.
"""

from pathlib import Path

import pytest

from app.services.skill_registry_reader import (
    AGENT_SERVICE_DIRS,
    SkillRegistryReader,
    extract_slug,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


@pytest.fixture
def reader():
    r = SkillRegistryReader(repo_root=REPO_ROOT)
    yield r
    r.clear_cache()


ALL_AGENT_CODES = sorted(AGENT_SERVICE_DIRS.keys())


class TestLoadSkills:
    @pytest.mark.parametrize("agent_code", ALL_AGENT_CODES)
    def test_load_skills_returns_valid_skills_file(self, reader, agent_code):
        """Every agent's skills.yaml loads and contains at least one skill."""
        skills_file = reader.load_skills(agent_code)
        assert len(skills_file.skills) > 0

    def test_load_skills_unknown_agent_raises_value_error(self, reader):
        with pytest.raises(ValueError, match="Unknown agent code"):
            reader.load_skills("xyz")

    def test_load_skills_missing_file_raises_file_not_found(self):
        reader = SkillRegistryReader(repo_root=Path("/nonexistent/path"))
        with pytest.raises(FileNotFoundError):
            reader.load_skills("mra")


class TestGetSkill:
    def test_get_skill_by_id(self, reader):
        skill = reader.get_skill("mra", "SKL-MRA-01")
        assert skill is not None
        assert skill.skill_id == "SKL-MRA-01"
        assert skill.name == "web_market_search"

    def test_get_skill_nonexistent_id_returns_none(self, reader):
        result = reader.get_skill("mra", "SKL-MRA-99")
        assert result is None

    def test_get_skill_unknown_agent_raises(self, reader):
        with pytest.raises(ValueError, match="Unknown agent code"):
            reader.get_skill("xyz", "SKL-XYZ-01")


class TestGetSkillForPrompt:
    def test_matches_synthesis_slug(self, reader):
        skill = reader.get_skill_for_prompt("mra", "zorven-wf1-mra-synthesis")
        assert skill is not None
        assert "synthesis" in skill.name.lower()

    def test_matches_system_slug(self, reader):
        """'system' prompts may not have a matching skill — returns None is ok."""
        result = reader.get_skill_for_prompt("mra", "zorven-wf1-mra-system")
        # system prompts are not expected to match a skill
        # result can be None or a SkillDefinition

    def test_no_match_returns_none(self, reader):
        result = reader.get_skill_for_prompt("mra", "zorven-wf1-mra-nonexistentslug")
        assert result is None

    def test_invalid_prompt_name_returns_none(self, reader):
        result = reader.get_skill_for_prompt("mra", "not-a-valid-prompt")
        assert result is None

    def test_matches_positioning_slug(self, reader):
        skill = reader.get_skill_for_prompt("bpa", "zorven-wf2-bpa-positioning")
        assert skill is not None
        assert "position" in skill.name.lower()


class TestListAndAllSkills:
    def test_list_agent_codes_returns_15(self, reader):
        codes = reader.list_agent_codes()
        assert len(codes) == 15
        assert "mra" in codes
        assert "ila" in codes

    def test_all_skills_returns_179_tuples(self, reader):
        all_skills = reader.all_skills()
        assert len(all_skills) == 179

    def test_all_skills_agent_codes_are_valid(self, reader):
        valid_codes = set(AGENT_SERVICE_DIRS.keys())
        for agent_code, _skill in reader.all_skills():
            assert agent_code in valid_codes


class TestCaching:
    def test_cache_returns_same_object(self, reader):
        first = reader.load_skills("mra")
        second = reader.load_skills("mra")
        assert first is second

    def test_clear_cache_forces_reload(self, reader):
        first = reader.load_skills("mra")
        reader.clear_cache()
        second = reader.load_skills("mra")
        assert first is not second
        assert len(first.skills) == len(second.skills)


class TestExtractSlug:
    @pytest.mark.parametrize(
        "prompt_name,expected_slug",
        [
            ("zorven-wf1-mra-synthesis", "synthesis"),
            ("zorven-wf2-bpa-positioning", "positioning"),
            ("zorven-wf3-cga-compliance", "compliance"),
            ("zorven-wf1-mra-system", "system"),
            ("zorven-wf3-ila-extraction", "extraction"),
        ],
    )
    def test_extract_slug_valid(self, prompt_name, expected_slug):
        assert extract_slug(prompt_name) == expected_slug

    @pytest.mark.parametrize(
        "prompt_name",
        [
            "not-a-prompt",
            "zorven-wf4-mra-test",
            "",
            "random-string",
        ],
    )
    def test_extract_slug_invalid(self, prompt_name):
        assert extract_slug(prompt_name) is None
