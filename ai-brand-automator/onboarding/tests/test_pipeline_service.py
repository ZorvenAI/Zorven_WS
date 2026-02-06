"""
Unit tests for OnboardingPipelineService.

Tests cover:
- Event publishing to Kafka
- Asset status updates
- Company document publishing
- Tenant pipeline configuration
"""

import uuid
from unittest.mock import MagicMock, patch

import pytest
from django.test import override_settings

from onboarding.models import BrandAsset
from onboarding.services import OnboardingPipelineService, get_pipeline_service


@pytest.fixture
def pipeline_service():
    """Create a fresh pipeline service instance for testing."""
    return OnboardingPipelineService()


@pytest.fixture
def mock_kafka_producer():
    """Create a mock Kafka producer."""
    producer = MagicMock()
    producer.publish_raw = MagicMock(return_value=None)
    return producer


@pytest.fixture
def sample_brand_asset(db, public_tenant):
    """Create a sample brand asset for testing."""
    from onboarding.models import Company

    # Delete any existing company for this tenant first
    Company.objects.filter(tenant=public_tenant).delete()

    company = Company.objects.create(
        tenant=public_tenant,
        name="Test Company",
        description="Test description",
    )
    asset = BrandAsset.objects.create(
        tenant=public_tenant,
        company=company,
        file_name="test_image.jpg",
        file_type="image",
        file_size=1024,
        gcs_path="_landing/1/abc_test_image.jpg",
        gcs_bucket="test-bucket",
        processed=False,
    )
    return asset


class TestOnboardingPipelineServiceInit:
    """Tests for OnboardingPipelineService initialization."""

    def test_service_initializes_with_kafka_enabled(self):
        """Service should initialize with Kafka enabled by default."""
        service = OnboardingPipelineService()
        assert service._kafka_enabled is True
        assert service._producer is None  # Lazy loaded

    @override_settings(ONBOARDING_KAFKA_ENABLED=False)
    def test_service_initializes_with_kafka_disabled(self):
        """Service should respect ONBOARDING_KAFKA_ENABLED=False."""
        service = OnboardingPipelineService()
        assert service._kafka_enabled is False


class TestPublishAssetEvent:
    """Tests for publish_asset_event method."""

    @override_settings(ONBOARDING_KAFKA_ENABLED=False)
    def test_publish_skipped_when_kafka_disabled(self, sample_brand_asset):
        """Should return None when Kafka is disabled."""
        service = OnboardingPipelineService()
        result = service.publish_asset_event(sample_brand_asset)
        assert result is None

    @override_settings(ONBOARDING_KAFKA_ENABLED=False)
    def test_sync_fallback_sets_ingested_status(self, sample_brand_asset):
        """When Kafka disabled, asset should be marked as ingested but NOT processed."""
        service = OnboardingPipelineService()
        sample_brand_asset.pipeline_status = "pending"
        sample_brand_asset.processed = False
        sample_brand_asset.save()

        service.publish_asset_event(sample_brand_asset)

        sample_brand_asset.refresh_from_db()
        assert sample_brand_asset.pipeline_status == "ingested"
        assert sample_brand_asset.processed is False

    def test_publish_updates_asset_trace_id(
        self, sample_brand_asset, mock_kafka_producer
    ):
        """Should update asset with trace_id when publishing."""
        service = OnboardingPipelineService()
        service._producer = mock_kafka_producer

        # Clear any previous trace_id
        sample_brand_asset.pipeline_trace_id = None
        sample_brand_asset.save()

        trace_id = service.publish_asset_event(sample_brand_asset)

        sample_brand_asset.refresh_from_db()
        assert trace_id is not None
        assert str(sample_brand_asset.pipeline_trace_id) == trace_id
        assert sample_brand_asset.pipeline_status == "pending"

    def test_publish_sends_correct_event_structure(
        self, sample_brand_asset, mock_kafka_producer
    ):
        """Should send properly structured event to Kafka."""
        service = OnboardingPipelineService()
        service._producer = mock_kafka_producer

        service.publish_asset_event(sample_brand_asset)

        mock_kafka_producer.publish_raw.assert_called_once()
        call_args = mock_kafka_producer.publish_raw.call_args
        topic = call_args[0][0]
        event = call_args[0][1]

        assert topic == "raw-ingestion-topic"
        assert "event_id" in event
        assert "trace_id" in event
        assert "timestamp" in event
        assert "file_path" in event
        assert event["source"] == "django-backend"
        assert event["metadata"]["source_service"] == "onboarding"

    def test_publish_marks_asset_failed_on_error(
        self, sample_brand_asset, mock_kafka_producer
    ):
        """Should mark asset as failed when Kafka send fails."""
        service = OnboardingPipelineService()
        service._producer = mock_kafka_producer
        mock_kafka_producer.publish_raw.side_effect = Exception(
            "Kafka connection error"
        )

        result = service.publish_asset_event(sample_brand_asset)

        sample_brand_asset.refresh_from_db()
        assert result is None
        assert sample_brand_asset.pipeline_status == "failed"
        assert "Kafka connection error" in sample_brand_asset.pipeline_error


