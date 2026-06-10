"""Unit tests for Celery Beat optimization schedules (US-046).

Validates that all 6 §14.1 tasks are registered with correct crontab
schedules, that WF3 schedule logic correctly handles all cadence options,
and that the health check regression detection works.

NO mocks — all tests use real imports and real Celery app configuration.
"""

from datetime import datetime, timezone

from celery.schedules import crontab

from app.tasks.optimize_wf3_pipeline import should_run_wf3_schedule
from app.tasks.prompt_health_check import _check_regression, _get_reopt_task_name


# ── Beat Schedule Configuration ──


class TestBeatScheduleConfiguration:
    """Verify all 6 §14.1 entries are present and correct."""

    def test_beat_schedule_has_6_entries(self):
        from app.celery_app import celery_app

        assert len(celery_app.conf.beat_schedule) == 6

    def test_mine_golden_examples_present(self):
        from app.celery_app import celery_app

        assert "mine-golden-examples-weekly" in celery_app.conf.beat_schedule

    def test_wf1_pipeline_present(self):
        from app.celery_app import celery_app

        assert "optimize-wf1-pipeline-monthly" in celery_app.conf.beat_schedule

    def test_wf2_pipeline_present(self):
        from app.celery_app import celery_app

        assert "optimize-wf2-pipeline-monthly" in celery_app.conf.beat_schedule

    def test_wf3_creative_present(self):
        from app.celery_app import celery_app

        assert "optimize-wf3-creative-pipeline" in celery_app.conf.beat_schedule

    def test_wf3_optloop_present(self):
        from app.celery_app import celery_app

        assert "optimize-wf3-optimization-loop" in celery_app.conf.beat_schedule

    def test_health_check_present(self):
        from app.celery_app import celery_app

        assert "prompt-health-check-daily" in celery_app.conf.beat_schedule

    def test_utc_timezone(self):
        from app.celery_app import celery_app

        assert celery_app.conf.timezone == "UTC"

    def test_json_serializer(self):
        from app.celery_app import celery_app

        assert celery_app.conf.task_serializer == "json"

    def test_include_has_all_task_modules(self):
        from app.celery_app import celery_app

        include = celery_app.conf.include
        assert "app.tasks.mine_golden_examples" in include
        assert "app.tasks.optimize_wf1_pipeline" in include
        assert "app.tasks.optimize_wf2_pipeline" in include
        assert "app.tasks.optimize_wf3_pipeline" in include
        assert "app.tasks.prompt_health_check" in include

    def test_all_entries_have_schedule(self):
        from app.celery_app import celery_app

        for name, entry in celery_app.conf.beat_schedule.items():
            assert "schedule" in entry, f"Entry '{name}' missing schedule"

    def test_all_entries_have_task(self):
        from app.celery_app import celery_app

        for name, entry in celery_app.conf.beat_schedule.items():
            assert "task" in entry, f"Entry '{name}' missing task"


# ── Mine Golden Examples Schedule (existing — regression test) ──


class TestMineGoldenExamplesSchedule:
    def test_task_name(self):
        from app.celery_app import celery_app

        entry = celery_app.conf.beat_schedule["mine-golden-examples-weekly"]
        assert entry["task"] == "app.tasks.mine_golden_examples.mine_golden_examples"

    def test_saturday_07_utc(self):
        from app.celery_app import celery_app

        entry = celery_app.conf.beat_schedule["mine-golden-examples-weekly"]
        schedule = entry["schedule"]
        assert schedule.hour == {7}
        assert schedule.minute == {0}

    def test_day_of_week_saturday(self):
        from app.celery_app import celery_app

        entry = celery_app.conf.beat_schedule["mine-golden-examples-weekly"]
        schedule = entry["schedule"]
        assert schedule.day_of_week == {6}  # Saturday


# ── WF1 Pipeline Schedule ──


class TestWf1PipelineSchedule:
    def test_task_name(self):
        from app.celery_app import celery_app

        entry = celery_app.conf.beat_schedule["optimize-wf1-pipeline-monthly"]
        assert entry["task"] == "app.tasks.optimize_wf1_pipeline.optimize_wf1_pipeline"

    def test_2nd_sunday_06_utc(self):
        from app.celery_app import celery_app

        entry = celery_app.conf.beat_schedule["optimize-wf1-pipeline-monthly"]
        schedule = entry["schedule"]
        assert schedule.hour == {6}
        assert schedule.minute == {0}
        assert schedule.day_of_week == {0}  # Sunday

    def test_day_of_month_8_to_14(self):
        from app.celery_app import celery_app

        entry = celery_app.conf.beat_schedule["optimize-wf1-pipeline-monthly"]
        schedule = entry["schedule"]
        assert schedule.day_of_month == {8, 9, 10, 11, 12, 13, 14}


