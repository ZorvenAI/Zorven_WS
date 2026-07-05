"""
US-054 Property Tests — Baseline Scorers Hypothesis Tests.

Property-based tests for scorer behavior guarantees. No mocks —
uses real skills.yaml files.
"""

import json
import sys
from pathlib import Path

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "prompt-optimization-svc"))

from app.scorers.baseline.checks import (  # noqa: E402
    make_field_presence_scorer,
    make_max_length_scorer,
    make_schema_completeness_scorer,
)
from app.scorers.baseline.factory import BaselineScorerFactory  # noqa: E402
from app.services.skill_registry_reader import (  # noqa: E402
    AGENT_SERVICE_DIRS,
    SkillRegistryReader,
)

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

VALID_CODES = sorted(AGENT_SERVICE_DIRS.keys())
valid_agent_codes = st.sampled_from(VALID_CODES)

# Arbitrary output strings (may or may not be JSON)
arbitrary_outputs = st.one_of(
    st.none(),
    st.text(min_size=0, max_size=200),
    st.builds(
        json.dumps,
        st.dictionaries(
            keys=st.from_regex(r"[a-z_]{1,20}", fullmatch=True),
            values=st.one_of(
                st.text(min_size=0, max_size=50),
                st.integers(min_value=-100, max_value=100),
                st.booleans(),
            ),
            min_size=0,
            max_size=5,
        ),
    ),
)

field_names = st.from_regex(r"[a-z_]{1,20}", fullmatch=True)
max_lengths = st.integers(min_value=1, max_value=10000)


# ---------------------------------------------------------------------------
# Property Tests
# ---------------------------------------------------------------------------


@pytest.mark.property
class TestBaselineScorerProperties:
    """Hypothesis property tests for baseline scorer behavior."""

    @given(field_name=field_names, output=arbitrary_outputs)
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_field_presence_never_raises(self, field_name, output):
        """Field presence scorer never raises, always returns Feedback."""
        scorer = make_field_presence_scorer(field_name, "SKL-TST-01")
        result = scorer(inputs={}, outputs=output)
        assert 0.0 <= result.value <= 1.0
        assert isinstance(result.rationale, str)

    @given(
        field_name=field_names,
        max_length=max_lengths,
        output=arbitrary_outputs,
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_max_length_score_always_in_range(self, field_name, max_length, output):
        """Max length scorer value is always in [0.0, 1.0]."""
        scorer = make_max_length_scorer(field_name, max_length, "SKL-TST-01")
        result = scorer(inputs={}, outputs=output)
        assert 0.0 <= result.value <= 1.0

    @given(
        data=st.data(),
    )
    @settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
    def test_schema_completeness_monotonic(self, data):
        """More fields present produces higher or equal score."""
        fields = ["a", "b", "c", "d", "e"]
        scorer = make_schema_completeness_scorer(fields, "SKL-TST-01")

        subset_size = data.draw(st.integers(min_value=0, max_value=4))
        superset_size = data.draw(st.integers(min_value=subset_size, max_value=5))

        subset_dict = {fields[i]: "val" for i in range(subset_size)}
        superset_dict = {fields[i]: "val" for i in range(superset_size)}

        r_sub = scorer(inputs={}, outputs=json.dumps(subset_dict))
        r_sup = scorer(inputs={}, outputs=json.dumps(superset_dict))
        assert r_sup.value >= r_sub.value

    @given(agent_code=valid_agent_codes)
    @settings(max_examples=15, suppress_health_check=[HealthCheck.too_slow])
    def test_all_scorers_return_feedback_type(self, agent_code):
        """Every generated scorer returns a Feedback object."""
        reader = SkillRegistryReader(repo_root=REPO_ROOT)
        factory = BaselineScorerFactory(reader)
        skills_file = reader.load_skills(agent_code)
        skill = skills_file.skills[0]
        scorers = factory.create_scorers(skill)
        output = json.dumps({"test": "value"})
        for scorer in scorers:
            result = scorer(inputs={}, outputs=output)
            assert hasattr(result, "value")
            assert hasattr(result, "rationale")
            assert hasattr(result, "name")

    @given(output=arbitrary_outputs)
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
    def test_scorer_deterministic(self, output):
        """Same input always produces same score."""
        scorer = make_field_presence_scorer("query", "SKL-MRA-01")
        r1 = scorer(inputs={}, outputs=output)
        r2 = scorer(inputs={}, outputs=output)
        assert r1.value == r2.value
        assert r1.rationale == r2.rationale
