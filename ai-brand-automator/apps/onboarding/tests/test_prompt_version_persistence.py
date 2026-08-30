"""L-03 — Prompt version persistence tests.

Covers: process_callback persists prompt_versions from OIA,
patch_session_prompt_versions for LIVE mode persistence,
backward compatibility when prompt_versions absent, and
read-only enforcement via API.
"""

from __future__ import annotations

import pytest
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APIClient

from apps.onboarding.models import SessionStatus
from apps.onboarding.tests.factories import make_company, make_session

pytestmark = pytest.mark.django_db

SERVICE_TOKEN = "test-oia-svc-token-l03"
CALLBACK_URL = "/api/v1/onboarding/internal/sessions/{pk}/process/callback/"

SAMPLE_VERSIONS = {
    "zorven-oia-research-brief": "3",
    "zorven-oia-questionnaire": "2",
    "zorven-oia-analyze-stream": "1",
    "zorven-oia-sufficiency": "1",
    "zorven-oia-followups": "1",
    "zorven-oia-media-analysis": "2",
    "zorven-oia-media-analysis-multi": "1",
    "zorven-oia-summarize-recording": "1",
    "zorven-oia-extract-fields": "4",
}


class TestProcessCallbackPersistsPromptVersions:
    @override_settings(OIA_SERVICE_TOKEN=SERVICE_TOKEN)
    def test_process_callback_persists_prompt_versions(self, public_tenant):
        company = make_company(tenant=public_tenant, name="Version Co")
        session = make_session(
            company=company,
            tenant=public_tenant,
            status=SessionStatus.PROCESSING,
        )
        assert session.prompt_versions == {}

        client = APIClient()
        client.defaults["SERVER_NAME"] = "localhost"
        url = CALLBACK_URL.format(pk=session.pk)
        resp = client.post(
            url,
            data={
                "job_id": "job-v1",
                "status": "SUCCEEDED",
                "summary": {"fields_extracted": 9},
                "prompt_versions": SAMPLE_VERSIONS,
            },
            format="json",
            HTTP_X_SERVICE_TOKEN=SERVICE_TOKEN,
            HTTP_X_TENANT_ID=str(public_tenant.pk),
        )
        assert resp.status_code == status.HTTP_200_OK

        session.refresh_from_db()
        assert session.status == SessionStatus.REVIEW_PENDING
        assert session.prompt_versions == SAMPLE_VERSIONS

    @override_settings(OIA_SERVICE_TOKEN=SERVICE_TOKEN)
    def test_process_callback_without_versions_leaves_empty(self, public_tenant):
        company = make_company(tenant=public_tenant, name="NoVer Co")
        session = make_session(
            company=company,
            tenant=public_tenant,
            status=SessionStatus.PROCESSING,
        )

        client = APIClient()
        client.defaults["SERVER_NAME"] = "localhost"
        url = CALLBACK_URL.format(pk=session.pk)
        resp = client.post(
            url,
            data={
                "job_id": "job-v2",
                "status": "SUCCEEDED",
                "summary": {"ok": True},
            },
            format="json",
            HTTP_X_SERVICE_TOKEN=SERVICE_TOKEN,
            HTTP_X_TENANT_ID=str(public_tenant.pk),
        )
        assert resp.status_code == status.HTTP_200_OK

        session.refresh_from_db()
        assert session.prompt_versions == {}

    @override_settings(OIA_SERVICE_TOKEN=SERVICE_TOKEN)
    def test_failed_callback_does_not_persist_versions(self, public_tenant):
        company = make_company(tenant=public_tenant, name="Fail Ver Co")
        session = make_session(
            company=company,
            tenant=public_tenant,
            status=SessionStatus.PROCESSING,
        )

        client = APIClient()
        client.defaults["SERVER_NAME"] = "localhost"
        url = CALLBACK_URL.format(pk=session.pk)
        resp = client.post(
            url,
            data={
                "job_id": "job-v3",
                "status": "FAILED",
                "prompt_versions": SAMPLE_VERSIONS,
            },
            format="json",
            HTTP_X_SERVICE_TOKEN=SERVICE_TOKEN,
            HTTP_X_TENANT_ID=str(public_tenant.pk),
        )
        assert resp.status_code == status.HTTP_200_OK

        session.refresh_from_db()
        assert session.status == SessionStatus.GATHERED
        assert session.prompt_versions == {}

    @override_settings(OIA_SERVICE_TOKEN=SERVICE_TOKEN)
    def test_prompt_versions_invalid_type_ignored(self, public_tenant):
        company = make_company(tenant=public_tenant, name="BadType Co")
        session = make_session(
            company=company,
            tenant=public_tenant,
            status=SessionStatus.PROCESSING,
        )

        client = APIClient()
        client.defaults["SERVER_NAME"] = "localhost"
        url = CALLBACK_URL.format(pk=session.pk)
        resp = client.post(
            url,
            data={
                "job_id": "job-v4",
                "status": "SUCCEEDED",
                "summary": {},
                "prompt_versions": "not-a-dict",
            },
            format="json",
            HTTP_X_SERVICE_TOKEN=SERVICE_TOKEN,
            HTTP_X_TENANT_ID=str(public_tenant.pk),
        )
        assert resp.status_code == status.HTTP_200_OK

        session.refresh_from_db()
        assert session.prompt_versions == {}


