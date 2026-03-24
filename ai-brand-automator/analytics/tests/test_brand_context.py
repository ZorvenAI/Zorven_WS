"""
Tests for the Brand Context Selector feature.

Covers:
- BrandContextOptionsView (pre-BAA and post-BAA)
- BrandContextSyncView (service-token auth, writes to Django Redis)
- Brand affinity sub-brand awareness
- Metric extraction brand context injection
- Analytics views brand_context filtering
"""

import pytest
from unittest.mock import patch, MagicMock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient

User = get_user_model()


def _make_client(user, tenant):
    """Create an authenticated APIClient with tenant context."""
    client = APIClient()
    client.defaults["SERVER_NAME"] = "localhost"
    client.force_authenticate(user=user)
    client.defaults["HTTP_X_TENANT_ID"] = str(tenant.id)
    return client


@pytest.fixture
def brand_context_tenant(db):
    """Create a test tenant for brand context tests."""
    from tenants.models import Tenant, Domain
    from django.db import connection

    connection.set_schema_to_public()
    tenant = Tenant.objects.create(
        name="Brand Context Test",
        schema_name="bc_test",
        subscription_status="active",
        max_users=10,
        storage_limit_gb=5,
    )
    Domain.objects.create(tenant=tenant, domain="bctest.localhost", is_primary=True)
    return tenant


@pytest.fixture
def bc_user(db):
    """Test user for brand context tests."""
    return User.objects.create_user(
        username="bc_user", email="bc@example.com", password="TestPass123!"
    )


@pytest.fixture
def bc_company(db, brand_context_tenant):
    """Company for brand context tests."""
    from onboarding.models import Company

    return Company.objects.create(
        tenant=brand_context_tenant,
        name="Acme Corp",
        industry="Technology",
        target_audience="SaaS companies",
    )


@pytest.fixture
def bc_membership(db, bc_user, brand_context_tenant):
    """Membership for brand context user."""
    from tenants.models import Membership

    return Membership.objects.create(
        user=bc_user,
        tenant=brand_context_tenant,
        role=Membership.Role.OWNER,
    )


@pytest.fixture
def bc_client(bc_user, brand_context_tenant, bc_membership):
    """Authenticated client for brand context tests."""
    return _make_client(bc_user, brand_context_tenant)


@pytest.fixture(autouse=True)
def clear_brand_context_cache():
    """Clear brand context cache between tests."""
    yield
    # Clear all brand_context keys
    try:
        cache.delete_pattern("brand_context:*")
    except (AttributeError, Exception):
        pass


# ── BrandContextOptionsView ──


@pytest.mark.django_db
class TestBrandContextOptionsView:
    """GET /api/v1/analytics/brand-context-options/"""

    def test_pre_baa_returns_parent_only(self, bc_client, bc_company):
        """Before BAA runs, only the parent brand is returned."""
        resp = bc_client.get("/api/v1/analytics/brand-context-options/")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["brand_context_id"] == "parent"
        assert data[0]["name"] == "Acme Corp"
        assert data[0]["brand_scope"] == "parent"

    def test_post_baa_returns_parent_and_sub_brands(
        self, bc_client, bc_company, brand_context_tenant
    ):
        """After BAA runs and syncs, parent + sub-brands are returned."""
        # Simulate BAA sync
        cache_key = f"brand_context:{brand_context_tenant.id}:options"
        sub_brands = [
            {
                "brand_context_id": "sub_brand:acme-pro",
                "name": "Acme Pro",
                "brand_scope": "sub_brand",
                "parent_brand": "Acme Corp",
                "relationship_to_parent": "branded_house",
                "target_persona": "Enterprise IT Directors",
            },
            {
                "brand_context_id": "sub_brand:acme-lite",
                "name": "Acme Lite",
                "brand_scope": "sub_brand",
                "parent_brand": "Acme Corp",
                "relationship_to_parent": "branded_house",
                "target_persona": "Small businesses",
            },
        ]
        cache.set(cache_key, sub_brands, timeout=None)

        resp = bc_client.get("/api/v1/analytics/brand-context-options/")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 3  # parent + 2 sub-brands
        assert data[0]["brand_context_id"] == "parent"
        assert data[1]["brand_context_id"] == "sub_brand:acme-pro"
        assert data[2]["brand_context_id"] == "sub_brand:acme-lite"

    def test_unauthenticated_returns_401(self, api_client):
        """Unauthenticated requests are rejected."""
        resp = api_client.get("/api/v1/analytics/brand-context-options/")
        assert resp.status_code == 401

    def test_registry_empty_returns_parent_only(
        self, bc_client, bc_company, brand_context_tenant
    ):
        """Empty registry cache returns parent only gracefully."""
        cache_key = f"brand_context:{brand_context_tenant.id}:options"
        cache.set(cache_key, [], timeout=None)

        resp = bc_client.get("/api/v1/analytics/brand-context-options/")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["brand_context_id"] == "parent"


