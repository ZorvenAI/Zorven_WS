"""What follows a signing action: notifying people and filing the final PDF.

Kept apart from ``signing.py`` because none of it may undo a signature. A
signature is recorded in its own transaction; everything here runs after that
commits and reports its failures to the audit trail instead of raising.
"""

from __future__ import annotations

import hashlib
import io
import logging

from celery import shared_task

from apps.onboarding.records import emails, signing
from apps.onboarding.records.models import (
    MeetingRecord,
    RecordStatus,
    SignatoryStatus,
)
from apps.onboarding.records.pdf import build_record_pdf
from apps.onboarding.records.presentation import view_of

logger = logging.getLogger(__name__)


def pdf_path(record: MeetingRecord) -> str:
    return (
        f"meeting-records/{record.tenant_id or 'none'}/{record.session_id}/"
        f"{record.record_number}.pdf"
    )


def _fresh(record_id: int) -> MeetingRecord | None:
    return (
        MeetingRecord.objects.select_related(
            "recording", "session", "session__company", "tenant", "supersedes"
        )
        .filter(pk=record_id)
        .first()
    )


def send_signing_requests(record_id: int, *, reminder: bool = False) -> int:
    """Email every signatory who has not acted. Returns how many were sent.

    Each send issues a new link, which replaces the last: a reminder is also
    how a lost or leaked link is retired.
    """
    record = _fresh(record_id)
    if record is None or record.status not in signing.OPEN_STATUSES:
        return 0
    sent = 0
    for signatory in record.signatories.filter(status=SignatoryStatus.PENDING):
        token = signing.issue_link(signatory)
        if emails.send_signing_request(record, signatory, token, reminder=reminder):
            sent += 1
    return sent


def notify_remarks(record_id: int) -> int:
    """Tell earlier signers about remarks they must acknowledge."""
    record = _fresh(record_id)
    if record is None or record.status not in signing.OPEN_STATUSES:
        return 0
    signatories = {s.pk: s for s in record.signatories.all()}
    sent = 0
    for pk, remarks in signing.pending_acknowledgements(record).items():
        signer = signatories[pk]
        token = signing.issue_link(signer)
        if emails.send_remarks_notice(record, signer, remarks[-1], token):
            sent += 1
    return sent


def notify_declined(record_id: int) -> int:
    record = _fresh(record_id)
    if record is None or record.status != RecordStatus.DECLINED:
        return 0
    signatories = list(record.signatories.all())
    # The required signatory whose refusal closed the record; an optional
    # signatory may have declined earlier without closing it.
    by = next(
        (s for s in signatories if s.required and s.status == SignatoryStatus.DECLINED),
        None,
    )
    if by is None:
        return 0
    return sum(
        1 for s in signatories if s.pk != by.pk and emails.send_declined(record, s, by)
    )


def finalize(record_id: int) -> bool:
    """File the completed record's PDF and send everyone their copy.

    The PDF is built once here and its hash stored. Storage is best-effort:
    the record is complete either way, the PDF can always be rebuilt from the
    frozen snapshot, and a missing bucket must not stop the parties getting
    their copies.
    """
    record = _fresh(record_id)
    if record is None or record.status != RecordStatus.COMPLETED:
        return False

    data = build_record_pdf(view_of(record))
    record.pdf_hash = hashlib.sha256(data).hexdigest()
    fields = ["pdf_hash", "updated_at"]
    try:
        from files.services import gcs_service

        path = pdf_path(record)
        gcs_service.upload_file(io.BytesIO(data), path, content_type="application/pdf")
        record.pdf_gcs_path = path
        fields.append("pdf_gcs_path")
    except Exception as exc:  # noqa: BLE001 - storage being down is not fatal
        logger.warning(
            "record_pdf_not_stored record=%s error=%s",
            record.record_number,
            type(exc).__name__,
        )
    record.save(update_fields=fields)

    for signatory in record.signatories.all():
        emails.send_completed(record, signatory, data)
    return True


def after_action(record: MeetingRecord, action: str) -> None:
    """Run the follow-ups for one signing action.

    Called once the action's own transaction has committed, and in the same
    request rather than through the task queue: a signing link or code would
    otherwise have to travel through the broker in the clear, and there are
    only a handful of emails to send. Nothing here may undo or fail the
    signature, so every failure is logged and swallowed.
    """
    try:
        if record.status == RecordStatus.COMPLETED and getattr(
            record, "just_completed", False
        ):
            finalize(record.pk)
        elif record.status == RecordStatus.DECLINED:
            notify_declined(record.pk)
        elif action == signing.SIGN_WITH_REMARKS:
            notify_remarks(record.pk)
    except Exception:  # noqa: BLE001 - see docstring
        logger.exception("record_follow_up_failed record=%s", record.record_number)


@shared_task(name="onboarding.records.expire")
def expire_records() -> int:
    """Daily: close records whose signing window has passed."""
    return len(signing.expire_due())
