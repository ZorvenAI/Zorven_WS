"""State changes of a meeting record, and the audit entry for each.

Every transition locks the record row, checks it is allowed from the current
state, and writes a ``RecordEvent`` in the same transaction — so the audit
trail cannot fall out of step with the state it describes.
"""

from __future__ import annotations

from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.onboarding.models import MeetingRecording
from apps.onboarding.records import readiness
from apps.onboarding.records.clauses import CLAUSE_VERSION
from apps.onboarding.records.models import (
    FROZEN_RECORD_STATUSES,
    SUPERSEDABLE_RECORD_STATUSES,
    TERMINAL_RECORD_STATUSES,
    MeetingRecord,
    RecordEvent,
    RecordEventType,
    RecordStatus,
)
from apps.onboarding.records.snapshot import build_snapshot, content_hash


class RecordError(Exception):
    """A transition that is not allowed. ``code`` is stable for callers."""

    def __init__(self, code: str, message: str, **extra: Any) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.extra = extra


def record_number(recording_id: int, version: int) -> str:
    return f"MR-{recording_id:06d}-v{version}"


def recording_is_frozen(recording: MeetingRecording) -> bool:
    """Whether this recording's description and transcript may no longer change.

    True once any record made from it has been issued — including one later
    voided or declined. Those records still exist and still say what they
    said; the text they were made from must keep matching them.
    """
    return MeetingRecord.objects.filter(
        recording=recording, status__in=FROZEN_RECORD_STATUSES
    ).exists()


def log_event(
    record: MeetingRecord,
    event_type: str,
    *,
    user=None,
    ip_address: str | None = None,
    **detail: Any,
) -> RecordEvent:
    return RecordEvent.objects.create(
        tenant=record.tenant,
        record=record,
        actor_user=user if getattr(user, "pk", None) else None,
        event_type=event_type,
        detail=detail,
        ip_address=ip_address,
    )


def _locked(record: MeetingRecord) -> MeetingRecord:
    return (
        MeetingRecord.objects.select_for_update(of=("self",))
        .select_related("recording", "session", "session__company", "tenant")
        .get(pk=record.pk)
    )


def has_content(recording: MeetingRecording) -> bool:
    return bool(recording.description or recording.transcript_clean)


@transaction.atomic
def create_draft(
    recording: MeetingRecording, *, user=None, ip_address: str | None = None
) -> MeetingRecord:
    """Open a DRAFT record for a meeting that has none in play."""
    # Serialise on the recording: two operators preparing the same meeting at
    # once must not both get past the "is there one already" check.
    recording = (
        MeetingRecording.objects.select_for_update(of=("self",))
        .select_related("session")
        .get(pk=recording.pk)
    )
    if not has_content(recording):
        raise RecordError(
            "no_content",
            "This meeting has no description or transcript to record yet.",
        )

    existing = MeetingRecord.objects.filter(recording=recording)
    open_record = existing.exclude(status__in=TERMINAL_RECORD_STATUSES).first()
    if open_record is not None:
        raise RecordError(
            "record_exists",
            f"{open_record.record_number} is already {open_record.status}.",
            record_id=open_record.pk,
        )
    if existing.filter(status=RecordStatus.COMPLETED).exists():
        raise RecordError(
            "record_completed",
            "This meeting already has a completed record. It stands as signed.",
        )
    if existing.exists():
        raise RecordError(
            "supersede_required",
            "This meeting has an earlier record. Supersede it to make a new "
            "version.",
            record_id=existing.order_by("-version").first().pk,
        )

    record = MeetingRecord.objects.create(
        tenant=recording.tenant,
        session=recording.session,
        recording=recording,
        record_number=record_number(recording.pk, 1),
        version=1,
        created_by=user if getattr(user, "pk", None) else None,
    )
    log_event(record, RecordEventType.CREATED, user=user, ip_address=ip_address)
    return record


