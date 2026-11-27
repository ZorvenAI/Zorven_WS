"""The content of a meeting record, and its fingerprint.

``build_snapshot`` gathers everything a record says into one plain dict. For a
DRAFT it is built fresh on every read, so the preview follows the recording.
At issue it is built once more, stored, and never built again.

``content_hash`` fingerprints a snapshot. The serialisation is canonical —
sorted keys, fixed separators, UTF-8 — so the same content always gives the
same hash regardless of how the dict was assembled, and any change to any
character gives a different one. Signatures bind to this hash rather than to
a PDF's bytes, so a later signature never invalidates an earlier one.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from apps.onboarding.contract_fields import required_to_issue
from apps.onboarding.models import ConsentRecord, MeetingAttendee
from apps.onboarding.records.agreements import split_agreements
from apps.onboarding.records.clauses import CLAUSE_VERSION, clause_text
from apps.onboarding.transcript_assembler import _completeness

SNAPSHOT_SCHEMA = 1

#: Client party details copied into a record: what a record cannot be issued
#: without, plus the registration number when one was given.
CLIENT_DETAIL_FIELDS = (*required_to_issue(), "registration_number")


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def transcript_lines(transcript_clean: Any) -> list[str]:
    """The clean transcript as the lines that will be numbered.

    PROCESS mode stores a string; LIVE mode stores segments. Blank lines carry
    nothing and are dropped so that line numbers count statements.
    """
    if isinstance(transcript_clean, str):
        return [line.rstrip() for line in transcript_clean.splitlines() if line.strip()]
    lines: list[str] = []
    if isinstance(transcript_clean, list):
        for segment in transcript_clean:
            if isinstance(segment, dict):
                text = str(segment.get("text") or "").strip()
                if not text:
                    continue
                speaker = segment.get("speaker_name") or segment.get("speaker")
                if speaker is None or speaker == "":
                    lines.append(text)
                elif isinstance(speaker, int):
                    lines.append(f"Speaker {speaker}: {text}")
                else:
                    lines.append(f"{speaker}: {text}")
            elif isinstance(segment, str) and segment.strip():
                lines.append(segment.strip())
    return lines


def build_snapshot(record) -> dict[str, Any]:
    """Everything this record says, as plain JSON-safe data."""
    recording = record.recording
    session = record.session
    company = session.company
    tenant = record.tenant

    attendees = MeetingAttendee.objects.filter(
        session=session, recording=recording
    ).order_by("stream_index")
    if not attendees.exists():
        # Roll call happens before a recording exists, so an attendee row may
        # not have been linked to it. The session's roll call is then the best
        # statement of who was there.
        attendees = MeetingAttendee.objects.filter(
            session=session, recording__isnull=True
        ).order_by("stream_index")

    # A revoked consent is not consent on file: the record must not present
    # a withdrawn agreement to be recorded as a standing one.
    consent = (
        ConsentRecord.objects.filter(session=session, revoked_at__isnull=True)
        .order_by("-granted_at")
        .first()
    )

    split = split_agreements(recording.description or "")

    return {
        "schema": SNAPSHOT_SCHEMA,
        "record": {
            "number": record.record_number,
            "version": record.version,
            "supersedes": (
                record.supersedes.record_number if record.supersedes_id else None
            ),
        },
        "clause": {
            "version": CLAUSE_VERSION,
            "text": clause_text(CLAUSE_VERSION),
        },
        "parties": {
            "agency": {"name": getattr(tenant, "name", "") or ""},
            "client": {
                "name": getattr(company, "name", "") or "",
                **{
                    name: (getattr(company, name, None) or "")
                    for name in CLIENT_DETAIL_FIELDS
                },
            },
        },
        "meeting": {
            "session_id": session.pk,
            "recording_id": recording.pk,
            "started_at": _iso(recording.started_at),
            "stopped_at": _iso(recording.stopped_at),
            "duration_s": recording.duration_s,
            "modality": recording.modality,
        },
        "attendees": [{"name": a.name, "role": a.role} for a in attendees],
        "consent": (
            {
                "subject_name": consent.subject_name,
                "method": consent.method,
                "granted_at": _iso(consent.granted_at),
                "revoked_at": _iso(consent.revoked_at),
            }
            if consent
            else None
        ),
        # Who is to sign is part of what is frozen: bound into the
        # fingerprint, the list cannot change after issue without showing.
        "signatories": [
            {
                "party": s.party,
                "name": s.name,
                "title": s.title,
                "email": s.email,
                "required": s.required,
            }
            for s in record.signatories.all()
        ],
        "completeness": _completeness(recording),
        "agreements": {
            "preamble": split.preamble,
            "items": [{"number": a.number, "text": a.text} for a in split.agreements],
        },
        "description": split.remainder.strip(),
        "transcript": transcript_lines(recording.transcript_clean),
    }


def canonical_json(snapshot: dict[str, Any]) -> bytes:
    """The one byte sequence a snapshot serialises to."""
    return json.dumps(
        snapshot,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def content_hash(snapshot: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(snapshot)).hexdigest()


def all_text(snapshot: dict[str, Any]) -> str:
    """Every piece of text a snapshot would print, for character checks."""
    parts: list[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(snapshot)
    return "\n".join(parts)
