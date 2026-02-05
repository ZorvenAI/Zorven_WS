"""
Phase 7.2: Backend Integration Tests for File Browser Feature

Integration tests that test the full flow:
- Upload file → List → Get signed URL → Verify accessible
- Delete file → Verify removed from list
- Pagination consistency across pages
"""

import pytest
from unittest.mock import patch
from rest_framework import status
from rest_framework.test import APIClient  # noqa: F401

from onboarding.models import BrandAsset


@pytest.mark.django_db
class TestFileBrowserIntegration:
    """Integration tests for file browser feature"""

    @pytest.fixture
    def authenticated_client_with_company(self, db, django_user_model):
        from tenants.models import Tenant, Domain
        from onboarding.models import Company
        import uuid

        # Create tenant with unique domain to avoid conflicts
        unique_id = uuid.uuid4().hex[:8]
        tenant = Tenant.objects.create(
            schema_name=f"test_integration_{unique_id}", name="Test Tenant"
        )
        domain_name = f"integration-{unique_id}.localhost"
        Domain.objects.create(domain=domain_name, tenant=tenant, is_primary=True)

        # Create user
        user = django_user_model.objects.create_user(
            username=f"integrationuser_{unique_id}",
            email=f"integration_{unique_id}@example.com",
            password="testpass123",
        )

        # Create company
        company = Company.objects.create(name="Integration Test Company", tenant=tenant)

        client = APIClient()
        client.force_authenticate(user=user)
        client.defaults["SERVER_NAME"] = domain_name
        client._force_tenant = tenant

        return client, user, tenant, company

    @patch("files.services.gcs_service.generate_signed_url")
    def test_full_upload_and_browse_flow(
        self, mock_signed_url, authenticated_client_with_company
    ):
        """Upload file → List → Get signed URL → Verify accessible"""
        client, user, tenant, company = authenticated_client_with_company

        # Mock GCS signed URL
        mock_signed_url.return_value = {
            "url": "https://storage.googleapis.com/test-signed-url",
            "expires_at": "2026-02-05T12:30:00Z",
        }

        # Step 1: Create an asset (simulating upload)
        BrandAsset.objects.create(
            company=company,
            tenant=tenant,
            file_name="integration-test.pdf",
            file_type="document",
            file_size=2048,
            gcs_path="test-tenant/integration-test.pdf",
            pipeline_status="indexed",
        )

        # Step 2: List assets
        response = client.get("/api/v1/assets/")
        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        assert data["count"] >= 1

        # Find our asset in results
        found = False
        for result in data["results"]:
            if result["file_name"] == "integration-test.pdf":
                found = True
                asset_id = result["id"]
                break
        assert found, "Created asset not found in list"

        # Step 3: Get signed URL
        response = client.get(f"/api/v1/assets/{asset_id}/signed-url/")
        assert response.status_code == status.HTTP_200_OK

        signed_data = response.json()
        assert "view_url" in signed_data
        assert "download_url" in signed_data
        assert "expires_at" in signed_data
        assert signed_data["file_name"] == "integration-test.pdf"

    def test_delete_then_list(self, authenticated_client_with_company):
        """Delete file → Verify removed from list"""
        client, user, tenant, company = authenticated_client_with_company

        # Create an asset
        asset = BrandAsset.objects.create(
            company=company,
            tenant=tenant,
            file_name="to-be-deleted.pdf",
            file_type="document",
            file_size=1024,
            gcs_path="test-tenant/to-be-deleted.pdf",
            pipeline_status="indexed",
        )
        asset_id = asset.id

        # Verify asset exists in list
        response = client.get("/api/v1/assets/")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        found = any(r["file_name"] == "to-be-deleted.pdf" for r in data["results"])
        assert found, "Asset should be in list before delete"

        # Delete the asset
        with patch("files.services.gcs_service.delete_file", return_value=True):
            response = client.delete(f"/api/v1/assets/{asset_id}/")
            assert response.status_code == status.HTTP_204_NO_CONTENT

        # Verify asset is removed from list
        response = client.get("/api/v1/assets/")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        found = any(r["file_name"] == "to-be-deleted.pdf" for r in data["results"])
        assert not found, "Deleted asset should not be in list"

    def test_pagination_consistency(self, authenticated_client_with_company):
        """Navigate pages → no duplicates or missing items"""
        client, user, tenant, company = authenticated_client_with_company

        # Create 25 assets
        for i in range(25):
            BrandAsset.objects.create(
                company=company,
                tenant=tenant,
                file_name=f"pagination-test-{i:02d}.pdf",
                file_type="document",
                file_size=1024 * (i + 1),
                gcs_path=f"test-tenant/pagination-{i}.pdf",
                pipeline_status="indexed",
            )

        # Collect all IDs across pages
        all_ids = set()
        page = 1
        page_size = 10

        while True:
            response = client.get(f"/api/v1/assets/?page={page}&page_size={page_size}")
            assert response.status_code == status.HTTP_200_OK

            data = response.json()

            for result in data["results"]:
                # Check for duplicates
                assert (
                    result["id"] not in all_ids
                ), f"Duplicate ID {result['id']} found on page {page}"
                all_ids.add(result["id"])

            if not data["has_next"]:
                break
            page += 1

            # Safety limit
            if page > 10:
                break

        # Verify we got all items
        assert len(all_ids) == 25, f"Expected 25 items, got {len(all_ids)}"

    def test_filter_persistence_across_pages(self, authenticated_client_with_company):
        """Filters persist correctly when navigating pages"""
        client, user, tenant, company = authenticated_client_with_company

        # Create mixed assets
        for i in range(20):
            BrandAsset.objects.create(
                company=company,
                tenant=tenant,
                file_name=f"filter-test-{i:02d}.{'jpg' if i % 2 == 0 else 'pdf'}",
                file_type="image" if i % 2 == 0 else "document",
                file_size=1024,
                gcs_path=f"test-tenant/filter-{i}.test",
                pipeline_status="indexed",
            )

        # Get page 1 with filter
        response = client.get("/api/v1/assets/?page=1&page_size=5&file_type=image")
        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        assert data["filters_applied"]["file_type"] == "image"
        assert all(r["file_type"] == "image" for r in data["results"])

        # Get page 2 with same filter
        if data["has_next"]:
            response = client.get("/api/v1/assets/?page=2&page_size=5&file_type=image")
            assert response.status_code == status.HTTP_200_OK

            data = response.json()
            assert data["filters_applied"]["file_type"] == "image"
            assert all(r["file_type"] == "image" for r in data["results"])

    def test_search_with_pagination(self, authenticated_client_with_company):
        """Search works correctly with pagination"""
        client, user, tenant, company = authenticated_client_with_company

        # Create assets with specific naming pattern
        for i in range(15):
            BrandAsset.objects.create(
                company=company,
                tenant=tenant,
                file_name=f"searchable-item-{i:02d}.pdf"
                if i < 12
                else f"other-item-{i}.pdf",
                file_type="document",
                file_size=1024,
                gcs_path=f"test-tenant/search-{i}.pdf",
                pipeline_status="indexed",
            )

        # Search for "searchable" with pagination
        response = client.get("/api/v1/assets/?page=1&page_size=5&search=searchable")
        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        assert data["count"] == 12  # Only 12 match "searchable"
        assert data["total_pages"] == 3  # 12 items / 5 per page = 3 pages
        assert len(data["results"]) == 5
        assert all("searchable" in r["file_name"] for r in data["results"])

    def test_sort_consistency_across_pages(self, authenticated_client_with_company):
        """Sorting is consistent across paginated results"""
        client, user, tenant, company = authenticated_client_with_company

        # Create assets with different sizes
        sizes = [100, 500, 200, 800, 300, 900, 400, 700, 600, 1000]
        for i, size in enumerate(sizes):
            BrandAsset.objects.create(
                company=company,
                tenant=tenant,
                file_name=f"sort-test-{i}.pdf",
                file_type="document",
                file_size=size,
                gcs_path=f"test-tenant/sort-{i}.pdf",
                pipeline_status="indexed",
            )

        # Get sorted by size descending
        all_sizes = []
        page = 1

        while True:
            url = f"/api/v1/assets/?page={page}&page_size=3"
            url += "&sort_by=file_size&sort_order=desc"
            response = client.get(url)
            assert response.status_code == status.HTTP_200_OK

            data = response.json()
            page_sizes = [r["file_size"] for r in data["results"]]
            all_sizes.extend(page_sizes)

            # Verify this page is sorted
            assert page_sizes == sorted(page_sizes, reverse=True)

            if not data["has_next"]:
                break
            page += 1

        # Verify overall order
        assert all_sizes == sorted(all_sizes, reverse=True)


