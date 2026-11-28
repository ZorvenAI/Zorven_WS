"""Deciding erasure requests held for signed meeting records.

A cascade that meets a session with a signed record leaves it untouched and
marks the request PENDING (PR #705). An owner or admin then decides:

- **keep** -- the sessions stay under legal hold until ``hold_until``, when the
  retention job puts the request back in the queue;
- **erase anyway** -- the held sessions are erased with the normal cascade,
  leaving only a tombstone of record numbers and fingerprints.

Both need a written reason and are final. The row is locked while deciding so
two reviewers cannot both act on one request.
"""

from __future__ import annotations

import logging
from datetime import date

from django.db import transaction
from django.utils import timezone

from apps.onboarding.erasure.models import (
    LEGAL_HOLD_YEARS_DEFAULT,
    ErasureLog,
    RetentionConfig,
    ReviewStatus,
)

logger = logging.getLogger(__name__)

MIN_REASON_CHARS = 10

#: GDPR allows one month to respond (Art. 12(3)); warn with time to spare.
OVERDUE_AFTER_DAYS = 25


class ReviewError(Exception):
    def __init__(self, code: str, detail: str, status: int = 400):
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.status = status


def days_waiting(log: ErasureLog, now=None) -> int:
    now = now or timezone.now()
    return max(0, (now - log.requested_at).days)


def is_overdue(log: ErasureLog, now=None) -> bool:
    return days_waiting(log, now) >= OVERDUE_AFTER_DAYS


def held_session_ids(log: ErasureLog) -> list[str]:
    return [
        str(entry["session_id"])
        for entry in (log.completion_report or {}).get("held_for_review", [])
    ]


def default_hold_until(tenant) -> date:
    config = RetentionConfig.objects.filter(tenant=tenant).first()
    years = config.legal_hold_years if config else LEGAL_HOLD_YEARS_DEFAULT
    today = timezone.localdate()
    try:
        return today.replace(year=today.year + years)
    except ValueError:  # 29 February into a non-leap year
        return today.replace(year=today.year + years, day=28)


def _clean_reason(reason) -> str:
    reason = " ".join(str(reason or "").split())
    if len(reason) < MIN_REASON_CHARS:
        raise ReviewError(
            "reason_required",
            f"Give a reason of at least {MIN_REASON_CHARS} characters.",
        )
    return reason


def _locked_pending(log: ErasureLog) -> ErasureLog:
    log = ErasureLog.objects.select_for_update().get(pk=log.pk)
    if log.review_status != ReviewStatus.PENDING:
        raise ReviewError(
            "not_pending",
            "This request is not awaiting review; it may already be decided.",
            status=409,
        )
    return log


@transaction.atomic
def keep(log: ErasureLog, *, user, reason, hold_until: date | None = None):
    """Keep the held sessions under legal hold until ``hold_until``."""
    reason = _clean_reason(reason)
    log = _locked_pending(log)
    hold_until = hold_until or default_hold_until(log.tenant)
    if hold_until <= timezone.localdate():
        raise ReviewError("hold_until_past", "The hold must end in the future.")

    log.review_status = ReviewStatus.KEPT
    log.reviewed_by = user if getattr(user, "pk", None) else None
    log.reviewed_at = timezone.now()
    log.review_reason = reason
    log.hold_until = hold_until
    log.save(
        update_fields=[
            "review_status",
            "reviewed_by",
            "reviewed_at",
            "review_reason",
            "hold_until",
            "updated_at",
        ]
    )
    logger.info(
        "erasure_review_kept",
        extra={"erasure_log_id": log.pk, "hold_until": str(hold_until)},
    )
    return log


@transaction.atomic
def erase_anyway(log: ErasureLog, *, user, reason, confirm_subject):
    """Record the decision and queue the erasure of the held sessions.

    The request stays PENDING until the cascade finishes, so a failed run
    leaves it in the queue with the error visible.
    """
    from apps.onboarding.erasure.tasks import execute_erasure_cascade

    reason = _clean_reason(reason)
    log = _locked_pending(log)
    if str(confirm_subject or "").strip() != log.subject_name:
        raise ReviewError(
            "confirmation_mismatch",
            "Type the subject's name exactly as shown to confirm.",
        )
    sessions = held_session_ids(log)
    if not sessions:
        raise ReviewError("nothing_held", "This request holds no sessions.", 409)
    if log.reviewed_at is not None:
        # Erase anyway was already chosen and its run is in flight.
        raise ReviewError(
            "erase_in_progress",
            "Erasure was already chosen for this request and is running.",
            status=409,
        )

    log.reviewed_by = user if getattr(user, "pk", None) else None
    log.reviewed_at = timezone.now()
    log.review_reason = reason
    log.save(
        update_fields=["reviewed_by", "reviewed_at", "review_reason", "updated_at"]
    )

    payload = {
        "tenant_id": str(log.tenant_id),
        "subject_name": log.subject_name,
        "requested_by_user_id": str(getattr(user, "pk", "") or "system"),
        "reason": f"review: {reason}"[:255],
        "erasure_log_id": log.pk,
        "force_session_ids": sessions,
        # Ties the queued run to this decision; see _decision_still_current.
        "decision_token": log.reviewed_at.isoformat(),
    }
    transaction.on_commit(lambda: execute_erasure_cascade.delay(**payload))
    logger.warning(
        "erasure_review_erase_anyway",
        extra={"erasure_log_id": log.pk, "sessions": sessions},
    )
    return log
