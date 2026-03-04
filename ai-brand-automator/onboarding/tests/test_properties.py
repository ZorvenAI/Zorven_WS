"""
Property-based tests using Hypothesis for onboarding app.
Tests invariants and edge cases through automated random data generation.

PERFORMANCE NOTE: Each test method creates a fresh tenant via create_test_tenant()
for EACH Hypothesis example (50 by default). This avoids OneToOneField violations
since Company has OneToOneField(Tenant).
"""

import pytest
import uuid
from hypothesis import given, assume, strategies as st, settings, HealthCheck
from django.db import connection

from onboarding.models import Company, BrandAsset, OnboardingProgress
from onboarding.serializers import CompanySerializer
from onboarding.tests.factories import CompanyFactory, BrandAssetFactory

# Suppress health check for function-scoped fixtures
# Use fewer examples (10 instead of default 50) for faster execution
property_settings = settings(
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    max_examples=10,  # Reduced from 50 for performance
    deadline=None,  # Disable deadline to avoid timeouts during tenant creation
)


def create_test_tenant():
    """
    Create a unique tenant for each Hypothesis example.

    This is critical for property tests because:
    - Company has OneToOneField(Tenant) - only ONE company per tenant
    - Hypothesis runs 50 examples per test (50 function calls)
    - Using a fixture would give all 50 examples the SAME tenant
    - Fresh tenant per example avoids constraint violations
    """
    from tenants.models import Tenant, Domain

    # Ensure we're in public schema
    connection.set_schema_to_public()

    # Generate unique identifier
    unique_id = uuid.uuid4().hex[:10]
    schema_name = f"test_{unique_id}"

    tenant = Tenant.objects.create(
        name=f"Test Tenant {unique_id}",
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
@pytest.mark.property
class TestCompanyProperties:
    """Property-based tests for Company model"""

    @property_settings
    @given(
        name=st.text(min_size=1, max_size=255),
        industry=st.sampled_from(
            [
                "Technology",
                "Healthcare",
                "Finance",
                "E-commerce",
                "Manufacturing",
            ]
        ),
        brand_voice=st.sampled_from(
            ["professional", "friendly", "bold", "authoritative", "playful"]
        ),
    )
    def test_company_name_always_valid_length(self, name, industry, brand_voice):
        """Property: Company names within max_length are always accepted"""
        tenant = create_test_tenant()
        assume(len(name.strip()) > 0)  # Non-empty after stripping

        company = Company(
            tenant=tenant,
            name=name[:255],  # Truncate to max_length
            industry=industry,
            brand_voice=brand_voice,
            values="integrity, innovation",  # Required field
        )

        # Should not raise validation error for length
        company.full_clean()
        company.save()

        assert Company.objects.filter(name=company.name).exists()

    @property_settings
    @given(
        description=st.text(min_size=0, max_size=1000),
        target_audience=st.text(min_size=0, max_size=500),
    )
    def test_company_text_fields_handle_all_unicode(self, description, target_audience):
        """Property: Text fields accept any unicode content"""
        tenant = create_test_tenant()
        company = CompanyFactory(
            tenant=tenant,
            description=description,
            target_audience=target_audience,
        )

        company.full_clean()
        company.save()

        # Verify data persisted correctly
        company.refresh_from_db()
        assert company.description == description
        assert company.target_audience == target_audience

    @property_settings
    @given(values_list=st.lists(st.text(min_size=1, max_size=50), min_size=1))
    def test_company_values_array_always_serializable(self, values_list):
        """Property: Any list of strings can be converted to comma-separated values"""
        tenant = create_test_tenant()
        # Convert list to comma-separated string (new values format)
        values_string = ", ".join(values_list)
        company = CompanyFactory(tenant=tenant, values=values_string)

        company.full_clean()
        company.save()

        company.refresh_from_db()
        assert company.values == values_string
        assert isinstance(company.values, str)


@pytest.mark.django_db
@pytest.mark.property
class TestBrandAssetProperties:
    """Property-based tests for BrandAsset model"""

    @property_settings
    @given(
        file_size=st.integers(min_value=1, max_value=100000000),
        file_type=st.sampled_from(["image", "video", "document", "other"]),
    )
    def test_asset_file_size_always_valid(self, file_size, file_type):
        """Property: Positive file sizes are always accepted"""
        tenant = create_test_tenant()
        company = CompanyFactory(tenant=tenant)

        asset = BrandAssetFactory(
            tenant=tenant,
            company=company,
            file_size=file_size,
            file_type=file_type,
        )

        asset.full_clean()
        asset.save()

        assert asset.file_size == file_size
        assert BrandAsset.objects.filter(pk=asset.pk).exists()


@pytest.mark.django_db
@pytest.mark.property
class TestOnboardingProgressProperties:
    """Property-based tests for OnboardingProgress model"""

    @property_settings
    @given(
        completed_steps=st.lists(
            st.sampled_from(
                [
                    "company_info",
                    "brand_strategy",
                    "brand_identity",
                    "assets_upload",
                    "review",
                ]
            ),
            min_size=0,
            max_size=5,
            unique=True,
        )
    )
    def test_progress_completed_steps_is_unique_list(self, completed_steps):
        """Property: Completed steps list contains unique values"""
        tenant = create_test_tenant()
        company = CompanyFactory(tenant=tenant)

        progress = OnboardingProgress.objects.create(
            tenant=tenant,
            company=company,
            completed_steps=completed_steps,
        )

        progress.refresh_from_db()
        assert len(progress.completed_steps) == len(set(progress.completed_steps))


@pytest.mark.django_db
@pytest.mark.property
class TestSerializerRoundtripProperties:
    """Property-based tests for serializer round-trips"""

    @property_settings
    @given(
        name=st.text(min_size=1, max_size=255),
        industry=st.text(min_size=0, max_size=100),
    )
    def test_company_serializer_roundtrip(self, name, industry):
        """Property: Serializer round-trip preserves data"""
        assume(len(name.strip()) > 0)
        tenant = create_test_tenant()

        company = CompanyFactory(
            tenant=tenant,
            name=name[:255],
            industry=industry[:100],
        )

        # Serialize
        serializer = CompanySerializer(company)
        data = serializer.data

        # Verify key fields preserved
        assert data["name"] == company.name
        assert data["industry"] == company.industry


@pytest.mark.django_db
@pytest.mark.property
class TestModelInvariants:
    """Property-based tests for model invariants"""

    @property_settings
    @given(
        vision=st.text(max_size=5000),
        mission=st.text(max_size=5000),
    )
    def test_company_strategy_fields_accept_long_text(self, vision, mission):
        """Property: Vision and mission statements accept long text"""
        tenant = create_test_tenant()

        company = CompanyFactory(
            tenant=tenant,
            vision_statement=vision,
            mission_statement=mission,
        )

        company.full_clean()
        company.save()

        company.refresh_from_db()
        assert company.vision_statement == vision
        assert company.mission_statement == mission

    @property_settings
    @given(data=st.data())
    def test_company_tenant_relationship_always_valid(self, data):
        """Property: Company-Tenant relationship is always consistent"""
        tenant = create_test_tenant()
        company = CompanyFactory(tenant=tenant)

        assert company.tenant == tenant
        assert company.tenant_id == tenant.id
        assert Company.objects.filter(tenant=tenant).count() == 1


@pytest.mark.django_db
@pytest.mark.property
class TestBusinessLogicInvariants:
    """Property-based tests for business logic invariants"""

    @property_settings
    @given(
        name=st.text(min_size=1, max_size=255),
        industry=st.text(min_size=0, max_size=100),
    )
    def test_company_can_be_created_with_minimal_fields(self, name, industry):
        """Property: Company can be created with just name and tenant"""
        assume(len(name.strip()) > 0)
        tenant = create_test_tenant()

        company = CompanyFactory(
            tenant=tenant,
            name=name[:255],
            industry=industry[:100] if industry else "",
        )

        company.full_clean()
        company.save()

        assert Company.objects.filter(pk=company.pk).exists()
        assert company.tenant == tenant


@pytest.mark.django_db
@pytest.mark.property
class TestDataIntegrityProperties:
    """Property-based tests for data integrity constraints"""

    @property_settings
    @given(asset_count=st.integers(min_value=0, max_value=10))
    def test_company_cascade_deletes_assets(self, asset_count):
        """Property: Deleting company cascades to all assets"""
        tenant = create_test_tenant()
        company = CompanyFactory(tenant=tenant)

        # Create multiple assets
        assets = [
            BrandAssetFactory(tenant=tenant, company=company)
            for _ in range(asset_count)
        ]

        asset_ids = [asset.id for asset in assets]

        # Delete company
        company.delete()

        # All assets should be deleted
        assert BrandAsset.objects.filter(id__in=asset_ids).count() == 0


# Add a simple non-property test to verify the fix works
@pytest.mark.django_db
class TestTenantCreationPerformance:
    """Verify tenant creation works efficiently"""

    def test_multiple_tenants_can_be_created(self):
        """Verify we can create multiple tenants without conflicts"""
        tenants = []
        for i in range(3):  # Reduced from 5 for performance
            tenant = create_test_tenant()
            tenants.append(tenant)
            # Create a company for each tenant
            company = CompanyFactory(tenant=tenant, name=f"Company {i}")
            assert company.pk is not None

        # Verify all tenants are unique
        tenant_ids = [t.id for t in tenants]
        assert len(tenant_ids) == len(set(tenant_ids))

    def test_create_test_tenant_function_works(self):
        """Verify the helper function creates valid tenants"""
        tenant = create_test_tenant()
        assert tenant.pk is not None
        assert tenant.schema_name.startswith("test_")

        # Verify we can create a company with this tenant
        company = CompanyFactory(tenant=tenant, name="Test Company")
        assert company.pk is not None
        assert company.tenant == tenant