@pytest.mark.django_db
class TestTenantIsolation:
    """Test that users can only access their own tenant's files"""

    def test_signed_url_wrong_tenant(self, db, django_user_model):
        """Verify 404 when accessing another tenant's file"""
        from tenants.models import Tenant, Domain
        from onboarding.models import Company, BrandAsset

        # Create tenant 1
        tenant1 = Tenant.objects.create(schema_name="tenant_one", name="Tenant One")
        Domain.objects.create(
            domain="tenant1.localhost", tenant=tenant1, is_primary=True
        )

        user1 = django_user_model.objects.create_user(
            username="user1", email="user1@example.com", password="pass123"
        )

        company1 = Company.objects.create(name="Company One", tenant=tenant1)

        asset1 = BrandAsset.objects.create(
            company=company1,
            tenant=tenant1,
            file_name="tenant1-file.pdf",
            file_type="document",
            file_size=1024,
            gcs_path="tenant1/file.pdf",
            pipeline_status="indexed",
        )

        # Create tenant 2
        tenant2 = Tenant.objects.create(schema_name="tenant_two", name="Tenant Two")
        Domain.objects.create(
            domain="tenant2.localhost", tenant=tenant2, is_primary=True
        )

        user2 = django_user_model.objects.create_user(
            username="user2", email="user2@example.com", password="pass123"
        )

        # User 2 tries to access User 1's asset
        client = APIClient()
        client.force_authenticate(user=user2)
        client.defaults["SERVER_NAME"] = "tenant2.localhost"
        client._force_tenant = tenant2

        response = client.get(f"/api/v1/assets/{asset1.id}/signed-url/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_list_only_own_tenant_assets(self, db, django_user_model):
        """Verify users only see their own tenant's assets"""
        from tenants.models import Tenant, Domain
        from onboarding.models import Company, BrandAsset

        # Create tenant 1 with assets
        tenant1 = Tenant.objects.create(
            schema_name="list_tenant_one", name="Tenant One"
        )
        Domain.objects.create(domain="list1.localhost", tenant=tenant1, is_primary=True)

        user1 = django_user_model.objects.create_user(
            username="listuser1", email="listuser1@example.com", password="pass123"
        )

        company1 = Company.objects.create(name="Company One", tenant=tenant1)

        for i in range(3):
            BrandAsset.objects.create(
                company=company1,
                tenant=tenant1,
                file_name=f"tenant1-file-{i}.pdf",
                file_type="document",
                file_size=1024,
                gcs_path=f"tenant1/file-{i}.pdf",
                pipeline_status="indexed",
            )

        # Create tenant 2 with assets
        tenant2 = Tenant.objects.create(
            schema_name="list_tenant_two", name="Tenant Two"
        )
        Domain.objects.create(domain="list2.localhost", tenant=tenant2, is_primary=True)

        user2 = django_user_model.objects.create_user(
            username="listuser2", email="listuser2@example.com", password="pass123"
        )

        company2 = Company.objects.create(name="Company Two", tenant=tenant2)

        for i in range(5):
            BrandAsset.objects.create(
                company=company2,
                tenant=tenant2,
                file_name=f"tenant2-file-{i}.pdf",
                file_type="document",
                file_size=1024,
                gcs_path=f"tenant2/file-{i}.pdf",
                pipeline_status="indexed",
            )

        # User 1 should only see 3 assets
        client1 = APIClient()
        client1.force_authenticate(user=user1)
        client1.defaults["SERVER_NAME"] = "list1.localhost"
        client1._force_tenant = tenant1

        response = client1.get("/api/v1/assets/")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data["count"] == 3
        assert all("tenant1" in r["file_name"] for r in data["results"])

        # User 2 should only see 5 assets
        client2 = APIClient()
        client2.force_authenticate(user=user2)
        client2.defaults["SERVER_NAME"] = "list2.localhost"
        client2._force_tenant = tenant2

        response = client2.get("/api/v1/assets/")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data["count"] == 5
        assert all("tenant2" in r["file_name"] for r in data["results"])