LIVE_URL = "/api/v1/onboarding/internal/sessions/{pk}/prompt-versions/"


class TestLivePromptVersionsPersistence:
    """LIVE mode persists prompt_versions via a dedicated PATCH endpoint."""

    @override_settings(OIA_SERVICE_TOKEN=SERVICE_TOKEN)
    def test_live_persists_prompt_versions(self, public_tenant):
        company = make_company(tenant=public_tenant, name="Live Co")
        session = make_session(
            company=company,
            tenant=public_tenant,
            status=SessionStatus.MEETING_LIVE,
        )
        assert session.prompt_versions == {}

        client = APIClient()
        client.defaults["SERVER_NAME"] = "localhost"
        url = LIVE_URL.format(pk=session.pk)
        resp = client.patch(
            url,
            data={"prompt_versions": SAMPLE_VERSIONS},
            format="json",
            HTTP_X_SERVICE_TOKEN=SERVICE_TOKEN,
            HTTP_X_TENANT_ID=str(public_tenant.pk),
        )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()["stored"] is True

        session.refresh_from_db()
        assert session.prompt_versions == SAMPLE_VERSIONS

    @override_settings(OIA_SERVICE_TOKEN=SERVICE_TOKEN)
    def test_live_rejects_empty_versions(self, public_tenant):
        company = make_company(tenant=public_tenant, name="EmptyLive Co")
        session = make_session(
            company=company,
            tenant=public_tenant,
            status=SessionStatus.MEETING_LIVE,
        )

        client = APIClient()
        client.defaults["SERVER_NAME"] = "localhost"
        url = LIVE_URL.format(pk=session.pk)
        resp = client.patch(
            url,
            data={"prompt_versions": {}},
            format="json",
            HTTP_X_SERVICE_TOKEN=SERVICE_TOKEN,
            HTTP_X_TENANT_ID=str(public_tenant.pk),
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    @override_settings(OIA_SERVICE_TOKEN=SERVICE_TOKEN)
    def test_live_rejects_bad_token(self, public_tenant):
        company = make_company(tenant=public_tenant, name="BadToken Co")
        session = make_session(
            company=company,
            tenant=public_tenant,
            status=SessionStatus.MEETING_LIVE,
        )

        client = APIClient()
        client.defaults["SERVER_NAME"] = "localhost"
        url = LIVE_URL.format(pk=session.pk)
        resp = client.patch(
            url,
            data={"prompt_versions": SAMPLE_VERSIONS},
            format="json",
            HTTP_X_SERVICE_TOKEN="wrong-token",
            HTTP_X_TENANT_ID=str(public_tenant.pk),
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    @override_settings(OIA_SERVICE_TOKEN=SERVICE_TOKEN)
    def test_live_returns_404_for_unknown_session(self, public_tenant):
        client = APIClient()
        client.defaults["SERVER_NAME"] = "localhost"
        url = LIVE_URL.format(pk=99999)
        resp = client.patch(
            url,
            data={"prompt_versions": SAMPLE_VERSIONS},
            format="json",
            HTTP_X_SERVICE_TOKEN=SERVICE_TOKEN,
            HTTP_X_TENANT_ID=str(public_tenant.pk),
        )
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    @override_settings(OIA_SERVICE_TOKEN=SERVICE_TOKEN)
    def test_live_works_for_any_session_status(self, public_tenant):
        """Prompt versions can be persisted regardless of session status."""
        company = make_company(tenant=public_tenant, name="AnyStatus Co")
        session = make_session(
            company=company,
            tenant=public_tenant,
            status=SessionStatus.GATHERED,
        )

        client = APIClient()
        client.defaults["SERVER_NAME"] = "localhost"
        url = LIVE_URL.format(pk=session.pk)
        resp = client.patch(
            url,
            data={"prompt_versions": SAMPLE_VERSIONS},
            format="json",
            HTTP_X_SERVICE_TOKEN=SERVICE_TOKEN,
            HTTP_X_TENANT_ID=str(public_tenant.pk),
        )
        assert resp.status_code == status.HTTP_200_OK

        session.refresh_from_db()
        assert session.prompt_versions == SAMPLE_VERSIONS
