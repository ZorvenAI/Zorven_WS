"""B-08 · recording open, stop and list (AC-1 … AC-4).

The consent gate is the part that matters. IG-08 says a recording may not
start without a valid ConsentRecord, and AC-1 adds "this holds even when the
client's UI would have prevented it" — because a caller who can reach the
endpoint can skip whatever the UI would have done.

Duration is the other one. FR-REC-02 requires it to derive from the audio
timeline rather than wall-clock, to under a second over 45 minutes, so the
server never computes elapsed time between open and stop.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from apps.onboarding.models import MeetingRecording, RecordingStatus, SessionStatus
from apps.onboarding.tests.factories import (
    make_company,
    make_consent,
    make_recording,
    make_session,
)
from tenants.models import Membership, Tenant

pytestmark = pytest.mark.django_db

SESSIONS = "/api/v1/onboarding/sessions/"
RECORDINGS = "/api/v1/onboarding/recordings/"


def client_for(user, tenant) -> APIClient:
    client = APIClient()
    client.defaults["SERVER_NAME"] = "localhost"
    client.force_authenticate(user=user)
    client.defaults["HTTP_X_TENANT_ID"] = str(tenant.id)
    return client


def member(tenant, role, username) -> User:
    user = User.objects.create_user(
        username=username, email=f"{username}@test.com", password="TestPass123!"
    )
    Membership.objects.create(user=user, tenant=tenant, role=role)
    return user


@pytest.fixture
def editor(public_tenant):
    return member(public_tenant, Membership.Role.EDITOR, "b08_editor")


@pytest.fixture
def viewer(public_tenant):
    return member(public_tenant, Membership.Role.VIEWER, "b08_viewer")


@pytest.fixture
def consented_session(public_tenant):
    session = make_session(tenant=public_tenant, status=SessionStatus.MEETING_LIVE)
    make_consent(session=session)
    return session


def recordings_url(session) -> str:
    return f"{SESSIONS}{session.pk}/recordings/"


# ── AC-1 · opening without consent is refused server-side ────────────


def test_open_without_consent_403(public_tenant, editor):
    """The card's named case: IG-08 is enforced at the API, not only the UI.

    And no row is created — a RECORDING row for a meeting that never lawfully
    started would be worse than the error, because the library would show it.
    """
    session = make_session(tenant=public_tenant, status=SessionStatus.READY)

    response = client_for(editor, public_tenant).post(recordings_url(session))

    assert response.status_code == 403
    assert response.data["code"] == "ERR-03"
    assert MeetingRecording.objects.filter(session=session).count() == 0


def test_revoked_consent_is_not_consent(public_tenant, editor):
    """Revoked consent must refuse exactly as absent consent does."""
    session = make_session(tenant=public_tenant, status=SessionStatus.MEETING_LIVE)
    client = client_for(editor, public_tenant)
    client.post(
        f"{SESSIONS}{session.pk}/consent/",
        {"subject_name": "Asha Kalyani", "method": "VERBAL_RECORDED", "scope": {}},
        format="json",
    )
    client.delete(f"{SESSIONS}{session.pk}/consent/")

    response = client.post(recordings_url(session))

    assert response.status_code == 403
    assert response.data["code"] == "ERR-03"
    assert MeetingRecording.objects.filter(session=session).count() == 0


def test_open_with_consent_creates_a_recording(
    consented_session, public_tenant, editor
):
    response = client_for(editor, public_tenant).post(recordings_url(consented_session))

    assert response.status_code == 201, response.data
    assert response.data["status"] == RecordingStatus.RECORDING
    assert response.data["stopped_at"] is None
    assert response.data["duration_s"] is None
    assert response.data["has_summary"] is False


def test_a_viewer_cannot_open_a_recording(consented_session, public_tenant, viewer):
    response = client_for(viewer, public_tenant).post(recordings_url(consented_session))

    assert response.status_code == 403
    assert MeetingRecording.objects.filter(session=consented_session).count() == 0


# ── AC-2 · stop finalises exactly the row it opened ──────────────────


def test_stop_sets_the_three_fields(consented_session, public_tenant, editor):
    client = client_for(editor, public_tenant)
    opened = client.post(recordings_url(consented_session))
    rid = opened.data["id"]

    stopped = client.post(f"{RECORDINGS}{rid}/stop/", {"duration_s": 95}, format="json")

    assert stopped.status_code == 200
    assert stopped.data["stopped_at"] is not None
    assert stopped.data["duration_s"] == 95
    assert stopped.data["status"] == RecordingStatus.UPLOADED


def test_stop_sets_uploaded_never_transcribed(consented_session, public_tenant, editor):
    """The transcript arrives asynchronously, so the library must be able to
    say "transcribing" honestly rather than claim a transcript that does not
    exist."""
    client = client_for(editor, public_tenant)
    rid = client.post(recordings_url(consented_session)).data["id"]

    stopped = client.post(f"{RECORDINGS}{rid}/stop/", {}, format="json")

    assert stopped.data["status"] == RecordingStatus.UPLOADED
    assert stopped.data["status"] != RecordingStatus.TRANSCRIBED


def test_stop_is_idempotent(consented_session, public_tenant, editor):
    """The card's named case: a double-stop must not corrupt the duration."""
    client = client_for(editor, public_tenant)
    rid = client.post(recordings_url(consented_session)).data["id"]

    first = client.post(f"{RECORDINGS}{rid}/stop/", {"duration_s": 95}, format="json")
    second = client.post(
        f"{RECORDINGS}{rid}/stop/", {"duration_s": 9999}, format="json"
    )

    assert first.status_code == second.status_code == 200
    assert second.data["duration_s"] == 95, "a second stop rewrote the duration"
    assert second.data["stopped_at"] == first.data["stopped_at"]


