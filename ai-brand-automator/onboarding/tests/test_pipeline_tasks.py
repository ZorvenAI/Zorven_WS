"""
Unit tests for onboarding Celery tasks.

Tests cover:
- export_company_for_rag task
- batch_export_companies_for_rag task
- Company document building
"""

import uuid
from unittest.mock import MagicMock, patch

import pytest

from onboarding.models import Company
from onboarding.tasks import (
    export_company_for_rag,
    batch_export_companies_for_rag,
    _build_company_document,
)


@pytest.fixture
def sample_company_for_task(db, public_tenant):
    """Create a sample company for testing (unique per test)."""
    # Delete any existing company for this tenant first
    Company.objects.filter(tenant=public_tenant).delete()

    return Company.objects.create(
        tenant=public_tenant,
        name="Test Export Company",
        description="A company for testing exports",
        industry="Technology",
        target_audience="Developers",
        values="Innovation, Quality",
        brand_voice="professional",
    )


class TestBuildCompanyDocument:
    """Tests for _build_company_document helper."""

    def test_builds_document_with_all_fields(self, sample_company_for_task):
        """Should build document with all company fields."""
        doc = _build_company_document(sample_company_for_task)

        assert doc["document_type"] == "company_profile"
        assert doc["company_id"] == sample_company_for_task.id
        assert doc["source"] == "onboarding_service"
        assert "Test Export Company" in doc["content"]
        assert "Technology" in doc["content"]
        assert "Developers" in doc["content"]
        assert "Innovation" in doc["content"]

    def test_builds_document_with_tenant_id(self, sample_company_for_task):
        """Should include tenant_id in document."""
        doc = _build_company_document(sample_company_for_task)

        assert doc["tenant_id"] == str(sample_company_for_task.tenant.id)

    def test_handles_empty_optional_fields(self, db, public_tenant):
        """Should handle companies with minimal data."""
        # Delete any existing company for this tenant first
        Company.objects.filter(tenant=public_tenant).delete()

        company = Company.objects.create(
            tenant=public_tenant,
            name="Minimal Company",
        )

        doc = _build_company_document(company)

        assert doc["document_type"] == "company_profile"
        assert "Minimal Company" in doc["content"]
        # Should not crash on empty fields

    def test_includes_asset_count(self, sample_company_for_task, public_tenant):
        """Should include brand asset count in content."""
        from onboarding.models import BrandAsset

        # Create some assets
        for i in range(3):
            BrandAsset.objects.create(
                tenant=public_tenant,
                company=sample_company_for_task,
                file_name=f"asset_{i}.jpg",
                file_type="image",
                file_size=1024,
                gcs_path=f"_landing/1/asset_{i}.jpg",
            )

        doc = _build_company_document(sample_company_for_task)

        assert "3 files uploaded" in doc["content"]


class TestExportCompanyForRag:
    """Tests for export_company_for_rag Celery task."""

    @pytest.mark.django_db
    def test_export_success(self, sample_company_for_task):
        """Should export company and return success."""
        with patch("onboarding.tasks.get_pipeline_service") as mock_get_service:
            mock_service = MagicMock()
            mock_service.publish_company_document.return_value = uuid.uuid4()
            mock_get_service.return_value = mock_service

            result = export_company_for_rag(sample_company_for_task.id)

            assert result["status"] == "success"
            assert result["company_id"] == sample_company_for_task.id
            assert "trace_id" in result
            mock_service.publish_company_document.assert_called_once()

    @pytest.mark.django_db
    def test_export_company_not_found(self):
        """Should return error for non-existent company."""
        result = export_company_for_rag(99999)

        assert result["status"] == "error"
        assert "not found" in result["message"]

    @pytest.mark.django_db
    def test_export_calls_pipeline_service(self, sample_company_for_task):
        """Should call pipeline service with correct document."""
        with patch("onboarding.tasks.get_pipeline_service") as mock_get_service:
            mock_service = MagicMock()
            mock_service.publish_company_document.return_value = uuid.uuid4()
            mock_get_service.return_value = mock_service

            export_company_for_rag(sample_company_for_task.id)

            call_args = mock_service.publish_company_document.call_args
            doc = call_args[0][0]

            assert doc["document_type"] == "company_profile"
            assert doc["company_id"] == sample_company_for_task.id


class TestBatchExportCompaniesForRag:
    """Tests for batch_export_companies_for_rag Celery task."""

    @pytest.mark.django_db
    def test_batch_export_all_companies(self, db, public_tenant):
        """Should queue export for all companies."""
        # Clean up first
        Company.objects.filter(tenant=public_tenant).delete()

        # Create a company (only one per tenant due to OneToOne)
        Company.objects.create(
            tenant=public_tenant,
            name="Batch Company 1",
        )

        with patch("onboarding.tasks.export_company_for_rag") as mock_export:
            mock_export.delay = MagicMock()

            result = batch_export_companies_for_rag()

            assert result["status"] == "success"
            assert result["queued_count"] >= 1
            mock_export.delay.assert_called()

    @pytest.mark.django_db
    def test_batch_export_filtered_by_tenant(self, db, public_tenant):
        """Should only queue companies for specified tenant."""
        # Clean up first
        Company.objects.filter(tenant=public_tenant).delete()

        # Create a company
        Company.objects.create(tenant=public_tenant, name="Tenant Company")

        with patch("onboarding.tasks.export_company_for_rag") as mock_export:
            mock_export.delay = MagicMock()

            result = batch_export_companies_for_rag(tenant_id=public_tenant.id)

            assert result["status"] == "success"
            assert result["tenant_id"] == public_tenant.id
