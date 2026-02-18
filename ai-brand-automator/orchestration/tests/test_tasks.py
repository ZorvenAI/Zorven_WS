"""
Unit tests for orchestration Celery tasks.

Tests verify dispatch_job_task retry behaviour and
check_stale_jobs periodic cleanup logic.
"""

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from orchestration.models import AnalysisJob
from orchestration.tasks import check_stale_jobs, dispatch_job_task


@pytest.mark.django_db
class TestDispatchJobTask:
    """Tests for dispatch_job_task Celery task."""

    @patch("orchestration.services.OrchestratorDispatcher")
    def test_calls_dispatcher(self, MockDispatcher, analysis_job):
        """Task creates dispatcher and calls dispatch()."""
        mock_instance = MockDispatcher.return_value
        mock_instance.dispatch.return_value = True

        dispatch_job_task(analysis_job.id)

        MockDispatcher.assert_called_once()
        mock_instance.dispatch.assert_called_once()

    @patch("orchestration.services.OrchestratorDispatcher")
    def test_nonexistent_job(self, MockDispatcher):
        """Task exits early for non-existent job ID."""
        dispatch_job_task(99999)

        MockDispatcher.assert_not_called()

    @patch("orchestration.services.OrchestratorDispatcher")
    def test_retry_on_failure(self, MockDispatcher, analysis_job):
        """Task retries when dispatch returns False."""
        mock_instance = MockDispatcher.return_value
        mock_instance.dispatch.return_value = False

        with pytest.raises(Exception):
            # Apply task eagerly so retry raises immediately
            dispatch_job_task.apply(args=[analysis_job.id]).get()


@pytest.mark.django_db
class TestCheckStaleJobs:
    """Tests for check_stale_jobs periodic task."""

    def test_marks_old_running_jobs(self, tenant, user, pipeline_manifest):
        """Jobs RUNNING > 30 minutes are marked FAILED."""
        stale_job = AnalysisJob.objects.create(
            tenant=tenant,
            manifest=pipeline_manifest,
            input_prompt="Stale job",
            status=AnalysisJob.Status.RUNNING,
            created_by=user,
            started_at=timezone.now() - timedelta(minutes=45),
        )

        check_stale_jobs()

        stale_job.refresh_from_db()
        assert stale_job.status == AnalysisJob.Status.FAILED
        assert "timed out" in stale_job.error_message

    def test_skips_recent_running_jobs(self, tenant, user, pipeline_manifest):
        """Jobs RUNNING < 30 minutes are not affected."""
        recent_job = AnalysisJob.objects.create(
            tenant=tenant,
            manifest=pipeline_manifest,
            input_prompt="Recent job",
            status=AnalysisJob.Status.RUNNING,
            created_by=user,
            started_at=timezone.now() - timedelta(minutes=5),
        )

        check_stale_jobs()

        recent_job.refresh_from_db()
        assert recent_job.status == AnalysisJob.Status.RUNNING

    def test_skips_completed_jobs(self, completed_job):
        """Completed jobs are never touched."""
        check_stale_jobs()

        completed_job.refresh_from_db()
        assert completed_job.status == AnalysisJob.Status.COMPLETED

    def test_skips_queued_jobs(self, analysis_job):
        """Queued jobs are not marked stale."""
        check_stale_jobs()

        analysis_job.refresh_from_db()
        assert analysis_job.status == AnalysisJob.Status.QUEUED
