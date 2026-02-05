"""
Phase 7.1: Backend Unit Tests for File Browser Feature

Tests for:
- Signed URL generation (GCSService)
- Signed URL API endpoint (BrandAssetViewSet.signed_url)
- Enhanced assets list with filters/pagination (BrandAssetViewSet.list)
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
from rest_framework import status
from rest_framework.test import APIClient  # noqa: F401

from files.services import GCSService


# ==========================================
# Signed URL Generation Tests (GCSService)
# ==========================================


class TestGCSServiceSignedUrl:
    """Test GCSService.generate_signed_url() method"""

    @pytest.fixture
    def gcs_service(self):
        return GCSService()

    def test_signed_url_generation_returns_url_and_expiry(self, gcs_service):
        """Verify signed URL includes url and expires_at fields"""
        with patch.object(gcs_service, "client", MagicMock()):
            with patch.object(gcs_service, "bucket", MagicMock()):
                mock_blob = MagicMock()
                mock_blob.generate_signed_url.return_value = (
                    "https://storage.googleapis.com/signed-url"
                )
                gcs_service.bucket.blob.return_value = mock_blob

                result = gcs_service.generate_signed_url(
                    file_path="test/file.pdf", expiration_minutes=15
                )

                assert "url" in result
                assert "expires_at" in result
                assert result["url"].startswith("https://")

    def test_signed_url_expiry_time_correct(self, gcs_service):
        """Verify URL includes correct expiration time (default 15 minutes)"""
        with patch.object(gcs_service, "client", MagicMock()):
            with patch.object(gcs_service, "bucket", MagicMock()):
                mock_blob = MagicMock()
                mock_blob.generate_signed_url.return_value = "https://test-url"
                gcs_service.bucket.blob.return_value = mock_blob

                before = datetime.utcnow()
                result = gcs_service.generate_signed_url(
                    file_path="test/file.pdf", expiration_minutes=15
                )
                after = datetime.utcnow()

                expires_at = datetime.fromisoformat(
                    result["expires_at"].replace("Z", "+00:00")
                ).replace(tzinfo=None)
                expected_min = before + timedelta(minutes=14, seconds=50)
                expected_max = after + timedelta(minutes=15, seconds=10)

                assert expected_min <= expires_at <= expected_max

    def test_signed_url_custom_expiry(self, gcs_service):
        """Verify custom expiration time works"""
        with patch.object(gcs_service, "client", MagicMock()):
            with patch.object(gcs_service, "bucket", MagicMock()):
                mock_blob = MagicMock()
                mock_blob.generate_signed_url.return_value = "https://test-url"
                gcs_service.bucket.blob.return_value = mock_blob

                result = gcs_service.generate_signed_url(
                    file_path="test/file.pdf", expiration_minutes=30
                )

                assert "expires_at" in result

    def test_signed_url_download_disposition(self, gcs_service):
        """Verify download URL includes content-disposition header"""
        with patch.object(gcs_service, "client", MagicMock()):
            with patch.object(gcs_service, "bucket", MagicMock()):
                mock_blob = MagicMock()
                mock_blob.generate_signed_url.return_value = "https://download-url"
                gcs_service.bucket.blob.return_value = mock_blob

                gcs_service.generate_signed_url(
                    file_path="test/file.pdf",
                    expiration_minutes=15,
                    for_download=True,
                    filename="my-file.pdf",
                )

                # Verify the blob's generate_signed_url was called with disposition
                call_kwargs = mock_blob.generate_signed_url.call_args[1]
                assert "response_disposition" in call_kwargs

    def test_signed_url_mock_mode_without_gcs(self, gcs_service):
        """Verify mock URL is returned when GCS not configured"""
        # Clear bucket to simulate no GCS
        gcs_service.bucket = None

        result = gcs_service.generate_signed_url(
            file_path="test/file.pdf", expiration_minutes=15
        )

        assert "url" in result
        assert "mock" in result["url"].lower() or "placeholder" in result["url"].lower()


# ==========================================
# Signed URL API Endpoint Tests
# ==========================================


@pytest.mark.django_db
class TestSignedUrlEndpoint:
    """Test GET /api/v1/assets/{id}/signed-url/ endpoint"""

    @pytest.fixture
    def authenticated_client(self, db, django_user_model):
        from tenants.models import Tenant, Domain
        import uuid

        # Create tenant with unique domain to avoid conflicts
        unique_id = uuid.uuid4().hex[:8]
        tenant = Tenant.objects.create(
            schema_name=f"test_signed_url_{unique_id}", name="Test Tenant"
        )
        domain_name = f"signedurl-{unique_id}.localhost"
        Domain.objects.create(domain=domain_name, tenant=tenant, is_primary=True)

        # Create user
        user = django_user_model.objects.create_user(
            username=f"testuser_{unique_id}",
            email=f"test_{unique_id}@example.com",
            password="testpass123",
        )

        client = APIClient()
        client.force_authenticate(user=user)
        client.defaults["SERVER_NAME"] = domain_name
        client.handler._force_tenant = tenant

        return client, user, tenant

    @pytest.fixture
    def test_asset(self, authenticated_client):
        client, user, tenant = authenticated_client
        from onboarding.models import Company, BrandAsset

        company = Company.objects.create(name="Test Company", tenant=tenant)

        asset = BrandAsset.objects.create(
            company=company,
            tenant=tenant,
            file_name="test-file.pdf",
            file_type="document",
            file_size=1024,
            gcs_path="test-tenant/test-file.pdf",
            pipeline_status="indexed",
        )

        return asset

    def test_signed_url_unauthorized(self, db):
        """Verify 401 for unauthenticated requests"""
        client = APIClient()
        client.defaults["SERVER_NAME"] = "localhost"

        response = client.get("/api/v1/assets/1/signed-url/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_signed_url_not_found(self, authenticated_client):
        """Verify 404 when asset doesn't exist"""
        client, user, tenant = authenticated_client

        response = client.get("/api/v1/assets/99999/signed-url/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    @patch("files.services.gcs_service.generate_signed_url")
    def test_signed_url_success(self, mock_generate, authenticated_client, test_asset):
        """Verify successful signed URL generation"""
        client, user, tenant = authenticated_client

        mock_generate.return_value = {
            "url": "https://storage.googleapis.com/signed-url",
            "expires_at": "2026-02-05T12:30:00Z",
        }

        response = client.get(f"/api/v1/assets/{test_asset.id}/signed-url/")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "view_url" in data
        assert "download_url" in data
        assert "expires_at" in data
        assert "file_name" in data

    def test_signed_url_no_gcs_path(self, authenticated_client):
        """Verify error when asset has no GCS path"""
        client, user, tenant = authenticated_client
        from onboarding.models import Company, BrandAsset

        company = Company.objects.create(name="Test Company", tenant=tenant)

        asset = BrandAsset.objects.create(
            company=company,
            tenant=tenant,
            file_name="no-path.pdf",
            file_type="document",
            file_size=1024,
            gcs_path=None,  # No GCS path
            pipeline_status="pending",
        )

        response = client.get(f"/api/v1/assets/{asset.id}/signed-url/")
        assert response.status_code == status.HTTP_400_BAD_REQUEST


# ==========================================
# Assets List with Filters & Pagination Tests
# ==========================================


@pytest.mark.django_db
class TestAssetsListFiltering:
    """Test GET /api/v1/assets/ with search, filters, and sorting"""

    @pytest.fixture
    def authenticated_client_with_assets(self, db, django_user_model):
        from tenants.models import Tenant, Domain
        from onboarding.models import Company, BrandAsset
        import uuid

        # Create tenant with unique domain to avoid conflicts
        unique_id = uuid.uuid4().hex[:8]
        tenant = Tenant.objects.create(
            schema_name=f"test_filters_{unique_id}", name="Test Tenant"
        )
        domain_name = f"filters-{unique_id}.localhost"
        Domain.objects.create(domain=domain_name, tenant=tenant, is_primary=True)

        # Create user
        user = django_user_model.objects.create_user(
            username=f"testuser2_{unique_id}",
            email=f"test2_{unique_id}@example.com",
            password="testpass123",
        )

        # Create company
        company = Company.objects.create(name="Test Company", tenant=tenant)

        # Create test assets
        assets = []
        for i in range(15):
            ext = "pdf" if i % 3 == 0 else "jpg" if i % 3 == 1 else "mp4"
            asset = BrandAsset.objects.create(
                company=company,
                tenant=tenant,
                file_name=f"test-file-{i:02d}.{ext}",
                file_type="document"
                if i % 3 == 0
                else "image"
                if i % 3 == 1
                else "video",
                file_size=1024 * (i + 1),
                gcs_path=f"tenant/file-{i}.test",
                pipeline_status="indexed"
                if i < 10
                else "pending"
                if i < 12
                else "failed",
            )
            assets.append(asset)

        client = APIClient()
        client.force_authenticate(user=user)
        client.defaults["SERVER_NAME"] = domain_name
        client.handler._force_tenant = tenant

        return client, assets

    def test_assets_list_search(self, authenticated_client_with_assets):
        """Verify search parameter filters by filename"""
        client, assets = authenticated_client_with_assets

        response = client.get("/api/v1/assets/?search=test-file-01")
        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        assert data["count"] >= 1
        assert all("01" in r["file_name"] for r in data["results"])

    def test_assets_list_file_type_filter(self, authenticated_client_with_assets):
        """Verify file_type filter works correctly"""
        client, assets = authenticated_client_with_assets

        response = client.get("/api/v1/assets/?file_type=image")
        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        assert all(r["file_type"] == "image" for r in data["results"])

    def test_assets_list_status_filter(self, authenticated_client_with_assets):
        """Verify status filter works correctly"""
        client, assets = authenticated_client_with_assets

        response = client.get("/api/v1/assets/?status=indexed")
        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        assert all(r["pipeline_status"] == "indexed" for r in data["results"])

    def test_assets_list_sort_by_date_desc(self, authenticated_client_with_assets):
        """Verify sorting by uploaded_at descending (default)"""
        client, assets = authenticated_client_with_assets

        response = client.get("/api/v1/assets/?sort_by=uploaded_at&sort_order=desc")
        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        results = data["results"]
        # Verify descending order
        for i in range(len(results) - 1):
            assert results[i]["uploaded_at"] >= results[i + 1]["uploaded_at"]

    def test_assets_list_sort_by_name_asc(self, authenticated_client_with_assets):
        """Verify sorting by file_name ascending"""
        client, assets = authenticated_client_with_assets

        response = client.get("/api/v1/assets/?sort_by=file_name&sort_order=asc")
        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        results = data["results"]
        # Verify ascending order
        for i in range(len(results) - 1):
            assert results[i]["file_name"] <= results[i + 1]["file_name"]

    def test_assets_list_sort_by_size(self, authenticated_client_with_assets):
        """Verify sorting by file_size"""
        client, assets = authenticated_client_with_assets

        response = client.get("/api/v1/assets/?sort_by=file_size&sort_order=desc")
        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        results = data["results"]
        # Verify descending order by size
        for i in range(len(results) - 1):
            assert results[i]["file_size"] >= results[i + 1]["file_size"]

    def test_assets_list_limit_3(self, authenticated_client_with_assets):
        """Verify limit parameter returns correct number (3)"""
        client, assets = authenticated_client_with_assets

        response = client.get("/api/v1/assets/?limit=3")
        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        assert data["showing"] == 3
        assert len(data["results"]) == 3
        assert data["has_more"] is True

    def test_assets_list_limit_6(self, authenticated_client_with_assets):
        """Verify limit parameter returns correct number (6)"""
        client, assets = authenticated_client_with_assets

        response = client.get("/api/v1/assets/?limit=6")
        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        assert data["showing"] == 6
        assert len(data["results"]) == 6

    def test_assets_list_limit_9(self, authenticated_client_with_assets):
        """Verify limit parameter returns correct number (9)"""
        client, assets = authenticated_client_with_assets

        response = client.get("/api/v1/assets/?limit=9")
        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        assert data["showing"] == 9
        assert len(data["results"]) == 9

    def test_assets_list_combined_filters(self, authenticated_client_with_assets):
        """Verify multiple filters work together"""
        client, assets = authenticated_client_with_assets

        response = client.get(
            "/api/v1/assets/?file_type=image&status=indexed&sort_by=file_name"
        )
        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        assert data["filters_applied"]["file_type"] == "image"
        assert data["filters_applied"]["status"] == "indexed"
        assert data["filters_applied"]["sort_by"] == "file_name"


@pytest.mark.django_db
class TestAssetsListPagination:
    """Test pagination functionality of assets list"""

    @pytest.fixture
    def authenticated_client_with_many_assets(self, db, django_user_model):
        from tenants.models import Tenant, Domain
        from onboarding.models import Company, BrandAsset
        import uuid

        # Create tenant with unique domain to avoid conflicts
        unique_id = uuid.uuid4().hex[:8]
        tenant = Tenant.objects.create(
            schema_name=f"test_pagination_{unique_id}", name="Test Tenant"
        )
        domain_name = f"pagination-{unique_id}.localhost"
        Domain.objects.create(domain=domain_name, tenant=tenant, is_primary=True)

        # Create user
        user = django_user_model.objects.create_user(
            username=f"testuser3_{unique_id}",
            email=f"test3_{unique_id}@example.com",
            password="testpass123",
        )

        # Create company
        company = Company.objects.create(name="Test Company", tenant=tenant)

        # Create 45 test assets
        assets = []
        for i in range(45):
            asset = BrandAsset.objects.create(
                company=company,
                tenant=tenant,
                file_name=f"file-{i:03d}.pdf",
                file_type="document",
                file_size=1024,
                gcs_path=f"tenant/file-{i}.pdf",
                pipeline_status="indexed",
            )
            assets.append(asset)

        client = APIClient()
        client.force_authenticate(user=user)
        client.defaults["SERVER_NAME"] = domain_name
        client.handler._force_tenant = tenant

        return client, assets

    def test_pagination_first_page(self, authenticated_client_with_many_assets):
        """Verify page=1 returns correct items"""
        client, assets = authenticated_client_with_many_assets

        response = client.get("/api/v1/assets/?page=1&page_size=10")
        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        assert data["current_page"] == 1
        assert data["page_size"] == 10
        assert len(data["results"]) == 10
        assert data["has_previous"] is False
        assert data["has_next"] is True

    def test_pagination_middle_page(self, authenticated_client_with_many_assets):
        """Verify page=3 returns correct offset"""
        client, assets = authenticated_client_with_many_assets

        response = client.get("/api/v1/assets/?page=3&page_size=10")
        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        assert data["current_page"] == 3
        assert len(data["results"]) == 10
        assert data["has_previous"] is True
        assert data["has_next"] is True

    def test_pagination_last_page(self, authenticated_client_with_many_assets):
        """Verify last page has correct item count"""
        client, assets = authenticated_client_with_many_assets

        response = client.get("/api/v1/assets/?page=5&page_size=10")
        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        assert data["current_page"] == 5
        assert len(data["results"]) == 5  # 45 total, 10 per page, page 5 has 5
        assert data["has_previous"] is True
        assert data["has_next"] is False

    def test_pagination_out_of_bounds(self, authenticated_client_with_many_assets):
        """Verify page beyond total returns empty results"""
        client, assets = authenticated_client_with_many_assets

        response = client.get("/api/v1/assets/?page=999&page_size=10")
        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        assert len(data["results"]) == 0

    def test_pagination_page_size_25(self, authenticated_client_with_many_assets):
        """Verify page_size=25 returns 25 items"""
        client, assets = authenticated_client_with_many_assets

        response = client.get("/api/v1/assets/?page=1&page_size=25")
        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        assert data["page_size"] == 25
        assert len(data["results"]) == 25
        assert data["total_pages"] == 2

    def test_pagination_max_page_size(self, authenticated_client_with_many_assets):
        """Verify page_size>50 is capped at 50"""
        client, assets = authenticated_client_with_many_assets

        response = client.get("/api/v1/assets/?page=1&page_size=100")
        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        assert data["page_size"] == 50  # Capped at 50

    def test_pagination_with_filters(self, authenticated_client_with_many_assets):
        """Verify pagination works with search/filters"""
        client, assets = authenticated_client_with_many_assets

        response = client.get("/api/v1/assets/?page=1&page_size=10&search=file-00")
        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        # file-000 through file-009 match "file-00"
        assert data["count"] == 10
        assert data["filters_applied"]["search"] == "file-00"

    def test_pagination_metadata(self, authenticated_client_with_many_assets):
        """Verify has_next, has_previous, total_pages are correct"""
        client, assets = authenticated_client_with_many_assets

        response = client.get("/api/v1/assets/?page=2&page_size=10")
        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        assert data["count"] == 45
        assert data["total_pages"] == 5
        assert data["has_next"] is True
        assert data["has_previous"] is True
        assert data["next"] is not None
        assert data["previous"] is not None
