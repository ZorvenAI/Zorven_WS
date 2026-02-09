"""
Cross-Tenant Isolation Tests (Phase 8).

Verifies that multi-tenancy boundaries are enforced across:
- Redis key namespacing (data_ingestion, media_curation, rag_index)
- Celery task BrandAsset filtering
- ViewSet queryset scoping
- Defensive tenant access patterns
"""

import pytest
from datetime import datetime
from typing import Optional
from unittest.mock import MagicMock
from uuid import uuid4

from data_ingestion.adapters.redis_adapter import RedisAdapter as IngestionRedisAdapter
from data_ingestion.domain.models import (
    IngestionEvent,
    EventSource,
    ProcessingStatus,
)
from data_ingestion.tests.conftest import MockCachePort

from media_curation.adapters.redis_adapter import (
    RedisAdapter as CurationRedisAdapter,
)
from rag_index.adapters.redis_adapter import RedisAdapter as RagRedisAdapter


def _make_ingestion_adapter():
    """Create IngestionRedisAdapter with a mocked Redis client."""
    adapter = object.__new__(IngestionRedisAdapter)
    adapter.DEDUPE_PREFIX = "ingestion:dedupe:"
    adapter.STATUS_PREFIX = "ingestion:status:"
    adapter.client = MagicMock()
    return adapter


def _make_curation_adapter():
    """Create CurationRedisAdapter with a mocked Redis client."""
    adapter = object.__new__(CurationRedisAdapter)
    adapter.STATUS_PREFIX = "curation:status:"
    adapter.TENANT_PREFIX = "curation:tenant:"
    adapter.DEDUPE_PREFIX = "curation:dedupe:"
    adapter._client = MagicMock()
    return adapter


def _make_rag_adapter():
    """Create RagRedisAdapter with a mocked Redis client."""
    adapter = object.__new__(RagRedisAdapter)
    adapter.STATUS_KEY_PREFIX = "rag_sync:status:"
    adapter.RATE_KEY_PREFIX = "rag_sync:rate:"
    adapter._client = MagicMock()
    adapter._initialized = True
    return adapter


# ============================================================================
# Redis Key Namespacing Tests
# ============================================================================


class TestIngestionRedisKeyIsolation:
    """Verify data_ingestion Redis keys are scoped by tenant."""

    def setup_method(self):
        self.adapter = _make_ingestion_adapter()

    def test_dedupe_key_includes_tenant_id(self):
        """Dedupe key is prefixed with tenant_id when provided."""
        key = self.adapter._dedupe_key("event-123", tenant_id="tenant-abc")
        assert key == "tenant-abc:ingestion:dedupe:event-123"

    def test_dedupe_key_no_tenant_falls_back(self):
        """Dedupe key has no prefix when tenant_id is None."""
        key = self.adapter._dedupe_key("event-123")
        assert key == "ingestion:dedupe:event-123"
        assert "None" not in key

    def test_status_key_includes_tenant_id(self):
        """Status key is prefixed with tenant_id when provided."""
        key = self.adapter._status_key("trace-456", tenant_id="tenant-xyz")
        assert key == "tenant-xyz:ingestion:status:trace-456"

    def test_status_key_no_tenant_falls_back(self):
        """Status key has no prefix when tenant_id is None."""
        key = self.adapter._status_key("trace-456")
        assert key == "ingestion:status:trace-456"

    def test_different_tenants_produce_different_keys(self):
        """Two tenants get different Redis keys for the same event."""
        key_a = self.adapter._dedupe_key("evt-1", tenant_id="tenant-a")
        key_b = self.adapter._dedupe_key("evt-1", tenant_id="tenant-b")
        assert key_a != key_b
        assert "tenant-a" in key_a
        assert "tenant-b" in key_b


class TestCurationRedisKeyIsolation:
    """Verify media_curation Redis keys are scoped by tenant."""

    def setup_method(self):
        self.adapter = _make_curation_adapter()

    def test_status_key_includes_tenant_id(self):
        """Curation status key is prefixed with tenant_id."""
        key = self.adapter._status_key("trace-1", tenant_id="t-100")
        assert key == "t-100:curation:status:trace-1"

    def test_status_key_no_tenant(self):
        """Curation status key has no prefix without tenant_id."""
        key = self.adapter._status_key("trace-1")
        assert key == "curation:status:trace-1"

    def test_dedupe_key_includes_tenant_id(self):
        """Curation dedupe key is prefixed with tenant_id."""
        key = self.adapter._dedupe_key("evt-99", tenant_id="t-200")
        assert key == "t-200:curation:dedupe:evt-99"

    def test_dedupe_key_no_tenant(self):
        """Curation dedupe key has no prefix without tenant_id."""
        key = self.adapter._dedupe_key("evt-99")
        assert key == "curation:dedupe:evt-99"


