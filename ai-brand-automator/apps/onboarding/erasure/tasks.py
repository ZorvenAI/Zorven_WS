"""M-02 · Celery task for async GDPR erasure execution."""

from __future__ import annotations

import logging

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=1, default_retry_delay=60)
def execute_erasure_cascade(
    self,
    *,
    tenant_id: str,
    subject_name: str,
    requested_by_user_id: str = "system",
    reason: str = "",
    erasure_log_id: int | None = None,
):
    from apps.onboarding.erasure.cascade import ErasureCascade
    from apps.onboarding.erasure.models import ErasureLog

    import apps.onboarding.erasure.stores.django_brand_assets  # noqa: F401
    import apps.onboarding.erasure.stores.django_sessions  # noqa: F401
    import apps.onboarding.erasure.stores.gcs_blobs  # noqa: F401
    import apps.onboarding.erasure.stores.oia_redis  # noqa: F401
    import apps.onboarding.erasure.stores.poi_golden_datasets  # noqa: F401
    import apps.onboarding.erasure.stores.rag_index_store  # noqa: F401

    log_entry = None
    if erasure_log_id:
        try:
            log_entry = ErasureLog.objects.get(pk=erasure_log_id)
        except ErasureLog.DoesNotExist:
            logger.warning("erasure_log_not_found", extra={"id": erasure_log_id})

    try:
        report = ErasureCascade().execute(
            tenant_id=tenant_id,
            subject_name=subject_name,
            requested_by=requested_by_user_id,
            reason=reason,
        )
    except Exception as exc:
        logger.exception(
            "erasure_cascade_task_failed",
            extra={
                "tenant_id": tenant_id,
                "subject_name": subject_name,
                "error": str(exc),
            },
        )
        if log_entry:
            log_entry.completion_report = {"error": str(exc)}
            log_entry.completed_at = timezone.now()
            log_entry.save(update_fields=["completion_report", "completed_at"])
        raise self.retry(exc=exc)

    if log_entry:
        log_entry.completion_report = report.to_dict()
        log_entry.completed_at = timezone.now()
        log_entry.save(update_fields=["completion_report", "completed_at"])

    return report.to_dict()
