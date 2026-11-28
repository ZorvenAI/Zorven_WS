"""Emails for meeting records.

Plain text, sent through Django's configured backend. A failed send never
fails the action that triggered it — an issued record is issued whether or
not a mail server was reachable — but it is written to the audit trail, so
the operator can see that a signatory was not reached and send a reminder.

Signing links and codes appear only in the email body. They are never logged
and never stored: the database holds their hashes.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import EmailMessage

from apps.onboarding.records.lifecycle import log_event
from apps.onboarding.records.models import (
    MeetingRecord,
    RecordEventType,
    RecordSignatory,
)
from apps.onboarding.records.pdf import format_time
from apps.onboarding.records.signing import CODE_TTL

logger = logging.getLogger(__name__)


def signing_url(token: str) -> str:
    base = getattr(settings, "FRONTEND_URL", "http://localhost:3000").rstrip("/")
    return f"{base}/sign/{token}"


def _parties(record: MeetingRecord) -> tuple[str, str]:
    parties = (record.snapshot or {}).get("parties", {})
    client = parties.get("client", {})
    return (
        parties.get("agency", {}).get("name") or "the agency",
        client.get("legal_name") or client.get("name") or "the client",
    )


def _meeting(record: MeetingRecord) -> str:
    started = (record.snapshot or {}).get("meeting", {}).get("started_at")
    return format_time(started)


def _send(
    record: MeetingRecord,
    signatory: RecordSignatory,
    kind: str,
    subject: str,
    body: str,
    attachment: tuple[str, bytes] | None = None,
) -> bool:
    message = EmailMessage(
        subject=subject,
        body=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[signatory.email],
    )
    if attachment:
        message.attach(attachment[0], attachment[1], "application/pdf")
    try:
        message.send(fail_silently=False)
    except Exception as exc:  # noqa: BLE001 - any transport failure is the same
        logger.warning(
            "record_email_failed record=%s kind=%s error=%s",
            record.record_number,
            kind,
            type(exc).__name__,
        )
        log_event(
            record,
            RecordEventType.EMAIL_FAILED,
            signatory=signatory,
            kind=kind,
            error=type(exc).__name__,
        )
        return False
    log_event(record, RecordEventType.EMAIL_SENT, signatory=signatory, kind=kind)
    return True


def send_signing_request(
    record: MeetingRecord, signatory: RecordSignatory, token: str, reminder=False
) -> bool:
    agency, client = _parties(record)
    lead = "A reminder: a" if reminder else "A"
    expires = format_time(record.expires_at.isoformat() if record.expires_at else None)
    body = (
        f"Hello {signatory.name},\n\n"
        f"{lead} record of the meeting between {agency} and {client} on "
        f"{_meeting(record)} is ready for your signature.\n\n"
        f"Read and sign it here:\n{signing_url(token)}\n\n"
        "The link is personal to you; please do not forward it. When you open "
        "it we will email you a one-time code to confirm it is you.\n\n"
        f"The link expires on {expires}.\n\n"
        f"Record number: {record.record_number}\n"
    )
    subject = f"{'Reminder: ' if reminder else ''}Meeting record to sign — {agency}"
    return _send(
        record, signatory, "reminder" if reminder else "signing_request", subject, body
    )


def send_code(record: MeetingRecord, signatory: RecordSignatory, code: str) -> bool:
    minutes = int(CODE_TTL.total_seconds() // 60)
    body = (
        f"Your code to open meeting record {record.record_number} is:\n\n"
        f"    {code}\n\n"
        f"It is valid for {minutes} minutes. If you did not ask for it, you "
        "can ignore this email.\n"
    )
    # The code is not in the subject: subjects show in notifications and
    # lock screens, and are the part of an email most often logged in transit.
    return _send(
        record, signatory, "code", f"Your code for {record.record_number}", body
    )


def send_completed(
    record: MeetingRecord, signatory: RecordSignatory, pdf: bytes
) -> bool:
    agency, client = _parties(record)
    body = (
        f"Hello {signatory.name},\n\n"
        f"The record of the meeting between {agency} and {client} on "
        f"{_meeting(record)} has been signed by everyone required. Your copy "
        "is attached.\n\n"
        f"Record number: {record.record_number}\n"
        f"Content fingerprint: {record.content_hash}\n"
    )
    return _send(
        record,
        signatory,
        "completed",
        f"Signed meeting record {record.record_number}",
        body,
        attachment=(f"{record.record_number}.pdf", pdf),
    )


def send_declined(
    record: MeetingRecord, signatory: RecordSignatory, by: RecordSignatory
) -> bool:
    body = (
        f"Hello {signatory.name},\n\n"
        f"{by.name} declined to sign meeting record {record.record_number}.\n\n"
        f"Reason given:\n{by.decline_reason}\n\n"
        "The record is closed and can no longer be signed. A corrected "
        "version can be prepared from it.\n"
    )
    return _send(
        record,
        signatory,
        "declined",
        f"Meeting record {record.record_number} was declined",
        body,
    )


def send_remarks_notice(
    record: MeetingRecord, signatory: RecordSignatory, by: RecordSignatory, token: str
) -> bool:
    body = (
        f"Hello {signatory.name},\n\n"
        f"{by.name} signed meeting record {record.record_number} with remarks, "
        "after you had signed:\n\n"
        f"{by.remarks}\n\n"
        "The record is not complete until you acknowledge them:\n"
        f"{signing_url(token)}\n"
    )
    return _send(
        record,
        signatory,
        "remarks",
        f"Remarks on meeting record {record.record_number}",
        body,
    )
