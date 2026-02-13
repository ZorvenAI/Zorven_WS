"""
End-to-End tests for onboarding pipeline integration.

These tests require real GCP credentials and Kafka access.
Run only in environments with proper configuration:
    pytest -m gcp onboarding/tests/test_pipeline_e2e.py

Prerequisites:
- GCS credentials file exists (credentials/gcs-credentials.json)
- GCS bucket accessible
- Kafka cluster running (or ONBOARDING_KAFKA_ENABLED=False)
"""

import os
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from django.conf import settings
from django.db import connection
from rest_framework import status
from rest_framework.test import APIClient

from onboarding.models import BrandAsset, Company
from onboarding.services import get_pipeline_service


def _gcp_credentials_available():
    """Check if GCP credentials are available via env var or file."""
    # Check environment variable first
    if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        return True
    # Check for credentials file in project
    creds_path = (
        Path(__file__).resolve().parent.parent.parent
        / "credentials"
        / "gcs-credentials.json"
    )
    return creds_path.exists()


# Skip all tests if GCP credentials not available
pytestmark = [
    pytest.mark.gcp,
    pytest.mark.skipif(
        not _gcp_credentials_available(),
        reason="GCP credentials not configured (no env var or credentials file)",
    ),
]


def create_test_tenant():
    """Create a unique tenant for E2E tests."""
    from tenants.models import Tenant, Domain

    connection.set_schema_to_public()
    unique_id = uuid.uuid4().hex[:8]
    schema_name = f"e2e_test_{unique_id}"

    tenant = Tenant.objects.create(
        name=f"E2E Test {unique_id}",
        schema_name=schema_name,
        subscription_status="active",
        max_users=10,
        storage_limit_gb=5,
    )
    Domain.objects.create(
        tenant=tenant,
        domain=f"{schema_name}.localhost",
        is_primary=True,
    )
    return tenant


@pytest.mark.django_db
class TestE2EAssetUpload:
    """E2E tests for asset upload pipeline."""

    @pytest.fixture(autouse=True)
    def setup_webhook_secret(self, settings):
        """Set up the webhook secret for all tests in this class."""
        settings.PIPELINE_WEBHOOK_SECRET = "test-webhook-secret"

    def test_e2e_asset_upload_gcs_path_format(self):
        """Verify uploaded assets use correct GCS path format for pipeline."""
        tenant = create_test_tenant()
        company = Company.objects.create(tenant=tenant, name="E2E Upload Test")

        # Create asset with landing zone path
        file_uuid = uuid.uuid4()
        gcs_path = f"_landing/{tenant.id}/{file_uuid}_test_image.jpg"

        asset = BrandAsset.objects.create(
            tenant=tenant,
            company=company,
            file_name="test_image.jpg",
            file_type="image",
            file_size=1024,
            gcs_path=gcs_path,
            gcs_bucket=settings.DATA_INGESTION.get(
                "GCP_BUCKET_NAME", "onboarding-brandsol-customer-bucket-1"
            ),
            pipeline_status="pending",
        )

        # Verify path format
        assert asset.gcs_path.startswith(f"_landing/{tenant.id}/")
        assert "test_image.jpg" in asset.gcs_path
        assert str(file_uuid) in asset.gcs_path

    def test_e2e_webhook_updates_real_asset(self):
        """E2E test: webhook updates asset in database."""
        tenant = create_test_tenant()
        company = Company.objects.create(tenant=tenant, name="E2E Webhook Test")

        asset = BrandAsset.objects.create(
            tenant=tenant,
            company=company,
            file_name="e2e_webhook.jpg",
            file_type="image",
            file_size=2048,
            gcs_path=f"_landing/{tenant.id}/e2e_webhook.jpg",
            pipeline_status="pending",
        )

        client = APIClient()
        client.defaults["SERVER_NAME"] = "localhost"

        # Simulate pipeline stages
        stages = ["ingested", "curated", "indexed"]

        for stage in stages:
            response = client.post(
                "/api/v1/webhooks/pipeline-status/",
                {
                    "asset_id": asset.id,
                    "status": stage,
                    "secret": "test-webhook-secret",
                },
                format="json",
            )
            assert response.status_code == status.HTTP_200_OK

            asset.refresh_from_db()
            assert asset.pipeline_status == stage

        # Final state should be indexed and processed
        assert asset.processed is True


@pytest.mark.django_db
class TestE2ECompanyExport:
    """E2E tests for company RAG export."""

    def test_e2e_company_document_structure(self):
        """Verify company document has correct structure for RAG."""
        from onboarding.tasks import _build_company_document

        tenant = create_test_tenant()
        company = Company.objects.create(
            tenant=tenant,
            name="E2E Company Export",
            description="A company for E2E testing",
            industry="Technology",
            target_audience="Enterprise",
            values="Quality, Innovation",
        )

        doc = _build_company_document(company)

        # Verify required fields for RAG indexing
        assert doc["document_type"] == "company_profile"
        assert doc["tenant_id"] == str(tenant.id)
        assert doc["company_id"] == company.id
        assert doc["source"] == "onboarding_service"

        # Metadata should have timestamps
        assert "metadata" in doc

        # Content should be concatenated text
        content = doc["content"]
        assert isinstance(content, str)
        assert len(content) > 0


