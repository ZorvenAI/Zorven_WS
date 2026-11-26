"""A record as it is shown: on screen, in the PDF, to a signer.

One place builds these views so the authenticated screen, the public signing
page and the stored PDF cannot disagree about what a record says.
"""

from __future__ import annotations

from typing import Any

from apps.onboarding.records import signing
from apps.onboarding.records.models import (
    MeetingRecord,
    RecordEventType,
    RecordSignatory,
    RecordStatus,
    SignatoryParty,
    SignatoryStatus,
    SigningMethod,
)
from apps.onboarding.records.pdf import AuditEntry, RecordView, SignatureBlock
from apps.onboarding.records.snapshot import build_snapshot

EVENT_LABELS = {
    RecordEventType.CREATED: "Draft prepared",
    RecordEventType.ISSUED: "Issued",
    RecordEventType.VOIDED: "Voided",
    RecordEventType.SUPERSEDED: "Superseded by a newer version",
    RecordEventType.DOWNLOADED: "Downloaded",
    RecordEventType.EMAIL_SENT: "Email sent",
    RecordEventType.EMAIL_FAILED: "Email could not be sent",
    RecordEventType.VIEWED: "Signing link opened",
    RecordEventType.CODE_SENT: "One-time code sent",
    RecordEventType.CODE_VERIFIED: "Identity confirmed by one-time code",
    RecordEventType.CODE_FAILED: "Incorrect one-time code entered",
    RecordEventType.SIGNED: "Signed",
    RecordEventType.REMARKS_ACKNOWLEDGED: "Remarks acknowledged",
    RecordEventType.DECLINED: "Declined",
    RecordEventType.COMPLETED: "Completed — all required signatures collected",
    RecordEventType.EXPIRED: "Expired unsigned",
    RecordEventType.REMINDED: "Reminder sent",
}

#: Kept in the database, left out of the printed certificate. A download
#: printed inside the copy being downloaded would make no two copies match,
#: and the others are delivery noise rather than evidence about the record.
NOT_PRINTED = frozenset(
    {
        RecordEventType.DOWNLOADED,
        RecordEventType.EMAIL_SENT,
        RecordEventType.CODE_SENT,
        RecordEventType.REMINDED,
    }
)

_METHODS = {
    SigningMethod.EMAIL_CODE: "Emailed link and one-time code",
    SigningMethod.ACCOUNT: "Signed in to the workspace",
}


def actor_name(user) -> str:
    if user is None:
        return ""
    return (user.get_full_name() or user.get_username() or "").strip()


def snapshot_of(record: MeetingRecord) -> dict[str, Any]:
    """Frozen content once issued; a live view of the recording before."""
    if record.status != RecordStatus.DRAFT and record.snapshot:
        return record.snapshot
    return build_snapshot(record)


def party_name(snapshot: dict[str, Any], party: str) -> str:
    parties = snapshot["parties"]
    if party == SignatoryParty.AGENCY:
        return parties["agency"]["name"] or "the agency"
    client = parties["client"]
    return client.get("legal_name") or client.get("name") or "the client"


def signature_blocks(
    record: MeetingRecord, snapshot: dict[str, Any]
) -> tuple[SignatureBlock, ...]:
    return tuple(
        SignatureBlock(
            party=party_name(snapshot, s.party),
            name=s.name,
            title=s.title,
            email=s.email,
            signed_at=s.signed_at.isoformat() if s.signed_at else "",
            typed_name=s.typed_name,
            method=_METHODS.get(s.method, ""),
            ip_address=s.ip_address or "",
            remarks=s.remarks,
            declined_at=s.declined_at.isoformat() if s.declined_at else "",
            decline_reason=s.decline_reason,
            acknowledged_at=(
                s.remarks_acknowledged_at.isoformat()
                if s.remarks_acknowledged_at
                else ""
            ),
            required=s.required,
            declined=s.status == SignatoryStatus.DECLINED,
        )
        for s in record.signatories.all()
    )


def events_of(record: MeetingRecord) -> list[dict[str, Any]]:
    return [
        {
            "event_type": event.event_type,
            "label": EVENT_LABELS.get(event.event_type, event.event_type),
            "actor": (
                event.signatory.name
                if event.signatory_id
                else actor_name(event.actor_user)
            ),
            "occurred_at": event.occurred_at.isoformat(),
            "detail": event.detail,
        }
        for event in record.events.select_related("actor_user", "signatory")
    ]


def view_of(record: MeetingRecord) -> RecordView:
    snapshot = snapshot_of(record)
    return RecordView(
        snapshot=snapshot,
        status=record.status,
        content_hash=record.content_hash,
        issued_at=record.issued_at.isoformat() if record.issued_at else "",
        signatures=signature_blocks(record, snapshot),
        audit=tuple(
            AuditEntry(
                occurred_at=event["occurred_at"],
                event=event["label"],
                actor=event["actor"],
            )
            for event in events_of(record)
            if event["event_type"] not in NOT_PRINTED
        ),
    )


def signatory_public(s: RecordSignatory, snapshot: dict[str, Any]) -> dict[str, Any]:
    """A signatory as other people may see them: no evidence, no secrets."""
    return {
        "id": s.pk,
        "party": s.party,
        "party_name": party_name(snapshot, s.party),
        "name": s.name,
        "title": s.title,
        "required": s.required,
        "status": s.status,
        "signed_at": s.signed_at,
        "declined_at": s.declined_at,
        "remarks": s.remarks,
        "decline_reason": s.decline_reason,
    }


def signatory_private(s: RecordSignatory, snapshot: dict[str, Any]) -> dict[str, Any]:
    """A signatory as the agency sees them, with contact and evidence."""
    return {
        **signatory_public(s, snapshot),
        "email": s.email,
        "method": s.method,
        "typed_name": s.typed_name,
        "ip_address": s.ip_address,
        "link_expires_at": s.token_expires_at,
        "remarks_acknowledged_at": s.remarks_acknowledged_at,
    }


def acknowledgements_owed(record: MeetingRecord) -> dict[int, list[str]]:
    """Signatory id → names of those whose remarks they must still accept."""
    return {
        pk: [r.name for r in remarks]
        for pk, remarks in signing.pending_acknowledgements(record).items()
    }
