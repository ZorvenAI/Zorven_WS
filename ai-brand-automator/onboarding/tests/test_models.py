"""
Unit tests for onboarding models
"""

import pytest
from django.db import IntegrityError
from django.core.exceptions import ValidationError
from freezegun import freeze_time

from onboarding.models import Company, BrandAsset, OnboardingProgress
from onboarding.tests.factories import (
    CompanyFactory,
    BrandAssetFactory,
    ImageAssetFactory,
    DocumentAssetFactory,
    OnboardingProgressFactory,
    CompletedOnboardingProgressFactory,
)


@pytest.mark.django_db
@pytest.mark.unit
class TestCompanyModel:
    """Test Company model"""

    def test_create_company_with_valid_data(self, tenant):
        """Test creating company with all required fields"""
        company = CompanyFactory(tenant=tenant, name="Acme Corporation")
        assert company.pk is not None
        assert company.name == "Acme Corporation"
        assert company.tenant == tenant

    @pytest.mark.skip(
        reason="Tenant field is nullable after migration 0003 for MVP mode"
    )
    def test_company_requires_tenant(self):
        """Test company creation fails without tenant"""
        with pytest.raises(IntegrityError):
            Company.objects.create(name="Test Company")

    def test_company_tenant_is_one_to_one(self, tenant):
        """Test OneToOne relationship - can't create two companies for same tenant"""
        CompanyFactory(tenant=tenant, name="First Company")

        with pytest.raises(IntegrityError):
            CompanyFactory(tenant=tenant, name="Second Company")

    def test_company_str_representation(self, tenant):
        """Test __str__ method returns expected format"""
        company = CompanyFactory(tenant=tenant, name="Test Co")
        expected = f"Test Co ({tenant.name})"
        assert str(company) == expected

    def test_company_name_max_length(self, tenant):
        """Test company name respects max_length=255"""
        long_name = "A" * 255
        company = CompanyFactory(tenant=tenant, name=long_name)
        assert len(company.name) == 255

        # Name longer than 255 should be truncated by database
        too_long_name = "A" * 256
        company = Company(tenant=tenant, name=too_long_name)
        # This will fail validation
        with pytest.raises(ValidationError):
            company.full_clean()

    def test_values_field_defaults_to_empty_string(self, tenant):
        """Test TextField default value is empty string"""
        company = Company.objects.create(tenant=tenant, name="Test")
        assert isinstance(company.values, str)
        assert len(company.values) == 0

    def test_values_field_accepts_comma_separated_string(self, tenant):
        """Test values field can store comma-separated strings"""
        values_str = "Innovation, Excellence, Integrity"
        company = CompanyFactory(tenant=tenant, values=values_str)
        assert company.values == values_str

    def test_brand_voice_valid_choices(self, tenant):
        """Test brand_voice field accepts valid choices"""
        valid_choices = [
            "professional",
            "friendly",
            "bold",
            "authoritative",
            "playful",
            "innovative",
            "warm",
            "technical",
        ]

        # Test each choice by creating and saving company
        for choice in valid_choices:
            company = CompanyFactory(
                tenant=tenant, name=f"Test {choice}", brand_voice=choice
            )
            assert company.brand_voice == choice
            company.delete()  # Clean up for next iteration

    def test_brand_voice_invalid_choice_rejected(self, tenant):
        """Test brand_voice rejects invalid choices"""
        company = Company(tenant=tenant, name="Test", brand_voice="invalid_choice")

        with pytest.raises(ValidationError) as exc_info:
            company.full_clean()

        assert "brand_voice" in str(exc_info.value)

    def test_blank_fields_allowed(self, tenant):
        """Test that optional fields can be blank"""
        company = Company.objects.create(
            tenant=tenant,
            name="Minimal Company",
            # All other fields left blank
        )
        assert company.description == ""
        assert company.industry == ""
        assert company.target_audience == ""
        assert company.core_problem == ""
        assert company.website == ""

    @freeze_time("2026-01-11 12:00:00")
    def test_created_at_timestamp(self, tenant):
        """Test created_at is set automatically"""
        company = CompanyFactory(tenant=tenant)
        assert company.created_at.year == 2026
        assert company.created_at.month == 1
        assert company.created_at.day == 11

    def test_updated_at_auto_updates(self, tenant):
        """Test updated_at changes on save"""
        company = CompanyFactory(tenant=tenant, name="Original Name")
        original_updated = company.updated_at

        # Wait a moment and update
        import time

        time.sleep(0.1)
        company.name = "New Name"
        company.save()

        assert company.updated_at > original_updated

    def test_related_name_company(self, tenant):
        """Test reverse relation from tenant to company"""
        company = CompanyFactory(tenant=tenant)
        assert tenant.company == company

    def test_cascade_delete_from_tenant(self, tenant):
        """Test company is deleted when tenant is deleted"""
        company = CompanyFactory(tenant=tenant)
        company_id = company.id

        tenant.delete()

        assert not Company.objects.filter(id=company_id).exists()


