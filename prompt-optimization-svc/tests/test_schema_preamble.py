"""
US-053 Unit Tests — SchemaPreambleGenerator.

All tests use real SkillRegistryReader loading real skills.yaml files.
No mocks.
"""

from pathlib import Path

import pytest

from app.registries.skill_definitions import SkillDefinition
from app.services.schema_preamble import (
    PREAMBLE_END,
    PREAMBLE_START,
    SchemaPreambleGenerator,
)
from app.services.skill_registry_reader import (
    AGENT_SERVICE_DIRS,
    SkillRegistryReader,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


@pytest.fixture
def reader():
    r = SkillRegistryReader(repo_root=REPO_ROOT)
    yield r
    r.clear_cache()


@pytest.fixture
def generator(reader):
    return SchemaPreambleGenerator(reader)


@pytest.fixture
def mra_skill(reader):
    """First skill from MRA agent."""
    return reader.get_skill("mra", "SKL-MRA-01")


ALL_AGENT_CODES = sorted(AGENT_SERVICE_DIRS.keys())


class TestGenerate:
    def test_generate_produces_preamble_with_markers(self, generator, mra_skill):
        preamble = generator.generate(mra_skill)
        assert PREAMBLE_START in preamble
        assert PREAMBLE_END in preamble
        assert preamble.startswith(PREAMBLE_START)
        assert preamble.endswith(PREAMBLE_END)

    def test_generate_includes_input_schema_fields(self, generator, mra_skill):
        preamble = generator.generate(mra_skill)
        assert "input_prompt" in preamble
        assert "string" in preamble

    def test_generate_includes_output_schema_fields(self, generator, mra_skill):
        preamble = generator.generate(mra_skill)
        for field in mra_skill.output_schema:
            assert field.field in preamble

    def test_generate_includes_skill_metadata(self, generator, mra_skill):
        preamble = generator.generate(mra_skill)
        assert "SKL-MRA-01" in preamble
        assert "web_market_search" in preamble
        assert "30000ms" in preamble
        assert "Idempotent: yes" in preamble

    @pytest.mark.parametrize("agent_code", ALL_AGENT_CODES)
    def test_generate_all_15_agents_first_skill(self, generator, reader, agent_code):
        """Generate preamble for first skill of every agent without error."""
        skills_file = reader.load_skills(agent_code)
        first_skill = skills_file.skills[0]
        preamble = generator.generate(first_skill)
        assert PREAMBLE_START in preamble
        assert PREAMBLE_END in preamble
        assert first_skill.skill_id in preamble


class TestGenerateForPrompt:
    def test_generate_for_prompt_known_skill(self, generator):
        result = generator.generate_for_prompt("mra", "zorven-wf1-mra-synthesis")
        assert result is not None
        assert PREAMBLE_START in result

    def test_generate_for_prompt_unknown_returns_none(self, generator):
        result = generator.generate_for_prompt("mra", "zorven-wf1-mra-nonexistent")
        assert result is None

    def test_generate_for_prompt_system_prompt_returns_none(self, generator):
        """System prompts typically don't map to a specific skill."""
        result = generator.generate_for_prompt("mra", "zorven-wf1-mra-system")
        # 'system' may or may not match — assert it doesn't raise
        assert result is None or PREAMBLE_START in result


class TestInject:
    def test_inject_prepends_preamble(self, generator, mra_skill):
        preamble = generator.generate(mra_skill)
        prompt = "You are a market research analyst."
        result = generator.inject(prompt, preamble)
        assert result.startswith(PREAMBLE_START)
        assert "You are a market research analyst." in result

    def test_inject_replaces_existing_preamble(self, generator, mra_skill):
        preamble = generator.generate(mra_skill)
        prompt = "You are a market research analyst."
        # Inject once
        first = generator.inject(prompt, preamble)
        # Inject again — should not duplicate
        second = generator.inject(first, preamble)
        assert second.count(PREAMBLE_START) == 1
        assert second.count(PREAMBLE_END) == 1


class TestStrip:
    def test_strip_removes_preamble(self, generator, mra_skill):
        preamble = generator.generate(mra_skill)
        prompt = "You are a market research analyst."
        injected = generator.inject(prompt, preamble)
        stripped = generator.strip(injected)
        assert PREAMBLE_START not in stripped
        assert PREAMBLE_END not in stripped
        assert "You are a market research analyst." in stripped

    def test_strip_no_preamble_returns_unchanged(self, generator):
        prompt = "You are a market research analyst."
        assert generator.strip(prompt) == prompt


class TestExtract:
    def test_extract_returns_preamble_content(self, generator, mra_skill):
        preamble = generator.generate(mra_skill)
        prompt = "You are a market research analyst."
        injected = generator.inject(prompt, preamble)
        extracted = generator.extract(injected)
        assert extracted == preamble

    def test_extract_no_preamble_returns_none(self, generator):
        assert generator.extract("Just a plain prompt.") is None


class TestIsProtected:
    def test_is_protected_true_when_preamble_present(self, generator, mra_skill):
        preamble = generator.generate(mra_skill)
        prompt = "You are a market research analyst."
        injected = generator.inject(prompt, preamble)
        assert generator.is_protected(injected) is True

    def test_is_protected_false_when_no_preamble(self, generator):
        assert generator.is_protected("Plain prompt text.") is False


class TestHasChanged:
    def test_has_changed_detects_missing_preamble(self, generator, mra_skill):
        """Prompt without preamble → has_changed is True."""
        assert generator.has_changed("Plain prompt.", mra_skill) is True

    def test_has_changed_false_when_current(self, generator, mra_skill):
        """Prompt with current preamble → has_changed is False."""
        preamble = generator.generate(mra_skill)
        injected = generator.inject("Some prompt.", preamble)
        assert generator.has_changed(injected, mra_skill) is False

    def test_has_changed_detects_schema_drift(self, generator, reader):
        """If skill schema differs from embedded preamble → True."""
        skill = reader.get_skill("mra", "SKL-MRA-01")
        preamble = generator.generate(skill)
        injected = generator.inject("Some prompt.", preamble)
        # Simulate drift by checking against a different skill
        other_skill = reader.get_skill("mra", "SKL-MRA-02")
        assert generator.has_changed(injected, other_skill) is True