# ── WF2 Pipeline Schedule ──


class TestWf2PipelineSchedule:
    def test_task_name(self):
        from app.celery_app import celery_app

        entry = celery_app.conf.beat_schedule["optimize-wf2-pipeline-monthly"]
        assert entry["task"] == "app.tasks.optimize_wf2_pipeline.optimize_wf2_pipeline"

    def test_3rd_sunday_06_utc(self):
        from app.celery_app import celery_app

        entry = celery_app.conf.beat_schedule["optimize-wf2-pipeline-monthly"]
        schedule = entry["schedule"]
        assert schedule.hour == {6}
        assert schedule.minute == {0}
        assert schedule.day_of_week == {0}  # Sunday

    def test_day_of_month_15_to_21(self):
        from app.celery_app import celery_app

        entry = celery_app.conf.beat_schedule["optimize-wf2-pipeline-monthly"]
        schedule = entry["schedule"]
        assert schedule.day_of_month == {15, 16, 17, 18, 19, 20, 21}


# ── WF3 Creative Pipeline Schedule ──


class TestWf3CreativePipelineSchedule:
    def test_task_name(self):
        from app.celery_app import celery_app

        entry = celery_app.conf.beat_schedule["optimize-wf3-creative-pipeline"]
        assert (
            entry["task"]
            == "app.tasks.optimize_wf3_pipeline.optimize_wf3_creative_pipeline"
        )

    def test_sunday_06_utc(self):
        from app.celery_app import celery_app

        entry = celery_app.conf.beat_schedule["optimize-wf3-creative-pipeline"]
        schedule = entry["schedule"]
        assert schedule.hour == {6}
        assert schedule.minute == {0}
        assert schedule.day_of_week == {0}  # Sunday


# ── WF3 Optimization Loop Schedule ──


class TestWf3OptimizationLoopSchedule:
    def test_task_name(self):
        from app.celery_app import celery_app

        entry = celery_app.conf.beat_schedule["optimize-wf3-optimization-loop"]
        assert (
            entry["task"]
            == "app.tasks.optimize_wf3_pipeline.optimize_wf3_optimization_loop"
        )

    def test_sunday_06_30_utc(self):
        from app.celery_app import celery_app

        entry = celery_app.conf.beat_schedule["optimize-wf3-optimization-loop"]
        schedule = entry["schedule"]
        assert schedule.hour == {6}
        assert schedule.minute == {30}
        assert schedule.day_of_week == {0}  # Sunday


# ── Health Check Schedule ──


class TestHealthCheckSchedule:
    def test_task_name(self):
        from app.celery_app import celery_app

        entry = celery_app.conf.beat_schedule["prompt-health-check-daily"]
        assert entry["task"] == "app.tasks.prompt_health_check.prompt_health_check"

    def test_daily_10_utc(self):
        from app.celery_app import celery_app

        entry = celery_app.conf.beat_schedule["prompt-health-check-daily"]
        schedule = entry["schedule"]
        assert schedule.hour == {10}
        assert schedule.minute == {0}

    def test_runs_every_day(self):
        from app.celery_app import celery_app

        entry = celery_app.conf.beat_schedule["prompt-health-check-daily"]
        schedule = entry["schedule"]
        # No day_of_week restriction — runs daily
        assert schedule.day_of_week == {0, 1, 2, 3, 4, 5, 6}


# ── Task Registration ──