@pytest.mark.django_db
@pytest.mark.unit
class TestBrandAssetModel:
    """Test BrandAsset model"""

    def test_create_brand_asset_with_required_fields(self, tenant):
        """Test creating brand asset with all required fields"""
        company = CompanyFactory(tenant=tenant)
        asset = BrandAssetFactory(tenant=tenant, company=company, file_name="logo.jpg")

        assert asset.pk is not None
        assert asset.file_name == "logo.jpg"
        assert asset.tenant == tenant
        assert asset.company == company

    def test_brand_asset_requires_tenant_and_company(self):
        """Test brand asset creation fails without tenant or company"""
        with pytest.raises(IntegrityError):
            BrandAsset.objects.create(file_name="test.jpg", file_size=1024)

    def test_brand_asset_str_representation(self, tenant):
        """Test __str__ method"""
        company = CompanyFactory(tenant=tenant, name="Test Co")
        asset = BrandAssetFactory(tenant=tenant, company=company, file_name="logo.png")

        expected = "logo.png (Test Co)"
        assert str(asset) == expected

    def test_file_type_valid_choices(self, tenant):
        """Test file_type accepts valid choices"""
        company = CompanyFactory(tenant=tenant)
        valid_types = ["image", "video", "document", "other"]

        for file_type in valid_types:
            asset = BrandAssetFactory(
                tenant=tenant, company=company, file_type=file_type
            )
            asset.full_clean()
            assert asset.file_type == file_type

    def test_image_asset_factory(self, tenant):
        """Test ImageAssetFactory creates image type asset"""
        company = CompanyFactory(tenant=tenant)
        asset = ImageAssetFactory(tenant=tenant, company=company)

        assert asset.file_type == "image"
        assert asset.file_name.endswith(".jpg")

    def test_document_asset_factory(self, tenant):
        """Test DocumentAssetFactory creates document type asset"""
        company = CompanyFactory(tenant=tenant)
        asset = DocumentAssetFactory(tenant=tenant, company=company)

        assert asset.file_type == "document"
        assert asset.file_name.endswith(".pdf")

    def test_gcs_path_format(self, tenant):
        """Test GCS path follows expected format"""
        company = CompanyFactory(tenant=tenant)
        asset = BrandAssetFactory(
            tenant=tenant, company=company, file_name="test_logo.jpg"
        )

        assert tenant.schema_name in asset.gcs_path
        assert "test_logo.jpg" in asset.gcs_path
        assert asset.gcs_path.startswith("assets/")

    def test_default_gcs_bucket(self, tenant):
        """Test default GCS bucket name"""
        company = CompanyFactory(tenant=tenant)
        asset = BrandAssetFactory(tenant=tenant, company=company)

        assert asset.gcs_bucket == "zorven-raw-assets"

    def test_processed_defaults_to_false(self, tenant):
        """Test processed flag defaults to False"""
        company = CompanyFactory(tenant=tenant)
        asset = BrandAssetFactory(tenant=tenant, company=company)

        assert asset.processed is False

    def test_ordering_by_uploaded_at_descending(self, tenant):
        """Test assets are ordered by upload time (newest first)"""
        company = CompanyFactory(tenant=tenant)

        with freeze_time("2026-01-01"):
            asset1 = BrandAssetFactory(tenant=tenant, company=company)

        with freeze_time("2026-01-02"):
            asset2 = BrandAssetFactory(tenant=tenant, company=company)

        with freeze_time("2026-01-03"):
            asset3 = BrandAssetFactory(tenant=tenant, company=company)

        assets = BrandAsset.objects.filter(company=company)
        assert list(assets) == [asset3, asset2, asset1]

    def test_cascade_delete_from_company(self, tenant):
        """Test assets deleted when company is deleted"""
        company = CompanyFactory(tenant=tenant)
        asset = BrandAssetFactory(tenant=tenant, company=company)
        asset_id = asset.id

        company.delete()

        assert not BrandAsset.objects.filter(id=asset_id).exists()

    def test_related_name_assets(self, tenant):
        """Test reverse relation from company to assets"""
        company = CompanyFactory(tenant=tenant)
        asset1 = BrandAssetFactory(tenant=tenant, company=company)
        asset2 = BrandAssetFactory(tenant=tenant, company=company)

        assert asset1 in company.assets.all()
        assert asset2 in company.assets.all()
        assert company.assets.count() == 2


