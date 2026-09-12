"""J-03 — internal endpoint tests for field extraction write-back.

Tests the three endpoints OIA uses to persist extraction results:
- PATCH /api/v1/onboarding/internal/companies/<pk>/fields/
- POST /api/v1/onboarding/internal/sessions/<pk>/provenance/bulk/
- GET /api/v1/onboarding/internal/sessions/<pk>/provenance/
"""

from __future__ import annotations

import pytest
from django.conf import settings
from rest_framework.test import APIClient

from apps.onboarding.models import (
    FieldProvenance,
    ProvenanceStatus,
)
from apps.onboarding.tests.factories import (
    make_company,
    make_provenance,
    make_recording,
    make_session,
)

pytestmark = pytest.mark.django_db

COMPANY_FIELDS_URL = "/api/v1/onboarding/internal/companies/{pk}/fields/"
PROVENANCE_BULK_URL = "/api/v1/onboarding/internal/sessions/{pk}/provenance/bulk/"
PROVENANCE_READ_URL = "/api/v1/onboarding/internal/sessions/{pk}/provenance/"
TOKEN = settings.OIA_SERVICE_TOKEN


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
def company(tenant):
    return make_company(tenant)


@pytest.fixture
def session(company, tenant):
    return make_session(company=company, tenant=tenant)


@pytest.fixture
def recording(session, tenant):
    return make_recording(session=session, tenant=tenant)


# ── PATCH /internal/companies/<pk>/fields/ ─────────────────────


def test_patch_company_fields_writes_subset(tenant, company):
    client = _service_client(tenant)
    url = COMPANY_FIELDS_URL.format(pk=company.pk)
    resp = client.patch(
        url,
        {"name": "Updated Co", "industry": "Technology"},
        format="json",
    )
    assert resp.status_code == 200
    body = resp.json()
    assert set(body["fields_written"]) == {"name", "industry"}

    company.refresh_from_db()
    assert company.name == "Updated Co"
    assert company.industry == "Technology"


