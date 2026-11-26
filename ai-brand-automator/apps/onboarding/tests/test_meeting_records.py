"""Signed meeting records · step 2 — the record, its lifecycle and its freeze.

Against the real database and the real endpoints. What is being protected:

- issuing copies the content and fingerprints it, and nothing can change
  either afterwards — not the company's details, not the agent's callbacks;
- a record is only issued when it is fit to be, and says why when it is not;
- the audit trail cannot be rewritten;
- one tenant cannot see or act on another's records.
"""

from __future__ import annotations

import io

import pytest
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from pypdf import PdfReader
from rest_framework.test import APIClient

from apps.onboarding.models import MeetingAttendee, ProvenanceStatus, RecordingStatus
from apps.onboarding.records import lifecycle
from apps.onboarding.records.models import (
    MeetingRecord,
    RecordEvent,
    RecordEventError,
    RecordEventType,
    RecordStatus,
)
from apps.onboarding.records.snapshot import content_hash
from apps.onboarding.tests.factories import (
    make_consent,
    make_provenance,
    make_recording,
    make_session,
)
from onboarding.models import Company
from tenants.models import Membership, Tenant

pytestmark = pytest.mark.django_db

BASE = "/api/v1/onboarding"

DESCRIPTION = (
    "## Agreements\n"
    "- Launch budget split evenly; proposed by the operator, accepted by the "
    "participant (~12:30).\n"
    "- Contract review before launch; proposed by the participant, accepted by "
    "the operator (~21:05).\n"
    "\n"
    "## Business Identity\n"
    "Pomodoro is a family restaurant.\n"
)
TRANSCRIPT = (
    "Naveen: Shall we split the launch budget evenly?\nMaria Rossi: Yes, agreed."
)
RAW = [{"speaker": 0, "text": "raw", "t_start": 0.0, "t_end": 1.0}]

PARTY = {
    "legal_name": "Pomodoro Trattoria LLC",
    "registered_address": "14 Main Street, Austin",
    "signatory_name": "Maria Rossi",
    "signatory_title": "Owner",
    "signatory_email": "maria@example.com",
}


@pytest.fixture
def api_client():
    client = APIClient()
    client.defaults["SERVER_NAME"] = "localhost"
    return client


@pytest.fixture
def tenant():
    return Tenant.objects.create(name="Zorven Agency", schema_name="records_a")


def member(tenant, role, username) -> User:
    user = User.objects.create_user(username, f"{username}@test.com", "TestPass123!")
    Membership.objects.create(user=user, tenant=tenant, role=role)
    return user


@pytest.fixture
def editor(api_client, tenant):
    user = member(tenant, Membership.Role.EDITOR, "rec_editor")
    api_client.force_authenticate(user=user)
    return user


@pytest.fixture
def company(tenant):
    return Company.objects.create(tenant=tenant, name="Pomodoro", **PARTY)


@pytest.fixture
def session(company):
    return make_session(company=company)


def a_recording(session, **overrides):
    values = {
        "status": RecordingStatus.SUMMARIZED,
        "description": DESCRIPTION,
        "transcript_clean": TRANSCRIPT,
        "transcript": RAW,
        "transcript_complete": True,
        "transcript_missing_s": 0,
        "duration_s": 1810,
    }
    values.update(overrides)
    return make_recording(session=session, **values)


@pytest.fixture
def recording(session):
    return a_recording(session)


def prepare(api_client, recording):
    return api_client.post(f"{BASE}/recordings/{recording.pk}/records/", format="json")


def issue(api_client, record_id, **body):
    return api_client.post(f"{BASE}/records/{record_id}/issue/", body, format="json")


def service_client(tenant, settings) -> APIClient:
    settings.OIA_SERVICE_TOKEN = "test-svc-token"
    client = APIClient()
    client.defaults["SERVER_NAME"] = "localhost"
    client.credentials(
        HTTP_X_SERVICE_TOKEN="test-svc-token", HTTP_X_TENANT_ID=str(tenant.id)
    )
    return client


@pytest.fixture
def draft(api_client, editor, recording):
    response = prepare(api_client, recording)
    assert response.status_code == 201, response.content
    return response.json()


@pytest.fixture
def issued(api_client, draft):
    response = issue(api_client, draft["id"])
    assert response.status_code == 200, response.content
    return response.json()


@pytest.fixture
def voided(api_client, issued):
    response = api_client.post(
        f"{BASE}/records/{issued['id']}/void/", {"reason": "Typo."}, format="json"
    )
    assert response.status_code == 200, response.content
    return response.json()


