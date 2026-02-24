"""
Celery tasks for the orchestration app.

dispatch_job_task       — async dispatch to pipeline-orchestrator-svc.
check_stale_jobs        — periodic cleanup of stuck/timed-out jobs.
consume_pipeline_results — Kafka consumer for pipeline result events.
consume_agent_traces     — Kafka consumer for real-time agent trace events.
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
    from django.conf import settings as django_settings

    from .models import AnalysisJob

    try:
        job = AnalysisJob.objects.get(id=job_id)
    except AnalysisJob.DoesNotExist:
        logger.error("dispatch_job_task: Job %s not found", job_id)
        return

    if getattr(django_settings, "ORCHESTRATION_KAFKA_ENABLED", False):
        from .kafka_producer import KafkaTriggerProducer

        dispatcher = KafkaTriggerProducer()
    else:
        from .services import OrchestratorDispatcher

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
            updated_at=timezone.now(),
        )
        logger.warning("Marked %d stale orchestration jobs as failed", count)


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def consume_pipeline_results(self, max_messages=50, timeout=5.0):
    """Consume pipeline result events from Kafka.

    Scheduled via CELERY_BEAT_SCHEDULE when ORCHESTRATION_KAFKA_ENABLED=True.
    """
    try:
        from .kafka_consumers import ResultConsumer

        count = ResultConsumer().consume(max_messages, timeout)
        return count
    except Exception as exc:
        logger.error("consume_pipeline_results failed: %s", exc)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=15)
def consume_agent_traces(self, max_messages=100, timeout=2.0):
    """Consume agent trace events from Kafka for real-time UI updates.

    Scheduled via CELERY_BEAT_SCHEDULE when ORCHESTRATION_KAFKA_ENABLED=True.
    """
    try:
        from .kafka_consumers import TraceConsumer

        count = TraceConsumer().consume(max_messages, timeout)
        return count
    except Exception as exc:
        logger.error("consume_agent_traces failed: %s", exc)
        raise self.retry(exc=exc)