def test_patch_company_fields_rejects_unmapped(tenant, company):
    """Unknown fields are silently filtered, not written."""
    client = _service_client(tenant)
    url = COMPANY_FIELDS_URL.format(pk=company.pk)
    resp = client.patch(
        url,
        {"name": "Good", "bogus_field_xyz": "ignored"},
        format="json",
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "bogus_field_xyz" not in body["fields_written"]
    assert "name" in body["fields_written"]


def test_patch_company_fields_403_without_token(tenant, company):
    client = APIClient()
    client.defaults["SERVER_NAME"] = "localhost"
    client.defaults["HTTP_X_TENANT_ID"] = str(tenant.id)
    url = COMPANY_FIELDS_URL.format(pk=company.pk)
    resp = client.patch(url, {"name": "Nope"}, format="json")
    assert resp.status_code == 403


def test_patch_company_fields_404_wrong_pk(tenant):
    client = _service_client(tenant)
    url = COMPANY_FIELDS_URL.format(pk=99999)
    resp = client.patch(url, {"name": "Ghost"}, format="json")
    assert resp.status_code == 404


def test_patch_company_fields_validates_shapes(tenant, company):
    """Serializer validation catches bad field shapes."""
    client = _service_client(tenant)
    url = COMPANY_FIELDS_URL.format(pk=company.pk)
    resp = client.patch(
        url,
        {"competitors": "not-a-list"},
        format="json",
    )
    assert resp.status_code == 400


# ── POST /internal/sessions/<pk>/provenance/bulk/ ──────────────


def test_provenance_bulk_create(tenant, session, recording):
    client = _service_client(tenant)
    url = PROVENANCE_BULK_URL.format(pk=session.pk)
    resp = client.post(
        url,
        {
            "records": [
                {
                    "model_name": "Company",
                    "field_name": "name",
                    "extracted_value": "Chai Point",
                    "confidence": 0.95,
                    "classification": "KEY",
                    "source_recording_id": str(recording.pk),
                    "source_span": {
                        "recording_id": str(recording.pk),
                        "t_start": 10.0,
                        "t_end": 25.0,
                    },
                },
                {
                    "model_name": "Company",
                    "field_name": "industry",
                    "extracted_value": "Food & Beverage",
                    "confidence": 0.9,
                    "classification": "KEY",
                    "source_recording_id": str(recording.pk),
                    "source_span": {
                        "recording_id": str(recording.pk),
                        "t_start": 30.0,
                        "t_end": 40.0,
                    },
                },
            ]
        },
        format="json",
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] == 2
    assert body["updated"] == 0

    assert FieldProvenance.objects.filter(session=session).count() == 2


def test_provenance_bulk_pg06_protection(tenant, session):
    """PG-06: CONFIRMED provenance is never overwritten."""
    make_provenance(
        session=session,
        tenant=tenant,
        field_name="name",
        extracted_value="Original Name",
        status=ProvenanceStatus.CONFIRMED,
    )

    client = _service_client(tenant)
    url = PROVENANCE_BULK_URL.format(pk=session.pk)
    resp = client.post(
        url,
        {
            "records": [
                {
                    "model_name": "Company",
                    "field_name": "name",
                    "extracted_value": "New Name",
                    "confidence": 0.95,
                    "classification": "KEY",
                    "source_span": {"recording_id": "r1", "t_start": 1, "t_end": 2},
                },
            ]
        },
        format="json",
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] == 0
    assert body["updated"] == 0
    assert len(body["skipped"]) == 1
    assert body["skipped"][0]["status"] == "CONFIRMED"
    assert len(body["conflicts"]) == 1
    assert body["conflicts"][0]["existing_value"] == "Original Name"

    prov = FieldProvenance.objects.get(session=session, field_name="name")
    assert prov.extracted_value == "Original Name"


def test_provenance_bulk_edited_also_protected(tenant, session):
    """PG-06: EDITED provenance is protected too."""
    make_provenance(
        session=session,
        tenant=tenant,
        field_name="industry",
        extracted_value="Old Industry",
        status=ProvenanceStatus.EDITED,
    )

    client = _service_client(tenant)
    url = PROVENANCE_BULK_URL.format(pk=session.pk)
    resp = client.post(
        url,
        {
            "records": [
                {
                    "model_name": "Company",
                    "field_name": "industry",
                    "extracted_value": "New Industry",
                    "confidence": 0.9,
                    "classification": "KEY",
                    "source_span": {"recording_id": "r1", "t_start": 1, "t_end": 2},
                },
            ]
        },
        format="json",
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] == 0
    assert len(body["skipped"]) == 1
    assert body["skipped"][0]["status"] == "EDITED"


def test_provenance_bulk_updates_pending(tenant, session):
    """PENDING provenance can be updated (not protected by PG-06)."""
    make_provenance(
        session=session,
        tenant=tenant,
        field_name="industry",
        extracted_value="Old Value",
        status=ProvenanceStatus.PENDING,
    )

    client = _service_client(tenant)
    url = PROVENANCE_BULK_URL.format(pk=session.pk)
    resp = client.post(
        url,
        {
            "records": [
                {
                    "model_name": "Company",
                    "field_name": "industry",
                    "extracted_value": "New Value",
                    "confidence": 0.85,
                    "classification": "SECONDARY",
                    "source_span": {"recording_id": "r1", "t_start": 1, "t_end": 2},
                },
            ]
        },
        format="json",
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["updated"] == 1
    assert body["created"] == 0
    assert len(body["skipped"]) == 0

    prov = FieldProvenance.objects.get(session=session, field_name="industry")
    assert prov.extracted_value == "New Value"
    assert prov.status == ProvenanceStatus.PENDING


def test_provenance_bulk_403_without_token(tenant, session):
    client = APIClient()
    client.defaults["SERVER_NAME"] = "localhost"
    client.defaults["HTTP_X_TENANT_ID"] = str(tenant.id)
    url = PROVENANCE_BULK_URL.format(pk=session.pk)
    resp = client.post(
        url,
        {"records": []},
        format="json",
    )
    assert resp.status_code == 403


def test_provenance_bulk_404_wrong_session(tenant):
    client = _service_client(tenant)
    url = PROVENANCE_BULK_URL.format(pk=99999)
    resp = client.post(
        url,
        {"records": []},
        format="json",
    )
    assert resp.status_code == 404


# ── GET /internal/sessions/<pk>/provenance/ ────────────────────


def test_existing_provenance_read(tenant, session):
    make_provenance(
        session=session,
        tenant=tenant,
        field_name="name",
        extracted_value="Chai Point",
        status=ProvenanceStatus.CONFIRMED,
    )
    make_provenance(
        session=session,
        tenant=tenant,
        field_name="industry",
        extracted_value="F&B",
        status=ProvenanceStatus.PENDING,
    )

    client = _service_client(tenant)
    url = PROVENANCE_READ_URL.format(pk=session.pk)
    resp = client.get(url, format="json")
    assert resp.status_code == 200

    records = resp.json()["records"]
    assert len(records) == 2

    by_field = {r["field_name"]: r for r in records}
    assert by_field["name"]["status"] == "CONFIRMED"
    assert by_field["industry"]["status"] == "PENDING"


def test_provenance_read_empty(tenant, session):
    client = _service_client(tenant)
    url = PROVENANCE_READ_URL.format(pk=session.pk)
    resp = client.get(url, format="json")
    assert resp.status_code == 200
    assert resp.json()["records"] == []


def test_provenance_bulk_conflict_marks_existing(tenant, session):
    """J-05: incoming status=CONFLICT marks the existing protected record."""
    make_provenance(
        session=session,
        tenant=tenant,
        field_name="name",
        extracted_value="Confirmed Name",
        status=ProvenanceStatus.CONFIRMED,
    )

    client = _service_client(tenant)
    url = PROVENANCE_BULK_URL.format(pk=session.pk)
    resp = client.post(
        url,
        {
            "records": [
                {
                    "model_name": "Company",
                    "field_name": "name",
                    "extracted_value": "Different Name",
                    "confidence": 0.92,
                    "classification": "KEY",
                    "source_span": {"recording_id": "r1", "t_start": 1, "t_end": 2},
                    "status": "CONFLICT",
                },
            ]
        },
        format="json",
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["updated"] == 1
    assert len(body["conflicts"]) == 1
    assert body["conflicts"][0]["marked"] is True
    assert len(body["skipped"]) == 0

    prov = FieldProvenance.objects.get(session=session, field_name="name")
    assert prov.status == ProvenanceStatus.CONFLICT
    assert prov.extracted_value == "Confirmed Name"


def test_provenance_read_403_without_token(tenant, session):
    client = APIClient()
    client.defaults["SERVER_NAME"] = "localhost"
    client.defaults["HTTP_X_TENANT_ID"] = str(tenant.id)
    url = PROVENANCE_READ_URL.format(pk=session.pk)
    resp = client.get(url, format="json")
    assert resp.status_code == 403
