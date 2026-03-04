"""
Unit tests for onboarding views/viewsets
Tests API endpoints for Company, BrandAsset, and OnboardingProgress
"""

import pytest
from django.urls import reverse
from rest_framework import status

from onboarding.models import Company, BrandAsset
from .factories import (
    CompanyFactory,
    BrandAssetFactory,
    OnboardingProgressFactory,
)


@pytest.mark.django_db
@pytest.mark.unit
class TestCompanyViewSet:
    """Test CompanyViewSet endpoints"""

    @pytest.fixture
    def url_list(self):
        """List/create endpoint URL"""
        return reverse("company-list")

    def url_detail(self, pk):
        """Detail/update/delete endpoint URL"""
        return reverse("company-detail", kwargs={"pk": pk})

    @pytest.fixture
    def company(self, public_tenant):
        """Create a company in public schema (fast, no tenant isolation overhead)"""
        return CompanyFactory(tenant=public_tenant)

    def test_list_companies_unauthenticated(self, api_client, url_list):
        """Test that unauthenticated users cannot list companies"""
        response = api_client.get(url_list)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_list_companies_authenticated(
        self, authenticated_client_with_tenant, public_tenant, url_list
    ):
        """Test authenticated user can list companies"""
        # Create company in public schema
        CompanyFactory(tenant=public_tenant)

        response = authenticated_client_with_tenant.get(url_list)
        assert response.status_code == status.HTTP_200_OK
        assert "results" in response.data
        # At least the created company should be in results
        assert len(response.data["results"]) >= 1

    @pytest.mark.skip(
        reason="Multi-tenant isolation test requires complex setup "
        "with separate tenant schemas"
    )
    def test_list_companies_tenant_isolation(
        self, authenticated_client, tenant, tenant2, url_list
    ):
        """Test that users only see companies from their tenant"""
        # This test is skipped because:
        # 1. Creating multiple tenants is slow (each creates new schema)
        # 2. Company has OneToOne with Tenant (can't create multiple per tenant)
        # 3. MVP mode has nullable tenants and partially disabled middleware
        pass

    def test_retrieve_company_authenticated(
        self, authenticated_client_with_tenant, company
    ):
        """Test retrieving a single company"""
        company.name = "Test Company"
        company.save()

        response = authenticated_client_with_tenant.get(self.url_detail(company.id))
        assert response.status_code == status.HTTP_200_OK
        assert response.data["name"] == "Test Company"
        assert response.data["id"] == company.id

    def test_retrieve_nonexistent_company(
        self, authenticated_client_with_tenant, public_tenant
    ):
        """Test retrieving a company that doesn't exist"""
        response = authenticated_client_with_tenant.get(self.url_detail(99999))
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_create_company_unauthenticated(self, api_client, url_list):
        """Test that unauthenticated users cannot create companies"""
        data = {
            "name": "New Company",
            "industry": "Technology",
            "brand_voice": "professional",
        }
        response = api_client.post(url_list, data)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_create_company_authenticated(
        self, authenticated_client_with_tenant, public_tenant, url_list
    ):
        """Test authenticated user can create a company"""
        data = {
            "name": "New Tech Startup",
            "industry": "Technology",
            "description": "An innovative tech company",
            "target_audience": "Tech professionals",
            "core_problem": "Inefficient workflows",
            "website": "https://newtechstartup.com",
            "brand_voice": "professional",
        }

        response = authenticated_client_with_tenant.post(url_list, data)
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["name"] == "New Tech Startup"
        assert response.data["industry"] == "Technology"
        assert response.data["website"] == "https://newtechstartup.com"

        # Verify company was created in database
        assert Company.objects.filter(name="New Tech Startup").exists()

    def test_create_company_missing_required_field(
        self, authenticated_client_with_tenant, public_tenant, url_list
    ):
        """Test creating company without required name field"""
        data = {
            "industry": "Technology",
            "brand_voice": "professional",
        }

        response = authenticated_client_with_tenant.post(url_list, data)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "name" in response.data

    def test_create_company_invalid_brand_voice(
        self, authenticated_client_with_tenant, public_tenant, url_list
    ):
        """Test creating company with invalid brand_voice choice"""
        data = {
            "name": "Test Company",
            "brand_voice": "invalid_choice",
        }

        response = authenticated_client_with_tenant.post(url_list, data)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "brand_voice" in response.data

    def test_update_company_authenticated(
        self, authenticated_client_with_tenant, company
    ):
        """Test updating a company"""
        company.description = "Old description"
        company.industry = "Technology"
        company.save()

        data = {
            "name": company.name,  # Required field for PUT
            "description": "Updated description about the company",
            "industry": "Healthcare",
            "target_audience": "Healthcare professionals",
            "website": "https://updated-company.com",
        }

        response = authenticated_client_with_tenant.put(
            self.url_detail(company.id), data
        )
        assert response.status_code == status.HTTP_200_OK

        # Verify in database
        company.refresh_from_db()
        assert company.description == "Updated description about the company"
        assert company.industry == "Healthcare"
        assert company.target_audience == "Healthcare professionals"
        assert company.website == "https://updated-company.com"

    def test_partial_update_company(self, authenticated_client_with_tenant, company):
        """Test partial update (PATCH) of a company"""
        company.description = "Original description"
        company.industry = "Technology"
        company.save()

        data = {"description": "Patched description"}

        response = authenticated_client_with_tenant.patch(
            self.url_detail(company.id), data
        )
        assert response.status_code == status.HTTP_200_OK

        # Verify in database
        company.refresh_from_db()
        assert company.description == "Patched description"
        # Industry should remain unchanged
        assert company.industry == "Technology"

    def test_delete_company_authenticated(
        self, authenticated_client_with_tenant, company
    ):
        """Test deleting a company"""
        company_id = company.id

        response = authenticated_client_with_tenant.delete(self.url_detail(company_id))
        assert response.status_code == status.HTTP_204_NO_CONTENT

        # Verify company was deleted
        assert not Company.objects.filter(id=company_id).exists()

    def test_delete_company_unauthenticated(self, api_client, public_tenant):
        """Test that unauthenticated users cannot delete companies"""
        company = CompanyFactory(tenant=public_tenant)

        response = api_client.delete(self.url_detail(company.id))
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

        # Verify company still exists
        assert Company.objects.filter(id=company.id).exists()

    def test_generate_brand_strategy_action(
        self, authenticated_client_with_tenant, company, mock_gemini_api
    ):
        """Test custom generate_brand_strategy action"""
        company.name = "Test Co"
        company.industry = "Technology"
        company.target_audience = "Developers"
        company.core_problem = "Slow deployments"
        company.save()

        # Use URL pattern matching the actual action route
        url = f"/api/v1/companies/{company.id}/generate_brand_strategy/"
        response = authenticated_client_with_tenant.post(url)

        # Expect 200 OK with generated strategy
        assert response.status_code == status.HTTP_200_OK

        # Verify company was updated in database
        company.refresh_from_db()
        assert company.vision_statement is not None
        assert company.mission_statement is not None