def readiness_of(body) -> dict[str, dict]:
    return {item["code"]: item for item in body["readiness"]}


# ── Preparing a draft ────────────────────────────────────────────────


def test_preparing_a_meeting_opens_a_numbered_draft(api_client, editor, recording):
    response = prepare(api_client, recording)

    assert response.status_code == 201, response.content
    body = response.json()
    assert body["status"] == RecordStatus.DRAFT
    assert body["record_number"] == f"MR-{recording.pk:06d}-v1"
    assert body["version"] == 1
    assert body["content_hash"] == ""
    assert [e["event_type"] for e in body["events"]] == [RecordEventType.CREATED]
    assert body["events"][0]["actor"] == "rec_editor"


def test_a_draft_shows_the_meetings_content(draft, recording):
    document = draft["document"]

    assert document["parties"]["agency"]["name"] == "Zorven Agency"
    assert document["parties"]["client"]["legal_name"] == "Pomodoro Trattoria LLC"
    assert document["parties"]["client"]["signatory_email"] == "maria@example.com"
    assert [a["number"] for a in document["agreements"]["items"]] == ["A-1", "A-2"]
    assert document["agreements"]["items"][0]["text"].startswith(
        "Launch budget split evenly;"
    )
    assert document["description"] == (
        "## Business Identity\nPomodoro is a family restaurant."
    )
    assert document["transcript"] == [
        "Naveen: Shall we split the launch budget evenly?",
        "Maria Rossi: Yes, agreed.",
    ]
    assert document["meeting"]["recording_id"] == recording.pk
    assert document["meeting"]["duration_s"] == 1810


def test_a_draft_follows_the_recording_until_it_is_issued(api_client, draft, recording):
    recording.description = "## Agreements\n- Launch moved to April.\n"
    recording.save(update_fields=["description"])

    body = api_client.get(f"{BASE}/records/{draft['id']}/").json()

    assert [a["text"] for a in body["document"]["agreements"]["items"]] == [
        "Launch moved to April."
    ]


def test_a_meeting_with_nothing_to_record_cannot_be_prepared(
    api_client, editor, session
):
    empty = a_recording(session, description="", transcript_clean=[])

    response = prepare(api_client, empty)

    assert response.status_code == 400, response.content
    assert response.json()["error"] == "no_content"
    assert MeetingRecord.objects.count() == 0


def test_a_meeting_has_one_record_in_play_at_a_time(api_client, draft, recording):
    response = prepare(api_client, recording)

    assert response.status_code == 409, response.content
    assert response.json()["error"] == "record_exists"
    assert response.json()["record_id"] == draft["id"]
    assert MeetingRecord.objects.filter(recording=recording).count() == 1


def test_the_database_refuses_a_second_open_record(draft, recording, session, tenant):
    """The API check is not the only thing standing between two operators
    and two different records of one meeting."""
    with pytest.raises(IntegrityError), transaction.atomic():
        MeetingRecord.objects.create(
            tenant=tenant,
            session=session,
            recording=recording,
            record_number="MR-DUPLICATE",
            version=2,
        )


def test_attendance_and_consent_are_carried_onto_the_record(
    api_client, editor, session, recording
):
    for index, (name, role) in enumerate(
        [("Naveen", "operator"), ("Maria Rossi", "participant")]
    ):
        MeetingAttendee.objects.create(
            tenant=session.tenant,
            session=session,
            recording=recording,
            name=name,
            role=role,
            stream_index=index,
        )
    make_consent(session=session, subject_name="Maria Rossi")

    document = prepare(api_client, recording).json()["document"]

    assert document["attendees"] == [
        {"name": "Naveen", "role": "operator"},
        {"name": "Maria Rossi", "role": "participant"},
    ]
    assert document["consent"]["subject_name"] == "Maria Rossi"
    assert document["consent"]["method"] == "VERBAL_RECORDED"


# ── Readiness ────────────────────────────────────────────────────────


def test_a_complete_draft_is_ready(draft):
    checks = readiness_of(draft)

    assert [
        c for c, item in checks.items() if item["blocking"] and not item["ok"]
    ] == []
    assert checks["agreements"]["message"] == "2 agreement(s) recorded."


def test_missing_party_details_are_named_and_block_issue(
    api_client, editor, recording, company
):
    Company.objects.filter(pk=company.pk).update(
        signatory_email=None, registered_address=""
    )
    draft = prepare(api_client, recording).json()

    item = readiness_of(draft)["party_details"]
    assert item["ok"] is False
    assert item["fields"] == ["registered_address", "signatory_email"]
    assert item["message"] == (
        "Missing client contract details: registered address, signatory email."
    )

    response = issue(api_client, draft["id"])
    assert response.status_code == 409, response.content
    assert response.json()["error"] == "not_ready"
    assert readiness_of(response.json())["party_details"]["ok"] is False
    assert MeetingRecord.objects.get(pk=draft["id"]).status == RecordStatus.DRAFT


