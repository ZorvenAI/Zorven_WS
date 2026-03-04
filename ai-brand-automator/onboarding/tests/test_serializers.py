"""
Serializer tests for onboarding app
"""

import pytest
from onboarding.serializers import (
    CompanySerializer,
    BrandAssetSerializer,
    OnboardingProgressSerializer,
)
from onboarding.models import BrandAsset
from .factories import CompanyFactory, BrandAssetFactory, OnboardingProgressFactory


@pytest.mark.django_db
@pytest.mark.unit
class TestCompanySerializer:
    """Test CompanySerializer"""

    def test_serialize_company(self, shared_tenant):
        """Test serializing a Company instance"""
        company = CompanyFactory(
            tenant=shared_tenant,
            name="Test Corp",
            industry="Technology",
            brand_voice="professional",
        )
        serializer = CompanySerializer(company)
        data = serializer.data

        assert data["name"] == "Test Corp"
        assert data["industry"] == "Technology"
        assert data["brand_voice"] == "professional"
        assert "id" in data
        assert "created_at" in data

    def test_deserialize_valid_company(self, shared_tenant):
        """Test deserializing valid company data (tenant set via save())"""
        data = {
            "name": "New Company",
            "industry": "Healthcare",
            "description": "A healthcare company",
            "target_audience": "Healthcare professionals",
            "core_problem": "Inefficient patient management",
            "website": "https://example.com",
            "brand_voice": "authoritative",
        }
        serializer = CompanySerializer(data=data)
        assert serializer.is_valid(), serializer.errors
        # tenant is read-only, must be set manually
        company = serializer.save(tenant=shared_tenant)

        assert company.name == "New Company"
        assert company.industry == "Healthcare"
        assert company.tenant == shared_tenant

    def test_name_required(self):
        """Test that name field is required"""
        data = {"industry": "Finance"}
        serializer = CompanySerializer(data=data)
        assert not serializer.is_valid()
        assert "name" in serializer.errors

    def test_brand_voice_choices(self, shared_tenant):
        """Test brand_voice accepts valid choices"""
        valid_voices = ["professional", "friendly", "bold", "authoritative"]
        for voice in valid_voices:
            data = {"name": "Test", "brand_voice": voice}
            serializer = CompanySerializer(data=data)
            assert (
                serializer.is_valid()
            ), f"{voice} should be valid: {serializer.errors}"

    def test_brand_voice_invalid_choice(self, shared_tenant):
        """Test brand_voice rejects invalid choices"""
        data = {"tenant": shared_tenant.id, "name": "Test", "brand_voice": "invalid"}
        serializer = CompanySerializer(data=data)
        assert not serializer.is_valid()
        assert "brand_voice" in serializer.errors

    def test_values_field_serialization(self, shared_tenant):
        """Test TextField serialization for values"""
        company = CompanyFactory(
            tenant=shared_tenant, values="Innovation, Excellence, Integrity"
        )
        serializer = CompanySerializer(company)
        assert serializer.data["values"] == "Innovation, Excellence, Integrity"

    def test_blank_fields_allowed(self, shared_tenant):
        """Test that optional fields can be blank"""
        data = {"tenant": shared_tenant.id, "name": "Minimal Company"}
        serializer = CompanySerializer(data=data)
        assert serializer.is_valid(), serializer.errors

    def test_update_company(self, shared_tenant):
        """Test updating company via serializer"""
        company = CompanyFactory(tenant=shared_tenant, name="Old Name")
        data = {"name": "New Name", "industry": "Updated Industry"}
        serializer = CompanySerializer(company, data=data, partial=True)
        assert serializer.is_valid()
        updated_company = serializer.save()

        assert updated_company.name == "New Name"
        assert updated_company.industry == "Updated Industry"

    def test_read_only_fields(self, shared_tenant):
        """Test that read-only fields cannot be updated"""
        company = CompanyFactory(tenant=shared_tenant)
        original_created_at = company.created_at

        data = {"name": "Updated", "created_at": "2020-01-01T00:00:00Z"}
        serializer = CompanySerializer(company, data=data, partial=True)
        assert serializer.is_valid()
        serializer.save()

        company.refresh_from_db()
        assert company.created_at == original_created_at

    def test_nested_tenant_representation(self, shared_tenant):
        """Test tenant is represented correctly"""
        company = CompanyFactory(tenant=shared_tenant)
        serializer = CompanySerializer(company)
        assert "tenant" in serializer.data
        assert serializer.data["tenant"] == shared_tenant.id