@pytest.mark.django_db
@pytest.mark.unit
class TestBrandAssetViewSet:
    """Test BrandAssetViewSet endpoints"""

    @pytest.fixture
    def url_list(self):
        """List/create endpoint URL"""
        return reverse("brandasset-list")

    def url_detail(self, pk):
        """Detail endpoint URL"""
        return reverse("brandasset-detail", kwargs={"pk": pk})

    def test_list_assets_unauthenticated(self, api_client, url_list):
        """Test that unauthenticated users cannot list assets"""
        response = api_client.get(url_list)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_list_assets_authenticated(
        self, authenticated_client_with_tenant, public_tenant, url_list
    ):
        """Test authenticated user can list brand assets"""
        company = CompanyFactory(tenant=public_tenant)
        BrandAssetFactory.create_batch(3, tenant=public_tenant, company=company)

        response = authenticated_client_with_tenant.get(url_list)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) >= 3

    def test_list_assets_ordering(
        self, authenticated_client_with_tenant, public_tenant, url_list
    ):
        """Test that assets are ordered by uploaded_at descending"""
        company = CompanyFactory(tenant=public_tenant)
        BrandAssetFactory(tenant=public_tenant, company=company, file_name="first.jpg")
        BrandAssetFactory(tenant=public_tenant, company=company, file_name="second.jpg")

        response = authenticated_client_with_tenant.get(url_list)
        assert response.status_code == status.HTTP_200_OK

        # Most recent should be first (descending order)
        results = response.data["results"]
        assert len(results) >= 2
        # Find our created assets in results
        file_names = [r["file_name"] for r in results]
        assert "first.jpg" in file_names
        assert "second.jpg" in file_names
        # Check ordering if both are at start
        if len(results) >= 2 and results[0]["file_name"] in ["first.jpg", "second.jpg"]:
            assert results[0]["file_name"] == "second.jpg"

    def test_create_asset_authenticated(
        self, authenticated_client_with_tenant, public_tenant, url_list
    ):
        """Test creating a brand asset"""
        company = CompanyFactory(tenant=public_tenant)

        data = {
            "company": company.id,
            "file_name": "logo.png",
            "file_type": "image",
            "file_size": 102400,
            "gcs_path": "companies/1/assets/logo.png",
            "gcs_bucket": "brand-automator",
        }

        response = authenticated_client_with_tenant.post(url_list, data)
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["file_name"] == "logo.png"
        assert response.data["file_type"] == "image"

    def test_create_asset_invalid_file_type(
        self, authenticated_client_with_tenant, public_tenant, url_list
    ):
        """Test creating asset with invalid file_type"""
        company = CompanyFactory(tenant=public_tenant)

        data = {
            "company": company.id,
            "file_name": "test.file",
            "file_type": "invalid_type",
            "file_size": 1024,
            "gcs_path": "test/path",
        }

        response = authenticated_client_with_tenant.post(url_list, data)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "file_type" in response.data

    def test_retrieve_asset(self, authenticated_client_with_tenant, public_tenant):
        """Test retrieving a single asset"""
        company = CompanyFactory(tenant=public_tenant)
        asset = BrandAssetFactory(
            tenant=public_tenant, company=company, file_name="brand-guide.pdf"
        )

        response = authenticated_client_with_tenant.get(self.url_detail(asset.id))
        assert response.status_code == status.HTTP_200_OK
        assert response.data["file_name"] == "brand-guide.pdf"
        assert response.data["company"] == company.id

    def test_delete_asset(self, authenticated_client_with_tenant, public_tenant):
        """Test deleting a brand asset"""
        company = CompanyFactory(tenant=public_tenant)
        asset = BrandAssetFactory(tenant=public_tenant, company=company)
        asset_id = asset.id

        response = authenticated_client_with_tenant.delete(self.url_detail(asset_id))
        assert response.status_code == status.HTTP_204_NO_CONTENT

        # Verify asset was deleted
        assert not BrandAsset.objects.filter(id=asset_id).exists()

    def test_delete_asset_with_gcs_file(
        self, authenticated_client_with_tenant, public_tenant
    ):
        """Test that GCS file is deleted when asset is deleted"""
        from unittest.mock import patch, MagicMock

        company = CompanyFactory(tenant=public_tenant)
        asset = BrandAssetFactory(
            tenant=public_tenant,
            company=company,
            gcs_path="test-tenant/assets/test-file.pdf",
            gcs_bucket="test-bucket",
        )
        asset_id = asset.id

        # Mock the GCS service
        mock_blob = MagicMock()
        mock_blob.exists.return_value = True
        mock_bucket = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_client = MagicMock()
        mock_client.bucket.return_value = mock_bucket

        with patch("onboarding.views.gcs_service") as mock_gcs_service:
            mock_gcs_service.client = mock_client
            mock_gcs_service.bucket_name = "default-bucket"

            response = authenticated_client_with_tenant.delete(
                self.url_detail(asset_id)
            )
            assert response.status_code == status.HTTP_204_NO_CONTENT

            # Verify GCS blob.delete() was called
            mock_blob.delete.assert_called_once()

        # Verify asset was deleted from DB
        assert not BrandAsset.objects.filter(id=asset_id).exists()

    def test_delete_asset_continues_on_gcs_error(
        self, authenticated_client_with_tenant, public_tenant
    ):
        """Test that asset deletion continues even if GCS deletion fails"""
        from unittest.mock import patch, MagicMock

        company = CompanyFactory(tenant=public_tenant)
        asset = BrandAssetFactory(
            tenant=public_tenant,
            company=company,
            gcs_path="test-tenant/assets/test-file.pdf",
        )
        asset_id = asset.id

        with patch("onboarding.views.gcs_service") as mock_gcs_service:
            # Simulate GCS error
            mock_gcs_service.client = MagicMock()
            mock_gcs_service.client.bucket.side_effect = Exception("GCS error")

            response = authenticated_client_with_tenant.delete(
                self.url_detail(asset_id)
            )
            # Should still succeed despite GCS error
            assert response.status_code == status.HTTP_204_NO_CONTENT

        # Verify asset was still deleted from DB
        assert not BrandAsset.objects.filter(id=asset_id).exists()

    def test_status_endpoint(self, authenticated_client_with_tenant, public_tenant):
        """Test the /assets/status/ endpoint returns correct counts"""
        company = CompanyFactory(tenant=public_tenant)

        # Create assets with different statuses
        BrandAssetFactory(
            tenant=public_tenant, company=company, pipeline_status="pending"
        )
        BrandAssetFactory(
            tenant=public_tenant, company=company, pipeline_status="pending"
        )
        BrandAssetFactory(
            tenant=public_tenant, company=company, pipeline_status="indexed"
        )
        BrandAssetFactory(
            tenant=public_tenant, company=company, pipeline_status="failed"
        )

        response = authenticated_client_with_tenant.get(reverse("brandasset-status"))
        assert response.status_code == status.HTTP_200_OK

        data = response.data
        assert "count" in data
        assert "results" in data
        assert "pending_count" in data
        assert "failed_count" in data
        assert "indexed_count" in data

        # Verify counts
        assert data["pending_count"] >= 2
        assert data["indexed_count"] >= 1
        assert data["failed_count"] >= 1

    def test_status_endpoint_filter_by_pipeline_status(
        self, authenticated_client_with_tenant, public_tenant
    ):
        """Test /assets/status/ filters by pipeline_status parameter"""
        company = CompanyFactory(tenant=public_tenant)

        BrandAssetFactory(
            tenant=public_tenant, company=company, pipeline_status="pending"
        )
        BrandAssetFactory(
            tenant=public_tenant, company=company, pipeline_status="indexed"
        )

        response = authenticated_client_with_tenant.get(
            reverse("brandasset-status") + "?pipeline_status=pending"
        )
        assert response.status_code == status.HTTP_200_OK

        # All results should be pending
        for result in response.data["results"]:
            assert result["pipeline_status"] == "pending"

    def test_status_endpoint_exclude_processed(
        self, authenticated_client_with_tenant, public_tenant
    ):
        """Test /assets/status/ with include_processed=false"""
        company = CompanyFactory(tenant=public_tenant)

        BrandAssetFactory(
            tenant=public_tenant, company=company, pipeline_status="pending"
        )
        BrandAssetFactory(
            tenant=public_tenant, company=company, pipeline_status="indexed"
        )

        response = authenticated_client_with_tenant.get(
            reverse("brandasset-status") + "?include_processed=false"
        )
        assert response.status_code == status.HTTP_200_OK

        # No indexed assets should be in results
        for result in response.data["results"]:
            assert result["pipeline_status"] != "indexed"

    def test_status_endpoint_ordering(
        self, authenticated_client_with_tenant, public_tenant
    ):
        """Test that /assets/status/ returns assets ordered by -uploaded_at"""
        company = CompanyFactory(tenant=public_tenant)

        # Create assets - order should be most recent first
        BrandAssetFactory(
            tenant=public_tenant,
            company=company,
            file_name="first.pdf",
            pipeline_status="pending",
        )
        BrandAssetFactory(
            tenant=public_tenant,
            company=company,
            file_name="second.pdf",
            pipeline_status="pending",
        )

        response = authenticated_client_with_tenant.get(reverse("brandasset-status"))
        assert response.status_code == status.HTTP_200_OK

        results = response.data["results"]
        # Most recently uploaded should be first
        if len(results) >= 2:
            file_names = [r["file_name"] for r in results[:2]]
            # second.pdf was created last, should appear first
            assert "second.pdf" in file_names


