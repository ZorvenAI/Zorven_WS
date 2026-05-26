"""Unit tests for golden dataset mining (US-028)."""

from datetime import datetime, timezone

from app.datasets.miner import MiningResult, _compute_quality_score


class TestMiningResult:
    def test_defaults(self):
        r = MiningResult()
        assert r.mined == 0
        assert r.skipped == 0
        assert r.errors == 0
        assert r.details == []

    def test_accumulation(self):
        r = MiningResult(mined=5, skipped=3, errors=1, details=["test"])
        assert r.mined == 5
        assert r.skipped == 3
        assert r.errors == 1
        assert len(r.details) == 1


class TestQualityScoreComputation:
    def test_with_mlflow_run_id(self):
        class FakeRun:
            mlflow_run_id = "run-123"

        score = _compute_quality_score(FakeRun())
        assert score == 0.85

    def test_without_mlflow_run_id(self):
        class FakeRun:
            mlflow_run_id = None

        score = _compute_quality_score(FakeRun())
        assert score == 0.5

    def test_empty_mlflow_run_id(self):
        class FakeRun:
            mlflow_run_id = ""

        score = _compute_quality_score(FakeRun())
        assert score == 0.5

    def test_score_in_range(self):
        class FakeRun:
            mlflow_run_id = "run-abc"

        score = _compute_quality_score(FakeRun())
        assert 0.0 <= score <= 1.0


class TestCeleryAppConfiguration:
    def test_celery_app_importable(self):
        from app.celery_app import celery_app

        assert celery_app is not None
        assert celery_app.main == "prompt_optimization"

    def test_beat_schedule_has_mining_task(self):
        from app.celery_app import celery_app

        schedule = celery_app.conf.beat_schedule
        assert "mine-golden-examples-weekly" in schedule

    def test_beat_schedule_task_name(self):
        from app.celery_app import celery_app

        entry = celery_app.conf.beat_schedule["mine-golden-examples-weekly"]
        assert entry["task"] == "app.tasks.mine_golden_examples.mine_golden_examples"

    def test_beat_schedule_is_saturday(self):
        from app.celery_app import celery_app

        entry = celery_app.conf.beat_schedule["mine-golden-examples-weekly"]
        schedule = entry["schedule"]
        # crontab Saturday = day_of_week 6
        assert "saturday" in str(
            schedule.day_of_week
        ).lower() or schedule.day_of_week == {6}

    def test_beat_schedule_07_utc(self):
        from app.celery_app import celery_app

        entry = celery_app.conf.beat_schedule["mine-golden-examples-weekly"]
        schedule = entry["schedule"]
        assert schedule.hour == {7}
        assert schedule.minute == {0}

    def test_celery_timezone_utc(self):
        from app.celery_app import celery_app

        assert celery_app.conf.timezone == "UTC"

    def test_celery_json_serializer(self):
        from app.celery_app import celery_app

        assert celery_app.conf.task_serializer == "json"


class TestMiningTaskRegistration:
    def test_task_importable(self):
        from app.tasks.mine_golden_examples import mine_golden_examples

        assert mine_golden_examples is not None

    def test_task_name(self):
        from app.tasks.mine_golden_examples import mine_golden_examples

        assert (
            mine_golden_examples.name
            == "app.tasks.mine_golden_examples.mine_golden_examples"
        )


class TestMiningConfig:
    def test_quality_threshold_default(self):
        from app.core.config import settings

        assert settings.MINING_QUALITY_THRESHOLD == 0.8

    def test_lookback_days_default(self):
        from app.core.config import settings

        assert settings.MINING_LOOKBACK_DAYS == 7

    def test_celery_broker_url(self):
        from app.core.config import settings

        assert "redis://" in settings.CELERY_BROKER_URL


class TestMinerSourceAndQuality:
    """AC-4: source='mined' and quality_score populated."""

    def test_mined_source_constant(self):
        # Verify the miner uses 'mined' source
        import inspect

        from app.datasets.miner import mine_completed_runs

        source = inspect.getsource(mine_completed_runs)
        assert 'source="mined"' in source

    def test_quality_score_populated(self):
        import inspect

        from app.datasets.miner import mine_completed_runs

        source = inspect.getsource(mine_completed_runs)
        assert "quality_score=quality_score" in source
