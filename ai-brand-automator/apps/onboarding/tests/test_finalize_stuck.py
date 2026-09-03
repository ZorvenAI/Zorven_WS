"""M-04 — stuck-session finalize endpoint.

The OIA watchdog calls POST /api/v1/onboarding/internal/sessions/<pk>/finalize-stuck/
to transition a stuck MEETING_LIVE session to GATHERED.
"""

from __future__ import annotations

import pytest
from django.conf import settings
from rest_framework.test import APIClient

from apps.onboarding.models import SessionStatus
from apps.onboarding.tests.factories import make_session

pytestmark = pytest.mark.django_db

FINALIZE_URL = "/api/v1/onboarding/internal/sessions/{pk}/finalize-stuck/"
TOKEN = (
    getattr(settings, "OIA_SERVICE_TOKEN", "") or settings.ORCHESTRATOR_SERVICE_TOKEN
)


def _service_client(tenant) -> APIClient:
    client = APIClient()
    client.defaults["SERVER_NAME"] = "localhost"
    client.defaults["HTTP_X_SERVICE_TOKEN"] = TOKEN
    client.defaults["HTTP_X_TENANT_ID"] = str(tenant.id)
    return client


@pytest.fixture
def tenant(public_tenant):
    return public_tenant


@pytest.fixture
def live_session(tenant):
    return make_session(tenant=tenant, status=SessionStatus.MEETING_LIVE)


def test_finalize_stuck_transitions_to_gathered(tenant, live_session):
    client = _service_client(tenant)
    url = FINALIZE_URL.format(pk=live_session.pk)
    resp = client.post(url, {"reason": "watchdog_stuck_session"}, format="json")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == SessionStatus.GATHERED
    assert body["session_id"] == live_session.pk

    live_session.refresh_from_db()
    assert live_session.status == SessionStatus.GATHERED


def test_finalize_stuck_rejects_non_meeting_live(tenant):
    session = make_session(tenant=tenant, status=SessionStatus.GATHERED)
    client = _service_client(tenant)
    url = FINALIZE_URL.format(pk=session.pk)
    resp = client.post(url, {"reason": "watchdog_stuck_session"}, format="json")
    assert resp.status_code == 409
    body = resp.json()
    assert body["current_status"] == SessionStatus.GATHERED


def test_finalize_stuck_requires_service_token(tenant, live_session):
    client = APIClient()
    client.defaults["SERVER_NAME"] = "localhost"
    url = FINALIZE_URL.format(pk=live_session.pk)
    resp = client.post(url, {"reason": "watchdog_stuck_session"}, format="json")
    assert resp.status_code == 403


def test_finalize_stuck_session_not_found(tenant):
    client = _service_client(tenant)
    url = FINALIZE_URL.format(pk=99999)
    resp = client.post(url, {"reason": "watchdog_stuck_session"}, format="json")
    assert resp.status_code == 404