class TestTaskRegistration:
    def test_mine_golden_examples_importable(self):
        from app.tasks.mine_golden_examples import mine_golden_examples

        assert mine_golden_examples is not None
        assert (
            mine_golden_examples.name
            == "app.tasks.mine_golden_examples.mine_golden_examples"
        )

    def test_optimize_wf1_importable(self):
        from app.tasks.optimize_wf1_pipeline import optimize_wf1_pipeline

        assert optimize_wf1_pipeline is not None
        assert (
            optimize_wf1_pipeline.name
            == "app.tasks.optimize_wf1_pipeline.optimize_wf1_pipeline"
        )

    def test_optimize_wf2_importable(self):
        from app.tasks.optimize_wf2_pipeline import optimize_wf2_pipeline

        assert optimize_wf2_pipeline is not None
        assert (
            optimize_wf2_pipeline.name
            == "app.tasks.optimize_wf2_pipeline.optimize_wf2_pipeline"
        )

    def test_optimize_wf3_creative_importable(self):
        from app.tasks.optimize_wf3_pipeline import optimize_wf3_creative_pipeline

        assert optimize_wf3_creative_pipeline is not None
        assert (
            optimize_wf3_creative_pipeline.name
            == "app.tasks.optimize_wf3_pipeline.optimize_wf3_creative_pipeline"
        )

    def test_optimize_wf3_optloop_importable(self):
        from app.tasks.optimize_wf3_pipeline import optimize_wf3_optimization_loop

        assert optimize_wf3_optimization_loop is not None
        assert (
            optimize_wf3_optimization_loop.name
            == "app.tasks.optimize_wf3_pipeline.optimize_wf3_optimization_loop"
        )

    def test_prompt_health_check_importable(self):
        from app.tasks.prompt_health_check import prompt_health_check

        assert prompt_health_check is not None
        assert (
            prompt_health_check.name
            == "app.tasks.prompt_health_check.prompt_health_check"
        )


# ── Task Configuration ──


class TestTaskConfig:
    def test_health_check_threshold_default(self):
        from app.core.config import settings

        assert settings.HEALTH_CHECK_REGRESSION_THRESHOLD == 0.10

    def test_celery_broker_url(self):
        from app.core.config import settings

        assert "redis://" in settings.CELERY_BROKER_URL


# ── WF3 Schedule Logic ──


class TestWf3ScheduleLogic:
    def test_on_demand_always_skips(self):
        now = datetime(2026, 6, 7, 6, 0, tzinfo=timezone.utc)  # Sunday
        assert should_run_wf3_schedule("on-demand", now) is False

    def test_biweekly_even_week_runs(self):
        # ISO week 24 (even) — should run
        now = datetime(2026, 6, 14, 6, 0, tzinfo=timezone.utc)  # Sunday
        assert now.isocalendar()[1] % 2 == 0
        assert should_run_wf3_schedule("biweekly", now) is True

    def test_biweekly_odd_week_skips(self):
        # ISO week 23 (odd) — should skip
        now = datetime(2026, 6, 7, 6, 0, tzinfo=timezone.utc)  # Sunday
        assert now.isocalendar()[1] % 2 == 1
        assert should_run_wf3_schedule("biweekly", now) is False

    def test_monthly_first_sunday_runs(self):
        # June 7, 2026 is a Sunday and day <= 7
        now = datetime(2026, 6, 7, 6, 0, tzinfo=timezone.utc)
        assert should_run_wf3_schedule("monthly", now) is True

    def test_monthly_later_sunday_skips(self):
        # June 14, 2026 is a Sunday but day > 7
        now = datetime(2026, 6, 14, 6, 0, tzinfo=timezone.utc)
        assert should_run_wf3_schedule("monthly", now) is False

    def test_quarterly_q1_first_sunday_runs(self):
        # January 4, 2026 is a Sunday in Q1 start month, day <= 7
        now = datetime(2026, 1, 4, 6, 0, tzinfo=timezone.utc)
        assert should_run_wf3_schedule("quarterly", now) is True

    def test_quarterly_non_q_month_skips(self):
        # June is not a quarter start month
        now = datetime(2026, 6, 7, 6, 0, tzinfo=timezone.utc)
        assert should_run_wf3_schedule("quarterly", now) is False

    def test_quarterly_q_month_later_day_skips(self):
        # April 12, 2026 — Q2 start month but day > 7
        now = datetime(2026, 4, 12, 6, 0, tzinfo=timezone.utc)
        assert should_run_wf3_schedule("quarterly", now) is False

    def test_unknown_schedule_skips(self):
        now = datetime(2026, 6, 7, 6, 0, tzinfo=timezone.utc)
        assert should_run_wf3_schedule("invalid_schedule", now) is False

    def test_empty_string_skips(self):
        now = datetime(2026, 6, 7, 6, 0, tzinfo=timezone.utc)
        assert should_run_wf3_schedule("", now) is False


