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


def _refresh_attachment_paths(job):
    """Re-read BrandAsset GCS paths so the orchestrator gets current locations.

    The data pipeline may move files from _landing/ to raw/ between the
    time the job is created and when it is dispatched.  The caller should
    use a Celery countdown to defer execution rather than blocking with sleep.
    """
    ctx = job.input_context
    if not ctx or not ctx.get("attachments"):
        return False

    from onboarding.models import BrandAsset

    changed = False
    for att in ctx["attachments"]:
        asset_id = att.get("asset_id")
        if not asset_id:
            continue
        try:
            asset = BrandAsset.objects.get(id=asset_id)
            if asset.gcs_path != att.get("gcs_path"):
                att["gcs_path"] = asset.gcs_path
                att["gcs_bucket"] = asset.gcs_bucket
                changed = True
        except BrandAsset.DoesNotExist:
            pass

    if changed:
        job.input_context = ctx
        job.save(update_fields=["input_context", "updated_at"])

    return changed


@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def dispatch_job_task(self, job_id, _attachment_refresh_pending=False):
    """
    Dispatch a job to the orchestrator service.

    Wrapped in a Celery task so the view returns immediately.
    Retries up to 3 times on connection errors (10s delay).

    When attachments are present, the first invocation defers via a 3-second
    countdown retry to let the data pipeline move files from _landing/ to
    raw/. The retry then snapshots the latest GCS paths before dispatching.
    """
    from django.conf import settings as django_settings

    from .models import AnalysisJob

    try:
        job = AnalysisJob.objects.get(id=job_id)
    except AnalysisJob.DoesNotExist:
        logger.error("dispatch_job_task: Job %s not found", job_id)
        return

    # On the first call, if there are attachments, defer 3s to let the
    # data pipeline finish before we snapshot GCS paths.
    ctx = job.input_context or {}
    if ctx.get("attachments") and not _attachment_refresh_pending:
        raise self.retry(
            args=[job_id],
            kwargs={"_attachment_refresh_pending": True},
            countdown=3,
        )

    # Refresh attachment GCS paths in case the data pipeline updated them
    _refresh_attachment_paths(job)

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


# ── TCIA Scheduled Scan Tasks ──


@shared_task(name="orchestration.tasks.emit_tcia_daily_scan")
def emit_tcia_daily_scan():
    """Emit daily trend scan commands for all active tenants.

    Runs hourly; each tenant has an adaptive optimal scan hour
    stored in Redis. Emits Kafka commands to the TCIA consumer.
    """
    from datetime import datetime as dt
    from datetime import timezone as tz

    from django.conf import settings as django_settings

    if not getattr(django_settings, "ORCHESTRATION_KAFKA_ENABLED", False):
        return

    try:
        from tenants.models import Tenant

        from .kafka_producer import KafkaTriggerProducer

        producer = KafkaTriggerProducer()
        current_hour = dt.now(tz.utc).hour
        count = 0

        for tenant in Tenant.objects.filter(is_active=True):
            # Default scan hour is 6 UTC
            optimal_hour = 6
            if current_hour != optimal_hour:
                continue

            command = {
                "command_type": "scheduled_trend_scan",
                "tenant_id": str(tenant.id),
                "payload": {
                    "scan_type": "daily_scan",
                    "industry": getattr(tenant, "industry", "") or "",
                    "focus_areas": [],
                },
                "idempotency_key": (
                    f"trend:daily:{tenant.id}:"
                    f"{dt.now(tz.utc).date().isoformat()}"
                ),
                "timestamp": dt.now(tz.utc).isoformat(),
            }
            producer.send_to_topic(
                "agent.commands.trend-cultural-agent", command
            )
            count += 1

        logger.info("Emitted %d TCIA daily scan commands", count)
    except Exception as exc:
        logger.error("emit_tcia_daily_scan failed: %s", exc)


@shared_task(name="orchestration.tasks.emit_tcia_weekly_report")
def emit_tcia_weekly_report():
    """Emit weekly comprehensive trend report commands (Mondays 04:00 UTC)."""
    from datetime import datetime as dt
    from datetime import timezone as tz

    from django.conf import settings as django_settings

    if not getattr(django_settings, "ORCHESTRATION_KAFKA_ENABLED", False):
        return

    try:
        from tenants.models import Tenant

        from .kafka_producer import KafkaTriggerProducer

        producer = KafkaTriggerProducer()
        count = 0

        for tenant in Tenant.objects.filter(is_active=True):
            command = {
                "command_type": "scheduled_trend_report",
                "tenant_id": str(tenant.id),
                "payload": {
                    "scan_type": "weekly_comprehensive",
                    "industry": getattr(tenant, "industry", "") or "",
                    "focus_areas": [],
                },
                "idempotency_key": (
                    f"trend:weekly:{tenant.id}:"
                    f"{dt.now(tz.utc).date().isoformat()}"
                ),
                "timestamp": dt.now(tz.utc).isoformat(),
            }
            producer.send_to_topic(
                "agent.commands.trend-cultural-agent", command
            )
            count += 1

        logger.info("Emitted %d TCIA weekly report commands", count)
    except Exception as exc:
        logger.error("emit_tcia_weekly_report failed: %s", exc)
