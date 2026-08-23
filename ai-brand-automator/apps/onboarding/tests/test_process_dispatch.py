"""J-01 — Process dispatch and lifecycle tests.

Covers: process action, callback endpoint, idempotency, state transitions.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APIClient

from apps.onboarding.models import RecordingStatus, SessionStatus
from apps.onboarding.tests.factories import (
    make_company,
    make_recording,
    make_session,
)
from tenants.models import Membership, Tenant

pytestmark = pytest.mark.django_db

SESSIONS = "/api/v1/onboarding/sessions/"
SERVICE_TOKEN = "test-service-token"


def _editor(tenant: Tenant) -> tuple[User, APIClient]:
    user = User.objects.create_user(
        username="j01_editor", email="j01@test.com", password="TestPass123!"
    )
    Membership.objects.create(user=user, tenant=tenant, role=Membership.Role.EDITOR)
    client = APIClient()
    client.defaults["SERVER_NAME"] = "localhost"
    client.force_authenticate(user=user)
    client.defaults["HTTP_X_TENANT_ID"] = str(tenant.id)
    return user, client


class TestProcessAction:
    """POST /sessions/{id}/process/ — dispatch PROCESS to OIA."""

    @override_settings(OIA_SERVICE_TOKEN=SERVICE_TOKEN)
    @patch("apps.onboarding.tasks.dispatch_process.delay")
    def test_process_from_gathered_transitions_to_processing(
        self, mock_delay, public_tenant
    ):
        user, client = _editor(public_tenant)
        company = make_company(tenant=public_tenant)
        session = make_session(
            company=company,
            tenant=public_tenant,
            status=SessionStatus.GATHERED,
            created_by=user,
        )
        make_recording(
            session=session,
            tenant=public_tenant,
            status=RecordingStatus.SUMMARIZED,
            summary={"text": "test", "key_moments": []},
        )

        resp = client.post(f"{SESSIONS}{session.pk}/process/")
        assert resp.status_code == status.HTTP_202_ACCEPTED
        assert resp.data["status"] == "PROCESSING"

        session.refresh_from_db()
        assert session.status == SessionStatus.PROCESSING
        assert session.evidence_manifest_hash != ""
        mock_delay.assert_called_once()

    @override_settings(OIA_SERVICE_TOKEN=SERVICE_TOKEN)
    def test_process_from_wrong_state_returns_409(self, public_tenant):
        user, client = _editor(public_tenant)
        company = make_company(tenant=public_tenant, name="Draft Co")
        session = make_session(
            company=company,
            tenant=public_tenant,
            status=SessionStatus.DRAFT,
            created_by=user,
        )

        resp = client.post(f"{SESSIONS}{session.pk}/process/")
        assert resp.status_code == status.HTTP_409_CONFLICT

    @override_settings(OIA_SERVICE_TOKEN=SERVICE_TOKEN)
    @patch("apps.onboarding.tasks.dispatch_process.delay")
    def test_same_manifest_returns_existing_job_id(self, mock_delay, public_tenant):
        user, client = _editor(public_tenant)
        company = make_company(tenant=public_tenant, name="Idem Co")
        session = make_session(
            company=company,
            tenant=public_tenant,
            status=SessionStatus.GATHERED,
            created_by=user,
        )
        make_recording(
            session=session,
            tenant=public_tenant,
            status=RecordingStatus.SUMMARIZED,
        )

        resp1 = client.post(f"{SESSIONS}{session.pk}/process/")
        assert resp1.status_code == status.HTTP_202_ACCEPTED
        mock_delay.assert_called_once()

        session.refresh_from_db()
        session.process_job_id = "test-job-123"
        session.status = SessionStatus.GATHERED
        session.save(update_fields=["process_job_id", "status", "updated_at"])

        mock_delay.reset_mock()
        resp2 = client.post(f"{SESSIONS}{session.pk}/process/")
        assert resp2.status_code == status.HTTP_200_OK
        assert resp2.data["idempotent"] is True
        assert resp2.data["job_id"] == "test-job-123"
        mock_delay.assert_not_called()

    @override_settings(OIA_SERVICE_TOKEN=SERVICE_TOKEN)
    @patch("apps.onboarding.tasks.dispatch_process.delay")
    def test_changed_manifest_triggers_new_run(self, mock_delay, public_tenant):
        user, client = _editor(public_tenant)
        company = make_company(tenant=public_tenant, name="Change Co")
        session = make_session(
            company=company,
            tenant=public_tenant,
            status=SessionStatus.GATHERED,
            created_by=user,
        )
        make_recording(
            session=session,
            tenant=public_tenant,
            status=RecordingStatus.SUMMARIZED,
        )

        resp1 = client.post(f"{SESSIONS}{session.pk}/process/")
        assert resp1.status_code == status.HTTP_202_ACCEPTED

        session.refresh_from_db()
        session.status = SessionStatus.GATHERED
        session.process_job_id = "old-job"
        session.save(update_fields=["status", "process_job_id", "updated_at"])
        make_recording(
            session=session,
            tenant=public_tenant,
            status=RecordingStatus.SUMMARIZED,
        )

        mock_delay.reset_mock()
        resp2 = client.post(f"{SESSIONS}{session.pk}/process/")
        assert resp2.status_code == status.HTTP_202_ACCEPTED
        mock_delay.assert_called_once()

    @override_settings(OIA_SERVICE_TOKEN=SERVICE_TOKEN)
    @patch("apps.onboarding.tasks.dispatch_process.delay")
    def test_evidence_manifest_shape(self, mock_delay, public_tenant):
        user, client = _editor(public_tenant)
        company = make_company(tenant=public_tenant, name="Manifest Co")
        session = make_session(
            company=company,
            tenant=public_tenant,
            status=SessionStatus.GATHERED,
            created_by=user,
        )
        make_recording(
            session=session,
            tenant=public_tenant,
            status=RecordingStatus.SUMMARIZED,
        )

        client.post(f"{SESSIONS}{session.pk}/process/")
        call_kwargs = mock_delay.call_args[1]
        manifest = call_kwargs["manifest"]
        assert "recordings" in manifest
        assert "media" in manifest
        assert "has_questionnaire" in manifest
        assert "has_transcript" in manifest


class TestProcessCallback:
    """POST /internal/sessions/{id}/process/callback/ — OIA calls back."""

    @override_settings(OIA_SERVICE_TOKEN=SERVICE_TOKEN)
    def test_callback_succeeded_transitions_to_review_pending(self, public_tenant):
        company = make_company(tenant=public_tenant, name="Cb Co")
        session = make_session(
            company=company,
            tenant=public_tenant,
            status=SessionStatus.PROCESSING,
        )

        client = APIClient()
        client.defaults["SERVER_NAME"] = "localhost"
        url = f"/api/v1/onboarding/internal/sessions/" f"{session.pk}/process/callback/"
        resp = client.post(
            url,
            data={
                "job_id": "job-abc",
                "status": "SUCCEEDED",
                "summary": {"fields_extracted": 5},
            },
            format="json",
            HTTP_X_SERVICE_TOKEN=SERVICE_TOKEN,
            HTTP_X_TENANT_ID=str(public_tenant.pk),
        )
        assert resp.status_code == status.HTTP_200_OK

        session.refresh_from_db()
        assert session.status == SessionStatus.REVIEW_PENDING
        assert session.process_job_id == "job-abc"
        assert session.process_summary == {"fields_extracted": 5}

    @override_settings(OIA_SERVICE_TOKEN=SERVICE_TOKEN)
    def test_callback_failed_transitions_to_gathered(self, public_tenant):
        company = make_company(tenant=public_tenant, name="Fail Co")
        session = make_session(
            company=company,
            tenant=public_tenant,
            status=SessionStatus.PROCESSING,
        )

        client = APIClient()
        client.defaults["SERVER_NAME"] = "localhost"
        url = f"/api/v1/onboarding/internal/sessions/" f"{session.pk}/process/callback/"
        resp = client.post(
            url,
            data={"job_id": "job-fail", "status": "FAILED"},
            format="json",
            HTTP_X_SERVICE_TOKEN=SERVICE_TOKEN,
            HTTP_X_TENANT_ID=str(public_tenant.pk),
        )
        assert resp.status_code == status.HTTP_200_OK

        session.refresh_from_db()
        assert session.status == SessionStatus.GATHERED

    @override_settings(OIA_SERVICE_TOKEN=SERVICE_TOKEN)
    def test_callback_requires_service_token(self, public_tenant):
        company = make_company(tenant=public_tenant, name="Auth Co")
        session = make_session(
            company=company,
            tenant=public_tenant,
            status=SessionStatus.PROCESSING,
        )

        client = APIClient()
        client.defaults["SERVER_NAME"] = "localhost"
        url = f"/api/v1/onboarding/internal/sessions/" f"{session.pk}/process/callback/"
        resp = client.post(
            url,
            data={"status": "SUCCEEDED"},
            format="json",
            HTTP_X_TENANT_ID=str(public_tenant.pk),
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    @override_settings(OIA_SERVICE_TOKEN=SERVICE_TOKEN)
    def test_cross_tenant_process_returns_404(self, public_tenant):
        other_tenant = Tenant.objects.create(name="other-tenant", schema_name="other")
        company = make_company(tenant=public_tenant, name="Cross Co")
        session = make_session(
            company=company,
            tenant=public_tenant,
            status=SessionStatus.PROCESSING,
        )

        client = APIClient()
        client.defaults["SERVER_NAME"] = "localhost"
        url = f"/api/v1/onboarding/internal/sessions/" f"{session.pk}/process/callback/"
        resp = client.post(
            url,
            data={"status": "SUCCEEDED"},
            format="json",
            HTTP_X_SERVICE_TOKEN=SERVICE_TOKEN,
            HTTP_X_TENANT_ID=str(other_tenant.pk),
        )
        assert resp.status_code == status.HTTP_404_NOT_FOUND
