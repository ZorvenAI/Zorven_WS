"""
US-053 Property Tests — Schema Preamble Hypothesis Tests.

Property-based tests for preamble inject/strip/extract idempotency
and roundtrip guarantees. No mocks — uses real skills.yaml files.
"""

import sys
from pathlib import Path

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "prompt-optimization-svc"))

from app.services.schema_preamble import (  # noqa: E402
    PREAMBLE_END,
    PREAMBLE_START,
    SchemaPreambleGenerator,
)
from app.services.skill_registry_reader import (  # noqa: E402
    AGENT_SERVICE_DIRS,
    SkillRegistryReader,
)

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

VALID_CODES = sorted(AGENT_SERVICE_DIRS.keys())

# Prompt templates that don't contain preamble markers
arbitrary_prompts = st.text(
    min_size=1,
    max_size=200,
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "Z"),
        whitelist_characters=" \n\t.,!?{}()",
    ),
).filter(lambda t: PREAMBLE_START not in t and PREAMBLE_END not in t)

valid_agent_codes = st.sampled_from(VALID_CODES)


def _make_generator() -> tuple[SchemaPreambleGenerator, SkillRegistryReader]:
    reader = SkillRegistryReader(repo_root=REPO_ROOT)
    return SchemaPreambleGenerator(reader), reader


# ---------------------------------------------------------------------------
# Property Tests
# ---------------------------------------------------------------------------


@pytest.mark.property
class TestSchemaPreambleProperties:
    """Hypothesis property tests for schema preamble operations."""

    @given(prompt_text=arbitrary_prompts, agent_code=valid_agent_codes)
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
    def test_inject_then_strip_is_identity(self, prompt_text, agent_code):
        """For any prompt text, strip(inject(text, preamble)) == text."""
        gen, reader = _make_generator()
        skills_file = reader.load_skills(agent_code)
        skill = skills_file.skills[0]
        preamble = gen.generate(skill)
        injected = gen.inject(prompt_text, preamble)
        stripped = gen.strip(injected)
        assert stripped == prompt_text.strip()

    @given(prompt_text=arbitrary_prompts, agent_code=valid_agent_codes)
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
    def test_inject_always_produces_protected_text(self, prompt_text, agent_code):
        """After inject, is_protected() is always True."""
        gen, reader = _make_generator()
        skills_file = reader.load_skills(agent_code)
        skill = skills_file.skills[0]
        preamble = gen.generate(skill)
        injected = gen.inject(prompt_text, preamble)
        assert gen.is_protected(injected)

    @given(prompt_text=arbitrary_prompts)
    @settings(max_examples=30)
    def test_strip_always_produces_unprotected_text(self, prompt_text):
        """After strip, is_protected() is always False."""
        gen, _ = _make_generator()
        stripped = gen.strip(prompt_text)
        assert not gen.is_protected(stripped)

    @given(prompt_text=arbitrary_prompts, agent_code=valid_agent_codes)
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
    def test_extract_after_inject_returns_preamble(self, prompt_text, agent_code):
        """inject then extract → gets the preamble back."""
        gen, reader = _make_generator()
        skills_file = reader.load_skills(agent_code)
        skill = skills_file.skills[0]
        preamble = gen.generate(skill)
        injected = gen.inject(prompt_text, preamble)
        extracted = gen.extract(injected)
        assert extracted == preamble

    @given(agent_code=valid_agent_codes)
    @settings(max_examples=15, suppress_health_check=[HealthCheck.too_slow])
    def test_generate_never_raises_for_valid_skill(self, agent_code):
        """Generating from any real skill never raises."""
        gen, reader = _make_generator()
        skills_file = reader.load_skills(agent_code)
        for skill in skills_file.skills:
            preamble = gen.generate(skill)
            assert PREAMBLE_START in preamble

    @given(prompt_text=arbitrary_prompts, agent_code=valid_agent_codes)
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
    def test_double_inject_same_as_single(self, prompt_text, agent_code):
        """Injecting twice produces same result as once (idempotent)."""
        gen, reader = _make_generator()
        skills_file = reader.load_skills(agent_code)
        skill = skills_file.skills[0]
        preamble = gen.generate(skill)
        first = gen.inject(prompt_text, preamble)
        second = gen.inject(first, preamble)
        assert first == second
