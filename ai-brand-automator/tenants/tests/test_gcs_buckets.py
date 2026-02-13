"""
Tests for per-tenant GCS bucket features.

Covers:
- TenantGCSService bucket provisioning
- Tenant model bucket resolution helpers
- Factory functions with tenant parameter
- Pipeline event payload bucket propagation
"""

import pytest
from unittest.mock import MagicMock, patch
from django.db import connection

from tenants.models import Tenant
from tenants.services import TenantGCSService


# ── Fixtures ────────────────────────────────────────────────────────


@pytest.fixture
def tenant(db):
    """Create a tenant with a slug for bucket tests."""
    connection.set_schema_to_public()
    return Tenant.objects.create(name="Bucket Test Co", slug="bucket-test")


@pytest.fixture
def tenant_with_buckets(db):
    """Create a tenant that already has bucket names set."""
    connection.set_schema_to_public()
    return Tenant.objects.create(
        name="Provisioned Co",
        slug="provisioned",
        gcs_raw_bucket="provisioned-raw",
        gcs_curated_bucket="provisioned-curated",
    )


# ── Tenant model bucket resolution ─────────────────────────────────


@pytest.mark.django_db
class TestTenantBucketResolution:
    """Tests for Tenant.get_raw_bucket() and Tenant.get_curated_bucket()."""

    def test_get_raw_bucket_returns_tenant_bucket(self, tenant_with_buckets):
        """When gcs_raw_bucket is set, get_raw_bucket returns it."""
        assert tenant_with_buckets.get_raw_bucket() == "provisioned-raw"

    def test_get_curated_bucket_returns_tenant_bucket(self, tenant_with_buckets):
        """When gcs_curated_bucket is set, get_curated_bucket returns it."""
        assert tenant_with_buckets.get_curated_bucket() == "provisioned-curated"

    def test_get_raw_bucket_falls_back_to_global(self, tenant):
        """When gcs_raw_bucket is empty, falls back to DATA_INGESTION setting."""
        assert tenant.gcs_raw_bucket == ""
        result = tenant.get_raw_bucket()
        # Should return the global fallback
        assert result is not None
        assert len(result) > 0

    def test_get_curated_bucket_falls_back_to_global(self, tenant):
        """When gcs_curated_bucket is empty, falls back to MEDIA_CURATION setting."""
        assert tenant.gcs_curated_bucket == ""
        result = tenant.get_curated_bucket()
        assert result is not None
        assert len(result) > 0


# ── TenantGCSService ────────────────────────────────────────────────


@pytest.mark.django_db
class TestTenantGCSService:
    """Tests for TenantGCSService bucket provisioning."""

    @patch("tenants.services.TenantGCSService._build_client")
    def test_create_tenant_buckets(self, mock_build_client, tenant):
        """create_tenant_buckets creates raw and curated buckets."""
        mock_client = MagicMock()
        mock_bucket = MagicMock()
        mock_bucket.exists.return_value = False
        mock_client.bucket.return_value = mock_bucket
        mock_build_client.return_value = mock_client

        service = TenantGCSService()
        service.create_tenant_buckets(tenant)

        # Should have created both buckets
        assert mock_client.create_bucket.call_count == 2
        # Verify bucket naming convention
        assert mock_client.bucket.call_count == 2
        calls = [c.args[0] for c in mock_client.bucket.call_args_list]
        assert "bucket-test-raw" in calls
        assert "bucket-test-curated" in calls

        # Should have saved names to tenant
        tenant.refresh_from_db()
        assert tenant.gcs_raw_bucket == "bucket-test-raw"
        assert tenant.gcs_curated_bucket == "bucket-test-curated"

    @patch("tenants.services.TenantGCSService._build_client")
    def test_create_tenant_buckets_idempotent(self, mock_build_client, tenant):
        """Existing buckets are skipped without error."""
        mock_client = MagicMock()
        mock_bucket = MagicMock()
        mock_bucket.exists.return_value = True  # Already exists
        mock_client.bucket.return_value = mock_bucket
        mock_build_client.return_value = mock_client

        service = TenantGCSService()
        service.create_tenant_buckets(tenant)

        # Should NOT have called create_bucket
        mock_client.create_bucket.assert_not_called()

        # But should still save the names
        tenant.refresh_from_db()
        assert tenant.gcs_raw_bucket == "bucket-test-raw"
        assert tenant.gcs_curated_bucket == "bucket-test-curated"

    @patch("tenants.services.TenantGCSService._build_client")
    def test_delete_tenant_buckets(self, mock_build_client, tenant_with_buckets):
        """delete_tenant_buckets deletes existing buckets."""
        mock_client = MagicMock()
        mock_bucket = MagicMock()
        mock_bucket.exists.return_value = True
        mock_client.bucket.return_value = mock_bucket
        mock_build_client.return_value = mock_client

        service = TenantGCSService()
        service.delete_tenant_buckets(tenant_with_buckets)

        # Should have deleted both buckets
        assert mock_bucket.delete.call_count == 2

    @patch("tenants.services.TenantGCSService._build_client")
    def test_no_client_skips_provisioning(self, mock_build_client, tenant):
        """If GCS client can't be created, provisioning raises RuntimeError
        and does NOT save bucket names to the tenant."""
        mock_build_client.return_value = None

        service = TenantGCSService()
        with pytest.raises(RuntimeError, match="GCS client unavailable"):
            service.create_tenant_buckets(tenant)

        # Bucket names should NOT be set — tenant uses shared defaults
        tenant.refresh_from_db()
        assert tenant.gcs_raw_bucket == ""
        assert tenant.gcs_curated_bucket == ""