@pytest.mark.parametrize(
    "status", [ProvenanceStatus.PENDING, ProvenanceStatus.CONFLICT]
)
def test_an_unconfirmed_detail_blocks_issue(
    api_client, editor, session, recording, status
):
    """What the agent heard is a guess until someone confirms it, and a guess
    about a legal name does not belong on a record people sign."""
    make_provenance(session=session, field_name="legal_name", status=status)
    draft = prepare(api_client, recording).json()

    item = readiness_of(draft)["unreviewed_details"]
    assert item["ok"] is False
    assert item["fields"] == ["legal_name"]
    assert issue(api_client, draft["id"]).status_code == 409


def test_a_confirmed_detail_does_not_block_issue(
    api_client, editor, session, recording
):
    make_provenance(
        session=session, field_name="legal_name", status=ProvenanceStatus.CONFIRMED
    )
    draft = prepare(api_client, recording).json()

    assert readiness_of(draft)["unreviewed_details"]["ok"] is True
    assert issue(api_client, draft["id"]).status_code == 200


@pytest.mark.parametrize(
    "complete, missing", [(False, 267), (None, None)], ids=["partial", "unknown"]
)
def test_an_incomplete_transcript_must_be_acknowledged(
    api_client, editor, session, complete, missing
):
    recording = a_recording(
        session, transcript_complete=complete, transcript_missing_s=missing
    )
    draft = prepare(api_client, recording).json()
    assert readiness_of(draft)["completeness"]["ok"] is False

    refused = issue(api_client, draft["id"])
    assert refused.status_code == 409, refused.content
    assert readiness_of(refused.json())["completeness"]["ok"] is False

    accepted = issue(api_client, draft["id"], acknowledge_incomplete=True)
    assert accepted.status_code == 200, accepted.content
    assert accepted.json()["status"] == RecordStatus.ISSUED
    issued_event = next(
        e
        for e in accepted.json()["events"]
        if e["event_type"] == RecordEventType.ISSUED
    )
    assert issued_event["detail"]["acknowledged_incomplete"] is True


def test_acknowledgement_must_be_an_explicit_true(api_client, editor, session):
    """A truthy string from a careless client is not a person acknowledging
    that the transcript has a gap."""
    recording = a_recording(session, transcript_complete=False, transcript_missing_s=5)
    draft = prepare(api_client, recording).json()

    response = issue(api_client, draft["id"], acknowledge_incomplete="yes")

    assert response.status_code == 409, response.content
    assert MeetingRecord.objects.get(pk=draft["id"]).status == RecordStatus.DRAFT


def test_text_the_pdf_cannot_reproduce_blocks_issue(api_client, editor, session):
    recording = a_recording(session, transcript_clean="Maria Rossi: ಕನ್ನಡ ಒಪ್ಪಿಗೆ")
    draft = prepare(api_client, recording).json()

    item = readiness_of(draft)["unsupported_characters"]
    assert item["ok"] is False
    assert "ಕ" in item["message"]
    assert issue(api_client, draft["id"]).status_code == 409


def test_no_agreements_and_no_consent_are_warnings_not_blockers(
    api_client, editor, session
):
    recording = a_recording(session, description="## Business Identity\nPomodoro.\n")
    draft = prepare(api_client, recording).json()
    checks = readiness_of(draft)

    assert checks["agreements"] == {
        "code": "agreements",
        "ok": False,
        "blocking": False,
        "fields": [],
        "message": (
            "No agreements were found in this meeting's description. The record "
            "will state that none were recorded."
        ),
    }
    assert checks["consent"]["ok"] is False
    assert checks["consent"]["blocking"] is False
    assert issue(api_client, draft["id"]).status_code == 200


# ── Issuing ──────────────────────────────────────────────────────────


def test_issuing_freezes_and_fingerprints_the_content(issued, editor):
    record = MeetingRecord.objects.get(pk=issued["id"])

    assert record.status == RecordStatus.ISSUED
    assert record.snapshot == issued["document"]
    assert record.content_hash == content_hash(record.snapshot)
    assert issued["content_hash"] == record.content_hash
    assert len(record.content_hash) == 64
    assert record.clause_version == "2026-11-draft-1"
    assert record.issued_by == editor
    assert record.issued_at is not None
    assert issued["readiness"] == []


