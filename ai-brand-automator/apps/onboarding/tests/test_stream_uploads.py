"""O-07 · per-stream upload sessions and per-stream finalisation.

Same division of labour as `test_uploads.py`: GCS is not exercised here.
What Django owns is minting one session per mic, persisting it, registering
exactly one BrandAsset per mic however many times finalisation is replayed,
and making those objects reachable by GDPR erasure. None of that is a
property of Google's storage API, and every test that needs an already-minted
session seeds it the way the existing F-03 tests seed `upload_gcs_path`.

The regression these tests exist for: before O-07 the browser absorbed every
mic's chunks into one buffer and PUT them to one object, so a two-mic meeting
uploaded a single interleaved stream that no decoder accepts.
"""

from __future__ import annotations

import re

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from apps.onboarding.models import (
    MeetingAttendee,
    MeetingRecording,
    RecordingStatus,
    SessionStatus,
)
from apps.onboarding.tests.factories import make_session
from apps.onboarding.uploads import landing_path
from onboarding.models import BrandAsset, Company
from tenants.models import Membership

pytestmark = pytest.mark.django_db

RECORDINGS = "/api/v1/onboarding/recordings/"


def client_for(user) -> APIClient:
    client = APIClient()
    client.defaults["SERVER_NAME"] = "localhost"
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def editor(public_tenant):
    user = User.objects.create_user("o07_editor", "o07@test.com", "TestPass123!")
    Membership.objects.create(
        user=user, tenant=public_tenant, role=Membership.Role.EDITOR
    )
    return user


@pytest.fixture
def recording(public_tenant):
    session = make_session(tenant=public_tenant, status=SessionStatus.MEETING_LIVE)
    if session.company is None:  # pragma: no cover - factory already sets one
        session.company = Company.objects.create(tenant=public_tenant, name="Kalyani")
        session.save()
    return MeetingRecording.objects.create(
        tenant=public_tenant, session=session, status=RecordingStatus.RECORDING
    )


def session_url(recording) -> str:
    return f"{RECORDINGS}{recording.pk}/upload-session/"


def stop_url(recording) -> str:
    return f"{RECORDINGS}{recording.pk}/stop/"


def seed_streams(recording, count: int) -> list[dict]:
    """Two already-minted per-mic sessions, as the browser would leave them."""
    prefix = f"_landing/{recording.tenant_id}"
    streams = [
        {
            "stream_index": i,
            "gcs_path": f"{prefix}/abc12{i}_{recording.pk}_s{i}.opus",
            "session_url": f"https://upload.example/session-{i}",
        }
        for i in range(count)
    ]
    recording.stream_assets = streams
    recording.save(update_fields=["stream_assets"])
    return streams


# ── AC-1 · a separate object per mic ─────────────────────────────────


def test_the_stream_landing_path_keeps_the_ingestion_prefix(public_tenant, recording):
    """AC-1, and a deliberate deviation from the card.

    The card illustrates `recordings/{id}/stream-{index}.webm`. That is not
    used: `_landing/` is what puts audio on the ingestion pipeline the
    single-stream path already rides, and `.webm` would contradict the content
    type both paths upload under.
    """
    path = landing_path(recording, 1)

    assert re.fullmatch(
        rf"_landing/{public_tenant.pk}/[0-9a-f]{{12}}_{recording.pk}_s1\.opus", path
    ), path


def test_each_mic_gets_its_own_path(recording):
    """Two mics that shared a path would overwrite each other, which is the
    interleaving bug in a different costume."""
    assert landing_path(recording, 0) != landing_path(recording, 1)


def test_the_single_stream_path_is_unchanged(public_tenant, recording):
    """The regression gate. A legacy recording must land exactly where it did
    before this story — `stream_index=None` is not `stream_index=0`."""
    path = landing_path(recording)

    assert re.fullmatch(
        rf"_landing/{public_tenant.pk}/[0-9a-f]{{12}}_{recording.pk}\.opus", path
    ), path
    assert "_s" not in path.rsplit("_", 1)[-1]


def test_an_existing_stream_session_is_returned_not_reminted(
    public_tenant, editor, recording
):
    """AC-1's resume rule, per stream.

    Re-minting for a mic that already has a session would strand that mic's
    uploaded bytes — and the operator would lose one participant rather than
    the whole meeting, which is harder to notice.
    """
    seed_streams(recording, 2)

    response = client_for(editor).post(
        session_url(recording), {"stream_index": 1}, format="json"
    )

    assert response.status_code == 200, response.data
    assert response.data["session_url"] == "https://upload.example/session-1"
    assert response.data["stream_index"] == 1
    recording.refresh_from_db()
    assert len(recording.stream_assets) == 2


