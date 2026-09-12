"""F-03 · resumable upload sessions and idempotent finalisation.

The card names `test_finalise_recording_is_idempotent`.

GCS itself is not exercised here. What Django owns is minting a session once,
persisting it, and registering exactly one BrandAsset however many times
finalisation is replayed — and none of that is a property of Google's storage
API. The bytes, the resume-after-a-drop and the "no duplication" claim are the
browser's half, covered by the fault-injection spec in
`e2e/upload-resume.spec.ts` against a real resumable-protocol server.
"""

from __future__ import annotations

import pathlib
import re

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from apps.onboarding.models import (
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


def client_for(user, tenant) -> APIClient:
    client = APIClient()
    client.defaults["SERVER_NAME"] = "localhost"
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def editor(public_tenant):
    user = User.objects.create_user("f03_editor", "f03@test.com", "TestPass123!")
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


def stop_url(recording) -> str:
    return f"{RECORDINGS}{recording.pk}/stop/"


# ── AC-1 · the landing path and the session ──────────────────────────


def test_the_landing_path_follows_the_card(public_tenant, recording):
    """AC-1: `_landing/{tenant_id}/{uuid}_{recording_id}.opus`.

    `_landing/` is the existing ingestion prefix, so the audio rides the
    pipeline that already exists rather than a parallel one.
    """
    path = landing_path(recording)

    assert re.fullmatch(
        rf"_landing/{public_tenant.pk}/[0-9a-f]{{12}}_{recording.pk}\.opus", path
    ), path


def test_two_recordings_never_share_a_path(public_tenant, recording):
    """A landing path that collides silently overwrites somebody's meeting."""
    paths = {landing_path(recording) for _ in range(20)}

    assert len(paths) == 20


# ── AC-4 · finalisation reflects reality, once ───────────────────────


def test_finalise_recording_is_idempotent(public_tenant, editor, recording):
    """The card's named case.

    The browser retries finalisation after a network drop — the same drop AC-2
    is about — so a replay is ordinary, not exotic. A second BrandAsset would
    put one meeting through ingestion twice and into RAG twice.
    """
    recording.upload_gcs_path = (
        f"_landing/{public_tenant.pk}/abc123_{recording.pk}.opus"
    )
    recording.save(update_fields=["upload_gcs_path"])
    api = client_for(editor, public_tenant)

    first = api.post(
        stop_url(recording),
        {"duration_s": 92},
        format="json",
        HTTP_IDEMPOTENCY_KEY="key-1",
    )
    second = api.post(
        stop_url(recording),
        {"duration_s": 92},
        format="json",
        HTTP_IDEMPOTENCY_KEY="key-1",
    )

    assert first.status_code == 200, first.data
    assert second.status_code == 200, second.data
    assert BrandAsset.objects.count() == 1


def test_finalisation_registers_the_asset_against_the_uploaded_object(
    public_tenant, editor, recording
):
    """B-08 left `audio_asset` null because there was nothing to point at.
    There is now, and the library and the RAG pipeline both read it."""
    path = f"_landing/{public_tenant.pk}/abc123_{recording.pk}.opus"
    recording.upload_gcs_path = path
    recording.save(update_fields=["upload_gcs_path"])

    client_for(editor, public_tenant).post(
        stop_url(recording), {"duration_s": 92}, format="json"
    )

    recording.refresh_from_db()
    assert recording.status == RecordingStatus.UPLOADED
    assert recording.duration_s == 92
    assert recording.audio_asset is not None
    assert recording.audio_asset.gcs_path == path


def test_a_recording_that_uploaded_nothing_gets_no_asset(
    public_tenant, editor, recording
):
    """The control, and the honest case: a recording whose session could never
    be minted still finalises, but inventing an asset for bytes that do not
    exist would put a broken row into the ingestion pipeline."""
    client_for(editor, public_tenant).post(
        stop_url(recording), {"duration_s": 5}, format="json"
    )

    recording.refresh_from_db()
    assert recording.audio_asset is None
    assert BrandAsset.objects.count() == 0
    # Still finalised: the cycle happened, and the library must say so.
    assert recording.status == RecordingStatus.UPLOADED


def test_a_replay_without_the_header_still_makes_only_one_asset(
    public_tenant, editor, recording
):
    """An older client that does not send Idempotency-Key must not be able to
    create duplicates by omission. The upload path is unique per recording and
    is the fallback key."""
    recording.upload_gcs_path = (
        f"_landing/{public_tenant.pk}/abc123_{recording.pk}.opus"
    )
    recording.save(update_fields=["upload_gcs_path"])
    api = client_for(editor, public_tenant)

    api.post(stop_url(recording), {"duration_s": 10}, format="json")
    api.post(stop_url(recording), {"duration_s": 10}, format="json")

    assert BrandAsset.objects.count() == 1


# ── AC-3 · the message comes from configuration ──────────────────────


def test_the_degraded_message_matches_the_breaker_config():
    """§18.2 owns this string and says why: "these strings are the entire user
    experience of a failure".

    The agent's YAML ships in a different image, so Django keeps a copy — and
    a copy nobody checks is a copy that drifts. This reads both and fails on
    the day they disagree, which is the only thing that makes duplicating it
    acceptable.
    """
    from django.conf import settings

    yaml_path = (
        pathlib.Path(__file__).resolve().parents[4]
        / "onboarding-intelligence-agent-svc"
        / "config"
        / "circuit_breakers.yaml"
    )
    assert yaml_path.exists(), f"breaker config not found at {yaml_path}"

    import yaml as pyyaml

    breakers = pyyaml.safe_load(yaml_path.read_text())
    # `dependencies`, not `breakers`: the key I guessed at was wrong and the
    # test said so, which is the point of reading the file rather than
    # restating what I believe is in it.
    from_yaml = breakers["dependencies"]["gcs"]["user_message"]

    assert settings.OIA_GCS_DEGRADED_MESSAGE == from_yaml


def test_the_key_can_arrive_in_the_body(public_tenant, editor, recording):
    """The frontend sends it there: apiClient takes no custom headers and this
    project forbids raw fetch. Both routes must reach the same guard, or the
    protection exists only for a client that cannot use it."""
    recording.upload_gcs_path = f"_landing/{public_tenant.pk}/abc_{recording.pk}.opus"
    recording.save(update_fields=["upload_gcs_path"])
    api = client_for(editor, public_tenant)
    body = {"duration_s": 30, "idempotency_key": "finalise-1"}

    api.post(stop_url(recording), body, format="json")
    api.post(stop_url(recording), body, format="json")

    assert BrandAsset.objects.count() == 1