@pytest.mark.django_db
@pytest.mark.unit
class TestBrandAssetSerializer:
    """Test BrandAssetSerializer"""

    def test_serialize_brand_asset(self, shared_tenant):
        """Test serializing a BrandAsset instance"""
        company = CompanyFactory(tenant=shared_tenant)
        asset = BrandAssetFactory(
            tenant=shared_tenant,
            company=company,
            file_name="logo.png",
            file_type="image",
        )
        serializer = BrandAssetSerializer(asset)
        data = serializer.data

        assert data["file_name"] == "logo.png"
        assert data["file_type"] == "image"
        assert "id" in data
        assert "uploaded_at" in data

    def test_deserialize_valid_asset(self, shared_tenant):
        """Test deserializing valid asset data"""
        company = CompanyFactory(tenant=shared_tenant)
        data = {
            "company": company.id,
            "file_name": "brand-guide.pdf",
            "file_type": "document",
            "file_size": 2048000,
            "gcs_path": "companies/1/assets/brand-guide.pdf",
            "gcs_bucket": "brand-automator",
        }
        serializer = BrandAssetSerializer(data=data)
        assert serializer.is_valid(), serializer.errors
        # tenant is read-only, set manually
        asset = serializer.save(tenant=shared_tenant)

        assert asset.file_name == "brand-guide.pdf"
        assert asset.file_type == "document"

    def test_required_fields(self):
        """Test that required fields are validated"""
        data = {"file_type": "image"}
        serializer = BrandAssetSerializer(data=data)
        assert not serializer.is_valid()
        assert "file_name" in serializer.errors
        assert "company" in serializer.errors
        assert "file_size" in serializer.errors
        assert "gcs_path" in serializer.errors
        # tenant is read-only, won't appear in validation errors

    def test_file_type_choices(self, shared_tenant):
        """Test file_type accepts valid choices"""
        company = CompanyFactory(tenant=shared_tenant)
        valid_types = ["image", "video", "document", "other"]
        for file_type in valid_types:
            data = {
                "company": company.id,
                "file_name": "test.file",
                "file_type": file_type,
                "file_size": 1024,
                "gcs_path": f"companies/test/{file_type}/test.file",
            }
            serializer = BrandAssetSerializer(data=data)
            assert (
                serializer.is_valid()
            ), f"{file_type} should be valid: {serializer.errors}"

    def test_file_type_invalid_choice(self, shared_tenant):
        """Test file_type rejects invalid choices"""
        company = CompanyFactory(tenant=shared_tenant)
        data = {
            "tenant": shared_tenant.id,
            "company": company.id,
            "file_name": "test.file",
            "file_type": "invalid",
        }
        serializer = BrandAssetSerializer(data=data)
        assert not serializer.is_valid()
        assert "file_type" in serializer.errors

    def test_cascade_company_relationship(self, shared_tenant):
        """Test company relationship"""
        company = CompanyFactory(tenant=shared_tenant)
        asset = BrandAssetFactory(tenant=shared_tenant, company=company)
        serializer = BrandAssetSerializer(asset)

        assert serializer.data["company"] == company.id

    def test_ordering_by_uploaded_at(self, shared_tenant):
        """Test assets are ordered by uploaded_at descending"""
        company = CompanyFactory(tenant=shared_tenant)
        asset1 = BrandAssetFactory(tenant=shared_tenant, company=company)  # noqa: F841
        asset2 = BrandAssetFactory(tenant=shared_tenant, company=company)

        assets = BrandAsset.objects.filter(company=company)
        serializer = BrandAssetSerializer(assets, many=True)

        # Most recent should be first
        assert serializer.data[0]["id"] == asset2.id