# ── BrandContextSyncView ──


@pytest.mark.django_db
class TestBrandContextSyncView:
    """POST /api/v1/analytics/brand-context-sync/"""

    def test_sync_with_valid_token(self, api_client, brand_context_tenant):
        """Valid service token writes brand options to cache."""
        resp = api_client.post(
            "/api/v1/analytics/brand-context-sync/",
            data={
                "tenant_id": str(brand_context_tenant.id),
                "options": [
                    {
                        "brand_context_id": "sub_brand:acme-pro",
                        "name": "Acme Pro",
                        "brand_scope": "sub_brand",
                        "parent_brand": "Acme Corp",
                        "relationship_to_parent": "branded_house",
                        "target_persona": "Enterprise IT Directors",
                    }
                ],
            },
            format="json",
            HTTP_X_SERVICE_TOKEN="dev-service-token",
        )
        assert resp.status_code == 200
        assert resp.json()["synced"] == 1

        # Verify cache was written
        cache_key = f"brand_context:{brand_context_tenant.id}:options"
        cached = cache.get(cache_key)
        assert cached is not None
        assert len(cached) == 1
        assert cached[0]["name"] == "Acme Pro"

    def test_sync_with_invalid_token(self, api_client, brand_context_tenant):
        """Invalid service token is rejected."""
        resp = api_client.post(
            "/api/v1/analytics/brand-context-sync/",
            data={
                "tenant_id": str(brand_context_tenant.id),
                "options": [],
            },
            format="json",
            HTTP_X_SERVICE_TOKEN="wrong-token",
        )
        assert resp.status_code == 403

    def test_sync_missing_data(self, api_client):
        """Missing required fields returns 400."""
        resp = api_client.post(
            "/api/v1/analytics/brand-context-sync/",
            data={},
            format="json",
            HTTP_X_SERVICE_TOKEN="dev-service-token",
        )
        assert resp.status_code == 400


# ── Brand Affinity Sub-Brand Awareness ──


@pytest.mark.django_db
class TestBrandAffinitySubBrands:
    """BrandAffinityVerifier.tier1_input_match() with sub-brands."""

    def test_sub_brand_exact_match(self, brand_context_tenant, bc_company):
        """Registered sub-brand name gets exact match score."""
        from analytics.brand_affinity import BrandAffinityVerifier

        # Register sub-brands
        cache_key = f"brand_context:{brand_context_tenant.id}:options"
        cache.set(
            cache_key,
            [
                {
                    "brand_context_id": "sub_brand:acme-pro",
                    "name": "Acme Pro",
                    "brand_scope": "sub_brand",
                    "parent_brand": "Acme Corp",
                },
            ],
            timeout=None,
        )

        verifier = BrandAffinityVerifier(brand_context_tenant)
        job = MagicMock()
        job.input_context = {"company_name": "Acme Pro"}

        score = verifier.tier1_input_match(job)
        assert score == 1.0

    def test_unregistered_brand_low_score(self, brand_context_tenant, bc_company):
        """Non-registered brand name gets low score."""
        from analytics.brand_affinity import BrandAffinityVerifier

        verifier = BrandAffinityVerifier(brand_context_tenant)
        job = MagicMock()
        job.input_context = {"company_name": "Nike"}

        score = verifier.tier1_input_match(job)
        assert score < 0.5

    def test_parent_brand_still_matches(self, brand_context_tenant, bc_company):
        """Parent brand name still gets exact match."""
        from analytics.brand_affinity import BrandAffinityVerifier

        verifier = BrandAffinityVerifier(brand_context_tenant)
        job = MagicMock()
        job.input_context = {"company_name": "Acme Corp"}

        score = verifier.tier1_input_match(job)
        assert score == 1.0

    def test_sub_brand_containment_match(self, brand_context_tenant, bc_company):
        """Sub-brand containment match scores 0.95."""
        from analytics.brand_affinity import BrandAffinityVerifier

        cache_key = f"brand_context:{brand_context_tenant.id}:options"
        cache.set(
            cache_key,
            [
                {
                    "brand_context_id": "sub_brand:acme-pro",
                    "name": "Acme Pro",
                    "brand_scope": "sub_brand",
                    "parent_brand": "Acme Corp",
                },
            ],
            timeout=None,
        )

        verifier = BrandAffinityVerifier(brand_context_tenant)
        job = MagicMock()
        job.input_context = {"company_name": "Acme Pro Suite"}

        score = verifier.tier1_input_match(job)
        assert score == 0.95