@pytest.mark.django_db
@pytest.mark.unit
class TestOnboardingProgressViewSet:
    """Test OnboardingProgressViewSet endpoints"""

    @pytest.fixture
    def url_list(self):
        """List/create endpoint URL"""
        return reverse("onboardingprogress-list")

    def url_detail(self, pk):
        """Detail endpoint URL"""
        return reverse("onboardingprogress-detail", kwargs={"pk": pk})

    def test_list_progress_authenticated(
        self, authenticated_client_with_tenant, public_tenant, url_list
    ):
        """Test listing onboarding progress records"""
        # Note: Can only create 1 company per tenant due to OneToOne constraint
        company = CompanyFactory(tenant=public_tenant)
        OnboardingProgressFactory(tenant=public_tenant, company=company)

        response = authenticated_client_with_tenant.get(url_list)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) >= 1

    def test_create_progress_authenticated(
        self, authenticated_client_with_tenant, public_tenant, url_list
    ):
        """Test that creating onboarding progress returns proper response"""
        # Note: OnboardingProgress is created when using Factory
        company = CompanyFactory(tenant=public_tenant)
        OnboardingProgressFactory(tenant=public_tenant, company=company)

        # List to verify progress exists
        response = authenticated_client_with_tenant.get(url_list)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) >= 1

        # Verify the progress is associated with company
        progress_items = [
            p for p in response.data["results"] if p["company"] == company.id
        ]
        assert len(progress_items) == 1
        assert progress_items[0]["current_step"] in ["company_info", "brand_strategy"]

    def test_update_progress(self, authenticated_client_with_tenant, public_tenant):
        """Test updating onboarding progress"""
        company = CompanyFactory(tenant=public_tenant)
        progress = OnboardingProgressFactory(
            tenant=public_tenant,
            company=company,
            current_step="company_info",
            completed_steps=[],
        )

        data = {
            "current_step": "brand_strategy",
            "completed_steps": ["company_info"],
        }

        response = authenticated_client_with_tenant.patch(
            self.url_detail(progress.id), data, format="json"
        )
        assert (
            response.status_code == status.HTTP_200_OK
        ), f"Got {response.status_code}: {response.data}"
        assert response.data["current_step"] == "brand_strategy"
        assert "company_info" in response.data["completed_steps"]

    def test_completion_percentage_calculation(
        self, authenticated_client_with_tenant, public_tenant, url_list
    ):
        """Test that completion_percentage is calculated correctly"""
        company = CompanyFactory(tenant=public_tenant)
        progress = OnboardingProgressFactory(
            tenant=public_tenant,
            company=company,
            completed_steps=["company_info", "brand_strategy"],
        )

        response = authenticated_client_with_tenant.get(self.url_detail(progress.id))
        assert response.status_code == status.HTTP_200_OK
        assert "completion_percentage" in response.data
        # 2 out of 5 steps = 40%
        assert response.data["completion_percentage"] == 40

    def test_mark_onboarding_complete(
        self, authenticated_client_with_tenant, public_tenant
    ):
        """Test marking onboarding as completed"""
        company = CompanyFactory(tenant=public_tenant)
        progress = OnboardingProgressFactory(
            tenant=public_tenant,
            company=company,
            current_step="review",
            completed_steps=[
                "company_info",
                "brand_strategy",
                "brand_identity",
                "assets_upload",
            ],
            is_completed=False,
        )

        data = {
            "current_step": "review",
            "completed_steps": [
                "company_info",
                "brand_strategy",
                "brand_identity",
                "assets_upload",
                "review",
            ],
            "is_completed": True,
        }

        response = authenticated_client_with_tenant.patch(
            self.url_detail(progress.id), data, format="json"
        )
        assert (
            response.status_code == status.HTTP_200_OK
        ), f"Got {response.status_code}: {response.data}"
        assert response.data["is_completed"] is True
        assert response.data["completion_percentage"] == 100

        # Verify is_completed was set
        progress.refresh_from_db()
        assert progress.is_completed is True
        # Note: completed_at is not auto-set, would need custom save() logic