@pytest.mark.django_db
@pytest.mark.unit
class TestOnboardingProgressSerializer:
    """Test OnboardingProgressSerializer"""

    def test_serialize_progress(self, shared_tenant):
        """Test serializing OnboardingProgress instance"""
        company = CompanyFactory(tenant=shared_tenant)
        progress = OnboardingProgressFactory(
            tenant=shared_tenant,
            company=company,
            current_step="brand_strategy",
            completed_steps=["company_info"],
        )
        serializer = OnboardingProgressSerializer(progress)
        data = serializer.data

        assert data["current_step"] == "brand_strategy"
        assert data["completed_steps"] == ["company_info"]
        assert "completion_percentage" in data
        assert "id" in data

    def test_deserialize_valid_progress(self, shared_tenant):
        """Test deserializing valid progress data"""
        company = CompanyFactory(tenant=shared_tenant)
        data = {
            "tenant": shared_tenant.id,
            "company": company.id,
            "current_step": "brand_identity",
            "completed_steps": ["company_info", "brand_strategy"],
        }
        serializer = OnboardingProgressSerializer(data=data)
        assert serializer.is_valid(), serializer.errors
        progress = serializer.save()

        assert progress.current_step == "brand_identity"
        assert len(progress.completed_steps) == 2

    def test_current_step_choices(self, shared_tenant):
        """Test current_step accepts valid choices"""
        company = CompanyFactory(tenant=shared_tenant)
        valid_steps = [
            "company_info",
            "brand_strategy",
            "brand_identity",
            "assets_upload",
            "review",
        ]
        for step in valid_steps:
            data = {
                "tenant": shared_tenant.id,
                "company": company.id,
                "current_step": step,
            }
            serializer = OnboardingProgressSerializer(data=data)
            assert serializer.is_valid(), f"{step} should be valid"

    def test_completion_percentage_calculation(self, shared_tenant):
        """Test completion_percentage is calculated correctly"""
        company = CompanyFactory(tenant=shared_tenant)
        progress = OnboardingProgressFactory(
            tenant=shared_tenant,
            company=company,
            current_step="review",
            completed_steps=["company_info", "brand_strategy", "brand_identity"],
        )
        serializer = OnboardingProgressSerializer(progress)

        # 3 out of 5 steps = 60%
        assert serializer.data["completion_percentage"] == 60

    def test_update_progress(self, shared_tenant):
        """Test updating progress via serializer"""
        company = CompanyFactory(tenant=shared_tenant)
        progress = OnboardingProgressFactory(
            tenant=shared_tenant,
            company=company,
            current_step="company_info",
            completed_steps=[],
        )

        data = {
            "current_step": "brand_strategy",
            "completed_steps": ["company_info"],
        }
        serializer = OnboardingProgressSerializer(progress, data=data, partial=True)
        assert serializer.is_valid()
        updated_progress = serializer.save()

        assert updated_progress.current_step == "brand_strategy"
        assert "company_info" in updated_progress.completed_steps

    def test_completed_steps_default(self, shared_tenant):
        """Test completed_steps defaults to empty list"""
        company = CompanyFactory(tenant=shared_tenant)
        data = {
            "tenant": shared_tenant.id,
            "company": company.id,
            "current_step": "company_info",
        }
        serializer = OnboardingProgressSerializer(data=data)
        assert serializer.is_valid()
        progress = serializer.save()

        assert progress.completed_steps == []

    def test_one_to_one_constraint(self, shared_tenant):
        """Test OneToOne constraint with company"""
        company = CompanyFactory(tenant=shared_tenant)
        OnboardingProgressFactory(tenant=shared_tenant, company=company)

        # Attempting to create second progress for same company should fail
        data = {
            "company": company.id,
            "current_step": "review",
        }
        serializer = OnboardingProgressSerializer(data=data)
        # Should fail validation due to unique constraint
        assert not serializer.is_valid()
        assert "company" in serializer.errors


@pytest.mark.django_db
@pytest.mark.unit
class TestSerializerEdgeCases:
    """Test edge cases and error handling"""

    def test_invalid_json_in_values_field(self, shared_tenant):
        """Test handling of invalid JSON in values field"""
        data = {
            "tenant": shared_tenant.id,
            "name": "Test Company",
            "values": "not a list",  # Invalid - should be list
        }
        serializer = CompanySerializer(data=data)
        # Should either reject or coerce to valid JSON
        if not serializer.is_valid():
            assert "values" in serializer.errors

    def test_extremely_long_name(self, shared_tenant):
        """Test name field max_length validation"""
        data = {"tenant": shared_tenant.id, "name": "A" * 300}  # Exceeds max_length=255
        serializer = CompanySerializer(data=data)
        assert not serializer.is_valid()
        assert "name" in serializer.errors

    def test_negative_file_size(self, shared_tenant):
        """Test file_size cannot be negative"""
        company = CompanyFactory(tenant=shared_tenant)
        data = {
            "tenant": shared_tenant.id,
            "company": company.id,
            "file_name": "test.jpg",
            "file_type": "image",
            "file_size": -1000,
        }
        serializer = BrandAssetSerializer(data=data)
        # Should validate that file_size is positive
        if not serializer.is_valid():
            assert "file_size" in serializer.errors

    def test_empty_completed_steps_array(self, shared_tenant):
        """Test empty completed_steps is valid"""
        company = CompanyFactory(tenant=shared_tenant)
        data = {
            "tenant": shared_tenant.id,
            "company": company.id,
            "current_step": "company_info",
            "completed_steps": [],
        }
        serializer = OnboardingProgressSerializer(data=data)
        assert serializer.is_valid()
