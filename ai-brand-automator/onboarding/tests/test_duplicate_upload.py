"""
Tests for duplicate file upload prevention.

Covers:
- Uploading the same filename twice returns 409 Conflict
- Uploading with replace_existing=true updates existing asset
- Uploading different filenames both succeed with 201
- confirm_gcs_upload duplicate detection
"""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status
from unittest.mock import patch, MagicMock

from onboarding.models import BrandAsset
from .factories import CompanyFactory, BrandAssetFactory


@pytest.mark.django_db
@pytest.mark.unit
class TestDuplicateUploadPrevention:
    """Test duplicate file upload detection in upload() action."""

    @pytest.fixture
    def upload_url(self):
        return reverse("brandasset-upload")

    @pytest.fixture
    def company(self, public_tenant):
        return CompanyFactory(tenant=public_tenant)

    @pytest.fixture
    def existing_asset(self, public_tenant, company):
        """Create an existing asset with a known filename."""
        return BrandAssetFactory(
            tenant=public_tenant,
            company=company,
            file_name="test-logo.png",
            file_type="image",
            file_size=1024,
            gcs_path=f"_landing/{public_tenant.id}/old123_test-logo.png",
            gcs_bucket="zorven-raw-assets",
            pipeline_status="indexed",
        )

    def _make_upload_file(self, name="test-logo.png", content_type="image/png"):
        """Create a SimpleUploadedFile for testing."""
        return SimpleUploadedFile(
            name=name,
            content=b"\x89PNG\r\n\x1a\n" + b"\x00" * 100,
            content_type=content_type,
        )

    @patch("onboarding.views.gcs_service")
    def test_duplicate_upload_returns_409(
        self, mock_gcs, authenticated_client_with_tenant, existing_asset, upload_url
    ):
        """Uploading a file with the same name returns 409 with existing asset info."""
        mock_gcs.client = None
        mock_gcs.bucket = None

        file = self._make_upload_file("test-logo.png")
        response = authenticated_client_with_tenant.post(
            upload_url,
            {"file": file, "file_type": "image"},
            format="multipart",
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        assert response.data["error"] == "duplicate_file"
        assert "already exists" in response.data["message"]
        assert response.data["existing_asset"]["id"] == existing_asset.id
        assert response.data["existing_asset"]["file_name"] == "test-logo.png"
        assert response.data["existing_asset"]["pipeline_status"] == "indexed"

        # Verify no new asset was created
        assert BrandAsset.objects.filter(file_name="test-logo.png").count() == 1

    @patch("onboarding.views.gcs_service")
    @patch("onboarding.views.get_pipeline_service")
    def test_duplicate_upload_with_replace_updates_existing(
        self,
        mock_pipeline,
        mock_gcs,
        authenticated_client_with_tenant,
        existing_asset,
        upload_url,
    ):
        """Uploading with replace_existing=true updates the existing asset."""
        mock_gcs.client = None
        mock_gcs.bucket = None
        mock_pipeline.return_value = MagicMock()

        old_id = existing_asset.id
        file = self._make_upload_file("test-logo.png")
        response = authenticated_client_with_tenant.post(
            upload_url,
            {"file": file, "file_type": "image", "replace_existing": "true"},
            format="multipart",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["id"] == old_id  # Same asset, updated
        assert response.data["file_name"] == "test-logo.png"

        # Verify no new asset was created
        assert BrandAsset.objects.filter(file_name="test-logo.png").count() == 1

        # Verify the asset was updated
        existing_asset.refresh_from_db()
        # Mock gcs_service.get_bucket() returns a truthy MagicMock,
        # so the upload "succeeds" and pipeline_status is "pending".
        assert existing_asset.pipeline_status == "pending"
        assert existing_asset.file_size == file.size

    @patch("onboarding.views.gcs_service")
    @patch("onboarding.views.get_pipeline_service")
    def test_different_filenames_both_succeed(
        self,
        mock_pipeline,
        mock_gcs,
        authenticated_client_with_tenant,
        existing_asset,
        upload_url,
    ):
        """Uploading a file with a different name succeeds normally."""
        mock_gcs.client = None
        mock_gcs.bucket = None
        mock_pipeline.return_value = MagicMock()

        file = self._make_upload_file("another-logo.png")
        response = authenticated_client_with_tenant.post(
            upload_url,
            {"file": file, "file_type": "image"},
            format="multipart",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["file_name"] == "another-logo.png"

        # Both assets exist
        assert BrandAsset.objects.filter(file_name="test-logo.png").count() == 1
        assert BrandAsset.objects.filter(file_name="another-logo.png").count() == 1

    @patch("onboarding.views.gcs_service")
    @patch("onboarding.views.get_pipeline_service")
    def test_first_upload_succeeds_normally(
        self,
        mock_pipeline,
        mock_gcs,
        authenticated_client_with_tenant,
        company,
        upload_url,
    ):
        """Uploading a brand new file succeeds with 201 (no duplicate)."""
        mock_gcs.client = None
        mock_gcs.bucket = None
        mock_pipeline.return_value = MagicMock()

        file = self._make_upload_file("brand-new-file.png")
        response = authenticated_client_with_tenant.post(
            upload_url,
            {"file": file, "file_type": "image"},
            format="multipart",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["file_name"] == "brand-new-file.png"

    @patch("onboarding.views.gcs_service")
    @patch("onboarding.views.get_pipeline_service")
    def test_replace_with_gcs_deletes_old_blob(
        self,
        mock_pipeline,
        mock_gcs,
        authenticated_client_with_tenant,
        existing_asset,
        upload_url,
    ):
        """When replacing, the old GCS blob is deleted before uploading new one."""
        # Set up GCS mock
        mock_blob = MagicMock()
        mock_blob.exists.return_value = True
        mock_bucket = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_client = MagicMock()
        mock_client.bucket.return_value = mock_bucket

        mock_gcs.client = mock_client
        mock_gcs.bucket = MagicMock()
        mock_gcs.bucket_name = "test-bucket"
        mock_gcs.upload_file = MagicMock()
        mock_pipeline.return_value = MagicMock()

        file = self._make_upload_file("test-logo.png")
        response = authenticated_client_with_tenant.post(
            upload_url,
            {"file": file, "file_type": "image", "replace_existing": "true"},
            format="multipart",
        )

        assert response.status_code == status.HTTP_200_OK

        # Verify old blob was deleted
        mock_blob.delete.assert_called_once()
        # Verify new file was uploaded
        mock_gcs.upload_file.assert_called_once()


@pytest.mark.django_db
@pytest.mark.unit
class TestDuplicateConfirmGCSUpload:
    """Test duplicate file detection in confirm_gcs_upload() action."""

    @pytest.fixture
    def confirm_url(self):
        return reverse("brandasset-confirm-gcs-upload")

    @pytest.fixture
    def company(self, public_tenant):
        return CompanyFactory(tenant=public_tenant)

    @pytest.fixture
    def existing_asset(self, public_tenant, company):
        return BrandAssetFactory(
            tenant=public_tenant,
            company=company,
            file_name="report.pdf",
            file_type="document",
            file_size=5000,
            gcs_path=f"_landing/{public_tenant.id}/abc123_report.pdf",
            gcs_bucket="zorven-raw-assets",
            pipeline_status="curated",
        )

    @patch("onboarding.views.get_pipeline_service")
    def test_confirm_duplicate_returns_409(
        self,
        mock_pipeline,
        authenticated_client_with_tenant,
        public_tenant,
        existing_asset,
        confirm_url,
    ):
        """confirm_gcs_upload with duplicate filename returns 409."""
        mock_pipeline.return_value = MagicMock()

        data = {
            "file_name": "report.pdf",
            "file_type": "document",
            "file_size": 8000,
            "gcs_path": f"_landing/{public_tenant.id}/new456_report.pdf",
        }

        response = authenticated_client_with_tenant.post(
            confirm_url, data, format="json"
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        assert response.data["error"] == "duplicate_file"
        assert response.data["existing_asset"]["id"] == existing_asset.id

    @patch("onboarding.views.get_pipeline_service")
    def test_confirm_with_replace_updates_existing(
        self,
        mock_pipeline,
        authenticated_client_with_tenant,
        public_tenant,
        existing_asset,
        confirm_url,
    ):
        """confirm_gcs_upload with replace_existing=true updates asset."""
        mock_pipeline.return_value = MagicMock()

        data = {
            "file_name": "report.pdf",
            "file_type": "document",
            "file_size": 8000,
            "gcs_path": f"_landing/{public_tenant.id}/new456_report.pdf",
            "replace_existing": "true",
        }

        response = authenticated_client_with_tenant.post(
            confirm_url, data, format="json"
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["id"] == existing_asset.id
        assert response.data["file_size"] == 8000

        # Verify asset was updated, not duplicated
        assert BrandAsset.objects.filter(file_name="report.pdf").count() == 1
        existing_asset.refresh_from_db()
        assert existing_asset.file_size == 8000
        assert existing_asset.pipeline_status == "pending"