# ── Factory functions with tenant param ─────────────────────────────


class TestDataIngestionFactory:
    """Tests for data_ingestion factory with tenant parameter."""

    def test_create_gcs_adapter_without_tenant(self):
        """Without tenant, uses global default bucket."""
        from data_ingestion.factory import create_gcs_adapter

        config = {
            "GCP_PROJECT_ID": "test-project",
            "GCP_BUCKET_NAME": "global-raw-bucket",
        }

        with patch("data_ingestion.adapters.gcs_adapter.storage"):
            adapter = create_gcs_adapter(config=config)
            assert adapter.default_bucket == "global-raw-bucket"

    def test_create_gcs_adapter_with_tenant(self, tenant_with_buckets):
        """With tenant, uses tenant's raw bucket."""
        from data_ingestion.factory import create_gcs_adapter

        config = {
            "GCP_PROJECT_ID": "test-project",
            "GCP_BUCKET_NAME": "global-raw-bucket",
        }

        with patch("data_ingestion.adapters.gcs_adapter.storage"):
            adapter = create_gcs_adapter(config=config, tenant=tenant_with_buckets)
            assert adapter.default_bucket == "provisioned-raw"


class TestMediaCurationFactory:
    """Tests for media_curation factory with tenant parameter."""

    def test_create_storage_adapter_without_tenant(self):
        """Without tenant, uses global default curated bucket."""
        from media_curation.factory import create_storage_adapter

        config = {
            "GCP_PROJECT_ID": "test-project",
            "STORAGE": {
                "CURATED_BUCKET": "global-curated-bucket",
            },
        }

        adapter = create_storage_adapter(config=config)
        assert adapter.default_bucket == "global-curated-bucket"

    def test_create_storage_adapter_with_tenant(self, tenant_with_buckets):
        """With tenant, uses tenant's curated bucket."""
        from media_curation.factory import create_storage_adapter

        config = {
            "GCP_PROJECT_ID": "test-project",
            "STORAGE": {
                "CURATED_BUCKET": "global-curated-bucket",
            },
        }

        adapter = create_storage_adapter(config=config, tenant=tenant_with_buckets)
        assert adapter.default_bucket == "provisioned-curated"


# ── Domain model bucket fields ──────────────────────────────────────


