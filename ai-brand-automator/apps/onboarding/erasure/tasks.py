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
    force_session_ids: list[str] | None = None,
    decision_token: str | None = None,
):
    """Run the cascade and record its outcome on the log.

    With ``force_session_ids`` this is an erase-anyway decision from the
    review queue: the log already carries the reviewer's decision, and the
    run's report is added to it rather than replacing the first run's.

    A forced run is never retried automatically, and only runs while the
    decision it was queued for is still the current one (``decision_token``
    is that decision's ``reviewed_at``). Otherwise a retry could erase after
    the decision was cleared -- or after someone chose to keep instead.
    """
    from apps.onboarding.erasure.cascade import ErasureCascade
    from apps.onboarding.erasure.models import ErasureLog, ReviewStatus

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

    if force_session_ids and not _decision_still_current(log_entry, decision_token):
        logger.warning(
            "erasure_forced_run_skipped",
            extra={"erasure_log_id": erasure_log_id},
        )
        return {"skipped": "decision_no_longer_current"}

    try:
        report = ErasureCascade().execute(
            tenant_id=tenant_id,
            subject_name=subject_name,
            requested_by=requested_by_user_id,
            reason=reason,
            force_session_ids=force_session_ids or (),
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
        if log_entry and force_session_ids:
            # Back in the queue, still PENDING, with the failure visible and
            # the decision cleared so a reviewer can try again.
            log_entry.completion_report = {
                **(log_entry.completion_report or {}),
                "review_erase_error": str(exc),
            }
            log_entry.reviewed_by = None
            log_entry.reviewed_at = None
            log_entry.review_reason = ""
            log_entry.save(
                update_fields=[
                    "completion_report",
                    "reviewed_by",
                    "reviewed_at",
                    "review_reason",
                    "updated_at",
                ]
            )
            # Not retried: the decision is cleared, and only a reviewer
            # deciding again may start another forced run.
            return {"error": str(exc)}
        elif log_entry:
            log_entry.completion_report = {"error": str(exc)}
            log_entry.completed_at = timezone.now()
            log_entry.save(update_fields=["completion_report", "completed_at"])
        raise self.retry(exc=exc)

    if log_entry and force_session_ids:
        log_entry.completion_report = {
            **(log_entry.completion_report or {}),
            "review_erase": report.to_dict(),
        }
        log_entry.review_status = ReviewStatus.ERASED
        log_entry.save(
            update_fields=["completion_report", "review_status", "updated_at"]
        )
    elif log_entry:
        log_entry.completion_report = report.to_dict()
        log_entry.completed_at = timezone.now()
        fields = ["completion_report", "completed_at"]
        if report.manual_review_required:
            log_entry.review_status = ReviewStatus.PENDING
            fields.append("review_status")
        log_entry.save(update_fields=fields)

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
            # Held sessions stay held until a person decides, and a kept
            # request until its hold runs out: re-queuing either would bury
            # the request in duplicates. An expired hold goes back in the
            # review queue instead of being erased unseen.
            if already_pending or _awaiting_review(tenant, entry["subject_name"]):
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


def _awaiting_review(tenant, subject_name: str) -> bool:
    """Whether a held erasure for this subject is pending or still on hold.

    Returns an expired hold to the queue as a side effect, so it is decided
    again rather than silently skipped or silently erased.
    """
    from apps.onboarding.erasure.models import ErasureLog, ReviewStatus

    today = timezone.localdate()
    held = ErasureLog.objects.filter(
        tenant=tenant,
        subject_name=subject_name,
        review_status__in=(ReviewStatus.PENDING, ReviewStatus.KEPT),
    )
    expired = held.filter(review_status=ReviewStatus.KEPT, hold_until__lte=today)
    for log in expired:
        log.review_status = ReviewStatus.PENDING
        log.save(update_fields=["review_status", "updated_at"])
        logger.info(
            "erasure_hold_expired",
            extra={"erasure_log_id": log.pk, "hold_until": str(log.hold_until)},
        )
    return held.exists()


def _decision_still_current(log, token: str | None) -> bool:
    """Whether a forced run's erase-anyway decision still stands.

    Checked under the row lock, so it agrees with whatever a reviewer just
    did: still PENDING, and the same decision (``reviewed_at``) that queued it.
    """
    from django.db import transaction

    from apps.onboarding.erasure.models import ErasureLog, ReviewStatus

    if log is None or not token:
        return False
    with transaction.atomic():
        current = ErasureLog.objects.select_for_update().filter(pk=log.pk).first()
        return (
            current is not None
            and current.review_status == ReviewStatus.PENDING
            and current.reviewed_at is not None
            and current.reviewed_at.isoformat() == token
        )
