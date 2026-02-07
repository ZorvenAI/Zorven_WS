"""
Tests for data_ingestion.tasks - Celery task gcs_path update.

Verifies that process_ingestion_event updates BrandAsset.gcs_path on success.
"""

import uuid
from unittest.mock import MagicMock, patch

import pytest

from data_ingestion.tasks import _update_asset_after_ingestion


@pytest.mark.django_db
class TestUpdateAssetAfterIngestion:
    """Tests for _update_asset_after_ingestion (Celery task helper)."""

    @pytest.fixture
    def brand_asset(self):
        """Create a BrandAsset for testing."""
        from onboarding.models import BrandAsset, Company
        from tenants.models import Tenant, Domain

        tenant, _ = Tenant.objects.get_or_create(
            schema_name="public",
            defaults={"name": "public"},
        )
        Domain.objects.get_or_create(
            domain="localhost",
            defaults={"tenant": tenant, "is_primary": True},
        )
        company = Company.objects.create(
            tenant=tenant,
            name="Test Company",
            industry="Technology",
        )
        asset = BrandAsset.objects.create(
            tenant=tenant,
            company=company,
            file_name="report.pdf",
            file_type="document",
            file_size=2048,
            gcs_path="1/_landing/report.pdf",
            pipeline_status="pending",
        )
        return asset

    def test_updates_gcs_path_from_gs_uri(self, brand_asset):
        """gcs_path is updated by stripping the gs://bucket prefix."""
        result = _update_asset_after_ingestion(
            str(brand_asset.id),
            "ingested",
            new_gcs_path="gs://my-bucket/1/raw/2026/02/06/report.pdf",
        )
        assert result is True

        brand_asset.refresh_from_db()
        assert brand_asset.gcs_path == "1/raw/2026/02/06/report.pdf"
        assert brand_asset.pipeline_status == "ingested"
        assert brand_asset.pipeline_error == ""

    def test_updates_gcs_path_from_plain_path(self, brand_asset):
        """Non-gs:// paths are stored as-is (no corruption)."""
        result = _update_asset_after_ingestion(
            str(brand_asset.id),
            "ingested",
            new_gcs_path="1/raw/2026/02/06/report.pdf",
        )
        assert result is True

        brand_asset.refresh_from_db()
        assert brand_asset.gcs_path == "1/raw/2026/02/06/report.pdf"

    def test_sets_failed_status_with_error(self, brand_asset):
        """Failed status stores the error message."""
        result = _update_asset_after_ingestion(
            str(brand_asset.id),
            "failed",
            error_msg="Corrupt file",
        )
        assert result is True

        brand_asset.refresh_from_db()
        assert brand_asset.pipeline_status == "failed"
        assert brand_asset.pipeline_error == "Corrupt file"

    def test_asset_not_found_returns_false(self):
        """Returns False when asset ID doesn't exist."""
        result = _update_asset_after_ingestion("999999", "ingested")
        assert result is False

    def test_clears_error_on_ingested(self, brand_asset):
        """Previous error is cleared when status becomes ingested."""
        brand_asset.pipeline_status = "failed"
        brand_asset.pipeline_error = "Old error"
        brand_asset.save()

        result = _update_asset_after_ingestion(str(brand_asset.id), "ingested")
        assert result is True

        brand_asset.refresh_from_db()
        assert brand_asset.pipeline_error == ""


@pytest.mark.django_db
class TestCeleryTaskUpdatesGcsPath:
    """Integration test: process_ingestion_event updates BrandAsset.gcs_path."""

    @pytest.fixture
    def brand_asset(self):
        from onboarding.models import BrandAsset, Company
        from tenants.models import Tenant, Domain

        tenant, _ = Tenant.objects.get_or_create(
            schema_name="public",
            defaults={"name": "public"},
        )
        Domain.objects.get_or_create(
            domain="localhost",
            defaults={"tenant": tenant, "is_primary": True},
        )
        company = Company.objects.create(
            tenant=tenant,
            name="Test Company",
            industry="Technology",
        )
        asset = BrandAsset.objects.create(
            tenant=tenant,
            company=company,
            file_name="photo.png",
            file_type="image",
            file_size=512,
            gcs_path="1/_landing/photo.png",
            pipeline_status="pending",
        )
        return asset

    @patch("data_ingestion.tasks.create_ingestion_service")
    def test_process_event_updates_asset_gcs_path(
        self, mock_create_service, brand_asset
    ):
        """Celery task updates BrandAsset.gcs_path after successful ingestion."""
        from data_ingestion.tasks import process_ingestion_event

        mock_service = MagicMock()
        mock_result = MagicMock()
        mock_result.destination_path = "gs://bucket/1/raw/2026/02/06/photo.png"
        mock_service.process_event.return_value = mock_result
        mock_create_service.return_value = mock_service

        result = process_ingestion_event.apply(
            args=[
                str(uuid.uuid4()),  # event_id
                "tenant-1",  # tenant_id
                "gs://bucket/1/_landing/photo.png",  # file_path
            ],
            kwargs={
                "metadata": {"asset_id": str(brand_asset.id)},
            },
        ).get()

        assert result["status"] == "success"

        brand_asset.refresh_from_db()
        assert brand_asset.gcs_path == "1/raw/2026/02/06/photo.png"
        assert brand_asset.pipeline_status == "ingested"