def test_stop_touches_only_its_own_row(consented_session, public_tenant, editor):
    """AC-2's "on that row only", with three cycles open at once — B-02 made
    MEETING_LIVE re-entrant, so concurrent opens are the normal case."""
    client = client_for(editor, public_tenant)
    ids = [client.post(recordings_url(consented_session)).data["id"] for _ in range(3)]

    client.post(f"{RECORDINGS}{ids[1]}/stop/", {"duration_s": 42}, format="json")

    rows = {r.pk: r for r in MeetingRecording.objects.filter(session=consented_session)}
    assert rows[ids[1]].status == RecordingStatus.UPLOADED
    assert rows[ids[0]].status == RecordingStatus.RECORDING
    assert rows[ids[2]].status == RecordingStatus.RECORDING
    assert rows[ids[0]].stopped_at is None and rows[ids[2]].stopped_at is None


def test_duration_is_absent_rather_than_wrong(consented_session, public_tenant, editor):
    """FR-REC-02 forbids wall-clock, and F-03's upload does not exist yet.

    A duration the server invented from elapsed time would be confidently
    wrong in the library; absent is honest.
    """
    client = client_for(editor, public_tenant)
    rid = client.post(recordings_url(consented_session)).data["id"]

    stopped = client.post(f"{RECORDINGS}{rid}/stop/", {}, format="json")

    assert stopped.data["stopped_at"] is not None
    assert stopped.data["duration_s"] is None, "the server invented a duration"


def test_a_negative_duration_is_refused(consented_session, public_tenant, editor):
    client = client_for(editor, public_tenant)
    rid = client.post(recordings_url(consented_session)).data["id"]

    response = client.post(
        f"{RECORDINGS}{rid}/stop/", {"duration_s": -1}, format="json"
    )

    assert response.status_code == 400


def test_a_viewer_cannot_stop_a_recording(
    consented_session, public_tenant, viewer, editor
):
    rid = (
        client_for(editor, public_tenant)
        .post(recordings_url(consented_session))
        .data["id"]
    )

    response = client_for(viewer, public_tenant).post(f"{RECORDINGS}{rid}/stop/")

    assert response.status_code == 403
    assert MeetingRecording.objects.get(pk=rid).stopped_at is None


# ── AC-3 · the list serves the library ───────────────────────────────


def test_list_newest_first_viewer_readonly(
    consented_session, public_tenant, editor, viewer
):
    """The card's named case: the library contract holds for all roles."""
    client = client_for(editor, public_tenant)
    for _ in range(3):
        client.post(recordings_url(consented_session))

    as_viewer = client_for(viewer, public_tenant).get(recordings_url(consented_session))

    assert as_viewer.status_code == 200
    rows = as_viewer.data
    assert len(rows) == 3
    started = [row["started_at"] for row in rows]
    assert started == sorted(started, reverse=True), "not newest-first"