def test_issuing_is_recorded_in_the_audit_trail_with_the_fingerprint(issued):
    """Issuing is followed by the signing requests it sends, one per person."""
    types = [e["event_type"] for e in issued["events"]]
    assert types[:2] == [RecordEventType.CREATED, RecordEventType.ISSUED]
    assert set(types[2:]) <= {
        RecordEventType.EMAIL_SENT,
        RecordEventType.EMAIL_FAILED,
    }
    issued_event = issued["events"][1]
    assert issued_event["detail"]["content_hash"] == issued["content_hash"]
    assert issued_event["actor"] == "rec_editor"


def test_a_record_cannot_be_issued_twice(api_client, issued):
    response = issue(api_client, issued["id"])

    assert response.status_code == 409, response.content
    assert response.json()["error"] == "not_draft"
    record = MeetingRecord.objects.get(pk=issued["id"])
    assert record.content_hash == issued["content_hash"]


# ── Nothing changes an issued record ─────────────────────────────────


def test_changing_the_companys_details_does_not_change_an_issued_record(
    api_client, issued, company
):
    Company.objects.filter(pk=company.pk).update(
        legal_name="Renamed Holdings Inc", signatory_name="Someone Else"
    )

    body = api_client.get(f"{BASE}/records/{issued['id']}/").json()

    assert body["document"] == issued["document"]
    assert body["document"]["parties"]["client"]["legal_name"] == (
        "Pomodoro Trattoria LLC"
    )
    assert body["content_hash"] == issued["content_hash"]


def test_the_agents_summary_callback_cannot_rewrite_an_issued_recording(
    issued, recording, tenant, settings
):
    """The endpoint that used to overwrite description and transcript without
    condition. After issue the words stay; only the summary still moves."""
    response = service_client(tenant, settings).patch(
        f"{BASE}/internal/recordings/{recording.pk}/summary/",
        data={
            "summary": {
                "key_findings": ["rewritten"],
                "transcript_coverage": {"complete": False, "missing_s": 99},
            },
            "transcript": [
                {"speaker": 0, "text": "different", "t_start": 0.0, "t_end": 2.0}
            ],
            "transcript_clean": "Naveen: Something else entirely.",
            "description": "## Agreements\n- A different agreement.\n",
        },
        format="json",
    )

    assert response.status_code == 200, response.content
    recording.refresh_from_db()
    assert recording.description == DESCRIPTION
    assert recording.transcript_clean == TRANSCRIPT
    assert recording.transcript == RAW
    assert recording.transcript_complete is True
    assert recording.transcript_missing_s == 0
    assert recording.summary["key_findings"] == ["rewritten"]


def test_the_summary_callback_still_writes_while_the_record_is_a_draft(
    draft, recording, tenant, settings
):
    response = service_client(tenant, settings).patch(
        f"{BASE}/internal/recordings/{recording.pk}/summary/",
        data={"summary": {}, "description": "## Agreements\n- Updated before issue.\n"},
        format="json",
    )

    assert response.status_code == 200, response.content
    recording.refresh_from_db()
    assert recording.description == "## Agreements\n- Updated before issue.\n"


@pytest.mark.parametrize(
    "status, frozen",
    [
        (RecordStatus.DRAFT, False),
        (RecordStatus.ISSUED, True),
        (RecordStatus.PARTIALLY_SIGNED, True),
        (RecordStatus.COMPLETED, True),
        (RecordStatus.DECLINED, True),
        (RecordStatus.VOIDED, True),
        (RecordStatus.EXPIRED, True),
    ],
)
def test_which_records_freeze_their_recording(
    recording, session, tenant, status, frozen
):
    """A voided record still exists and still says what it said, so the text
    it was made from must keep matching it."""
    MeetingRecord.objects.create(
        tenant=tenant,
        session=session,
        recording=recording,
        record_number="MR-TEST",
        status=status,
    )

    assert lifecycle.recording_is_frozen(recording) is frozen


def test_a_recording_with_no_record_is_not_frozen(recording):
    assert lifecycle.recording_is_frozen(recording) is False


def test_a_recording_with_an_issued_record_cannot_be_deleted(
    api_client, issued, recording, tenant
):
    api_client.force_authenticate(user=member(tenant, Membership.Role.ADMIN, "rec_adm"))

    response = api_client.delete(f"{BASE}/recordings/{recording.pk}/")

    assert response.status_code == 409, response.content
    assert response.json()["error"] == "recording_has_issued_record"
    assert MeetingRecord.objects.filter(pk=issued["id"]).exists()