class TestIngestionEventBucketFields:
    """Tests that IngestionEvent preserves bucket info."""

    def test_ingestion_event_with_buckets(self):
        """IngestionEvent accepts and preserves bucket fields."""
        from uuid import uuid4
        from datetime import datetime
        from data_ingestion.domain.models import (
            IngestionEvent,
            EventSource,
        )

        event = IngestionEvent(
            event_id=uuid4(),
            trace_id=uuid4(),
            timestamp=datetime.utcnow(),
            source=EventSource.FRONTEND_UPLOAD,
            tenant_id="test-tenant",
            file_path="gs://test-bucket/_landing/file.pdf",
            file_type="application/pdf",
            raw_bucket="test-tenant-raw",
            curated_bucket="test-tenant-curated",
        )

        assert event.raw_bucket == "test-tenant-raw"
        assert event.curated_bucket == "test-tenant-curated"

    def test_ingestion_event_buckets_optional(self):
        """Bucket fields default to None when omitted."""
        from uuid import uuid4
        from datetime import datetime
        from data_ingestion.domain.models import (
            IngestionEvent,
            EventSource,
        )

        event = IngestionEvent(
            event_id=uuid4(),
            trace_id=uuid4(),
            timestamp=datetime.utcnow(),
            source=EventSource.FRONTEND_UPLOAD,
            tenant_id="test-tenant",
            file_path="gs://test-bucket/_landing/file.pdf",
            file_type="application/pdf",
        )

        assert event.raw_bucket is None
        assert event.curated_bucket is None


class TestCurationEventBucketField:
    """Tests that CurationEvent preserves curated_bucket."""

    def test_curation_event_with_curated_bucket(self):
        """CurationEvent accepts curated_bucket."""
        from uuid import uuid4
        from media_curation.domain.models import CurationEvent

        event = CurationEvent(
            tenant_id="test-tenant",
            file_id=uuid4(),
            raw_gcs_uri="gs://test-bucket/raw/file.pdf",
            mime_type="application/pdf",
            curated_bucket="test-tenant-curated",
        )

        assert event.curated_bucket == "test-tenant-curated"

    def test_curation_event_curated_bucket_optional(self):
        """curated_bucket defaults to None when omitted."""
        from uuid import uuid4
        from media_curation.domain.models import CurationEvent

        event = CurationEvent(
            tenant_id="test-tenant",
            file_id=uuid4(),
            raw_gcs_uri="gs://test-bucket/raw/file.pdf",
            mime_type="application/pdf",
        )

        assert event.curated_bucket is None


# ── Pipeline event propagation ──────────────────────────────────────


class TestBucketPropagation:
    """Tests that bucket info propagates through the pipeline."""

    def test_ingestion_service_propagates_buckets_to_processed_event(self):
        """IngestionService includes bucket info in ProcessedEvent metadata."""
        from uuid import uuid4
        from datetime import datetime
        from unittest.mock import MagicMock

        from data_ingestion.domain.models import (
            IngestionEvent,
            EventSource,
            FileMetadata,
        )
        from data_ingestion.domain.services import IngestionService

        # Create mock adapters
        mock_storage = MagicMock()
        mock_storage.check_exists.return_value = True
        mock_storage.move_file.return_value = (
            "gs://my-tenant-raw/my-tenant/raw/2026/01/01/file.pdf"
        )
        mock_storage.get_metadata.return_value = FileMetadata(
            bucket="my-tenant-raw",
            path="my-tenant/raw/2026/01/01/file.pdf",
            full_uri="gs://my-tenant-raw/my-tenant/raw/2026/01/01/file.pdf",
            size_bytes=1024,
            content_type="application/pdf",
            created_at=datetime.utcnow(),
        )

        mock_cache = MagicMock()
        mock_cache.is_duplicate.return_value = False
        mock_producer = MagicMock()

        service = IngestionService(
            storage=mock_storage,
            cache=mock_cache,
            producer=mock_producer,
            output_topic="test-topic",
            dlq_topic="test-dlq",
            dedupe_ttl_seconds=3600,
            status_ttl_seconds=86400,
        )

        event = IngestionEvent(
            event_id=uuid4(),
            trace_id=uuid4(),
            timestamp=datetime.utcnow(),
            source=EventSource.FRONTEND_UPLOAD,
            tenant_id="my-tenant",
            file_path="gs://my-tenant-raw/_landing/file.pdf",
            file_type="application/pdf",
            raw_bucket="my-tenant-raw",
            curated_bucket="my-tenant-curated",
            metadata={"asset_id": 42},
        )

        result = service.process_event(event)

        # Verify bucket info is in the processed event metadata
        assert result.metadata.get("raw_bucket") == "my-tenant-raw"
        assert result.metadata.get("curated_bucket") == "my-tenant-curated"
        # Original metadata should also be preserved
        assert result.metadata.get("asset_id") == 42
