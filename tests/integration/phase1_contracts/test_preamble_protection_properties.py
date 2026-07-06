"""
US-057 Property Tests — OPT-12 Preamble Protection Hypothesis Tests.

Property-based tests for schema preamble protection guarantees.
No mocks — uses real skills.yaml files.
"""

import sys
from pathlib import Path

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "prompt-optimization-svc"))

from app.logic.preamble_validator import validate_preamble_protection  # noqa: E402
from app.services.schema_preamble import (  # noqa: E402
    PREAMBLE_START,
    PREAMBLE_END,
    SchemaPreambleGenerator,
)
from app.services.skill_registry_reader import (  # noqa: E402
    AGENT_SERVICE_DIRS,
    SkillRegistryReader,
)

VALID_CODES = sorted(AGENT_SERVICE_DIRS.keys())
valid_agent_codes = st.sampled_from(VALID_CODES)


def _get_preamble_template(agent_code: str) -> str | None:
    """Build a real preamble template for an agent. Returns None if no output_schema."""
    reader = SkillRegistryReader(repo_root=REPO_ROOT)
    gen = SchemaPreambleGenerator(reader)
    skills_file = reader.load_skills(agent_code)
    for skill in skills_file.skills:
        if skill.output_schema:
            preamble = gen.generate(skill)
            return gen.inject("You are an agent.", preamble)
    return None


@pytest.mark.property
class TestPreambleProtectionProperties:
    """Hypothesis property tests for OPT-12 preamble protection."""

    @given(agent_code=valid_agent_codes)
    @settings(max_examples=15, suppress_health_check=[HealthCheck.too_slow])
    def test_self_invariant_always_valid(self, agent_code):
        """Any agent's preamble template validated against itself is always valid."""
        template = _get_preamble_template(agent_code)
        if template is None:
            return  # Skip agents without output_schema
        result = validate_preamble_protection(template, template)
        assert result.valid is True

    @given(
        original=st.text(min_size=1, max_size=200),
        mutated=st.text(min_size=1, max_size=200),
    )
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
    def test_no_preamble_original_always_valid(self, original, mutated):
        """If original has no preamble markers, result is always valid."""
        # Ensure no markers in original
        original = original.replace(PREAMBLE_START, "").replace(PREAMBLE_END, "")
        result = validate_preamble_protection(original, mutated)
        assert result.valid is True

    @given(agent_code=valid_agent_codes)
    @settings(max_examples=15, suppress_health_check=[HealthCheck.too_slow])
    def test_removing_start_marker_always_invalid(self, agent_code):
        """Removing PREAMBLE_START from any agent's template always yields invalid."""
        template = _get_preamble_template(agent_code)
        if template is None:
            return
        mutated = template.replace(PREAMBLE_START, "")
        result = validate_preamble_protection(template, mutated)
        assert result.valid is False
        assert result.preamble_present is False

    @given(agent_code=valid_agent_codes)
    @settings(max_examples=15, suppress_health_check=[HealthCheck.too_slow])
    def test_removing_end_marker_always_invalid(self, agent_code):
        """Removing PREAMBLE_END from any agent's template always yields invalid."""
        template = _get_preamble_template(agent_code)
        if template is None:
            return
        mutated = template.replace(PREAMBLE_END, "")
        result = validate_preamble_protection(template, mutated)
        assert result.valid is False
        assert result.preamble_present is False

    @given(agent_code=valid_agent_codes, extra=st.text(max_size=200))
    @settings(max_examples=15, suppress_health_check=[HealthCheck.too_slow])
    def test_appending_text_stays_valid(self, agent_code, extra):
        """Appending arbitrary text after the template keeps preamble at top."""
        template = _get_preamble_template(agent_code)
        if template is None:
            return
        # Ensure extra doesn't contain preamble markers
        extra = extra.replace(PREAMBLE_START, "").replace(PREAMBLE_END, "")
        mutated = template + "\n" + extra
        result = validate_preamble_protection(template, mutated)
        assert result.valid is True