def test_a_recording_with_only_a_draft_can_be_deleted_and_takes_it_along(
    api_client, draft, recording, tenant
):
    api_client.force_authenticate(user=member(tenant, Membership.Role.ADMIN, "rec_adm"))

    response = api_client.delete(f"{BASE}/recordings/{recording.pk}/")

    assert response.status_code == 204, response.content
    assert not MeetingRecord.objects.filter(pk=draft["id"]).exists()


# ── Voiding, superseding, discarding ─────────────────────────────────


def test_voiding_needs_a_reason(api_client, issued):
    response = api_client.post(
        f"{BASE}/records/{issued['id']}/void/", {"reason": "   "}, format="json"
    )

    assert response.status_code == 400, response.content
    assert response.json()["error"] == "reason_required"
    assert MeetingRecord.objects.get(pk=issued["id"]).status == RecordStatus.ISSUED


def test_voiding_withdraws_the_record_and_keeps_its_content(api_client, issued):
    response = api_client.post(
        f"{BASE}/records/{issued['id']}/void/",
        {"reason": "Wrong signatory named."},
        format="json",
    )

    assert response.status_code == 200, response.content
    body = response.json()
    assert body["status"] == RecordStatus.VOIDED
    assert body["void_reason"] == "Wrong signatory named."
    assert body["document"] == issued["document"]
    assert body["content_hash"] == issued["content_hash"]
    assert body["events"][-1]["event_type"] == RecordEventType.VOIDED
    assert body["events"][-1]["detail"] == {"reason": "Wrong signatory named."}


def test_a_draft_cannot_be_voided(api_client, draft):
    response = api_client.post(
        f"{BASE}/records/{draft['id']}/void/", {"reason": "x"}, format="json"
    )

    assert response.status_code == 409, response.content
    assert response.json()["error"] == "is_draft"


@pytest.mark.parametrize(
    "status",
    [
        RecordStatus.COMPLETED,
        RecordStatus.VOIDED,
        RecordStatus.DECLINED,
        RecordStatus.EXPIRED,
    ],
)
def test_a_finished_record_cannot_be_voided(api_client, issued, status):
    """Above all a completed one: a signed record stands."""
    MeetingRecord.objects.filter(pk=issued["id"]).update(status=status)

    response = api_client.post(
        f"{BASE}/records/{issued['id']}/void/", {"reason": "x"}, format="json"
    )

    assert response.status_code == 409, response.content
    assert response.json()["error"] == "is_terminal"
    assert MeetingRecord.objects.get(pk=issued["id"]).status == status


def test_superseding_opens_the_next_version_and_keeps_the_old_one(
    api_client, voided, recording
):
    response = api_client.post(
        f"{BASE}/records/{voided['id']}/supersede/", format="json"
    )

    assert response.status_code == 201, response.content
    successor = response.json()
    assert successor["status"] == RecordStatus.DRAFT
    assert successor["version"] == 2
    assert successor["record_number"] == f"MR-{recording.pk:06d}-v2"
    assert successor["supersedes"] == voided["id"]
    assert successor["document"]["record"]["supersedes"] == voided["record_number"]

    old = MeetingRecord.objects.get(pk=voided["id"])
    assert old.status == RecordStatus.VOIDED
    assert old.snapshot == voided["document"]
    assert old.content_hash == voided["content_hash"]


def test_a_superseding_record_gets_its_own_fingerprint(api_client, voided):
    """The new version names the one it replaces, so its content — and its
    fingerprint — differ even if nothing else did."""
    successor = api_client.post(
        f"{BASE}/records/{voided['id']}/supersede/", format="json"
    ).json()

    reissued = issue(api_client, successor["id"])

    assert reissued.status_code == 200, reissued.content
    assert reissued.json()["content_hash"] != voided["content_hash"]


def test_only_a_withdrawn_record_can_be_superseded(api_client, issued):
    response = api_client.post(
        f"{BASE}/records/{issued['id']}/supersede/", format="json"
    )

    assert response.status_code == 409, response.content
    assert response.json()["error"] == "not_supersedable"


def test_a_completed_record_cannot_be_superseded(api_client, issued):
    MeetingRecord.objects.filter(pk=issued["id"]).update(status=RecordStatus.COMPLETED)

    response = api_client.post(
        f"{BASE}/records/{issued['id']}/supersede/", format="json"
    )

    assert response.status_code == 409, response.content
    assert MeetingRecord.objects.filter(supersedes_id=issued["id"]).count() == 0


