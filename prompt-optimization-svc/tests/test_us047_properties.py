"""Hypothesis property tests for US-047 per-tenant schedule (US-047).

Validates invariants for schedule validation, priority ordering,
and Pydantic field validators using property-based testing.
"""

from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from app.cache.tenant_config import VALID_SCHEDULES, strict_validate_schedule
from app.tasks.optimize_wf3_pipeline import SCHEDULE_PRIORITY

# Strategy for invalid schedule strings (not in VALID_SCHEDULES)
_invalid_schedules = st.text(max_size=30).filter(lambda s: s not in VALID_SCHEDULES)


class TestScheduleValidationProperties:
    @given(schedule=_invalid_schedules)
    @settings(max_examples=100)
    def test_invalid_schedules_always_raise(self, schedule):
        """Any string not in VALID_SCHEDULES must raise ValueError."""
        try:
            strict_validate_schedule(schedule)
            assert False, f"Expected ValueError for '{schedule}'"
        except ValueError:
            pass

    @given(schedule=st.sampled_from(list(VALID_SCHEDULES)))
    def test_valid_schedules_always_pass(self, schedule):
        """Any valid schedule passes strict validation unchanged."""
        assert strict_validate_schedule(schedule) == schedule


class TestSchedulePriorityProperties:
    @given(
        schedules=st.lists(
            st.sampled_from(list(VALID_SCHEDULES)), min_size=1, max_size=20
        )
    )
    def test_min_by_priority_is_valid(self, schedules):
        """The most aggressive schedule is always a valid schedule."""
        result = min(schedules, key=lambda s: SCHEDULE_PRIORITY.get(s, 3))
        assert result in VALID_SCHEDULES

    @given(
        schedules=st.lists(
            st.sampled_from(list(VALID_SCHEDULES)), min_size=1, max_size=20
        )
    )
    def test_biweekly_wins_when_present(self, schedules):
        """If biweekly is in the list, it always wins."""
        if "biweekly" in schedules:
            result = min(schedules, key=lambda s: SCHEDULE_PRIORITY.get(s, 3))
            assert result == "biweekly"

    def test_priority_covers_all_valid_schedules(self):
        """Every valid schedule has a priority entry."""
        for sched in VALID_SCHEDULES:
            assert sched in SCHEDULE_PRIORITY


class TestPydanticValidatorProperties:
    @given(schedule=_invalid_schedules)
    @settings(max_examples=100)
    def test_pydantic_rejects_invalid(self, schedule):
        """Pydantic validator rejects any invalid schedule string."""
        from app.api.schemas import TenantConfigUpdateRequest

        try:
            TenantConfigUpdateRequest(wf3_optimization_schedule=schedule)
            assert False, f"Expected ValidationError for '{schedule}'"
        except ValidationError:
            pass
