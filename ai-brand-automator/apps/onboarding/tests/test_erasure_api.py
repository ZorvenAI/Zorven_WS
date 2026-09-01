"""M-02 · Erasure API endpoint tests — RBAC + consent trigger."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.onboarding.models import (
    ConsentRecord,
    OnboardingSession,
    SessionStatus,
)

User = get_user_model()


@pytest.fixture
def api_client():
    client = APIClient()
    client.defaults["SERVER_NAME"] = "localhost"
    return client


@pytest.fixture
def company(db, tenant):
    from onboarding.models import Company

    return Company.objects.create(
        tenant=tenant,
        name="Test GDPR Co",
    )


@pytest.fixture
def admin_client_with_tenant(api_client, tenant):
    from tenants.models import Membership

    admin = User.objects.create_user(
        username="erasure_admin",
        email="erasure_admin@test.com",
        password="TestPass123!",
    )
    Membership.objects.create(
        user=admin,
        tenant=tenant,
        role=Membership.Role.ADMIN,
    )
    api_client.force_authenticate(user=admin)
    api_client.credentials(HTTP_X_TENANT_ID=str(tenant.id))
    return api_client


@pytest.fixture
def viewer_client_with_tenant(api_client, tenant):
    from tenants.models import Membership

    viewer = User.objects.create_user(
        username="erasure_viewer",
        email="erasure_viewer@test.com",
        password="TestPass123!",
    )
    Membership.objects.create(
        user=viewer,
        tenant=tenant,
        role=Membership.Role.VIEWER,
    )
    api_client.force_authenticate(user=viewer)
    api_client.credentials(HTTP_X_TENANT_ID=str(tenant.id))
    return api_client


@pytest.mark.django_db
class TestErasureEndpointRBAC:
    def test_admin_can_request_erasure(self, admin_client_with_tenant, tenant, company):
        session = OnboardingSession.objects.create(
            tenant=tenant,
            company=company,
            status=SessionStatus.COMPLETED,
        )
        ConsentRecord.objects.create(
            tenant=tenant,
            session=session,
            subject_name="Admin Subject",
            granted_at=timezone.now(),
        )

        resp = admin_client_with_tenant.post(
            "/api/v1/onboarding/erasure/",
            {"subject_name": "Admin Subject", "reason": "GDPR request"},
            format="json",
        )
        assert resp.status_code == status.HTTP_202_ACCEPTED
        assert resp.data["subject_name"] == "Admin Subject"

    def test_viewer_cannot_request_erasure(
        self, viewer_client_with_tenant, tenant, company
    ):
        session = OnboardingSession.objects.create(
            tenant=tenant,
            company=company,
            status=SessionStatus.COMPLETED,
        )
        ConsentRecord.objects.create(
            tenant=tenant,
            session=session,
            subject_name="Viewer Subject",
            granted_at=timezone.now(),
        )

        resp = viewer_client_with_tenant.post(
            "/api/v1/onboarding/erasure/",
            {"subject_name": "Viewer Subject", "reason": "GDPR request"},
            format="json",
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_nonexistent_subject_returns_404(self, admin_client_with_tenant, tenant):
        resp = admin_client_with_tenant.post(
            "/api/v1/onboarding/erasure/",
            {"subject_name": "Ghost", "reason": "test"},
            format="json",
        )
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_unauthenticated_returns_error(self, api_client):
        resp = api_client.post(
            "/api/v1/onboarding/erasure/",
            {"subject_name": "Test", "reason": "test"},
            format="json",
        )
        assert resp.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )


@pytest.mark.django_db
class TestErasureLogList:
    def test_admin_can_list_logs(self, admin_client_with_tenant):
        resp = admin_client_with_tenant.get("/api/v1/onboarding/erasure/logs/")
        assert resp.status_code == status.HTTP_200_OK
        assert isinstance(resp.data, list)