@pytest.mark.django_db
@pytest.mark.unit
class TestOnboardingProgressModel:
    """Test OnboardingProgress model"""

    def test_create_onboarding_progress(self, tenant):
        """Test creating onboarding progress"""
        company = CompanyFactory(tenant=tenant)
        progress = OnboardingProgressFactory(tenant=tenant, company=company)

        assert progress.pk is not None
        assert progress.tenant == tenant
        assert progress.company == company

    def test_onboarding_progress_requires_tenant_and_company(self):
        """Test creation fails without tenant or company"""
        with pytest.raises(IntegrityError):
            OnboardingProgress.objects.create(current_step="company_info")

    def test_onboarding_progress_str_representation(self, tenant):
        """Test __str__ method"""
        company = CompanyFactory(tenant=tenant)
        progress = OnboardingProgressFactory(
            tenant=tenant, company=company, current_step="brand_strategy"
        )

        expected = f"{tenant.name} - brand_strategy"
        assert str(progress) == expected

    def test_current_step_valid_choices(self, tenant):
        """Test current_step accepts valid choices"""
        company = CompanyFactory(tenant=tenant)
        valid_steps = [
            "company_info",
            "brand_strategy",
            "brand_identity",
            "assets_upload",
            "review",
        ]

        for step in valid_steps:
            progress = OnboardingProgress(
                tenant=tenant, company=company, current_step=step
            )
            progress.save()  # Save instead of full_clean to test model works
            assert progress.current_step == step
            progress.delete()  # Clean up for next iteration

    def test_default_current_step(self, tenant):
        """Test current_step defaults to company_info"""
        company = CompanyFactory(tenant=tenant)
        progress = OnboardingProgress.objects.create(tenant=tenant, company=company)

        assert progress.current_step == "company_info"

    def test_completed_steps_defaults_to_empty_list(self, tenant):
        """Test completed_steps defaults to empty list"""
        company = CompanyFactory(tenant=tenant)
        progress = OnboardingProgress.objects.create(tenant=tenant, company=company)

        assert isinstance(progress.completed_steps, list)
        assert len(progress.completed_steps) == 0

    def test_is_completed_defaults_to_false(self, tenant):
        """Test is_completed defaults to False"""
        company = CompanyFactory(tenant=tenant)
        progress = OnboardingProgressFactory(tenant=tenant, company=company)

        assert progress.is_completed is False

    def test_completed_onboarding_factory(self, tenant):
        """Test CompletedOnboardingProgressFactory creates completed progress"""
        company = CompanyFactory(tenant=tenant)
        progress = CompletedOnboardingProgressFactory(tenant=tenant, company=company)

        assert progress.is_completed is True
        assert progress.current_step == "review"
        assert len(progress.completed_steps) == 5

    def test_completion_percentage_empty(self, tenant):
        """Test completion_percentage with no completed steps"""
        company = CompanyFactory(tenant=tenant)
        progress = OnboardingProgressFactory(
            tenant=tenant, company=company, completed_steps=[]
        )

        assert progress.completion_percentage == 0

    def test_completion_percentage_partial(self, tenant):
        """Test completion_percentage with some steps completed"""
        company = CompanyFactory(tenant=tenant)
        progress = OnboardingProgressFactory(
            tenant=tenant,
            company=company,
            completed_steps=["company_info", "brand_strategy"],
        )

        # 2 out of 5 steps = 40%
        assert progress.completion_percentage == 40

    def test_completion_percentage_full(self, tenant):
        """Test completion_percentage when all steps completed"""
        company = CompanyFactory(tenant=tenant)
        progress = CompletedOnboardingProgressFactory(tenant=tenant, company=company)

        assert progress.completion_percentage == 100

    def test_one_to_one_with_tenant(self, tenant):
        """Test OneToOne relationship with tenant"""
        company = CompanyFactory(tenant=tenant)
        progress = OnboardingProgressFactory(tenant=tenant, company=company)

        assert tenant.onboarding_progress == progress

    def test_one_to_one_with_company(self, tenant):
        """Test OneToOne relationship with company"""
        company = CompanyFactory(tenant=tenant)
        progress = OnboardingProgressFactory(tenant=tenant, company=company)

        assert company.onboarding_progress == progress

    @freeze_time("2026-01-11 12:00:00")
    def test_started_at_timestamp(self, tenant):
        """Test started_at is set automatically"""
        company = CompanyFactory(tenant=tenant)
        progress = OnboardingProgressFactory(tenant=tenant, company=company)

        assert progress.started_at.year == 2026
        assert progress.started_at.month == 1

    def test_completed_at_initially_null(self, tenant):
        """Test completed_at is null for incomplete onboarding"""
        company = CompanyFactory(tenant=tenant)
        progress = OnboardingProgressFactory(tenant=tenant, company=company)

        assert progress.completed_at is None

    def test_last_updated_auto_updates(self, tenant):
        """Test last_updated changes on save"""
        company = CompanyFactory(tenant=tenant)
        progress = OnboardingProgressFactory(tenant=tenant, company=company)
        original_updated = progress.last_updated

        import time

        time.sleep(0.1)
        progress.current_step = "brand_strategy"
        progress.save()

        assert progress.last_updated > original_updated

    def test_cascade_delete_from_tenant(self, tenant):
        """Test progress deleted when tenant is deleted"""
        company = CompanyFactory(tenant=tenant)
        progress = OnboardingProgressFactory(tenant=tenant, company=company)
        progress_id = progress.id

        tenant.delete()

        assert not OnboardingProgress.objects.filter(id=progress_id).exists()
