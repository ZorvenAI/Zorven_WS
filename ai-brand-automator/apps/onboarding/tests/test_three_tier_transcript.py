"""Three-Tier Transcript · D-01/D-02 — Django model, serializer, endpoint tests.

Covers:
- MeetingRecording new fields (transcript_clean, description, GCS paths)
- MeetingRecordingSerializer has_description / has_clean_transcript flags
- update_recording_summary accepts string and list for transcript_clean
- session_description GET endpoint
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from apps.onboarding.models import (
    RecordingStatus,
    SessionStatus,
)
from apps.onboarding.serializers import MeetingRecordingSerializer
from apps.onboarding.tests.factories import make_recording, make_session
from tenants.models import Membership, Tenant

pytestmark = pytest.mark.django_db


def _client_for(user: User, tenant: Tenant) -> APIClient:
    client = APIClient()
    client.defaults["SERVER_NAME"] = "localhost"
    client.force_authenticate(user=user)
    client.defaults["HTTP_X_TENANT_ID"] = str(tenant.id)
    return client


def _member(tenant: Tenant, role: str, username: str) -> User:
    user = User.objects.create_user(
        username=username, email=f"{username}@test.com", password="TestPass123!"
    )
    Membership.objects.create(user=user, tenant=tenant, role=role)
    return user


@pytest.fixture
def public_tenant():
    tenant = Tenant.objects.filter(schema_name="public").first()
    assert tenant is not None, "public tenant must exist (setup_public_tenant fixture)"
    return tenant


@pytest.fixture
def editor(public_tenant):
    return _member(public_tenant, Membership.Role.EDITOR, "ttt_editor")


@pytest.fixture
def client(editor, public_tenant):
    return _client_for(editor, public_tenant)


# ── D-01: Model fields ──────────────────────────────────────────────


class TestModelFields:
    def test_recording_has_transcript_clean_field(self, public_tenant):
        rec = make_recording(tenant=public_tenant)
        assert hasattr(rec, "transcript_clean")
        assert rec.transcript_clean == []

    def test_recording_has_description_field(self, public_tenant):
        rec = make_recording(tenant=public_tenant)
        assert hasattr(rec, "description")
        assert rec.description == ""

    def test_recording_has_gcs_path_fields(self, public_tenant):
        rec = make_recording(tenant=public_tenant)
        assert rec.transcript_clean_gcs_path == ""
        assert rec.description_gcs_path == ""
        assert rec.raw_transcript_gcs_path == ""

    def test_transcript_clean_stores_list(self, public_tenant):
        rec = make_recording(tenant=public_tenant)
        segments = [{"speaker": "A", "text": "hello"}]
        rec.transcript_clean = segments
        rec.save(update_fields=["transcript_clean"])
        rec.refresh_from_db()
        assert rec.transcript_clean == segments

    def test_transcript_clean_stores_string(self, public_tenant):
        """PROCESS mode sends T2 as a plain string, not a list."""
        rec = make_recording(tenant=public_tenant)
        rec.transcript_clean = "Speaker 1: Hello\nSpeaker 2: Hi"
        rec.save(update_fields=["transcript_clean"])
        rec.refresh_from_db()
        assert isinstance(rec.transcript_clean, str)

    def test_description_stores_text(self, public_tenant):
        rec = make_recording(tenant=public_tenant)
        rec.description = "## Business Identity\nAcme Corp"
        rec.save(update_fields=["description"])
        rec.refresh_from_db()
        assert "Acme Corp" in rec.description


# ── D-01: Serializer ────────────────────────────────────────────────


class TestSerializer:
    def test_has_description_true_when_set(self, public_tenant):
        rec = make_recording(tenant=public_tenant)
        rec.description = "Some description"
        rec.save(update_fields=["description"])
        data = MeetingRecordingSerializer(rec).data
        assert data["has_description"] is True

    def test_has_description_false_when_empty(self, public_tenant):
        rec = make_recording(tenant=public_tenant)
        data = MeetingRecordingSerializer(rec).data
        assert data["has_description"] is False

    def test_has_clean_transcript_true_when_set(self, public_tenant):
        rec = make_recording(tenant=public_tenant)
        rec.transcript_clean = [{"speaker": "A", "text": "hi"}]
        rec.save(update_fields=["transcript_clean"])
        data = MeetingRecordingSerializer(rec).data
        assert data["has_clean_transcript"] is True

    def test_has_clean_transcript_false_when_empty(self, public_tenant):
        rec = make_recording(tenant=public_tenant)
        data = MeetingRecordingSerializer(rec).data
        assert data["has_clean_transcript"] is False


# ── D-02: update_recording_summary accepts T2/T3 ────────────────────


class TestUpdateRecordingSummary:
    """Tests the internal PATCH endpoint that OIA calls back with results."""

    def test_accepts_string_transcript_clean(self, public_tenant, settings):
        settings.OIA_SERVICE_TOKEN = "test-svc-token"
        rec = make_recording(
            tenant=public_tenant,
            status=RecordingStatus.RECORDING,
            transcript=[{"speaker": 0, "text": "hello"}],
        )

        svc = APIClient()
        svc.defaults["SERVER_NAME"] = "localhost"
        svc.credentials(
            HTTP_X_SERVICE_TOKEN="test-svc-token",
            HTTP_X_TENANT_ID=str(public_tenant.id),
        )
        url = f"/api/v1/onboarding/internal/recordings/{rec.pk}/summary/"
        resp = svc.patch(
            url,
            data={
                "summary": {"key_findings": ["finding 1"]},
                "transcript_clean": "Speaker 1: Hello there.",
                "description": "## Business Identity\nAcme",
                "raw_transcript_gcs_path": "_landing/oia/t1/sess/transcript/raw.json",
            },
            format="json",
        )
        assert resp.status_code == 200, resp.data

        rec.refresh_from_db()
        assert rec.transcript_clean == "Speaker 1: Hello there."
        assert rec.description == "## Business Identity\nAcme"
        assert rec.raw_transcript_gcs_path == "_landing/oia/t1/sess/transcript/raw.json"

    def test_accepts_list_transcript_clean(self, public_tenant, settings):
        settings.OIA_SERVICE_TOKEN = "test-svc-token"
        rec = make_recording(
            tenant=public_tenant,
            status=RecordingStatus.RECORDING,
            transcript=[{"speaker": 0, "text": "hello"}],
        )

        svc = APIClient()
        svc.defaults["SERVER_NAME"] = "localhost"
        svc.credentials(
            HTTP_X_SERVICE_TOKEN="test-svc-token",
            HTTP_X_TENANT_ID=str(public_tenant.id),
        )
        url = f"/api/v1/onboarding/internal/recordings/{rec.pk}/summary/"
        resp = svc.patch(
            url,
            data={
                "summary": {"key_findings": ["finding 1"]},
                "transcript_clean": [{"speaker": "A", "text": "cleaned"}],
            },
            format="json",
        )
        assert resp.status_code == 200, resp.data

        rec.refresh_from_db()
        assert rec.transcript_clean == [{"speaker": "A", "text": "cleaned"}]


# ── F-01: session_description endpoint ───────────────────────────────


class TestSessionDescriptionEndpoint:
    def test_returns_description(self, client, public_tenant):
        session = make_session(tenant=public_tenant, status=SessionStatus.COMPLETED)
        rec = make_recording(
            session=session,
            tenant=public_tenant,
            status=RecordingStatus.SUMMARIZED,
        )
        rec.description = "## Business Identity\nTest Corp"
        rec.transcript_clean = "cleaned text"
        rec.save(update_fields=["description", "transcript_clean"])

        url = f"/api/v1/onboarding/sessions/{session.pk}/description/"
        resp = client.get(url)
        assert resp.status_code == 200
        assert resp.data["description"] == "## Business Identity\nTest Corp"
        assert resp.data["has_clean_transcript"] is True

    def test_returns_empty_when_no_recording(self, client, public_tenant):
        session = make_session(tenant=public_tenant, status=SessionStatus.DRAFT)
        url = f"/api/v1/onboarding/sessions/{session.pk}/description/"
        resp = client.get(url)
        assert resp.status_code == 200
        assert resp.data["description"] == ""
        assert resp.data["has_clean_transcript"] is False

    def test_returns_empty_when_no_description(self, client, public_tenant):
        session = make_session(tenant=public_tenant, status=SessionStatus.COMPLETED)
        make_recording(
            session=session,
            tenant=public_tenant,
            status=RecordingStatus.SUMMARIZED,
        )
        url = f"/api/v1/onboarding/sessions/{session.pk}/description/"
        resp = client.get(url)
        assert resp.status_code == 200
        assert resp.data["description"] == ""

    def test_requires_authentication(self, public_tenant):
        session = make_session(tenant=public_tenant)
        anon = APIClient()
        anon.defaults["SERVER_NAME"] = "localhost"
        url = f"/api/v1/onboarding/sessions/{session.pk}/description/"
        resp = anon.get(url)
        assert resp.status_code == 401

    def test_404_for_nonexistent_session(self, client):
        resp = client.get("/api/v1/onboarding/sessions/99999/description/")
        assert resp.status_code == 404