# ── Health Check Logic ──


class TestHealthCheckRegression:
    def test_regression_above_threshold_detected(self):
        # Score 0.85 is below (1.0 - 0.10) = 0.90 → regression
        assert _check_regression(0.85, 0.10) is True

    def test_no_regression_below_threshold(self):
        # Score 0.95 is above 0.90 → healthy
        assert _check_regression(0.95, 0.10) is False

    def test_exactly_at_threshold_not_flagged(self):
        # Score 0.90 is at boundary — not below (1.0 - 0.10) → healthy
        assert _check_regression(0.90, 0.10) is False

    def test_none_score_no_regression(self):
        assert _check_regression(None, 0.10) is False

    def test_zero_score_regression(self):
        assert _check_regression(0.0, 0.10) is True


class TestHealthCheckTaskRouting:
    def test_wf1_prompt_routes_to_wf1_task(self):
        task = _get_reopt_task_name("zorven-wf1-mra-planning")
        assert task == "app.tasks.optimize_wf1_pipeline.optimize_wf1_pipeline"

    def test_wf2_prompt_routes_to_wf2_task(self):
        task = _get_reopt_task_name("zorven-wf2-bpa-positioning")
        assert task == "app.tasks.optimize_wf2_pipeline.optimize_wf2_pipeline"

    def test_wf3_caa_routes_to_creative(self):
        task = _get_reopt_task_name("zorven-wf3-caa-blueprint")
        assert task == "app.tasks.optimize_wf3_pipeline.optimize_wf3_creative_pipeline"

    def test_wf3_cga_routes_to_creative(self):
        task = _get_reopt_task_name("zorven-wf3-cga-profiling")
        assert task == "app.tasks.optimize_wf3_pipeline.optimize_wf3_creative_pipeline"

    def test_wf3_coa_routes_to_optloop(self):
        task = _get_reopt_task_name("zorven-wf3-coa-optimization")
        assert task == "app.tasks.optimize_wf3_pipeline.optimize_wf3_optimization_loop"

    def test_wf3_ila_routes_to_optloop(self):
        task = _get_reopt_task_name("zorven-wf3-ila-extraction")
        assert task == "app.tasks.optimize_wf3_pipeline.optimize_wf3_optimization_loop"

    def test_unknown_prompt_returns_none(self):
        task = _get_reopt_task_name("unknown-prompt")
        assert task is None

    def test_wf3_adpub_routes_to_creative(self):
        task = _get_reopt_task_name("zorven-wf3-adpub-publishing")
        assert task == "app.tasks.optimize_wf3_pipeline.optimize_wf3_creative_pipeline"


# ── Task Group Constants ──


class TestTaskGroupConstants:
    def test_wf1_group_name(self):
        from app.tasks.optimize_wf1_pipeline import GROUP_NAME

        assert GROUP_NAME == "wf1-discovery-pipeline"

    def test_wf2_group_name(self):
        from app.tasks.optimize_wf2_pipeline import GROUP_NAME

        assert GROUP_NAME == "wf2-brand-strategy-pipeline"

    def test_wf3_creative_group_name(self):
        from app.tasks.optimize_wf3_pipeline import WF3_CREATIVE_GROUP

        assert WF3_CREATIVE_GROUP == "wf3-creative-pipeline"

    def test_wf3_optloop_group_name(self):
        from app.tasks.optimize_wf3_pipeline import WF3_OPTLOOP_GROUP

        assert WF3_OPTLOOP_GROUP == "wf3-optimization-loop"

    def test_all_groups_exist_in_registry(self):
        from app.registries.optimization_groups import OPTIMIZATION_GROUPS
        from app.tasks.optimize_wf1_pipeline import GROUP_NAME as WF1_GROUP
        from app.tasks.optimize_wf2_pipeline import GROUP_NAME as WF2_GROUP
        from app.tasks.optimize_wf3_pipeline import (
            WF3_CREATIVE_GROUP,
            WF3_OPTLOOP_GROUP,
        )

        for group in [WF1_GROUP, WF2_GROUP, WF3_CREATIVE_GROUP, WF3_OPTLOOP_GROUP]:
            assert group in OPTIMIZATION_GROUPS, f"Group '{group}' not in registry"
