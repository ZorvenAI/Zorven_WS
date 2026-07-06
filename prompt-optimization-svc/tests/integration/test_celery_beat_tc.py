"""Integration tests for Celery Beat schedule via testcontainers (US-059).

Tests Celery app connectivity, beat schedule entries, task module
imports, and task routing against a real Redis container.
"""

import importlib
import os

import pytest
from celery import Celery


@pytest.mark.integration
class TestCeleryBeatTC:
    """Celery Beat schedule validation via testcontainers."""

    @pytest.fixture
    def celery_test_app(self):
        """Create a Celery app connected to testcontainer Redis."""
        broker_url = os.environ.get(
            "POI_CELERY_BROKER_URL",
            os.environ.get("POI_REDIS_URL", "redis://localhost:6379/26"),
        )
        from app.celery_app import celery_app

        celery_app.conf.broker_url = broker_url
        celery_app.conf.result_backend = broker_url
        return celery_app

    def test_celery_app_connects_to_redis_broker(self, celery_test_app):
        """Celery app can connect to testcontainer Redis broker."""
        conn = celery_test_app.connection()
        try:
            conn.ensure_connection(max_retries=3, timeout=5)
            assert conn.connected is True
        finally:
            conn.close()

    def test_beat_schedule_has_required_entries(self, celery_test_app):
        """Verify all 6 scheduled tasks are present in beat_schedule."""
        schedule = celery_test_app.conf.beat_schedule
        required_keys = [
            "mine-golden-examples-weekly",
            "optimize-wf1-pipeline-monthly",
            "optimize-wf2-pipeline-monthly",
            "optimize-wf3-creative-pipeline",
            "optimize-wf3-optimization-loop",
            "prompt-health-check-daily",
        ]
        for key in required_keys:
            assert key in schedule, f"Missing beat schedule entry: {key}"
            assert "task" in schedule[key], f"No task in schedule entry: {key}"
            assert "schedule" in schedule[key], f"No schedule in entry: {key}"

    def test_all_task_modules_importable(self, celery_test_app):
        """Each module in celery_app.conf.include is importable."""
        include = celery_test_app.conf.include
        assert (
            len(include) >= 5
        ), f"Expected at least 5 task modules, got {len(include)}"

        for module_path in include:
            mod = importlib.import_module(module_path)
            assert mod is not None, f"Failed to import {module_path}"

    def test_task_routing_keys_valid(self, celery_test_app):
        """All beat schedule tasks reference valid task paths."""
        schedule = celery_test_app.conf.beat_schedule
        for entry_name, entry in schedule.items():
            task_path = entry["task"]
            parts = task_path.rsplit(".", 1)
            assert len(parts) == 2, (
                f"Task path '{task_path}' in '{entry_name}' "
                "should be 'module.function'"
            )
            module_path, func_name = parts
            mod = importlib.import_module(module_path)
            assert hasattr(mod, func_name), (
                f"Module '{module_path}' has no function '{func_name}' "
                f"(referenced by '{entry_name}')"
            )
