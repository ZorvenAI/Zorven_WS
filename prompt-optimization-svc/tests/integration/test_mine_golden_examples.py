"""Integration tests for golden dataset mining (US-028)."""

import os

import pytest


def _postgres_available() -> bool:
    db_url = os.environ.get("POI_DATABASE_URL", "")
    if not db_url:
        return False
    try:
        import psycopg2

        conn = psycopg2.connect(db_url)
        conn.close()
        return True
    except Exception:
        return False


requires_postgres = pytest.mark.skipif(
    not _postgres_available(),
    reason="PostgreSQL not available (set POI_DATABASE_URL)",
)


class TestCeleryAppIntegration:
    """Celery app configuration tests (no broker needed)."""

    def test_celery_app_creates(self):
        from app.celery_app import celery_app

        assert celery_app is not None

    def test_beat_schedule_valid(self):
        from app.celery_app import celery_app

        schedule = celery_app.conf.beat_schedule
        assert len(schedule) >= 1
        entry = schedule["mine-golden-examples-weekly"]
        assert "task" in entry
        assert "schedule" in entry

    def test_task_registered(self):
        from app.tasks.mine_golden_examples import mine_golden_examples

        assert mine_golden_examples.name is not None


@requires_postgres
class TestMiningPipeline:
    """Full mining pipeline — requires PostgreSQL."""

    async def test_mine_empty_db(self):
        from app.datasets.miner import mine_completed_runs
        from app.models.database import async_session_factory

        result = await mine_completed_runs(
            session_factory=async_session_factory,
            quality_threshold=0.8,
            lookback_days=7,
        )
        assert result.mined >= 0
        assert result.errors == 0
