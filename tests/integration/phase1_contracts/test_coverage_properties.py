"""
US-058 Property Tests — Coverage Hypothesis Tests.

Property-based tests for optimization budgets, skill ID patterns,
and clamp function bounds. No mocks.
"""

import sys
from pathlib import Path

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "prompt-optimization-svc"))

from app.cache.tenant_config import clamp_dataset_size, clamp_ttl  # noqa: E402
from app.registries.optimization_budgets import get_budget  # noqa: E402
from app.registries.skill_definitions import SKILL_ID_PATTERN  # noqa: E402


@pytest.mark.property
class TestCoverageProperties:
    """Hypothesis property tests for coverage targets."""

    @given(agent_code=st.text(max_size=50))
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_get_budget_always_positive(self, agent_code):
        """get_budget returns a positive integer for any input."""
        budget = get_budget(agent_code)
        assert isinstance(budget, int)
        assert budget > 0

    @given(
        agent=st.text(
            alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ",
            min_size=2,
            max_size=5,
        ),
        num=st.integers(min_value=1, max_value=99),
    )
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
    def test_skill_id_pattern_accepts_valid_format(self, agent, num):
        """Generated SKL-<AGENT>-<NN> always matches SKILL_ID_PATTERN."""
        skill_id = f"SKL-{agent}-{num:02d}"
        assert SKILL_ID_PATTERN.match(
            skill_id
        ), f"Expected '{skill_id}' to match SKILL_ID_PATTERN"

    @given(text=st.text(min_size=1, max_size=30))
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_skill_id_pattern_rejects_most_random_strings(self, text):
        """Random strings rarely match SKL-<AGENT>-<NN> pattern."""
        # Not an assertion about every string, but a sanity check
        # that the pattern is selective (most random text won't match)
        if not text.startswith("SKL-"):
            assert not SKILL_ID_PATTERN.match(text)

    @given(value=st.integers(min_value=-10000, max_value=100000))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_clamp_ttl_always_in_bounds(self, value):
        """clamp_ttl result is always in [10, 3600]."""
        result = clamp_ttl(value)
        assert 10 <= result <= 3600

    @given(value=st.integers(min_value=-1000, max_value=10000))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_clamp_dataset_size_always_in_bounds(self, value):
        """clamp_dataset_size result is always in [3, 50]."""
        result = clamp_dataset_size(value)
        assert 3 <= result <= 50
