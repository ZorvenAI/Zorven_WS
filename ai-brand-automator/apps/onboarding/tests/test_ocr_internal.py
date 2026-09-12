"""H-03 — internal OCR update endpoint.

The OIA service calls PATCH /api/v1/internal/assets/<pk>/ocr/
to write ocr_text, ocr_confidence, sensitivity_class, and rag_excluded
back to a BrandAsset after running the OCR pipeline.
"""

from __future__ import annotations

import pytest
from django.conf import settings
from rest_framework.test import APIClient

from apps.onboarding.tests.factories import make_company
from onboarding.models import BrandAsset
from tenants.models import Tenant

pytestmark = pytest.mark.django_db

OCR_URL = "/api/v1/internal/assets/{pk}/ocr/"
TOKEN = settings.ORCHESTRATOR_SERVICE_TOKEN


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
def asset(tenant):
    company = make_company(tenant)
    return BrandAsset.objects.create(
        tenant=tenant,
        company=company,
        file_name="receipt.jpg",
        file_type="image",
        file_size=4096,
    )


def test_ocr_update_endpoint_200(tenant, asset):
    client = _service_client(tenant)
    url = OCR_URL.format(pk=asset.pk)
    resp = client.patch(
        url,
        {
            "ocr_text": "Total: $42.00",
            "ocr_confidence": 0.92,
            "sensitivity_class": "FINANCIAL",
            "rag_excluded": False,
        },
        format="json",
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["asset_id"] == asset.id
    assert body["ocr_confidence"] == 0.92
    assert body["sensitivity_class"] == "FINANCIAL"
    assert body["rag_excluded"] is False


def test_ocr_update_without_service_token_403(tenant, asset):
    client = APIClient()
    client.defaults["SERVER_NAME"] = "localhost"
    client.defaults["HTTP_X_TENANT_ID"] = str(tenant.id)
    url = OCR_URL.format(pk=asset.pk)
    resp = client.patch(url, {"ocr_text": "test"}, format="json")
    assert resp.status_code == 403


def test_ocr_update_sets_only_specified_fields(tenant, asset):
    asset.file_name = "receipt.jpg"
    asset.save()

    client = _service_client(tenant)
    url = OCR_URL.format(pk=asset.pk)
    client.patch(
        url,
        {"ocr_text": "Redacted <PERSON>", "ocr_confidence": 0.85},
        format="json",
    )
    asset.refresh_from_db()
    assert asset.ocr_text == "Redacted <PERSON>"
    assert asset.ocr_confidence == 0.85
    assert asset.sensitivity_class is None
    assert asset.rag_excluded is False
    assert asset.file_name == "receipt.jpg"


def test_sensitivity_class_choices_validated(tenant, asset):
    client = _service_client(tenant)
    url = OCR_URL.format(pk=asset.pk)
    resp = client.patch(
        url,
        {"sensitivity_class": "TOP_SECRET"},
        format="json",
    )
    assert resp.status_code == 400
    assert "Invalid sensitivity_class" in resp.json()["error"]


def test_rag_excluded_defaults_false(tenant, asset):
    assert asset.rag_excluded is False


def test_cross_tenant_asset_not_found(tenant, asset):
    other_tenant = Tenant.objects.create(name="Other Corp", schema_name="other_corp")
    client = _service_client(other_tenant)
    url = OCR_URL.format(pk=asset.pk)
    resp = client.patch(url, {"ocr_text": "stolen"}, format="json")
    assert resp.status_code == 404