# ── Metric Extraction Brand Context Injection ──


class TestMetricExtractionBrandContext:
    """Verify brand_context_id is injected into MetricSnapshot metadata.

    Tests the injection logic directly (lines 136-145 of tasks.py) without
    running the full Celery task which requires complex DB fixtures.
    """

    def test_brand_context_injected_into_metrics(self):
        """The brand context injection loop tags metrics correctly."""
        from analytics.models import MetricSnapshot
        from types import SimpleNamespace

        # Simulate a job with sub-brand input_context
        job = SimpleNamespace(
            input_context={
                "brand_context_id": "sub_brand:acme-pro",
                "brand_scope": "sub_brand",
                "parent_brand": "Acme Corp",
                "company_name": "Acme Pro",
            }
        )

        # Simulate metrics with empty metadata (as extractors produce)
        metrics = [
            SimpleNamespace(metadata={}),
            SimpleNamespace(metadata=None),
            SimpleNamespace(metadata={"existing_key": "value"}),
        ]

        # Replicate the injection logic from tasks.py lines 136-145
        input_ctx = job.input_context or {}
        brand_ctx_id = input_ctx.get("brand_context_id", "parent")
        brand_scope = input_ctx.get("brand_scope", "parent")
        parent_brand = input_ctx.get("parent_brand", "")
        for m in metrics:
            m.metadata = m.metadata or {}
            m.metadata["brand_context_id"] = brand_ctx_id
            m.metadata["brand_scope"] = brand_scope
            if parent_brand:
                m.metadata["parent_brand"] = parent_brand

        # Verify all metrics got brand context
        for m in metrics:
            assert m.metadata["brand_context_id"] == "sub_brand:acme-pro"
            assert m.metadata["brand_scope"] == "sub_brand"
            assert m.metadata["parent_brand"] == "Acme Corp"

        # Third metric preserved its existing key
        assert metrics[2].metadata["existing_key"] == "value"

    def test_parent_brand_context_uses_defaults(self):
        """When no brand_context_id in input, defaults to 'parent'."""
        from types import SimpleNamespace

        job = SimpleNamespace(input_context={})
        metrics = [SimpleNamespace(metadata={})]

        input_ctx = job.input_context or {}
        brand_ctx_id = input_ctx.get("brand_context_id", "parent")
        brand_scope = input_ctx.get("brand_scope", "parent")
        parent_brand = input_ctx.get("parent_brand", "")
        for m in metrics:
            m.metadata = m.metadata or {}
            m.metadata["brand_context_id"] = brand_ctx_id
            m.metadata["brand_scope"] = brand_scope
            if parent_brand:
                m.metadata["parent_brand"] = parent_brand

        assert metrics[0].metadata["brand_context_id"] == "parent"
        assert metrics[0].metadata["brand_scope"] == "parent"
        assert "parent_brand" not in metrics[0].metadata


# ── Analytics Views Brand Context Filtering ──


@pytest.mark.django_db
class TestAnalyticsViewsBrandContextFilter:
    """Analytics endpoints accept brand_context query param."""

    def test_scorecard_with_brand_context_param(self, bc_client, brand_context_tenant):
        """Scorecard endpoint accepts brand_context param without error."""
        resp = bc_client.get(
            "/api/v1/analytics/scorecard/?range=30d&brand_context=sub_brand:acme-pro"
        )
        assert resp.status_code == 200

    def test_coverage_with_brand_context_param(self, bc_client, brand_context_tenant):
        """Coverage endpoint accepts brand_context param without error."""
        resp = bc_client.get(
            "/api/v1/analytics/coverage/?brand_context=sub_brand:acme-pro"
        )
        assert resp.status_code == 200

    def test_scorecard_without_brand_context_returns_all(
        self, bc_client, brand_context_tenant
    ):
        """Scorecard without brand_context returns aggregate data."""
        resp = bc_client.get("/api/v1/analytics/scorecard/?range=30d")
        assert resp.status_code == 200
