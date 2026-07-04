"""Hypothesis property tests for tenant config keys (US-041)."""

from hypothesis import given, settings
from hypothesis import strategies as st

from app.cache.tenant_config import (
    MAX_OPTIMIZATION_BUDGET,
    MIN_OPTIMIZATION_BUDGET,
    VALID_SCHEDULES,
    clamp_optimization_budget,
    validate_schedule,
)


class TestBudgetClampProperties:
    @given(st.integers(min_value=-1000, max_value=5000))
    @settings(max_examples=100, deadline=None)
    def test_always_in_range(self, budget):
        result = clamp_optimization_budget(budget)
        assert MIN_OPTIMIZATION_BUDGET <= result <= MAX_OPTIMIZATION_BUDGET

    @given(
        st.integers(
            min_value=MIN_OPTIMIZATION_BUDGET, max_value=MAX_OPTIMIZATION_BUDGET
        )
    )
    @settings(max_examples=50, deadline=None)
    def test_in_range_unchanged(self, budget):
        assert clamp_optimization_budget(budget) == budget


class TestScheduleValidationProperties:
    @given(st.sampled_from(list(VALID_SCHEDULES)))
    @settings(max_examples=4, deadline=None)
    def test_valid_schedules_unchanged(self, schedule):
        assert validate_schedule(schedule) == schedule

    @given(st.text(max_size=30))
    @settings(max_examples=50, deadline=None)
    def test_always_returns_valid_schedule(self, schedule):
        result = validate_schedule(schedule)
        assert result in VALID_SCHEDULES