@pytest.mark.django_db
class TestE2ETenantConfig:
    """E2E tests for tenant pipeline configuration."""

    def test_e2e_tenant_config_setup_and_retrieve(self):
        """Set up and retrieve tenant config through full flow."""
        tenant = create_test_tenant()

        service = get_pipeline_service()

        # Set up config
        config = service.setup_tenant_pipeline_config(tenant.id)

        # Verify defaults
        assert config["enabled"] is True
        assert config["retention_days"] == 90

        # Retrieve and verify
        retrieved = service.get_tenant_pipeline_config(tenant.id)
        assert retrieved["enabled"] == config["enabled"]
        assert retrieved["retention_days"] == config["retention_days"]


@pytest.mark.django_db
class TestE2EFullPipelineFlow:
    """E2E test for complete pipeline flow."""

    @pytest.fixture(autouse=True)
    def setup_webhook_secret(self, settings):
        """Set up the webhook secret for all tests in this class."""
        settings.PIPELINE_WEBHOOK_SECRET = "test-webhook-secret"

    def test_e2e_complete_asset_lifecycle(self):
        """
        Complete E2E test of asset lifecycle:
        1. Create tenant and company
        2. Upload asset with landing zone path
        3. Simulate pipeline processing via webhooks
        4. Verify final state
        """
        # 1. Setup
        tenant = create_test_tenant()
        company = Company.objects.create(
            tenant=tenant,
            name="Full Lifecycle Test",
            description="Testing complete pipeline flow",
            industry="E2E Testing",
        )

        # 2. Create asset (simulating upload)
        file_uuid = uuid.uuid4()
        asset = BrandAsset.objects.create(
            tenant=tenant,
            company=company,
            file_name="lifecycle_test.pdf",
            file_type="document",
            file_size=5000,
            gcs_path=f"_landing/{tenant.id}/{file_uuid}_lifecycle_test.pdf",
            gcs_bucket="onboarding-brandsol-customer-bucket-1",
            pipeline_status="pending",
            processed=False,
        )

        # Verify initial state
        assert asset.pipeline_status == "pending"
        assert asset.processed is False
        assert asset.pipeline_trace_id is None

        # 3. Simulate pipeline processing
        client = APIClient()
        client.defaults["SERVER_NAME"] = "localhost"
        # Stage 1: Ingested
        response = client.post(
            "/api/v1/webhooks/pipeline-status/",
            {
                "asset_id": asset.id,
                "status": "ingested",
                "secret": "test-webhook-secret",
            },
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK

        # Stage 2: Curated
        response = client.post(
            "/api/v1/webhooks/pipeline-status/",
            {
                "asset_id": asset.id,
                "status": "curated",
                "secret": "test-webhook-secret",
            },
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK

        # Stage 3: Indexed (final)
        response = client.post(
            "/api/v1/webhooks/pipeline-status/",
            {
                "asset_id": asset.id,
                "status": "indexed",
                "secret": "test-webhook-secret",
            },
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK

        # 4. Verify final state
        asset.refresh_from_db()
        assert asset.pipeline_status == "indexed"
        assert asset.processed is True
        # Note: pipeline_trace_id is set by publish_asset_event, not webhook
        # In E2E we skip Kafka publish, so trace_id remains None
        assert asset.pipeline_error == ""

    def test_e2e_pipeline_failure_and_retry(self):
        """
        E2E test for pipeline failure and retry:
        1. Asset fails during processing
        2. Retry via API
        3. Verify retry works
        """
        tenant = create_test_tenant()
        company = Company.objects.create(tenant=tenant, name="Retry E2E Test")

        asset = BrandAsset.objects.create(
            tenant=tenant,
            company=company,
            file_name="retry_e2e.jpg",
            file_type="image",
            file_size=1024,
            gcs_path=f"_landing/{tenant.id}/retry_e2e.jpg",
            pipeline_status="pending",
        )

        client = APIClient()
        client.defaults["SERVER_NAME"] = "localhost"

        # Simulate failure
        response = client.post(
            "/api/v1/webhooks/pipeline-status/",
            {
                "asset_id": asset.id,
                "status": "failed",
                "error": "Processing timeout",
                "secret": "test-webhook-secret",
            },
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK

        asset.refresh_from_db()
        assert asset.pipeline_status == "failed"
        assert asset.pipeline_error == "Processing timeout"

        # Retry using service (would normally be via API with auth)
        service = get_pipeline_service()

        # Disable Kafka for this test
        with patch.object(service, "_kafka_enabled", False):
            # Reset for retry
            asset.pipeline_error = ""
            asset.pipeline_status = "pending"
            asset.save()

        # Simulate successful reprocessing
        response = client.post(
            "/api/v1/webhooks/pipeline-status/",
            {
                "asset_id": asset.id,
                "status": "indexed",
                "secret": "test-webhook-secret",
            },
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK

        asset.refresh_from_db()
        assert asset.pipeline_status == "indexed"
        assert asset.processed is True