@transaction.atomic
def issue(
    record: MeetingRecord,
    *,
    user=None,
    ip_address: str | None = None,
    acknowledge_incomplete: bool = False,
) -> MeetingRecord:
    """Freeze the record's content and fingerprint it. There is no undo."""
    # Recording first, the same order as create_draft. A summary callback
    # locks the recording before writing its texts, so holding that lock
    # while the snapshot is read means the frozen content is the recording's
    # final content: a callback either lands before, and is frozen in, or
    # waits and then sees the record issued.
    MeetingRecording.objects.select_for_update(of=("self",)).get(pk=record.recording_id)
    record = _locked(record)
    if record.status != RecordStatus.DRAFT:
        raise RecordError(
            "not_draft", f"{record.record_number} is {record.status}, not a draft."
        )

    snapshot = build_snapshot(record)
    items = readiness.check_readiness(
        record, snapshot, acknowledge_incomplete=acknowledge_incomplete
    )
    failures = readiness.blocking_failures(items)
    if failures:
        raise RecordError(
            "not_ready",
            "This record is not ready to issue.",
            readiness=[item.as_dict() for item in items],
        )

    now = timezone.now()
    record.snapshot = snapshot
    record.content_hash = content_hash(snapshot)
    record.clause_version = CLAUSE_VERSION
    record.status = RecordStatus.ISSUED
    record.issued_at = now
    record.issued_by = user if getattr(user, "pk", None) else None
    record.save(
        update_fields=[
            "snapshot",
            "content_hash",
            "clause_version",
            "status",
            "issued_at",
            "issued_by",
            "updated_at",
        ]
    )
    log_event(
        record,
        RecordEventType.ISSUED,
        user=user,
        ip_address=ip_address,
        content_hash=record.content_hash,
        clause_version=record.clause_version,
        acknowledged_incomplete=bool(acknowledge_incomplete),
    )
    return record


@transaction.atomic
def void(
    record: MeetingRecord, *, reason: str, user=None, ip_address: str | None = None
) -> MeetingRecord:
    """Withdraw an issued record that has not been completed."""
    record = _locked(record)
    reason = (reason or "").strip()
    if not reason:
        raise RecordError("reason_required", "A reason is required to void a record.")
    if record.status == RecordStatus.DRAFT:
        raise RecordError(
            "is_draft", "A draft has not been issued. Discard it instead."
        )
    if record.status in TERMINAL_RECORD_STATUSES:
        raise RecordError(
            "is_terminal",
            f"{record.record_number} is {record.status} and cannot be voided.",
        )

    record.status = RecordStatus.VOIDED
    record.voided_at = timezone.now()
    record.void_reason = reason
    record.save(update_fields=["status", "voided_at", "void_reason", "updated_at"])
    log_event(
        record, RecordEventType.VOIDED, user=user, ip_address=ip_address, reason=reason
    )
    return record


@transaction.atomic
def supersede(
    record: MeetingRecord, *, user=None, ip_address: str | None = None
) -> MeetingRecord:
    """Open the next version as a DRAFT. The earlier version is kept as it was."""
    record = _locked(record)
    if record.status not in SUPERSEDABLE_RECORD_STATUSES:
        raise RecordError(
            "not_supersedable",
            f"{record.record_number} is {record.status}. Only a voided, "
            "declined or expired record can be superseded.",
        )
    if MeetingRecord.objects.filter(supersedes=record).exists():
        raise RecordError(
            "already_superseded",
            f"{record.record_number} already has a newer version.",
            record_id=MeetingRecord.objects.get(supersedes=record).pk,
        )

    version = record.version + 1
    successor = MeetingRecord.objects.create(
        tenant=record.tenant,
        session=record.session,
        recording=record.recording,
        record_number=record_number(record.recording_id, version),
        version=version,
        supersedes=record,
        created_by=user if getattr(user, "pk", None) else None,
    )
    log_event(
        record,
        RecordEventType.SUPERSEDED,
        user=user,
        ip_address=ip_address,
        superseded_by=successor.record_number,
    )
    log_event(
        successor,
        RecordEventType.CREATED,
        user=user,
        ip_address=ip_address,
        supersedes=record.record_number,
    )
    return successor


@transaction.atomic
def discard_draft(record: MeetingRecord) -> None:
    """Remove a draft that was never issued. Nothing was ever fixed by it."""
    record = _locked(record)
    if record.status != RecordStatus.DRAFT:
        raise RecordError(
            "not_draft",
            f"{record.record_number} is {record.status}. Only a draft can be "
            "discarded.",
        )
    # The audit entries of a draft go with it: they describe a document that
    # never existed outside this system. Removed with a queryset delete, which
    # is the one path the insert-only model does not intercept, and only here.
    RecordEvent.objects.filter(record=record).delete()
    record.delete()
