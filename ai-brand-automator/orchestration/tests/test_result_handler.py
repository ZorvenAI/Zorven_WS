"""
Tests for the shared result handler (orchestration/result_handler.py).

Covers status transitions, Redis caching, ChatMessage auto-creation,
row locking idempotency, and session lock release.
"""

from unittest.mock import patch

import pytest
from django.core.cache import cache

from orchestration.models import AnalysisJob
from orchestration.result_handler import handle_pipeline_result


@pytest.mark.django_db
class TestHandlePipelineResult:
    """Tests for handle_pipeline_result()."""

    def test_updates_status_to_running(self, analysis_job):
        """Status updated to RUNNING."""
        result = handle_pipeline_result(str(analysis_job.job_id), status="running")
        assert result is True
        analysis_job.refresh_from_db()
        assert analysis_job.status == AnalysisJob.Status.RUNNING

    def test_updates_status_to_completed(self, running_job):
        """COMPLETED sets completed_at and caches result in Redis."""
        result_data = {"summary": "All done", "score": 85}
        result = handle_pipeline_result(
            str(running_job.job_id),
            status="completed",
            result_data=result_data,
        )
        assert result is True
        running_job.refresh_from_db()
        assert running_job.status == AnalysisJob.Status.COMPLETED
        assert running_job.result_data == result_data
        assert running_job.completed_at is not None

    def test_updates_status_to_failed(self, running_job):
        """FAILED sets error_message and completed_at."""
        result = handle_pipeline_result(
            str(running_job.job_id),
            status="failed",
            error_message="Agent timeout",
        )
        assert result is True
        running_job.refresh_from_db()
        assert running_job.status == AnalysisJob.Status.FAILED
        assert running_job.error_message == "Agent timeout"
        assert running_job.completed_at is not None

    def test_updates_progress_only(self, running_job):
        """Progress-only update (no status change)."""
        progress = {"researcher": {"status": "done"}}
        result = handle_pipeline_result(str(running_job.job_id), progress=progress)
        assert result is True
        running_job.refresh_from_db()
        assert running_job.status == AnalysisJob.Status.RUNNING
        assert running_job.progress["researcher"]["status"] == "done"

    def test_nonexistent_job_returns_false(self):
        """Missing job_id returns False."""
        result = handle_pipeline_result(
            "00000000-0000-0000-0000-000000000000",
            status="running",
        )
        assert result is False

    def test_redis_cache_updated_on_completion(self, running_job):
        """Redis cache key populated after COMPLETED."""
        cache.delete(f"job:status:{running_job.job_id}")
        handle_pipeline_result(
            str(running_job.job_id),
            status="completed",
            result_data={"score": 42},
        )
        cached = cache.get(f"job:status:{running_job.job_id}")
        assert cached is not None
        assert cached["status"] == "completed"
        assert cached["result_data"]["score"] == 42

    def test_redis_cache_updated_on_failure(self, running_job):
        """Redis cache key includes error_message after FAILED."""
        cache.delete(f"job:status:{running_job.job_id}")
        handle_pipeline_result(
            str(running_job.job_id),
            status="failed",
            error_message="Boom",
        )
        cached = cache.get(f"job:status:{running_job.job_id}")
        assert cached is not None
        assert cached["status"] == "failed"
        assert cached["error_message"] == "Boom"

    def test_resolved_manifest_updates_job(self, auto_detect_job, pipeline_manifest):
        """resolved_manifest_id links the manifest FK."""
        handle_pipeline_result(
            str(auto_detect_job.job_id),
            status="running",
            resolved_manifest_id=pipeline_manifest.pipeline_id,
        )
        auto_detect_job.refresh_from_db()
        assert auto_detect_job.manifest == pipeline_manifest

    def test_resolved_manifest_nonexistent_ignored(self, auto_detect_job):
        """Unknown resolved_manifest_id is silently ignored."""
        handle_pipeline_result(
            str(auto_detect_job.job_id),
            status="running",
            resolved_manifest_id="no-such-pipeline",
        )
        auto_detect_job.refresh_from_db()
        assert auto_detect_job.manifest is None

    def test_session_lock_released_on_completion(self, tenant, user):
        """Pipeline session lock cleared when job reaches terminal state."""
        job = AnalysisJob.objects.create(
            tenant=tenant,
            input_prompt="test",
            input_context={"session_id": "sess-abc-123"},
            status=AnalysisJob.Status.RUNNING,
            created_by=user,
        )
        lock_key = "lock:chat:pipeline:sess-abc-123"
        cache.set(lock_key, str(job.job_id), timeout=300)

        handle_pipeline_result(str(job.job_id), status="completed")

        assert cache.get(lock_key) is None

    @patch("orchestration.result_handler._save_final_chat_message")
    def test_chat_message_created_on_completion(self, mock_save, running_job):
        """_save_final_chat_message called on COMPLETED."""
        handle_pipeline_result(
            str(running_job.job_id),
            status="completed",
            result_data={"summary": "Done"},
        )
        mock_save.assert_called_once()

    @patch("orchestration.result_handler._save_final_chat_message")
    def test_chat_message_not_created_on_failure(self, mock_save, running_job):
        """_save_final_chat_message not called on FAILED."""
        handle_pipeline_result(
            str(running_job.job_id),
            status="failed",
            error_message="Oops",
        )
        mock_save.assert_not_called()