def test_a_stream_request_does_not_touch_the_single_stream_columns(
    public_tenant, editor, recording
):
    """The two paths are independent. A per-mic request that wrote
    `upload_session_url` would make the legacy finaliser register a stream's
    object as the whole meeting's audio."""
    seed_streams(recording, 1)

    client_for(editor).post(session_url(recording), {"stream_index": 0}, format="json")

    recording.refresh_from_db()
    assert recording.upload_session_url == ""
    assert recording.upload_gcs_path == ""


@pytest.mark.parametrize("bad", ["abc", None, 256, -1, 1.5, "--5", "---12", "", " "])
def test_an_unaddressable_stream_index_is_refused(editor, recording, bad):
    """O-03 carries the index in one byte, so the protocol cannot address a
    stream outside 0–255. A 400 here beats minting an object nothing will
    ever upload to."""
    response = client_for(editor).post(
        session_url(recording), {"stream_index": bad}, format="json"
    )

    # `None` means "no stream_index", which is the legacy path: it reaches GCS,
    # which is unconfigured in tests, and honestly reports 503.
    if bad is None:
        assert response.status_code == 503, response.data
    else:
        assert response.status_code == 400, response.data
        assert response.data["error"] == "invalid_stream_index"


# ── AC-4 · finalisation is atomic across streams ─────────────────────


def test_finalisation_registers_one_asset_per_stream(public_tenant, editor, recording):
    """AC-1 and AC-4 together: each mic's object becomes its own BrandAsset so
    each rides ingestion separately, and all of them land in one transaction."""
    streams = seed_streams(recording, 2)

    response = client_for(editor).post(
        stop_url(recording), {"duration_s": 120}, format="json"
    )

    assert response.status_code == 200, response.data
    recording.refresh_from_db()
    assert recording.status == RecordingStatus.UPLOADED
    paths = {a.gcs_path for a in BrandAsset.objects.all()}
    assert paths == {s["gcs_path"] for s in streams}
    for entry in recording.stream_assets:
        assert entry["brand_asset_id"]


def test_replaying_finalisation_makes_no_second_stream_asset(
    public_tenant, editor, recording
):
    """The browser retries finalisation after a network drop. A second asset
    per mic would put one participant's audio through ingestion and into RAG
    twice — the same failure F-03 guards for the single-stream case."""
    seed_streams(recording, 2)
    api = client_for(editor)
    body = {"duration_s": 120}

    api.post(stop_url(recording), body, format="json", HTTP_IDEMPOTENCY_KEY="k-1")
    api.post(stop_url(recording), body, format="json", HTTP_IDEMPOTENCY_KEY="k-1")

    assert BrandAsset.objects.count() == 2


def test_a_stream_that_uploaded_nothing_gets_no_asset(public_tenant, editor, recording):
    """A mic whose session could never be minted still finalises with the
    others, but inventing an asset for absent bytes puts a broken row into
    ingestion. AC-3's isolation, seen from the finaliser."""
    recording.stream_assets = [
        {"stream_index": 0, "gcs_path": f"_landing/x/a_{recording.pk}_s0.opus"},
        {"stream_index": 1},  # session never minted
    ]
    recording.save(update_fields=["stream_assets"])

    client_for(editor).post(stop_url(recording), {"duration_s": 60}, format="json")

    recording.refresh_from_db()
    assert BrandAsset.objects.count() == 1
    assert recording.stream_assets[1].get("brand_asset_id") is None
    assert recording.status == RecordingStatus.UPLOADED


def test_a_replayed_finalisation_still_records_the_speaker(
    public_tenant, editor, recording
):
    """The dedup branch must leave the entry in the same state a first pass
    would. Otherwise what the archive claims about who was recorded depends on
    how many times the browser retried."""
    streams = seed_streams(recording, 1)
    MeetingAttendee.objects.create(
        tenant=public_tenant,
        session=recording.session,
        name="Sarah Kelso",
        role="operator",
        stream_index=0,
    )
    # An asset already exists for this path — the state a retried finalisation
    # finds after the first one got as far as creating it.
    BrandAsset.objects.create(
        tenant=public_tenant,
        company=recording.session.company,
        file_name="pre-existing.opus",
        file_type="other",
        file_size=0,
        gcs_path=streams[0]["gcs_path"],
    )

    client_for(editor).post(stop_url(recording), {"duration_s": 60}, format="json")

    recording.refresh_from_db()
    assert BrandAsset.objects.count() == 1
    assert recording.stream_assets[0]["speaker_name"] == "Sarah Kelso"