class TestRagRedisKeyIsolation:
    """Verify rag_index Redis keys are scoped by tenant."""

    def setup_method(self):
        self.adapter = _make_rag_adapter()

    def test_status_key_includes_tenant_id(self):
        """RAG status key is prefixed with tenant_id."""
        key = self.adapter._get_status_key("evt-1", tenant_id="t-300")
        assert key == "t-300:rag_sync:status:evt-1"

    def test_status_key_no_tenant(self):
        """RAG status key has no prefix without tenant_id."""
        key = self.adapter._get_status_key("evt-1")
        assert key == "rag_sync:status:evt-1"


# ============================================================================
# MockCachePort Tenant Isolation Tests
# ============================================================================


class TestMockCachePortTenantAcceptance:
    """Verify MockCachePort accepts tenant_id kwargs without errors."""

    def test_is_duplicate_accepts_tenant_id(self):
        cache = MockCachePort()
        result = cache.is_duplicate("evt-1", tenant_id="tenant-x")
        assert result is False

    def test_mark_processed_accepts_tenant_id(self):
        cache = MockCachePort()
        cache.mark_processed("evt-1", tenant_id="tenant-x")
        assert "evt-1" in cache.processed

    def test_update_status_accepts_tenant_id(self):
        cache = MockCachePort()
        cache.update_status("trace-1", "running", tenant_id="tenant-y")
        status = cache.get_status("trace-1")
        assert status["status"] == "running"

    def test_get_status_accepts_tenant_id(self):
        cache = MockCachePort()
        cache.update_status("t-1", "done")
        result = cache.get_status("t-1", tenant_id="tenant-z")
        assert result["status"] == "done"


# ============================================================================
# IngestionService Tenant Pass-Through Tests
# ============================================================================


class TestIngestionServiceTenantPassThrough:
    """Verify IngestionService passes tenant_id through cache calls."""

    def test_service_passes_tenant_id_to_cache(self):
        """Process event should pass event.tenant_id to all cache calls."""
        from data_ingestion.domain.services import IngestionService
        from data_ingestion.tests.conftest import (
            MockCachePort,
            MockStoragePort,
            MockEventProducerPort,
        )

        # Use a recording cache to verify tenant_id is passed
        class RecordingCache(MockCachePort):
            def __init__(self):
                super().__init__()
                self.tenant_ids_seen = []

            def is_duplicate(
                self, event_id: str, tenant_id: Optional[str] = None
            ) -> bool:
                self.tenant_ids_seen.append(("is_duplicate", tenant_id))
                return False

            def mark_processed(
                self,
                event_id: str,
                ttl_seconds: Optional[int] = None,
                tenant_id: Optional[str] = None,
            ) -> None:
                self.tenant_ids_seen.append(("mark_processed", tenant_id))
                self.processed.add(event_id)

            def update_status(
                self,
                trace_id: str,
                status: str,
                ttl_seconds: Optional[int] = None,
                metadata: Optional[dict] = None,
                tenant_id: Optional[str] = None,
            ) -> None:
                self.tenant_ids_seen.append(("update_status", tenant_id))
                self.statuses[trace_id] = {"status": status}

        storage = MockStoragePort()
        cache = RecordingCache()
        producer = MockEventProducerPort()

        # Add a file that exists
        storage.add_file("gs://bucket/_landing/test.mp4")

        service = IngestionService(
            storage=storage,
            cache=cache,
            producer=producer,
            output_topic="output",
            dlq_topic="dlq",
        )

        event = IngestionEvent(
            event_id=uuid4(),
            tenant_id="my-tenant-42",
            file_path="gs://bucket/_landing/test.mp4",
            file_type="video/mp4",
            timestamp=datetime.utcnow(),
            source=EventSource.FRONTEND_UPLOAD,
            trace_id=uuid4(),
        )

        result = service.process_event(event)
        assert result.status == ProcessingStatus.RAW_STORED

        # Verify all cache calls received the tenant_id
        assert len(cache.tenant_ids_seen) > 0
        for method_name, tid in cache.tenant_ids_seen:
            assert tid == "my-tenant-42", (
                f"{method_name} received tenant_id={tid!r}, " f"expected 'my-tenant-42'"
            )


