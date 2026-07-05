"""
US-052 Property Tests — SkillRegistryReader Hypothesis Tests.

Hypothesis-based property tests for SkillRegistryReader. Exercises slug
extraction, agent code validation, and lookup stability with random
inputs. No mocks — all tests use real file I/O.
"""

import sys
from pathlib import Path

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent

sys.path.insert(0, str(REPO_ROOT / "prompt-optimization-svc"))

from app.services.skill_registry_reader import (  # noqa: E402
    AGENT_SERVICE_DIRS,
    SkillRegistryReader,
    extract_slug,
)

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

VALID_CODES = sorted(AGENT_SERVICE_DIRS.keys())

valid_agent_codes = st.sampled_from(VALID_CODES)
valid_wf_numbers = st.sampled_from([1, 2, 3])
valid_slugs = st.from_regex(r"[a-z][a-z0-9_]{1,20}", fullmatch=True)

# Generate valid prompt names: zorven-wf{N}-{agent}-{slug}
valid_prompt_names = st.builds(
    lambda wf, agent, slug: f"zorven-wf{wf}-{agent}-{slug}",
    wf=valid_wf_numbers,
    agent=valid_agent_codes,
    slug=valid_slugs,
)

# Agent codes guaranteed NOT to be valid
invalid_agent_codes = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789",
    min_size=1,
    max_size=10,
).filter(lambda x: x not in AGENT_SERVICE_DIRS)


# ---------------------------------------------------------------------------
# Property Tests
# ---------------------------------------------------------------------------


@pytest.mark.property
class TestSkillRegistryReaderProperties:
    """Hypothesis property tests for SkillRegistryReader."""

    @given(agent_code=valid_agent_codes)
    @settings(max_examples=15, suppress_health_check=[HealthCheck.too_slow])
    def test_load_skills_always_returns_skills_file_for_valid_agent(self, agent_code):
        """Any valid agent code returns a SkillsFile with at least one skill."""
        reader = SkillRegistryReader(repo_root=REPO_ROOT)
        skills_file = reader.load_skills(agent_code)
        assert len(skills_file.skills) > 0
        reader.clear_cache()

    @given(agent_code=invalid_agent_codes)
    @settings(max_examples=30)
    def test_load_skills_always_raises_for_invalid_agent(self, agent_code):
        """Any string not in the 15 valid codes raises ValueError."""
        reader = SkillRegistryReader(repo_root=REPO_ROOT)
        with pytest.raises(ValueError, match="Unknown agent code"):
            reader.load_skills(agent_code)

    @given(agent_code=valid_agent_codes, prompt_name=valid_prompt_names)
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_get_skill_for_prompt_never_raises(self, agent_code, prompt_name):
        """get_skill_for_prompt returns SkillDefinition or None, never raises."""
        reader = SkillRegistryReader(repo_root=REPO_ROOT)
        result = reader.get_skill_for_prompt(agent_code, prompt_name)
        assert result is None or hasattr(result, "skill_id")
        reader.clear_cache()

    @given(prompt_name=valid_prompt_names)
    @settings(max_examples=50)
    def test_slug_extraction_is_deterministic(self, prompt_name):
        """Same prompt name always extracts the same slug."""
        slug1 = extract_slug(prompt_name)
        slug2 = extract_slug(prompt_name)
        assert slug1 == slug2
        assert slug1 is not None

    @given(
        garbage=st.text(min_size=0, max_size=50).filter(
            lambda t: not t.startswith("zorven-wf")
        )
    )
    @settings(max_examples=30)
    def test_extract_slug_rejects_non_prompt_strings(self, garbage):
        """Strings not matching the prompt pattern return None."""
        assert extract_slug(garbage) is None

    def test_all_skills_result_is_stable(self):
        """Calling all_skills() twice returns same count and order."""
        reader = SkillRegistryReader(repo_root=REPO_ROOT)
        first = reader.all_skills()
        second = reader.all_skills()
        assert len(first) == len(second)
        for (c1, s1), (c2, s2) in zip(first, second):
            assert c1 == c2
            assert s1.skill_id == s2.skill_id
        reader.clear_cache()