def test_a_record_cannot_be_superseded_twice(api_client, voided):
    first = api_client.post(f"{BASE}/records/{voided['id']}/supersede/", format="json")
    second = api_client.post(f"{BASE}/records/{voided['id']}/supersede/", format="json")

    assert first.status_code == 201
    assert second.status_code == 409, second.content
    assert second.json()["error"] == "already_superseded"
    assert second.json()["record_id"] == first.json()["id"]


def test_after_a_void_a_fresh_prepare_points_at_supersede(
    api_client, voided, recording
):
    """Preparing from scratch would start again at version 1 and lose the
    link to the record it replaces."""
    response = prepare(api_client, recording)

    assert response.status_code == 409, response.content
    assert response.json()["error"] == "supersede_required"
    assert response.json()["record_id"] == voided["id"]


def test_a_draft_can_be_discarded(api_client, draft):
    response = api_client.post(f"{BASE}/records/{draft['id']}/discard/", format="json")

    assert response.status_code == 204, response.content
    assert not MeetingRecord.objects.filter(pk=draft["id"]).exists()
    assert RecordEvent.objects.filter(record_id=draft["id"]).count() == 0


def test_an_issued_record_cannot_be_discarded(api_client, issued):
    response = api_client.post(f"{BASE}/records/{issued['id']}/discard/", format="json")

    assert response.status_code == 409, response.content
    assert response.json()["error"] == "not_draft"
    assert MeetingRecord.objects.filter(pk=issued["id"]).exists()


# ── The audit trail cannot be rewritten ──────────────────────────────


def test_an_audit_entry_cannot_be_changed(issued):
    event = RecordEvent.objects.filter(record_id=issued["id"]).first()
    event.detail = {"tampered": True}

    with pytest.raises(RecordEventError):
        event.save()

    event.refresh_from_db()
    assert event.detail == {}


def test_an_audit_entry_cannot_be_deleted(issued):
    event = RecordEvent.objects.filter(record_id=issued["id"]).first()

    with pytest.raises(RecordEventError):
        event.delete()

    assert RecordEvent.objects.filter(pk=event.pk).exists()


# ── Who may do what ──────────────────────────────────────────────────


def test_a_viewer_can_read_but_not_prepare_or_issue(api_client, draft, tenant, session):
    api_client.force_authenticate(user=member(tenant, Membership.Role.VIEWER, "rec_v"))
    other = a_recording(session)

    assert api_client.get(f"{BASE}/records/{draft['id']}/").status_code == 200
    assert api_client.get(f"{BASE}/records/{draft['id']}/pdf/").status_code == 200
    assert prepare(api_client, other).status_code == 403
    assert issue(api_client, draft["id"]).status_code == 403
    assert MeetingRecord.objects.get(pk=draft["id"]).status == RecordStatus.DRAFT


def test_an_anonymous_caller_gets_nothing(draft):
    anonymous = APIClient()
    anonymous.defaults["SERVER_NAME"] = "localhost"

    assert anonymous.get(f"{BASE}/records/{draft['id']}/").status_code == 401
    assert anonymous.get(f"{BASE}/records/{draft['id']}/pdf/").status_code == 401


@pytest.mark.parametrize(
    "method, path",
    [
        ("get", "records/{record}/"),
        ("get", "records/{record}/pdf/"),
        ("post", "records/{record}/issue/"),
        ("post", "records/{record}/void/"),
        ("post", "records/{record}/supersede/"),
        ("post", "records/{record}/discard/"),
        ("get", "sessions/{session}/records/"),
        ("get", "sessions/{session}/binder/"),
        ("post", "recordings/{recording}/records/"),
    ],
)
def test_another_tenant_cannot_see_or_touch_a_record(
    api_client, draft, session, recording, method, path
):
    other = Tenant.objects.create(name="Other Agency", schema_name="records_b")
    api_client.force_authenticate(
        user=member(other, Membership.Role.ADMIN, "rec_outsider")
    )
    url = f"{BASE}/" + path.format(
        record=draft["id"], session=session.pk, recording=recording.pk
    )

    response = getattr(api_client, method)(url, {"reason": "x"}, format="json")

    assert response.status_code == 404, (path, response.content)
    record = MeetingRecord.objects.get(pk=draft["id"])
    assert record.status == RecordStatus.DRAFT
    assert RecordEvent.objects.filter(record=record).count() == 1


# ── The PDF and the binder, end to end ───────────────────────────────