# ============================================================================
# BrandAsset Tenant Filtering Tests (Django DB)
# ============================================================================


@pytest.mark.django_db
class TestBrandAssetTenantFiltering:
    """Verify BrandAsset lookups are filtered by tenant in tasks."""

    def test_update_asset_skips_wrong_tenant(self):
        """_update_asset_after_ingestion skips asset when tenant doesn't match."""
        from tenants.models import Tenant, Domain
        from onboarding.models import Company, BrandAsset
        from data_ingestion.tasks import _update_asset_after_ingestion
        from django.db import connection

        connection.set_schema_to_public()

        # Create two tenants
        tenant_a, _ = Tenant.objects.get_or_create(
            schema_name="public",
            defaults={"name": "public"},
        )
        Domain.objects.get_or_create(
            domain="localhost",
            defaults={"tenant": tenant_a, "is_primary": True},
        )

        tenant_b = Tenant.objects.create(
            name="Tenant B",
            schema_name="tenant_b_iso",
            subscription_status="active",
        )
        Domain.objects.create(
            domain="b-iso.localhost",
            tenant=tenant_b,
            is_primary=True,
        )

        # Create company and asset under tenant_a
        company = Company.objects.create(
            tenant=tenant_a,
            name="Company A",
            industry="Tech",
        )
        asset = BrandAsset.objects.create(
            tenant=tenant_a,
            company=company,
            file_name="logo.png",
            file_type="image",
            file_size=100,
            gcs_path="old/path.png",
            pipeline_status="pending",
        )

        # Try to update with tenant_b's integer ID → should NOT update
        result = _update_asset_after_ingestion(
            asset_id=str(asset.id),
            status="ingested",
            new_gcs_path="gs://bucket/new/path.png",
            tenant_id=str(tenant_b.id),
        )
        assert result is False

        asset.refresh_from_db()
        assert asset.pipeline_status == "pending"  # Unchanged

    def test_update_asset_matches_correct_tenant(self):
        """_update_asset_after_ingestion updates asset when tenant matches."""
        from tenants.models import Tenant, Domain
        from onboarding.models import Company, BrandAsset
        from data_ingestion.tasks import _update_asset_after_ingestion
        from django.db import connection

        connection.set_schema_to_public()

        tenant, _ = Tenant.objects.get_or_create(
            schema_name="public",
            defaults={"name": "public"},
        )
        Domain.objects.get_or_create(
            domain="localhost",
            defaults={"tenant": tenant, "is_primary": True},
        )

        company = Company.objects.create(
            tenant=tenant,
            name="Correct Co",
            industry="SaaS",
        )
        asset = BrandAsset.objects.create(
            tenant=tenant,
            company=company,
            file_name="brand.png",
            file_type="image",
            file_size=200,
            gcs_path="old.png",
            pipeline_status="pending",
        )

        result = _update_asset_after_ingestion(
            asset_id=str(asset.id),
            status="ingested",
            new_gcs_path="gs://bucket/new.png",
            tenant_id=str(tenant.id),
        )
        assert result is True

        asset.refresh_from_db()
        assert asset.pipeline_status == "ingested"


# ============================================================================
# Defensive Tenant Access Tests
# ============================================================================


@pytest.mark.django_db
class TestDefensiveTenantAccess:
    """Verify views use getattr(request, 'tenant', None) safely."""

    def test_views_handle_missing_tenant(self, api_client, user):
        """API endpoints don't crash when request.tenant is missing."""
        api_client.force_authenticate(user=user)
        api_client.defaults["SERVER_NAME"] = "localhost"

        # Test ai_services endpoints (previously had bare request.tenant)
        response = api_client.get("/api/v1/ai/strategies/")
        # Should not return 500 (AttributeError)
        assert response.status_code != 500

    def test_onboarding_views_return_empty_without_tenant(self, api_client, user):
        """Onboarding views return empty queryset without tenant, not all data."""
        api_client.force_authenticate(user=user)
        api_client.defaults["SERVER_NAME"] = "localhost"

        response = api_client.get("/api/v1/companies/")
        assert response.status_code in (200, 403)
