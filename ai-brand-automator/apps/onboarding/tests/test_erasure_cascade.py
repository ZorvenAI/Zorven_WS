"""M-02 · End-to-end cascade tests with real Django models."""

from __future__ import annotations

import pytest
from django.utils import timezone

from apps.onboarding.erasure.cascade import ErasureCascade
from apps.onboarding.erasure.registry import StoreRegistry
from apps.onboarding.erasure.stores.django_brand_assets import (
    DjangoBrandAssetStore,
)
from apps.onboarding.erasure.stores.django_sessions import DjangoSessionStore
from apps.onboarding.erasure.stores.gcs_blobs import GCSBlobStore
from apps.onboarding.erasure.stores.oia_redis import OIARedisStore
from apps.onboarding.erasure.stores.poi_golden_datasets import POIGoldenStore
from apps.onboarding.erasure.stores.rag_index_store import RAGIndexStore
from apps.onboarding.models import (
    ConsentRecord,
    OnboardingSession,
    SessionStatus,
)

ALL_STORE_CLASSES = [
    DjangoBrandAssetStore,
    DjangoSessionStore,
    GCSBlobStore,
    OIARedisStore,
    POIGoldenStore,
    RAGIndexStore,
]


def _register_all_stores():
    for cls in ALL_STORE_CLASSES:
        StoreRegistry.register(cls)


@pytest.fixture(autouse=True)
def _reset_registry():
    StoreRegistry.reset()
    yield
    StoreRegistry.reset()


@pytest.fixture
def company(db, tenant):
    from onboarding.models import Company

    return Company.objects.create(
        tenant=tenant,
        name="Test GDPR Co",
    )


@pytest.mark.django_db(transaction=True)
class TestErasureCascadeNoSessions:
    def test_empty_cascade_returns_complete(self, tenant):
        _register_all_stores()
        report = ErasureCascade().execute(
            tenant_id=str(tenant.pk),
            subject_name="nobody",
        )
        assert report.completeness_verified is True
        assert len(report.store_results) == 0


@pytest.mark.django_db(transaction=True)
class TestErasureCascadeWithData:
    def test_django_sessions_deleted(self, tenant, company):
        _register_all_stores()

        session = OnboardingSession.objects.create(
            tenant=tenant,
            company=company,
            status=SessionStatus.COMPLETED,
        )
        ConsentRecord.objects.create(
            tenant=tenant,
            session=session,
            subject_name="Test Subject",
            granted_at=timezone.now(),
        )

        report = ErasureCascade().execute(
            tenant_id=str(tenant.pk),
            subject_name="Test Subject",
        )

        assert not OnboardingSession.objects.filter(pk=session.pk).exists()
        assert not ConsentRecord.objects.filter(session=session).exists()

        django_result = next(
            r for r in report.store_results if r.store_name == "django_sessions"
        )
        assert django_result.ok
        assert django_result.items_erased >= 1

    def test_cascade_continues_on_store_failure(self, tenant, company, mocker):
        _register_all_stores()

        session = OnboardingSession.objects.create(
            tenant=tenant,
            company=company,
            status=SessionStatus.COMPLETED,
        )
        ConsentRecord.objects.create(
            tenant=tenant,
            session=session,
            subject_name="Fail Subject",
            granted_at=timezone.now(),
        )

        mocker.patch(
            "apps.onboarding.erasure.stores.gcs_blobs.GCSBlobStore.erase",
            side_effect=RuntimeError("GCS down"),
        )

        report = ErasureCascade().execute(
            tenant_id=str(tenant.pk),
            subject_name="Fail Subject",
        )

        assert report.completeness_verified is False
        gcs_result = next(
            r for r in report.store_results if r.store_name == "gcs_storage"
        )
        assert not gcs_result.ok

        django_result = next(
            r for r in report.store_results if r.store_name == "django_sessions"
        )
        assert django_result.ok

    def test_report_to_dict_is_serializable(self, tenant, company):
        import json

        _register_all_stores()

        session = OnboardingSession.objects.create(
            tenant=tenant,
            company=company,
            status=SessionStatus.COMPLETED,
        )
        ConsentRecord.objects.create(
            tenant=tenant,
            session=session,
            subject_name="Serialize Subject",
            granted_at=timezone.now(),
        )

        report = ErasureCascade().execute(
            tenant_id=str(tenant.pk),
            subject_name="Serialize Subject",
        )

        data = report.to_dict()
        serialized = json.dumps(data)
        assert len(serialized) > 0
        assert data["tenant_id"] == str(tenant.pk)