class TestBuildIngestionEvent:
    """Tests for _build_ingestion_event method."""

    def test_builds_event_with_all_fields(self, sample_brand_asset):
        """Should build event with all required fields."""
        service = OnboardingPipelineService()
        trace_id = uuid.uuid4()

        event = service._build_ingestion_event(sample_brand_asset, trace_id)

        assert event["trace_id"] == str(trace_id)
        assert event["source"] == "django-backend"
        assert event["file_type"] == "image/jpeg"
        assert event["file_size_bytes"] == 1024
        assert "gs://" in event["file_path"]

    def test_builds_event_with_metadata(self, sample_brand_asset):
        """Should include asset metadata in event."""
        service = OnboardingPipelineService()
        trace_id = uuid.uuid4()

        event = service._build_ingestion_event(sample_brand_asset, trace_id)

        assert event["metadata"]["original_filename"] == "test_image.jpg"
        assert event["metadata"]["asset_id"] == sample_brand_asset.id
        assert event["metadata"]["source_service"] == "onboarding"


class TestRetryAssetPipeline:
    """Tests for retry_asset_pipeline method."""

    def test_retry_resets_error_and_republishes(
        self, sample_brand_asset, mock_kafka_producer
    ):
        """Should reset error and republish when retrying."""
        service = OnboardingPipelineService()
        service._producer = mock_kafka_producer

        # Set asset to failed state
        sample_brand_asset.pipeline_status = "failed"
        sample_brand_asset.pipeline_error = "Previous error"
        sample_brand_asset.save()

        result = service.retry_asset_pipeline(sample_brand_asset)

        sample_brand_asset.refresh_from_db()
        assert result is not None
        assert sample_brand_asset.pipeline_error == ""
        mock_kafka_producer.publish_raw.assert_called_once()

    def test_retry_rejected_for_non_failed_asset(self, sample_brand_asset):
        """Should reject retry for assets not in failed/pending state."""
        service = OnboardingPipelineService()

        # Set asset to curated state
        sample_brand_asset.pipeline_status = "curated"
        sample_brand_asset.save()

        result = service.retry_asset_pipeline(sample_brand_asset)

        assert result is None


class TestPublishCompanyDocument:
    """Tests for publish_company_document method."""

    @override_settings(ONBOARDING_KAFKA_ENABLED=False)
    def test_publish_skipped_when_kafka_disabled(self):
        """Should return trace_id but not actually publish when Kafka disabled."""
        service = OnboardingPipelineService()

        company_doc = {
            "document_type": "company_profile",
            "company_id": 1,
            "content": "Test company content",
        }

        result = service.publish_company_document(company_doc)

        assert result is not None  # Returns trace_id even when disabled

    def test_publish_sends_to_rag_topic(self, mock_kafka_producer):
        """Should send company document to RAG topic."""
        service = OnboardingPipelineService()
        service._producer = mock_kafka_producer
        service._kafka_enabled = True

        company_doc = {
            "document_type": "company_profile",
            "company_id": 1,
            "content": "Test company content",
        }

        result = service.publish_company_document(company_doc)

        mock_kafka_producer.publish_raw.assert_called_once()
        call_args = mock_kafka_producer.publish_raw.call_args
        topic = call_args[0][0]

        assert topic == "rag-sync-ready-topic"
        assert result is not None


class TestTenantPipelineConfig:
    """Tests for tenant pipeline configuration methods."""

    def test_setup_creates_default_config(self, pipeline_service):
        """Should create default config for new tenant."""
        with patch("django.core.cache.cache") as mock_cache:
            mock_cache.set = MagicMock()

            config = pipeline_service.setup_tenant_pipeline_config(1)

            assert config["enabled"] is True
            assert config["auto_curation"] is True
            assert config["rag_indexing"] is True
            mock_cache.set.assert_called_once()

    def test_get_returns_cached_config(self, pipeline_service):
        """Should return cached config if available."""
        cached_config = {"enabled": False, "custom": "value"}

        with patch("django.core.cache.cache") as mock_cache:
            mock_cache.get = MagicMock(return_value=cached_config)

            config = pipeline_service.get_tenant_pipeline_config(1)

            assert config == cached_config

    def test_get_returns_defaults_when_not_cached(self, pipeline_service):
        """Should return defaults when config not in cache."""
        with patch("django.core.cache.cache") as mock_cache:
            mock_cache.get = MagicMock(return_value=None)

            config = pipeline_service.get_tenant_pipeline_config(1)

            assert config["enabled"] is True
            assert config["retention_days"] == 90


class TestGetPipelineService:
    """Tests for singleton service accessor."""

    def test_returns_same_instance(self):
        """Should return the same instance on multiple calls."""
        # Reset singleton
        import onboarding.services as svc

        svc._pipeline_service = None

        service1 = get_pipeline_service()
        service2 = get_pipeline_service()

        assert service1 is service2