def pdf_text(response) -> str:
    assert response.status_code == 200, response.content[:200]
    assert response["Content-Type"] == "application/pdf"
    reader = PdfReader(io.BytesIO(response.content))
    text = "\n".join(page.extract_text() for page in reader.pages)
    assert "Meeting Record" in text, "no text was extracted from the PDF"
    return text


def test_an_issued_record_downloads_as_a_watermarked_pdf(api_client, issued):
    response = api_client.get(f"{BASE}/records/{issued['id']}/pdf/")
    text = pdf_text(response)

    assert response["Content-Disposition"] == (
        f'attachment; filename="{issued["record_number"]}.pdf"'
    )
    assert "NOT FULLY SIGNED" in text
    assert "Pomodoro Trattoria LLC" in text
    assert "Launch budget split evenly;" in text
    assert "Maria Rossi: Yes, agreed." in text
    assert issued["content_hash"] in text.replace("\n", "")
    assert "For Zorven Agency" in text
    assert "For Pomodoro Trattoria LLC" in text


def test_a_draft_downloads_marked_as_not_issued(api_client, draft):
    text = pdf_text(api_client.get(f"{BASE}/records/{draft['id']}/pdf/"))

    assert "DRAFT — NOT ISSUED" in text
    assert "NOT FULLY SIGNED" not in text


def test_every_download_is_logged_and_does_not_change_the_document(api_client, issued):
    """Downloads are in the audit trail, but not printed inside the copy
    being downloaded — or no two copies would ever match."""
    first = api_client.get(f"{BASE}/records/{issued['id']}/pdf/")
    second = api_client.get(f"{BASE}/records/{issued['id']}/pdf/")

    assert first.content == second.content
    downloads = RecordEvent.objects.filter(
        record_id=issued["id"], event_type=RecordEventType.DOWNLOADED
    )
    assert downloads.count() == 2
    assert downloads.first().detail == {"kind": "record"}
    assert "Downloaded" not in pdf_text(first)


def test_the_session_lists_every_meeting_with_or_without_a_record(
    api_client, issued, session, recording
):
    later = a_recording(session)
    untranscribed = a_recording(session, description="", transcript_clean=[])

    body = api_client.get(f"{BASE}/sessions/{session.pk}/records/").json()

    assert [m["recording_id"] for m in body["meetings"]] == [
        recording.pk,
        later.pk,
        untranscribed.pk,
    ]
    assert body["meetings"][0]["record"]["id"] == issued["id"]
    assert body["meetings"][0]["record"]["status"] == RecordStatus.ISSUED
    assert body["meetings"][1]["record"] is None
    assert body["meetings"][1]["has_content"] is True
    assert body["meetings"][2]["has_content"] is False


def test_the_session_list_shows_the_latest_version_and_keeps_the_history(
    api_client, voided, session
):
    successor = api_client.post(
        f"{BASE}/records/{voided['id']}/supersede/", format="json"
    ).json()

    listing = api_client.get(f"{BASE}/sessions/{session.pk}/records/").json()
    meeting = listing["meetings"][0]

    assert meeting["record"]["id"] == successor["id"]
    assert [r["id"] for r in meeting["history"]] == [voided["id"]]
    assert meeting["history"][0]["status"] == RecordStatus.VOIDED


def test_the_binder_compiles_every_meeting_in_order(api_client, issued, session):
    later = a_recording(
        session,
        description="## Agreements\n- Photo shoot booked for January.\n",
        transcript_clean="Naveen: Second meeting.",
    )
    second = prepare(api_client, later).json()

    response = api_client.get(f"{BASE}/sessions/{session.pk}/binder/")
    text = pdf_text(response)

    assert response["Content-Disposition"] == (
        f'attachment; filename="meeting-records-session-{session.pk}.pdf"'
    )
    assert text.index(issued["record_number"]) < text.index(second["record_number"])
    assert "Launch budget split evenly;" in text
    assert "Photo shoot booked for January." in text
    assert "NOT FULLY SIGNED" in text
    assert "DRAFT — NOT ISSUED" in text


def test_adding_a_meeting_leaves_the_earlier_record_untouched(
    api_client, issued, session
):
    later = a_recording(session, transcript_clean="Naveen: Second meeting.")
    second = prepare(api_client, later).json()
    assert issue(api_client, second["id"]).status_code == 200
    api_client.get(f"{BASE}/sessions/{session.pk}/binder/")

    first = MeetingRecord.objects.get(pk=issued["id"])

    assert first.snapshot == issued["document"]
    assert first.content_hash == issued["content_hash"]
    assert first.content_hash != MeetingRecord.objects.get(pk=second["id"]).content_hash
    assert first.status == RecordStatus.ISSUED


