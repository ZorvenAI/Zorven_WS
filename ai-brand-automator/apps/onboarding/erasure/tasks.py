"""Celery tasks for GDPR erasure and retention enforcement.

execute_erasure_cascade (M-02): runs the registry-driven cascade for one subject.
enforce_retention_windows (M-03): daily sweep that erases expired subjects.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from django.db.models import Max
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


@shared_task(bind=True, max_retries=0)
def enforce_retention_windows(self):
    """Daily retention enforcement (M-03, §20, FR-GDPR-02).

    For each tenant, find subjects whose most recent session is older
    than the tenant's retention window and dispatch an erasure cascade
    for each.
    """
    from tenants.models import Tenant

    from apps.onboarding.erasure.models import (
        RETENTION_DAYS_DEFAULT,
        ErasureLog,
    )
    from apps.onboarding.models import ConsentRecord

    total_dispatched = 0

    for tenant in Tenant.objects.select_related("retention_config").all():
        retention_config = getattr(tenant, "retention_config", None)
        retention_days = (
            retention_config.retention_days
            if retention_config
            else RETENTION_DAYS_DEFAULT
        )
        cutoff = timezone.now() - timedelta(days=retention_days)

        expired_subjects = (
            ConsentRecord.objects.filter(
                tenant=tenant,
                revoked_at__isnull=True,
            )
            .values("subject_name")
            .annotate(latest=Max("session__created_at"))
            .filter(latest__lt=cutoff)
        )

        for entry in expired_subjects:
            already_pending = ErasureLog.objects.filter(
                tenant=tenant,
                subject_name=entry["subject_name"],
                reason="retention_enforcement",
                completed_at__isnull=True,
            ).exists()
            if already_pending:
                continue

            log_entry = ErasureLog.objects.create(
                tenant=tenant,
                subject_name=entry["subject_name"],
                reason="retention_enforcement",
            )
            execute_erasure_cascade.delay(
                tenant_id=str(tenant.pk),
                subject_name=entry["subject_name"],
                requested_by_user_id="system",
                reason="retention_enforcement",
                erasure_log_id=log_entry.pk,
            )
            total_dispatched += 1

    logger.info(
        "retention_enforcement_complete",
        extra={"dispatched": total_dispatched},
    )
    return {"dispatched": total_dispatched}
