"""M-03 · Configurable retention and enforcement tests.

Covers: per-tenant retention config API (RBAC, validation, impact
warning on shortening) and the Celery Beat enforcement task.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.onboarding.erasure.models import ErasureLog, RetentionConfig
from apps.onboarding.models import (
    ConsentRecord,
    OnboardingSession,
    SessionStatus,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def api_client():
    client = APIClient()
    client.defaults["SERVER_NAME"] = "localhost"
    return client


@pytest.fixture
def company(db, tenant):
    from onboarding.models import Company

    return Company.objects.create(tenant=tenant, name="Retention Co")


def _make_client(api_client, tenant, role):
    from tenants.models import Membership

    user = User.objects.create_user(
        username=f"ret_{role}_{tenant.pk}",
        email=f"ret_{role}_{tenant.pk}@test.com",
        password="TestPass123!",
    )
    Membership.objects.create(user=user, tenant=tenant, role=role)
    api_client.force_authenticate(user=user)
    api_client.credentials(HTTP_X_TENANT_ID=str(tenant.id))
    return api_client


@pytest.fixture
def admin_client(api_client, tenant):
    from tenants.models import Membership

    return _make_client(api_client, tenant, Membership.Role.ADMIN)


@pytest.fixture
def owner_client(tenant):
    from tenants.models import Membership

    client = APIClient()
    client.defaults["SERVER_NAME"] = "localhost"
    return _make_client(client, tenant, Membership.Role.OWNER)


@pytest.fixture
def editor_client(tenant):
    from tenants.models import Membership

    client = APIClient()
    client.defaults["SERVER_NAME"] = "localhost"
    return _make_client(client, tenant, Membership.Role.EDITOR)


@pytest.fixture
def viewer_client(tenant):
    from tenants.models import Membership

    client = APIClient()
    client.defaults["SERVER_NAME"] = "localhost"
    return _make_client(client, tenant, Membership.Role.VIEWER)


def _create_subject(tenant, company, subject_name, days_ago):
    """Create a session + consent record with created_at in the past."""
    session = OnboardingSession.objects.create(
        tenant=tenant,
        company=company,
        status=SessionStatus.COMPLETED,
    )
    consent = ConsentRecord.objects.create(
        tenant=tenant,
        session=session,
        subject_name=subject_name,
        granted_at=timezone.now(),
    )
    past = timezone.now() - timedelta(days=days_ago)
    OnboardingSession.objects.filter(pk=session.pk).update(created_at=past)
    return session, consent


# ---------------------------------------------------------------------------
# GET /api/v1/onboarding/retention/
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestRetentionGet:
    def test_get_retention_default(self, admin_client):
        resp = admin_client.get("/api/v1/onboarding/retention/")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["retention_days"] == 365
        assert resp.data["is_default"] is True
        assert "next_enforcement_run" in resp.data

    def test_get_retention_custom(self, admin_client, tenant):
        RetentionConfig.objects.create(tenant=tenant, retention_days=90)
        resp = admin_client.get("/api/v1/onboarding/retention/")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["retention_days"] == 90
        assert resp.data["is_default"] is False


# ---------------------------------------------------------------------------
# PATCH /api/v1/onboarding/retention/ — RBAC
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestRetentionRBAC:
    def test_admin_can_set_retention(self, admin_client):
        resp = admin_client.patch(
            "/api/v1/onboarding/retention/",
            {"retention_days": 180},
            format="json",
        )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["retention_days"] == 180

    def test_owner_can_set_retention(self, owner_client):
        resp = owner_client.patch(
            "/api/v1/onboarding/retention/",
            {"retention_days": 180},
            format="json",
        )
        assert resp.status_code == status.HTTP_200_OK

    def test_editor_cannot_set_retention(self, editor_client):
        resp = editor_client.patch(
            "/api/v1/onboarding/retention/",
            {"retention_days": 180},
            format="json",
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_viewer_cannot_set_retention(self, viewer_client):
        resp = viewer_client.patch(
            "/api/v1/onboarding/retention/",
            {"retention_days": 180},
            format="json",
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_unauthenticated_returns_error(self, api_client):
        resp = api_client.patch(
            "/api/v1/onboarding/retention/",
            {"retention_days": 180},
            format="json",
        )
        assert resp.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )


# ---------------------------------------------------------------------------
# PATCH /api/v1/onboarding/retention/ — validation and impact
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestRetentionPatch:
    def test_patch_retention_creates_config(self, admin_client, tenant):
        assert not RetentionConfig.objects.filter(tenant=tenant).exists()
        resp = admin_client.patch(
            "/api/v1/onboarding/retention/",
            {"retention_days": 90},
            format="json",
        )
        assert resp.status_code == status.HTTP_200_OK
        assert RetentionConfig.objects.filter(tenant=tenant, retention_days=90).exists()

    def test_patch_retention_updates_existing(self, admin_client, tenant):
        RetentionConfig.objects.create(tenant=tenant, retention_days=365)
        resp = admin_client.patch(
            "/api/v1/onboarding/retention/",
            {"retention_days": 60},
            format="json",
        )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["retention_days"] == 60
        assert resp.data["previous_days"] == 365

    def test_retention_validation_bounds(self, admin_client):
        resp = admin_client.patch(
            "/api/v1/onboarding/retention/",
            {"retention_days": 0},
            format="json",
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

        resp = admin_client.patch(
            "/api/v1/onboarding/retention/",
            {"retention_days": 3651},
            format="json",
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_shortening_warns_with_counts(self, admin_client, tenant, company):
        RetentionConfig.objects.create(tenant=tenant, retention_days=365)

        _create_subject(tenant, company, "Old Subject", days_ago=100)
        _create_subject(tenant, company, "Recent Subject", days_ago=10)

        resp = admin_client.patch(
            "/api/v1/onboarding/retention/",
            {"retention_days": 30},
            format="json",
        )
        assert resp.status_code == status.HTTP_200_OK
        assert "impact" in resp.data
        assert resp.data["impact"]["subjects"] >= 1
        assert resp.data["impact"]["sessions"] >= 1
        assert "enforced_at" in resp.data["impact"]

    def test_lengthening_no_impact(self, admin_client, tenant, company):
        RetentionConfig.objects.create(tenant=tenant, retention_days=30)
        _create_subject(tenant, company, "Some Subject", days_ago=100)

        resp = admin_client.patch(
            "/api/v1/onboarding/retention/",
            {"retention_days": 365},
            format="json",
        )
        assert resp.status_code == status.HTTP_200_OK
        assert "impact" not in resp.data


# ---------------------------------------------------------------------------
# enforce_retention_windows beat task
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
class TestRetentionEnforcement:
    def test_beat_job_erases_expired_subjects(self, tenant, company):
        from apps.onboarding.erasure.tasks import enforce_retention_windows

        RetentionConfig.objects.create(tenant=tenant, retention_days=30)
        _create_subject(tenant, company, "Expired Subject", days_ago=60)

        result = enforce_retention_windows()
        assert result["dispatched"] >= 1

        assert ErasureLog.objects.filter(
            tenant=tenant,
            subject_name="Expired Subject",
            reason="retention_enforcement",
        ).exists()

    def test_beat_job_skips_recent_subjects(self, tenant, company):
        from apps.onboarding.erasure.tasks import enforce_retention_windows

        RetentionConfig.objects.create(tenant=tenant, retention_days=365)
        _create_subject(tenant, company, "Fresh Subject", days_ago=10)

        result = enforce_retention_windows()
        assert result["dispatched"] == 0

        assert not ErasureLog.objects.filter(
            subject_name="Fresh Subject",
            reason="retention_enforcement",
        ).exists()

    def test_beat_job_idempotent(self, tenant, company):
        from apps.onboarding.erasure.tasks import enforce_retention_windows

        RetentionConfig.objects.create(tenant=tenant, retention_days=30)
        _create_subject(tenant, company, "Idem Subject", days_ago=60)

        result1 = enforce_retention_windows()
        count1 = ErasureLog.objects.filter(
            tenant=tenant, reason="retention_enforcement"
        ).count()

        result2 = enforce_retention_windows()
        count2 = ErasureLog.objects.filter(
            tenant=tenant, reason="retention_enforcement"
        ).count()

        assert result1["dispatched"] >= 1
        assert result2["dispatched"] == 0
        assert count2 == count1

    def test_beat_job_uses_default_without_config(self, tenant, company):
        from apps.onboarding.erasure.tasks import enforce_retention_windows

        _create_subject(tenant, company, "Default Subject", days_ago=10)

        result = enforce_retention_windows()
        assert result["dispatched"] == 0