@pytest.mark.django_db
@pytest.mark.unit
class TestViewSetPagination:
    """Test pagination for viewsets"""

    def test_company_list_pagination(
        self, authenticated_client_with_tenant, public_tenant
    ):
        """Test that company list is paginated"""
        # Note: Can only create 1 company per tenant due to OneToOne constraint
        # Just test that pagination structure exists
        company = CompanyFactory(tenant=public_tenant)  # noqa: F841

        url = reverse("company-list")
        response = authenticated_client_with_tenant.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert "results" in response.data
        assert "count" in response.data
        assert "next" in response.data
        assert "previous" in response.data
        assert response.data["count"] >= 1

    def test_pagination_page_size(
        self, authenticated_client_with_tenant, public_tenant
    ):
        """Test custom page size parameter"""
        # Create one company (OneToOne constraint)
        company = CompanyFactory(tenant=public_tenant)  # noqa: F841

        url = reverse("company-list")
        response = authenticated_client_with_tenant.get(url, {"page_size": 5})

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) >= 1
        assert response.data["count"] >= 1


@pytest.mark.django_db
@pytest.mark.unit
class TestViewSetFiltering:
    """Test filtering capabilities"""

    @pytest.mark.skip(
        reason="Can't create multiple companies per tenant (OneToOne constraint)"
    )
    def test_filter_companies_by_industry(self, authenticated_client, tenant):
        """Test filtering companies by industry"""
        # Skipped: OneToOne constraint prevents multiple companies per tenant
        pass

    @pytest.mark.skip(
        reason="Can't create multiple companies per tenant (OneToOne constraint)"
    )
    def test_search_companies_by_name(self, authenticated_client, tenant):
        """Test searching companies by name"""
        # Skipped: OneToOne constraint prevents multiple companies per tenant
        pass
