"""
Tests for CGAContextView — service-to-service CGA context endpoint.

Covers:
- Service-token auth (valid, invalid, missing config)
- Tenant selection (X-Tenant-ID header vs request tenant)
- Response shape with CGA data
- 404 when no CGA data exists
"""

import uuid

import pytest
from unittest.mock import patch

from django.conf import settings as django_settings
from django.db import connection
from rest_framework.test import APIClient

TEST_SERVICE_TOKEN = "test-service-token"


@pytest.fixture
def cga_tenant(db):
    """Create a test tenant for CGA context tests."""
    from tenants.models import Tenant, Domain

    connection.set_schema_to_public()
    tenant = Tenant.objects.create(
        name="CGA Context Test",
        schema_name="cga_test",
        subscription_status="active",
        max_users=10,
        storage_limit_gb=5,
    )
    Domain.objects.create(tenant=tenant, domain="cgatest.localhost", is_primary=True)
    return tenant


@pytest.fixture
def cga_manifest(db, cga_tenant):
    """Pipeline manifest for creative generation."""
    from orchestration.models import PipelineManifest

    return PipelineManifest.objects.create(
        tenant=cga_tenant,
        pipeline_id="meta-creative-generation",
        name="Meta Creative Generation",
        manifest_data={"nodes": []},
    )


@pytest.fixture
def cga_completed_job(db, cga_tenant, cga_manifest):
    """A completed CGA job with creative packages in result_data."""
    from orchestration.models import AnalysisJob

    job = AnalysisJob.objects.create(
        tenant=cga_tenant,
        manifest=cga_manifest,
        status=AnalysisJob.Status.COMPLETED,
        result_data={
            "node_results": {
                "creative_generation": {
                    "creative_package": {
                        "campaign_id": "camp_123",
                        "brand_name": "TestBrand",
                    },
                    "ad_set_packages": [
                        {
                            "ad_set_name": "TOFU - Test",
                            "persona": "Tech Enthusiast",
                            "funnel_stage": "TOFU",
                            "creative_units": [
                                {
                                    "gcs_url": "gs://bucket/img.jpg",
                                    "headline": "Test",
                                }
                            ],
                        }
                    ],
                    "ad_units": [
                        {"gcs_url": "gs://bucket/img.jpg", "headline": "Test"}
                    ],
                    "generated_images": [{"gcs_url": "gs://bucket/img.jpg"}],
                    "confidence_score": 0.92,
                    "compliance_pass_rate": 0.85,
                }
            }
        },
    )
    return job


@pytest.fixture
def service_client():
    """APIClient with valid service token."""
    client = APIClient()
    client.defaults["SERVER_NAME"] = "localhost"
    return client


def _service_headers(tenant_id=None, token=None):
    """Build service-to-service headers."""
    headers = {}
    if token is not None:
        headers["HTTP_X_SERVICE_TOKEN"] = token
    if tenant_id is not None:
        headers["HTTP_X_TENANT_ID"] = str(tenant_id)
    return headers


