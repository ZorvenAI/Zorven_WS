"""
US-055 Property Tests — Reflection Context Enricher Hypothesis Tests.

Property-based tests for reflection context enrichment guarantees.
No mocks — uses real skills.yaml files.
"""

import sys
from pathlib import Path

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "prompt-optimization-svc"))

from app.services.reflection_context_enricher import (  # noqa: E402
    ReflectionContextEnricher,
)
from app.services.skill_registry_reader import (  # noqa: E402
    AGENT_SERVICE_DIRS,
    SkillRegistryReader,
)

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

VALID_CODES = sorted(AGENT_SERVICE_DIRS.keys())
valid_agent_codes = st.sampled_from(VALID_CODES)

# Mix of plausible and implausible prompt names
prompt_names = st.lists(
    st.one_of(
        st.from_regex(r"zorven-wf[123]-[a-z]+-[a-z-]+", fullmatch=True),
        st.text(min_size=0, max_size=50),
    ),
    min_size=0,
    max_size=5,
)


# ---------------------------------------------------------------------------
# Property Tests
# ---------------------------------------------------------------------------


@pytest.mark.property
class TestReflectionContextProperties:
    """Hypothesis property tests for reflection context enrichment."""

    @given(agent_code=valid_agent_codes, names=prompt_names)
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
    def test_build_task_description_never_raises(self, agent_code, names):
        """build_task_description never raises, always returns str."""
        reader = SkillRegistryReader(repo_root=REPO_ROOT)
        enricher = ReflectionContextEnricher(reader)
        result = enricher.build_task_description(agent_code, names)
        assert isinstance(result, str)

    @given(agent_code=valid_agent_codes, names=prompt_names)
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
    def test_enrich_gepa_kwargs_always_returns_dict(self, agent_code, names):
        """enrich_gepa_kwargs always returns a dict."""
        reader = SkillRegistryReader(repo_root=REPO_ROOT)
        enricher = ReflectionContextEnricher(reader)
        result = enricher.enrich_gepa_kwargs(agent_code, names)
        assert isinstance(result, dict)

    @given(agent_code=valid_agent_codes)
    @settings(max_examples=15, suppress_health_check=[HealthCheck.too_slow])
    def test_context_length_bounded(self, agent_code):
        """Context length scales with skills but stays bounded."""
        reader = SkillRegistryReader(repo_root=REPO_ROOT)
        enricher = ReflectionContextEnricher(reader)
        skills_file = reader.load_skills(agent_code)
        # Build context for all skills in agent
        prompt_names = [
            f"zorven-wf1-{agent_code}-{s.name.lower().replace(' ', '-')}"
            for s in skills_file.skills
        ]
        desc = enricher.build_task_description(agent_code, prompt_names)
        # Context should not exceed 50KB (well within any reasonable limit)
        assert len(desc) < 50_000

    @given(agent_code=valid_agent_codes)
    @settings(max_examples=15, suppress_health_check=[HealthCheck.too_slow])
    def test_enrichment_idempotent(self, agent_code):
        """Calling twice with same inputs produces same result."""
        reader = SkillRegistryReader(repo_root=REPO_ROOT)
        enricher = ReflectionContextEnricher(reader)
        skills_file = reader.load_skills(agent_code)
        first_skill = skills_file.skills[0]
        names = [
            f"zorven-wf1-{agent_code}-" f"{first_skill.name.lower().replace(' ', '-')}"
        ]
        r1 = enricher.build_task_description(agent_code, names)
        r2 = enricher.build_task_description(agent_code, names)
        assert r1 == r2

    @given(agent_code=valid_agent_codes)
    @settings(max_examples=15, suppress_health_check=[HealthCheck.too_slow])
    def test_format_skill_context_deterministic(self, agent_code):
        """Same skill always produces same formatted context."""
        reader = SkillRegistryReader(repo_root=REPO_ROOT)
        enricher = ReflectionContextEnricher(reader)
        skills_file = reader.load_skills(agent_code)
        skill = skills_file.skills[0]
        c1 = enricher._format_skill_context(skill)
        c2 = enricher._format_skill_context(skill)
        assert c1 == c2
