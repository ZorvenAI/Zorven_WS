"""Hypothesis property tests for Celery Beat schedules (US-046).

Validates invariants across all beat schedule entries and WF3
schedule logic using property-based testing.
"""

from datetime import datetime, timezone

from celery.schedules import crontab
from hypothesis import given, settings as hypothesis_settings
from hypothesis import strategies as st

from app.tasks.optimize_wf3_pipeline import should_run_wf3_schedule


class TestBeatScheduleProperties:
    def test_all_entries_have_crontab_schedule(self):
        """Every beat schedule entry uses a crontab schedule."""
        from app.celery_app import celery_app

        for name, entry in celery_app.conf.beat_schedule.items():
            assert isinstance(entry["schedule"], crontab), (
                f"Entry '{name}' schedule is not a crontab: "
                f"{type(entry['schedule'])}"
            )

    def test_all_task_names_match_module_paths(self):
        """Every task name starts with 'app.tasks.' and ends with function name."""
        from app.celery_app import celery_app

        for name, entry in celery_app.conf.beat_schedule.items():
            task_name = entry["task"]
            assert task_name.startswith(
                "app.tasks."
            ), f"Entry '{name}' task '{task_name}' doesn't start with app.tasks."
            # Task name should be module_path.function_name
            parts = task_name.rsplit(".", 1)
            assert len(parts) == 2, (
                f"Entry '{name}' task '{task_name}' doesn't have "
                f"module.function format"
            )

    def test_all_optimization_groups_exist(self):
        """All group names referenced in tasks exist in OPTIMIZATION_GROUPS."""
        from app.registries.optimization_groups import OPTIMIZATION_GROUPS
        from app.tasks.optimize_wf1_pipeline import GROUP_NAME as WF1
        from app.tasks.optimize_wf2_pipeline import GROUP_NAME as WF2
        from app.tasks.optimize_wf3_pipeline import (
            WF3_CREATIVE_GROUP,
            WF3_OPTLOOP_GROUP,
        )

        for group_name in [WF1, WF2, WF3_CREATIVE_GROUP, WF3_OPTLOOP_GROUP]:
            assert group_name in OPTIMIZATION_GROUPS

    def test_health_check_threshold_valid_range(self):
        """Health check regression threshold is between 0 and 1."""
        from app.core.config import settings

        threshold = settings.HEALTH_CHECK_REGRESSION_THRESHOLD
        assert (
            0.0 < threshold < 1.0
        ), f"Threshold {threshold} outside valid range (0, 1)"

    @given(
        schedule=st.sampled_from(["on-demand", "biweekly", "monthly", "quarterly"]),
        year=st.integers(min_value=2025, max_value=2030),
        month=st.integers(min_value=1, max_value=12),
        day=st.integers(min_value=1, max_value=28),
        hour=st.integers(min_value=0, max_value=23),
    )
    @hypothesis_settings(max_examples=50, deadline=None)
    def test_wf3_schedule_is_deterministic(self, schedule, year, month, day, hour):
        """Same (schedule, datetime) inputs always produce the same result."""
        dt = datetime(year, month, day, hour, 0, tzinfo=timezone.utc)
        result1 = should_run_wf3_schedule(schedule, dt)
        result2 = should_run_wf3_schedule(schedule, dt)
        assert result1 == result2, (
            f"Non-deterministic: schedule={schedule}, dt={dt} "
            f"returned {result1} then {result2}"
        )

    @given(schedule=st.text(min_size=0, max_size=30))
    @hypothesis_settings(max_examples=30, deadline=None)
    def test_wf3_schedule_returns_bool(self, schedule):
        """should_run_wf3_schedule always returns a bool."""
        dt = datetime(2026, 6, 7, 6, 0, tzinfo=timezone.utc)
        result = should_run_wf3_schedule(schedule, dt)
        assert isinstance(result, bool)

    @given(
        year=st.integers(min_value=2025, max_value=2030),
        month=st.integers(min_value=1, max_value=12),
        day=st.integers(min_value=1, max_value=28),
    )
    @hypothesis_settings(max_examples=30, deadline=None)
    def test_on_demand_never_runs(self, year, month, day):
        """on-demand schedule never triggers a run."""
        dt = datetime(year, month, day, 6, 0, tzinfo=timezone.utc)
        assert should_run_wf3_schedule("on-demand", dt) is False
