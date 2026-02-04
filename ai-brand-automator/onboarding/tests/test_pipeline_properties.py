"""
Property-based tests for pipeline integration using Hypothesis.

Tests invariants and edge cases through automated random data generation
for the OnboardingPipelineService and webhook endpoints.

PERFORMANCE NOTE: Each test method creates a fresh tenant via create_test_tenant()
for EACH Hypothesis example to avoid OneToOneField violations.

These tests are marked with @pytest.mark.slow and should be run in CI only.
To run locally: pytest -m slow
To skip locally: pytest -m "not slow"
"""

import uuid

import pytest
from django.db import connection
from hypothesis import given, strategies as st, settings, HealthCheck
from rest_framework import status
from rest_framework.test import APIClient

from onboarding.models import BrandAsset, Company
from onboarding.services import OnboardingPipelineService


# Suppress health check for function-scoped fixtures
# PERFORMANCE: Using only 3 examples per test since tenant creation is slow
property_settings = settings(
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    max_examples=3,  # Minimal examples - tenant creation is slow
    deadline=None,  # Disable deadline to avoid timeouts
)


# Mark all tests in this module as slow (skip during rapid development)
pytestmark = [pytest.mark.slow, pytest.mark.property]


def create_test_tenant():
    """
    Create a unique tenant for each Hypothesis example.
    """
    from tenants.models import Tenant, Domain

    connection.set_schema_to_public()
    unique_id = uuid.uuid4().hex[:10]
    schema_name = f"test_pipeline_{unique_id}"

    tenant = Tenant.objects.create(
        name=f"Pipeline Test Tenant {unique_id}",
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


# Strategies for generating test data
pipeline_status_strategy = st.sampled_from(
    ["pending", "ingested", "curated", "indexed", "failed"]
)
file_type_strategy = st.sampled_from(["image", "video", "document", "other"])
file_name_strategy = st.text(
    min_size=1, max_size=100, alphabet="abcdefghijklmnopqrstuvwxyz0123456789_."
)
file_size_strategy = st.integers(
    min_value=1, max_value=100 * 1024 * 1024
)  # Up to 100MB
error_message_strategy = st.text(min_size=0, max_size=500)


@pytest.mark.django_db
class TestPipelineServiceProperties:
    """Property-based tests for OnboardingPipelineService."""

    @property_settings
    @given(
        file_name=file_name_strategy,
        file_type=file_type_strategy,
        file_size=file_size_strategy,
    )
    def test_build_ingestion_event_always_has_required_fields(
        self, db, file_name, file_type, file_size
    ):
        """Ingestion events should always have required fields regardless of input."""
        tenant = create_test_tenant()

        # Create company and asset
        company = Company.objects.create(
            tenant=tenant,
            name="Test Company",
        )
        asset = BrandAsset.objects.create(
            tenant=tenant,
            company=company,
            file_name=file_name if file_name else "default.txt",
            file_type=file_type,
            file_size=file_size,
            gcs_path=f"_landing/{tenant.id}/{uuid.uuid4()}_{file_name or 'file'}",
        )

        service = OnboardingPipelineService()
        trace_id = uuid.uuid4()
        event = service._build_ingestion_event(asset, trace_id)

        # Required fields invariant
        assert "event_id" in event
        assert "trace_id" in event
        assert "timestamp" in event
        assert "file_path" in event
        assert "file_type" in event
        assert "metadata" in event
        assert event["source"] == "django-backend"

    @property_settings
    @given(tenant_id=st.integers(min_value=1, max_value=10000))
    def test_tenant_config_always_returns_valid_structure(self, tenant_id):
        """Tenant config should always have expected structure."""
        service = OnboardingPipelineService()
        config = service.get_tenant_pipeline_config(tenant_id)

        # Config structure invariant
        assert isinstance(config, dict)
        assert "enabled" in config
        assert "auto_curation" in config
        assert "rag_indexing" in config
        assert "retention_days" in config
        assert isinstance(config["retention_days"], int)

    @property_settings
    @given(
        company_name=st.text(min_size=1, max_size=255),
        description=st.text(min_size=0, max_size=1000),
        industry=st.text(min_size=0, max_size=100),
    )
    def test_company_document_content_includes_name(
        self, db, company_name, description, industry
    ):
        """Company document should always include company name in content."""
        from onboarding.tasks import _build_company_document

        tenant = create_test_tenant()
        company = Company.objects.create(
            tenant=tenant,
            name=company_name if company_name.strip() else "Default",
            description=description,
            industry=industry,
        )

        doc = _build_company_document(company)

        assert doc["document_type"] == "company_profile"
        assert doc["company_id"] == company.id
        # Name should be in content
        assert company.name in doc["content"]


@pytest.mark.django_db
class TestWebhookProperties:
    """Property-based tests for pipeline webhooks."""

    @pytest.fixture(autouse=True)
    def setup_webhook_secret(self, settings):
        """Set up the webhook secret for all tests in this class."""
        settings.PIPELINE_WEBHOOK_SECRET = "test-webhook-secret"

    @property_settings
    @given(new_status=pipeline_status_strategy)
    def test_status_update_transitions_correctly(self, db, new_status):
        """Status updates should always result in the new status being set."""
        tenant = create_test_tenant()
        company = Company.objects.create(tenant=tenant, name="Webhook Test")
        asset = BrandAsset.objects.create(
            tenant=tenant,
            company=company,
            file_name="test.jpg",
            file_type="image",
            file_size=1024,
            gcs_path=f"_landing/{tenant.id}/test.jpg",
            pipeline_status="pending",
        )

        client = APIClient()
        client.defaults["SERVER_NAME"] = "localhost"

        response = client.post(
            "/api/v1/webhooks/pipeline-status/",
            {
                "asset_id": asset.id,
                "status": new_status,
                "secret": "test-webhook-secret",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        asset.refresh_from_db()
        assert asset.pipeline_status == new_status

    @property_settings
    @given(error_msg=error_message_strategy)
    def test_error_messages_stored_correctly(self, db, error_msg):
        """Error messages should be stored exactly as provided."""
        tenant = create_test_tenant()
        company = Company.objects.create(tenant=tenant, name="Error Test")
        asset = BrandAsset.objects.create(
            tenant=tenant,
            company=company,
            file_name="test.jpg",
            file_type="image",
            file_size=1024,
            gcs_path=f"_landing/{tenant.id}/test.jpg",
            pipeline_status="pending",
        )

        client = APIClient()
        client.defaults["SERVER_NAME"] = "localhost"

        response = client.post(
            "/api/v1/webhooks/pipeline-status/",
            {
                "asset_id": asset.id,
                "status": "failed",
                "error": error_msg,
                "secret": "test-webhook-secret",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        asset.refresh_from_db()
        assert asset.pipeline_error == error_msg

    @property_settings
    @given(
        invalid_status=st.text(min_size=1, max_size=50).filter(
            lambda x: x not in ["pending", "ingested", "curated", "indexed", "failed"]
        )
    )
    def test_invalid_status_rejected(self, db, invalid_status):
        """Invalid status values should always be rejected."""
        tenant = create_test_tenant()
        company = Company.objects.create(tenant=tenant, name="Invalid Test")
        asset = BrandAsset.objects.create(
            tenant=tenant,
            company=company,
            file_name="test.jpg",
            file_type="image",
            file_size=1024,
            gcs_path=f"_landing/{tenant.id}/test.jpg",
            pipeline_status="pending",
        )

        client = APIClient()
        client.defaults["SERVER_NAME"] = "localhost"

        response = client.post(
            "/api/v1/webhooks/pipeline-status/",
            {
                "asset_id": asset.id,
                "status": invalid_status,
                "secret": "test-webhook-secret",
            },
            format="json",
        )

        # Invalid status should be rejected
        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestBatchWebhookProperties:
    """Property-based tests for batch pipeline webhooks."""

    @pytest.fixture(autouse=True)
    def setup_webhook_secret(self, settings):
        """Set up the webhook secret for all tests in this class."""
        settings.PIPELINE_WEBHOOK_SECRET = "test-webhook-secret"

    @property_settings
    @given(
        num_updates=st.integers(min_value=1, max_value=3),
        statuses=st.lists(pipeline_status_strategy, min_size=1, max_size=3),
    )
    def test_batch_updates_count_correctly(
        self, db, public_tenant, num_updates, statuses
    ):
        """Batch updates should correctly count successes and failures."""
        # Use public_tenant fixture to avoid transaction isolation issues
        # Clean up any existing company for this tenant
        Company.objects.filter(tenant=public_tenant).delete()

        company = Company.objects.create(tenant=public_tenant, name="Batch Test")

        # Create assets
        assets = []
        for i in range(min(num_updates, len(statuses))):
            asset = BrandAsset.objects.create(
                tenant=public_tenant,
                company=company,
                file_name=f"batch_{i}.jpg",
                file_type="image",
                file_size=1024,
                gcs_path=f"_landing/{public_tenant.id}/batch_{i}.jpg",
                pipeline_status="pending",
            )
            assets.append(asset)

        # Build updates
        updates = [
            {"asset_id": asset.id, "status": statuses[i]}
            for i, asset in enumerate(assets)
        ]

        client = APIClient()
        client.defaults["SERVER_NAME"] = "localhost"

        response = client.post(
            "/api/v1/webhooks/pipeline-batch-status/",
            {"updates": updates, "secret": "test-webhook-secret"},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        # All updates should succeed
        assert response.data["success"] == len(updates)
        assert response.data["failed"] == 0