@pytest.mark.django_db
class TestCGAContextViewAuth:
    def test_valid_token_returns_200(
        self, service_client, cga_tenant, cga_completed_job, settings
    ):
        settings.ORCHESTRATOR_SERVICE_TOKEN = TEST_SERVICE_TOKEN
        settings.DEBUG = True
        resp = service_client.get(
            "/api/v1/analytics/cga-context/",
            **_service_headers(cga_tenant.id, TEST_SERVICE_TOKEN),
        )
        assert resp.status_code == 200

    def test_invalid_token_returns_403(self, service_client, cga_tenant, settings):
        settings.ORCHESTRATOR_SERVICE_TOKEN = TEST_SERVICE_TOKEN
        settings.DEBUG = True
        resp = service_client.get(
            "/api/v1/analytics/cga-context/",
            **_service_headers(cga_tenant.id, "bad-token"),
        )
        assert resp.status_code == 403

    def test_missing_token_returns_403(self, service_client, cga_tenant, settings):
        settings.ORCHESTRATOR_SERVICE_TOKEN = TEST_SERVICE_TOKEN
        settings.DEBUG = True
        resp = service_client.get(
            "/api/v1/analytics/cga-context/",
            **_service_headers(cga_tenant.id, ""),
        )
        assert resp.status_code == 403

    def test_unconfigured_token_returns_500(self, service_client, cga_tenant, settings):
        """When ORCHESTRATOR_SERVICE_TOKEN is not set, return 500."""
        settings.ORCHESTRATOR_SERVICE_TOKEN = ""
        resp = service_client.get(
            "/api/v1/analytics/cga-context/",
            **_service_headers(cga_tenant.id, "any-token"),
        )
        assert resp.status_code == 500
        assert "not configured" in resp.json()["error"]

    def test_dev_token_rejected_in_production(
        self, service_client, cga_tenant, settings
    ):
        """Default dev-service-token rejected when DEBUG=False."""
        settings.ORCHESTRATOR_SERVICE_TOKEN = "dev-service-token"
        settings.DEBUG = False
        resp = service_client.get(
            "/api/v1/analytics/cga-context/",
            **_service_headers(cga_tenant.id, "dev-service-token"),
        )
        assert resp.status_code == 500
        assert "not configured" in resp.json()["error"]


@pytest.mark.django_db
class TestCGAContextViewTenant:
    def _get_with_token(self, client, tenant_id, settings):
        settings.ORCHESTRATOR_SERVICE_TOKEN = TEST_SERVICE_TOKEN
        settings.DEBUG = True
        return client.get(
            "/api/v1/analytics/cga-context/",
            **_service_headers(tenant_id, TEST_SERVICE_TOKEN),
        )

    def test_tenant_from_header(
        self, service_client, cga_tenant, cga_completed_job, settings
    ):
        resp = self._get_with_token(service_client, cga_tenant.id, settings)
        assert resp.status_code == 200

    def test_missing_tenant_returns_404(self, service_client, settings):
        resp = self._get_with_token(service_client, None, settings)
        assert resp.status_code == 404

    def test_invalid_tenant_id_returns_404(self, service_client, settings):
        resp = self._get_with_token(service_client, uuid.uuid4(), settings)
        assert resp.status_code == 404


@pytest.mark.django_db
class TestCGAContextViewResponse:
    def _get(self, client, tenant_id, settings):
        settings.ORCHESTRATOR_SERVICE_TOKEN = TEST_SERVICE_TOKEN
        settings.DEBUG = True
        return client.get(
            "/api/v1/analytics/cga-context/",
            **_service_headers(tenant_id, TEST_SERVICE_TOKEN),
        )

    def test_response_shape(
        self, service_client, cga_tenant, cga_completed_job, settings
    ):
        resp = self._get(service_client, cga_tenant.id, settings)
        assert resp.status_code == 200
        data = resp.json()
        assert "creative_packages" in data
        assert "ad_set_packages" in data
        assert "ad_units" in data
        assert "creative_package" in data
        assert "confidence_score" in data
        assert "cga_completed_at" in data
        assert "cga_job_id" in data

    def test_response_data(
        self, service_client, cga_tenant, cga_completed_job, settings
    ):
        resp = self._get(service_client, cga_tenant.id, settings)
        data = resp.json()
        # creative_packages mapped from ad_set_packages
        assert len(data["creative_packages"]) == 1
        assert data["creative_packages"][0]["ad_set_name"] == "TOFU - Test"
        assert len(data["creative_packages"][0]["ad_units"]) == 1
        assert data["confidence_score"] == 0.92
        assert data["cga_job_id"] == str(cga_completed_job.job_id)

    def test_no_cga_data_returns_404(self, service_client, cga_tenant, settings):
        resp = self._get(service_client, cga_tenant.id, settings)
        assert resp.status_code == 404
        assert resp.json()["error"] == "No CGA data with creative packages"