def test_the_list_carries_what_the_library_needs(
    consented_session, public_tenant, editor
):
    make_recording(
        session=consented_session,
        duration_s=95,
        status=RecordingStatus.SUMMARIZED,
        summary={"text": "They started in a garage.", "key_moments": []},
    )

    rows = client_for(editor, public_tenant).get(recordings_url(consented_session)).data

    row = rows[0]
    for key in ("duration_s", "status", "has_summary", "audio_asset"):
        assert key in row, key
    assert row["has_summary"] is True


def test_the_list_sends_presence_not_the_summary_blob(
    consented_session, public_tenant, editor
):
    """A long meeting's summary for every row would make the rail heavy for a
    boolean's worth of information."""
    make_recording(session=consented_session, summary={"text": "x" * 5000})

    rows = client_for(editor, public_tenant).get(recordings_url(consented_session)).data

    assert "summary" not in rows[0]
    assert rows[0]["has_summary"] is True


def test_the_recording_list_is_tenant_scoped(public_tenant, editor):
    other = Tenant.objects.create(name="Other B08", schema_name="other_b08")
    theirs = make_session(company=make_company(tenant=other, name="Theirs"))

    response = client_for(editor, public_tenant).get(recordings_url(theirs))

    assert response.status_code == 404


def test_stopping_another_tenants_recording_is_404(public_tenant, editor):
    other = Tenant.objects.create(name="Other B08 stop", schema_name="other_b08_stop")
    theirs = make_session(company=make_company(tenant=other, name="Theirs"))
    recording = make_recording(session=theirs)

    response = client_for(editor, public_tenant).post(
        f"{RECORDINGS}{recording.pk}/stop/"
    )

    assert response.status_code == 404


# ── AC-4 · what M-05's sweeper will need ─────────────────────────────


def test_the_sweeper_index_exists():
    """AC-4's sweeper is M-05's; this story owes it the index.

    Added here rather than there because the query shape — "still RECORDING
    and started before X" — is a property of this table, and an index arriving
    with the sweeper would mean its first run scans.
    """
    from django.db import connection

    # Introspection rather than a raw pg_indexes query against a hardcoded
    # table name: _meta.db_table survives a rename, and the assertion then
    # describes the *columns* the sweeper needs rather than a string that
    # happens to match today.
    with connection.cursor() as cursor:
        constraints = connection.introspection.get_constraints(
            cursor, MeetingRecording._meta.db_table
        )

    indexed_column_sets = [
        tuple(c["columns"]) for c in constraints.values() if c.get("index")
    ]
    assert ("status", "started_at") in indexed_column_sets, indexed_column_sets


def test_failed_is_reachable_and_visible_in_the_library(
    consented_session, public_tenant, editor
):
    """AC-4: an abandoned recording is closed as FAILED and the operator sees
    it in the library, rather than the row vanishing."""
    recording = make_recording(session=consented_session, status=RecordingStatus.FAILED)

    rows = client_for(editor, public_tenant).get(recordings_url(consented_session)).data

    assert any(row["id"] == recording.pk for row in rows)
    assert rows[0]["status"] == RecordingStatus.FAILED


# ── PR #550 review · all three findings were real ────────────────────


def test_the_storage_path_is_not_exposed(consented_session, public_tenant, editor):
    """FR-LIB-01: media is served "only through short-lived signed URLs minted
    per request".

    Handing out the raw bucket path leaks infrastructure detail and routes
    around that design before it exists. The library only needs to know
    whether a transcript has arrived.
    """
    make_recording(
        session=consented_session,
        transcript_gcs_path="gs://zorven-raw-assets/_raw/t-1/transcript.json",
    )

    rows = client_for(editor, public_tenant).get(recordings_url(consented_session)).data

    assert "transcript_gcs_path" not in rows[0]
    assert rows[0]["has_transcript"] is True
    assert "gs://" not in str(rows[0]), "a storage path reached the response"


def test_has_transcript_is_false_before_one_arrives(
    consented_session, public_tenant, editor
):
    make_recording(session=consented_session, transcript_gcs_path="")

    rows = client_for(editor, public_tenant).get(recordings_url(consented_session)).data

    assert rows[0]["has_transcript"] is False
