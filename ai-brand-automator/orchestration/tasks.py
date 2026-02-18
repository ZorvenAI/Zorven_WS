"""
Celery tasks for the orchestration app.

dispatch_job_task — async dispatch to pipeline-orchestrator-svc.
check_stale_jobs — periodic cleanup of stuck/timed-out jobs.
"""

import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def dispatch_job_task(self, job_id):
    """
    Dispatch a job to the orchestrator service.

    Wrapped in a Celery task so the view returns immediately.
    Retries up to 3 times on connection errors (10s delay).
    """
    from .models import AnalysisJob
    from .services import OrchestratorDispatcher

    try:
        job = AnalysisJob.objects.get(id=job_id)
    except AnalysisJob.DoesNotExist:
        logger.error("dispatch_job_task: Job %s not found", job_id)
        return

    dispatcher = OrchestratorDispatcher()
    success = dispatcher.dispatch(job)

    if not success:
        try:
            raise self.retry(exc=Exception(f"Dispatch failed for job {job.job_id}"))
        except self.MaxRetriesExceededError:
            logger.error("Max retries exceeded for job %s", job.job_id)
            job.status = AnalysisJob.Status.FAILED
            job.error_message = "Failed to dispatch job after multiple retries"
            job.completed_at = timezone.now()
            job.save(
                update_fields=[
                    "status",
                    "error_message",
                    "completed_at",
                    "updated_at",
                ]
            )


@shared_task
def check_stale_jobs():
    """
    Periodic task: mark jobs as FAILED if RUNNING for > 30 minutes.

    Scheduled via CELERY_BEAT_SCHEDULE in settings.py (every 5 minutes).
    Catches runaway pipelines and unresponsive orchestrator scenarios.
    """
    from .models import AnalysisJob

    threshold = timezone.now() - timedelta(minutes=30)
    stale_jobs = AnalysisJob.objects.filter(
        status=AnalysisJob.Status.RUNNING,
        started_at__lt=threshold,
    )

    count = stale_jobs.count()
    if count > 0:
        stale_jobs.update(
            status=AnalysisJob.Status.FAILED,
            error_message="Job timed out after 30 minutes",
            completed_at=timezone.now(),
        )
        logger.warning("Marked %d stale orchestration jobs as failed", count)