def test_stream_assets_are_reachable_by_the_brandasset_erasure_store(
    public_tenant, editor, recording
):
    """M-02's other half.

    Deleting the bytes is not enough: the BrandAsset rows carry the landing
    path, a file name containing the recording id, and the speaker. The store
    filters on ``onboarding_session``, so a per-mic asset created without it
    survives an erasure that reported success.
    """
    from apps.onboarding.erasure.stores.django_brand_assets import (
        DjangoBrandAssetStore,
    )

    seed_streams(recording, 2)
    client_for(editor).post(stop_url(recording), {"duration_s": 60}, format="json")

    manifest = DjangoBrandAssetStore().collect(
        tenant_id=public_tenant.pk,
        session_ids=[recording.session_id],
        subject_name="Sarah Kelso",
    )

    assert manifest.item_count == 2


def test_the_speaker_name_is_frozen_onto_the_stream_entry(
    public_tenant, editor, recording
):
    """O-05's roll call names the mic; the attendee row stays editable and the
    asset is an archive. What the archive claims about who was recorded must
    be what was true when the recording stopped."""
    seed_streams(recording, 2)
    MeetingAttendee.objects.create(
        tenant=public_tenant,
        session=recording.session,
        name="Sarah Kelso",
        role="operator",
        stream_index=0,
    )
    MeetingAttendee.objects.create(
        tenant=public_tenant,
        session=recording.session,
        name="Devan Roy",
        role="participant",
        stream_index=1,
    )

    client_for(editor).post(stop_url(recording), {"duration_s": 120}, format="json")

    recording.refresh_from_db()
    names = {e["stream_index"]: e.get("speaker_name") for e in recording.stream_assets}
    assert names == {0: "Sarah Kelso", 1: "Devan Roy"}


def test_a_stream_without_an_attendee_still_finalises(public_tenant, editor, recording):
    """Roll call is voice-driven and can miss somebody. A missing name must not
    cost us the audio."""
    seed_streams(recording, 2)

    client_for(editor).post(stop_url(recording), {"duration_s": 60}, format="json")

    recording.refresh_from_db()
    assert BrandAsset.objects.count() == 2
    assert recording.stream_assets[0].get("speaker_name") in (None, "")


def test_legacy_finalisation_is_untouched_by_this_story(
    public_tenant, editor, recording
):
    """The regression gate for AC-4: a single-mic recording still produces
    exactly one asset from `upload_gcs_path`, and no stream entries."""
    recording.upload_gcs_path = f"_landing/{public_tenant.pk}/abc_{recording.pk}.opus"
    recording.save(update_fields=["upload_gcs_path"])

    client_for(editor).post(stop_url(recording), {"duration_s": 45}, format="json")

    recording.refresh_from_db()
    assert BrandAsset.objects.count() == 1
    assert recording.audio_asset is not None
    assert recording.stream_assets == []


# ── M-02 · erasure reaches per-stream objects ────────────────────────


def test_erasure_collects_every_stream_object(public_tenant, recording):
    """The gap O-07 would otherwise open.

    `GCSBlobStore` reads `upload_gcs_path` and sweeps BrandAssets by
    `onboarding_session` — which recording assets never set. Per-mic objects
    are reachable only through `stream_assets`, and an erasure that reports
    success while leaving a participant's audio in the bucket is precisely the
    failure M-02 exists to prevent.
    """
    from apps.onboarding.erasure.stores.gcs_blobs import GCSBlobStore

    streams = seed_streams(recording, 2)

    manifest = GCSBlobStore().collect(
        tenant_id=public_tenant.pk,
        session_ids=[recording.session_id],
        subject_name="Sarah Kelso",
    )

    collected = {entry["path"] for entry in manifest.details["gcs_paths"]}
    for stream in streams:
        assert stream["gcs_path"] in collected
    assert manifest.item_count == len(collected)


# ── The library surface ──────────────────────────────────────────────


def test_the_library_reports_a_stream_count_not_the_paths(
    public_tenant, editor, recording
):
    """The serializer hides `transcript_gcs_path` as an infrastructure leak.
    A stream entry is worse than a path: it holds a resumable session URL,
    which carries its own authorisation to write to somebody's meeting audio.
    """
    seed_streams(recording, 2)

    response = client_for(editor).get(f"{RECORDINGS}{recording.pk}/")

    assert response.status_code == 200, response.data
    assert response.data["stream_count"] == 2
    assert "stream_assets" not in response.data
    assert "upload.example" not in str(response.data)


def test_a_single_mic_recording_reports_no_streams(editor, recording):
    response = client_for(editor).get(f"{RECORDINGS}{recording.pk}/")

    assert response.data["stream_count"] == 0
