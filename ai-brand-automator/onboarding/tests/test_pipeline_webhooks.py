"""
Unit tests for pipeline webhook endpoints.

Tests cover:
- Single asset status updates
- Batch status updates
- Authentication validation
- Error handling
"""

import uuid

import pytest
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APIClient

from onboarding.models import BrandAsset, Company


@pytest.fixture
def api_client():
    """Create API client for testing webhooks."""
    client = APIClient()
    client.defaults["SERVER_NAME"] = "localhost"
    return client


@pytest.fixture
def sample_asset_for_webhook(db, public_tenant):
    """Create a sample brand asset for testing (unique company per test)."""
    # Delete any existing company for this tenant first
    Company.objects.filter(tenant=public_tenant).delete()

    company = Company.objects.create(
        tenant=public_tenant,
        name="Webhook Test Company",
        description="Test description",
    )
    asset = BrandAsset.objects.create(
        tenant=public_tenant,
        company=company,
        file_name="webhook_test.jpg",
        file_type="image",
        file_size=1024,
        gcs_path="_landing/1/abc_webhook_test.jpg",
        gcs_bucket="test-bucket",
        processed=False,
        pipeline_status="pending",
        pipeline_trace_id=uuid.uuid4(),
    )
    return asset


class TestPipelineStatusWebhook:
    """Tests for single asset pipeline status webhook."""

    @pytest.mark.django_db
    def test_update_status_success(self, api_client, sample_asset_for_webhook):
        """Should update asset status successfully."""
        response = api_client.post(
            "/api/v1/webhooks/pipeline-status/",
            {
                "asset_id": sample_asset_for_webhook.id,
                "status": "ingested",
                "trace_id": str(sample_asset_for_webhook.pipeline_trace_id),
            },
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == "updated"
        assert response.data["pipeline_status"] == "ingested"

        sample_asset_for_webhook.refresh_from_db()
        assert sample_asset_for_webhook.pipeline_status == "ingested"

    @pytest.mark.django_db
    def test_update_to_indexed_marks_processed(
        self, api_client, sample_asset_for_webhook
    ):
        """Should mark asset as processed when status is 'indexed'."""
        response = api_client.post(
            "/api/v1/webhooks/pipeline-status/",
            {
                "asset_id": sample_asset_for_webhook.id,
                "status": "indexed",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK

        sample_asset_for_webhook.refresh_from_db()
        assert sample_asset_for_webhook.pipeline_status == "indexed"
        assert sample_asset_for_webhook.processed is True

    @pytest.mark.django_db
    def test_update_with_error_message(self, api_client, sample_asset_for_webhook):
        """Should store error message when status is 'failed'."""
        error_msg = "Processing failed: Invalid file format"

        response = api_client.post(
            "/api/v1/webhooks/pipeline-status/",
            {
                "asset_id": sample_asset_for_webhook.id,
                "status": "failed",
                "error": error_msg,
            },
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK

        sample_asset_for_webhook.refresh_from_db()
        assert sample_asset_for_webhook.pipeline_status == "failed"
        assert sample_asset_for_webhook.pipeline_error == error_msg

    @pytest.mark.django_db
    def test_invalid_status_rejected(self, api_client, sample_asset_for_webhook):
        """Should reject invalid status values."""
        response = api_client.post(
            "/api/v1/webhooks/pipeline-status/",
            {
                "asset_id": sample_asset_for_webhook.id,
                "status": "invalid_status",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Invalid status" in response.data["error"]

    @pytest.mark.django_db
    def test_missing_asset_id_rejected(self, api_client):
        """Should reject requests without asset_id."""
        response = api_client.post(
            "/api/v1/webhooks/pipeline-status/",
            {
                "status": "ingested",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "asset_id is required" in response.data["error"]

    @pytest.mark.django_db
    def test_asset_not_found(self, api_client):
        """Should return 404 for non-existent asset."""
        response = api_client.post(
            "/api/v1/webhooks/pipeline-status/",
            {
                "asset_id": 99999,
                "status": "ingested",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "not found" in response.data["error"]

    @pytest.mark.django_db
    @override_settings(PIPELINE_WEBHOOK_SECRET="test-secret-123")
    def test_authentication_required_when_secret_configured(
        self, api_client, sample_asset_for_webhook
    ):
        """Should require secret when PIPELINE_WEBHOOK_SECRET is set."""
        # Request without secret
        response = api_client.post(
            "/api/v1/webhooks/pipeline-status/",
            {
                "asset_id": sample_asset_for_webhook.id,
                "status": "ingested",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.django_db
    @override_settings(PIPELINE_WEBHOOK_SECRET="test-secret-123")
    def test_authentication_with_valid_secret(
        self, api_client, sample_asset_for_webhook
    ):
        """Should accept request with valid secret."""
        response = api_client.post(
            "/api/v1/webhooks/pipeline-status/",
            {
                "asset_id": sample_asset_for_webhook.id,
                "status": "ingested",
                "secret": "test-secret-123",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.django_db
    @override_settings(PIPELINE_WEBHOOK_SECRET="test-secret-123")
    def test_authentication_via_header(self, api_client, sample_asset_for_webhook):
        """Should accept secret via X-Pipeline-Secret header."""
        response = api_client.post(
            "/api/v1/webhooks/pipeline-status/",
            {
                "asset_id": sample_asset_for_webhook.id,
                "status": "ingested",
            },
            format="json",
            HTTP_X_PIPELINE_SECRET="test-secret-123",
        )

        assert response.status_code == status.HTTP_200_OK


class TestPipelineBatchStatusWebhook:
    """Tests for batch pipeline status webhook."""

    @pytest.mark.django_db
    def test_batch_update_success(self, api_client, public_tenant):
        """Should update multiple assets in batch."""
        # Clean up any existing company
        Company.objects.filter(tenant=public_tenant).delete()

        # Create company and assets
        company = Company.objects.create(
            tenant=public_tenant,
            name="Batch Test Company",
        )
        assets = []
        for i in range(3):
            asset = BrandAsset.objects.create(
                tenant=public_tenant,
                company=company,
                file_name=f"batch_test_{i}.jpg",
                file_type="image",
                file_size=1024,
                gcs_path=f"_landing/1/abc_batch_{i}.jpg",
                gcs_bucket="test-bucket",
                pipeline_status="pending",
            )
            assets.append(asset)

        response = api_client.post(
            "/api/v1/webhooks/pipeline-batch-status/",
            {
                "updates": [
                    {"asset_id": assets[0].id, "status": "ingested"},
                    {"asset_id": assets[1].id, "status": "curated"},
                    {"asset_id": assets[2].id, "status": "indexed"},
                ],
            },
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["success"] == 3
        assert response.data["failed"] == 0

        # Verify updates
        assets[0].refresh_from_db()
        assets[1].refresh_from_db()
        assets[2].refresh_from_db()
        assert assets[0].pipeline_status == "ingested"
        assert assets[1].pipeline_status == "curated"
        assert assets[2].pipeline_status == "indexed"
        assert assets[2].processed is True

    @pytest.mark.django_db
    def test_batch_update_partial_failure(self, api_client, sample_asset_for_webhook):
        """Should handle partial failures in batch."""
        response = api_client.post(
            "/api/v1/webhooks/pipeline-batch-status/",
            {
                "updates": [
                    {"asset_id": sample_asset_for_webhook.id, "status": "ingested"},
                    {"asset_id": 99999, "status": "ingested"},  # Non-existent
                ],
            },
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["success"] == 1
        assert response.data["failed"] == 1
        assert len(response.data["errors"]) == 1

    @pytest.mark.django_db
    def test_batch_empty_updates_rejected(self, api_client):
        """Should reject empty updates array."""
        response = api_client.post(
            "/api/v1/webhooks/pipeline-batch-status/",
            {
                "updates": [],
            },
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.django_db
    @override_settings(PIPELINE_WEBHOOK_SECRET="batch-secret")
    def test_batch_authentication_required(self, api_client):
        """Should require authentication for batch endpoint."""
        response = api_client.post(
            "/api/v1/webhooks/pipeline-batch-status/",
            {
                "updates": [{"asset_id": 1, "status": "ingested"}],
            },
            format="json",
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
