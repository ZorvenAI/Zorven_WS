"""
Integration tests for onboarding pipeline flow.

These tests mock Kafka but test the complete integration between:
- BrandAsset upload → Pipeline service → Kafka publish
- Company save → Signal → Celery task → RAG export
- Webhook callback → Asset status update

Uses mocks for Kafka producer to avoid external dependencies.
"""

import uuid
from unittest.mock import MagicMock, patch

import pytest
from django.db import connection
from rest_framework import status
from rest_framework.test import APIClient

from onboarding.models import BrandAsset, Company
from onboarding.services import OnboardingPipelineService, get_pipeline_service

pytestmark = pytest.mark.integration


def create_test_tenant():
    """Create a unique tenant for integration tests."""
    from tenants.models import Tenant, Domain

    connection.set_schema_to_public()
    unique_id = uuid.uuid4().hex[:8]
    schema_name = f"int_test_{unique_id}"

    tenant = Tenant.objects.create(
        name=f"Integration Test {unique_id}",
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
class TestAssetUploadPipelineFlow:
    """Integration tests for asset upload → pipeline flow."""

    def test_asset_upload_triggers_kafka_publish(self):
        """Complete flow: asset creation → pipeline service → Kafka."""
        tenant = create_test_tenant()
        company = Company.objects.create(tenant=tenant, name="Upload Flow Test")

        # Create asset with pipeline fields
        asset = BrandAsset.objects.create(
            tenant=tenant,
            company=company,
            file_name="integration_test.jpg",
            file_type="image",
            file_size=2048,
            gcs_path=f"_landing/{tenant.id}/{uuid.uuid4()}_integration_test.jpg",
            pipeline_status="pending",
        )

        # Mock Kafka producer
        mock_producer = MagicMock()
        mock_producer.publish_raw = MagicMock(return_value=None)

        with patch.object(
            OnboardingPipelineService,
            "producer",
            new_callable=lambda: property(lambda self: mock_producer),
        ):
            service = OnboardingPipelineService()
            service._kafka_enabled = True
            trace_id = service.publish_asset_event(asset)

        # Verify event was published
        assert trace_id is not None
        mock_producer.publish_raw.assert_called_once()

        # Verify event structure
        call_args = mock_producer.publish_raw.call_args
        topic = call_args[0][0]
        event = call_args[0][1]

        assert topic == "raw-ingestion-topic"
        assert event["trace_id"] == trace_id
        assert event["source"] == "django-backend"
        assert str(tenant.id) in event["tenant_id"]
        assert event["metadata"]["asset_id"] == asset.id

        # Verify asset was updated
        asset.refresh_from_db()
        assert asset.pipeline_trace_id is not None
        assert asset.pipeline_status == "pending"

    def test_asset_upload_handles_kafka_failure(self):
        """Asset should be marked failed if Kafka publish fails."""
        tenant = create_test_tenant()
        company = Company.objects.create(tenant=tenant, name="Failure Test")

        asset = BrandAsset.objects.create(
            tenant=tenant,
            company=company,
            file_name="fail_test.jpg",
            file_type="image",
            file_size=1024,
            gcs_path=f"_landing/{tenant.id}/fail_test.jpg",
        )

        # Mock Kafka producer to raise exception
        mock_producer = MagicMock()
        mock_producer.publish_raw = MagicMock(
            side_effect=Exception("Kafka connection failed")
        )

        with patch.object(
            OnboardingPipelineService,
            "producer",
            new_callable=lambda: property(lambda self: mock_producer),
        ):
            service = OnboardingPipelineService()
            service._kafka_enabled = True
            trace_id = service.publish_asset_event(asset)

        # Should return None on failure
        assert trace_id is None

        # Asset should be marked as failed
        asset.refresh_from_db()
        assert asset.pipeline_status == "failed"
        assert "Kafka connection failed" in asset.pipeline_error


@pytest.mark.django_db
class TestCompanyRAGExportFlow:
    """Integration tests for company save → RAG export flow."""

    def test_company_document_build_complete(self):
        """Build company document with all fields populated."""
        from rag_index.services.db_sync_service import DbSyncService

        tenant = create_test_tenant()
        company = Company.objects.create(
            tenant=tenant,
            name="RAG Export Company",
            description="A test company for RAG",
            industry="Technology",
            target_audience="Developers",
            values="Innovation, Quality",
        )

        doc = DbSyncService().build_document("Company", company)

        # Verify document structure
        assert doc["document_type"] == "company_profile"
        assert doc["metadata"]["company_id"] == str(company.id)

        # Verify content includes all text fields
        content = doc["extracted_text"]
        assert "RAG Export Company" in content
        assert "test company for RAG" in content
        assert "Technology" in content
        assert "Developers" in content
        assert "Innovation" in content

    def test_rag_export_publishes_to_correct_topic(self):
        """Company document should be published to RAG topic."""
        tenant = create_test_tenant()
        company = Company.objects.create(
            tenant=tenant,
            name="RAG Topic Test",
        )

        mock_producer = MagicMock()
        mock_producer.publish_raw = MagicMock()

        company_doc = {
            "document_type": "company_profile",
            "company_id": company.id,
            "content": "Test content",
        }

        with patch.object(
            OnboardingPipelineService,
            "producer",
            new_callable=lambda: property(lambda self: mock_producer),
        ):
            service = OnboardingPipelineService()
            service._kafka_enabled = True
            trace_id = service.publish_company_document(company_doc)

        # Verify published to RAG topic
        mock_producer.publish_raw.assert_called_once()
        call_args = mock_producer.publish_raw.call_args
        topic = call_args[0][0]

        assert topic == "rag-sync-ready-topic"
        assert trace_id is not None


@pytest.mark.django_db
class TestWebhookPipelineFlow:
    """Integration tests for webhook → asset update flow."""

    @pytest.fixture(autouse=True)
    def setup_webhook_secret(self, settings):
        """Set up the webhook secret for all tests in this class."""
        settings.PIPELINE_WEBHOOK_SECRET = "test-webhook-secret"

    def test_webhook_updates_asset_and_marks_processed(self):
        """Webhook with indexed status should mark asset as processed."""
        tenant = create_test_tenant()
        company = Company.objects.create(tenant=tenant, name="Webhook Flow Test")

        asset = BrandAsset.objects.create(
            tenant=tenant,
            company=company,
            file_name="webhook_test.jpg",
            file_type="image",
            file_size=1024,
            gcs_path=f"_landing/{tenant.id}/webhook_test.jpg",
            pipeline_status="pending",
            processed=False,
        )

        client = APIClient()
        client.defaults["SERVER_NAME"] = "localhost"

        # Simulate pipeline completion webhook with secret
        response = client.post(
            "/api/v1/webhooks/pipeline-status/",
            {
                "asset_id": asset.id,
                "status": "indexed",
                "trace_id": str(uuid.uuid4()),
                "secret": "test-webhook-secret",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK

        # Verify asset is now fully processed
        asset.refresh_from_db()
        assert asset.pipeline_status == "indexed"
        assert asset.processed is True

    def test_webhook_flow_pending_to_failed(self):
        """Webhook can transition asset from pending to failed with error."""
        tenant = create_test_tenant()
        company = Company.objects.create(tenant=tenant, name="Failure Flow Test")

        asset = BrandAsset.objects.create(
            tenant=tenant,
            company=company,
            file_name="failure_flow.jpg",
            file_type="image",
            file_size=1024,
            gcs_path=f"_landing/{tenant.id}/failure_flow.jpg",
            pipeline_status="ingested",
        )

        client = APIClient()
        client.defaults["SERVER_NAME"] = "localhost"

        error_msg = "Curation failed: unsupported image format"
        response = client.post(
            "/api/v1/webhooks/pipeline-status/",
            {
                "asset_id": asset.id,
                "status": "failed",
                "error": error_msg,
                "secret": "test-webhook-secret",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK

        asset.refresh_from_db()
        assert asset.pipeline_status == "failed"
        assert asset.pipeline_error == error_msg
        assert asset.processed is False

    def test_batch_webhook_mixed_results(self):
        """Batch webhook with mix of valid and invalid asset IDs."""
        tenant = create_test_tenant()
        company = Company.objects.create(tenant=tenant, name="Batch Mixed Test")

        # Create 2 valid assets
        asset1 = BrandAsset.objects.create(
            tenant=tenant,
            company=company,
            file_name="batch1.jpg",
            file_type="image",
            file_size=1024,
            gcs_path=f"_landing/{tenant.id}/batch1.jpg",
            pipeline_status="pending",
        )
        asset2 = BrandAsset.objects.create(
            tenant=tenant,
            company=company,
            file_name="batch2.jpg",
            file_type="image",
            file_size=1024,
            gcs_path=f"_landing/{tenant.id}/batch2.jpg",
            pipeline_status="pending",
        )

        client = APIClient()
        client.defaults["SERVER_NAME"] = "localhost"

        response = client.post(
            "/api/v1/webhooks/pipeline-batch-status/",
            {
                "updates": [
                    {"asset_id": asset1.id, "status": "indexed"},
                    {"asset_id": 99999, "status": "indexed"},  # Non-existent
                    {"asset_id": asset2.id, "status": "curated"},
                ],
                "secret": "test-webhook-secret",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["success"] == 2
        assert response.data["failed"] == 1

        # Verify correct assets were updated
        asset1.refresh_from_db()
        asset2.refresh_from_db()
        assert asset1.pipeline_status == "indexed"
        assert asset2.pipeline_status == "curated"


@pytest.mark.django_db
class TestTenantConfigFlow:
    """Integration tests for tenant pipeline configuration."""

    def test_new_tenant_gets_default_config(self):
        """New tenant should have default pipeline config available."""
        tenant = create_test_tenant()

        service = get_pipeline_service()
        config = service.get_tenant_pipeline_config(tenant.id)

        # Should have all required fields
        assert config["enabled"] is True
        assert config["auto_curation"] is True
        assert config["rag_indexing"] is True
        assert config["retention_days"] == 90
        assert "image" in config["allowed_file_types"]

    def test_tenant_config_persists_to_cache(self):
        """Tenant config should be retrievable after being set."""
        tenant = create_test_tenant()

        service = get_pipeline_service()

        # Set up config
        service.setup_tenant_pipeline_config(tenant.id)

        # Retrieve config
        config = service.get_tenant_pipeline_config(tenant.id)

        assert config["enabled"] is True
        assert isinstance(config["retention_days"], int)


@pytest.mark.django_db
class TestRetryFlow:
    """Integration tests for pipeline retry functionality."""

    def test_retry_failed_asset_republishes(self):
        """Retrying a failed asset should republish to Kafka."""
        tenant = create_test_tenant()
        company = Company.objects.create(tenant=tenant, name="Retry Test")

        asset = BrandAsset.objects.create(
            tenant=tenant,
            company=company,
            file_name="retry_test.jpg",
            file_type="image",
            file_size=1024,
            gcs_path=f"_landing/{tenant.id}/retry_test.jpg",
            pipeline_status="failed",
            pipeline_error="Previous failure",
        )

        mock_producer = MagicMock()
        mock_producer.publish_raw = MagicMock()

        with patch.object(
            OnboardingPipelineService,
            "producer",
            new_callable=lambda: property(lambda self: mock_producer),
        ):
            service = OnboardingPipelineService()
            service._kafka_enabled = True
            new_trace_id = service.retry_asset_pipeline(asset)

        assert new_trace_id is not None
        mock_producer.publish_raw.assert_called_once()

        # Error should be cleared
        asset.refresh_from_db()
        assert asset.pipeline_error == ""
        assert asset.pipeline_status == "pending"

    def test_cannot_retry_completed_asset(self):
        """Should not retry an asset that's already indexed."""
        tenant = create_test_tenant()
        company = Company.objects.create(tenant=tenant, name="No Retry Test")

        asset = BrandAsset.objects.create(
            tenant=tenant,
            company=company,
            file_name="completed.jpg",
            file_type="image",
            file_size=1024,
            gcs_path=f"_landing/{tenant.id}/completed.jpg",
            pipeline_status="indexed",
            processed=True,
        )

        service = get_pipeline_service()
        result = service.retry_asset_pipeline(asset)

        # Should return None and not modify asset
        assert result is None
        asset.refresh_from_db()
        assert asset.pipeline_status == "indexed"