def test_a_session_with_no_records_still_gives_a_binder(api_client, editor, session):
    text = pdf_text(api_client.get(f"{BASE}/sessions/{session.pk}/binder/"))

    assert "No meeting records have been prepared for this session." in text


# ── Two parties, not one named twice ─────────────────────────────────


@pytest.mark.parametrize(
    "workspace, same",
    [
        ("Pomodoro", True),
        ("  pomodoro ", True),
        ("Pomodoro Trattoria LLC", True),
        ("Zorven Agency", False),
    ],
)
def test_a_workspace_named_after_its_client_cannot_issue(
    api_client, editor, tenant, recording, workspace, same
):
    """Found on real data: a workspace named after the client printed
    "Pomodoro and Pomodoro". A record needs two parties."""
    Tenant.objects.filter(pk=tenant.pk).update(name=workspace)
    draft = prepare(api_client, recording).json()

    item = readiness_of(draft)["parties_distinct"]
    assert item["blocking"] is True
    assert item["ok"] is not same
    assert issue(api_client, draft["id"]).status_code == (409 if same else 200)


# ── The address in the audit trail cannot be chosen by the caller ────


def created_from(recording) -> str | None:
    return RecordEvent.objects.get(
        record__recording=recording, event_type=RecordEventType.CREATED
    ).ip_address


def test_the_audit_trail_ignores_addresses_the_caller_put_in_the_header(
    api_client, editor, recording
):
    """Each proxy appends to X-Forwarded-For, so everything left of the last
    entry was supplied by the caller. The first entry is the one a forger
    controls."""
    response = api_client.post(
        f"{BASE}/recordings/{recording.pk}/records/",
        format="json",
        HTTP_X_FORWARDED_FOR="1.1.1.1, 10.9.9.9, 203.0.113.7",
    )

    assert response.status_code == 201, response.content
    assert created_from(recording) == "203.0.113.7"


def test_with_two_trusted_proxies_the_address_is_two_from_the_right(
    api_client, editor, recording, settings
):
    settings.RECORDS_TRUSTED_PROXY_COUNT = 2

    api_client.post(
        f"{BASE}/recordings/{recording.pk}/records/",
        format="json",
        HTTP_X_FORWARDED_FOR="1.1.1.1, 203.0.113.7, 10.0.0.2",
    )

    assert created_from(recording) == "203.0.113.7"


def test_with_no_trusted_proxy_the_header_is_ignored(
    api_client, editor, recording, settings
):
    """Reached directly, the whole header is the caller's to write."""
    settings.RECORDS_TRUSTED_PROXY_COUNT = 0

    api_client.post(
        f"{BASE}/recordings/{recording.pk}/records/",
        format="json",
        HTTP_X_FORWARDED_FOR="1.1.1.1",
        REMOTE_ADDR="198.51.100.4",
    )

    assert created_from(recording) == "198.51.100.4"


def test_without_the_header_the_socket_address_is_recorded(
    api_client, editor, recording
):
    api_client.post(
        f"{BASE}/recordings/{recording.pk}/records/",
        format="json",
        REMOTE_ADDR="198.51.100.4",
    )

    assert created_from(recording) == "198.51.100.4"


def test_a_header_shorter_than_the_proxy_chain_is_not_believed(
    api_client, editor, recording, settings
):
    settings.RECORDS_TRUSTED_PROXY_COUNT = 2

    api_client.post(
        f"{BASE}/recordings/{recording.pk}/records/",
        format="json",
        HTTP_X_FORWARDED_FOR="1.1.1.1",
        REMOTE_ADDR="198.51.100.4",
    )

    assert created_from(recording) == "198.51.100.4"


@pytest.mark.parametrize(
    "header", ["not-an-address", "203.0.113.7:8443", "<script>", "999.1.1.1"]
)
def test_a_value_that_is_not_an_address_is_recorded_as_nothing(
    api_client, editor, recording, header
):
    """Not passed on to the column, which would reject it and fail the
    request — a malformed header must not stop a record being prepared."""
    response = api_client.post(
        f"{BASE}/recordings/{recording.pk}/records/",
        format="json",
        HTTP_X_FORWARDED_FOR=header,
    )

    assert response.status_code == 201, response.content
    assert created_from(recording) is None


def test_an_ipv6_address_is_recorded(api_client, editor, recording):
    api_client.post(
        f"{BASE}/recordings/{recording.pk}/records/",
        format="json",
        HTTP_X_FORWARDED_FOR="2001:db8::1",
    )

    assert created_from(recording) == "2001:db8::1"
