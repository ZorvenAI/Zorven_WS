"""
Integration Tests for Media Curation Pipeline.

End-to-end tests for the curation workflow including:
- Full pipeline processing
- Multi-step processing flows
- Error recovery scenarios
- Cross-component interactions
"""

import pytest
import asyncio
import json
from datetime import datetime, timezone
from uuid import UUID, uuid4
from unittest.mock import patch

from django.conf import settings

from media_curation.domain.services import CurationService, ProcessorFactory
from media_curation.domain.models import (
    CurationEvent,
    TenantConfig,
    CurationStatus,
    CurationStatusRecord,
    ContentType,
)
from media_curation.domain.exceptions import (
    ProcessorNotFoundError,
    StorageError,
    AIModelError,
)
from media_curation.adapters import (
    GCSAdapter,
    RedisAdapter,
)
from media_curation.factory import (
    create_processor_factory,
    create_cache_adapter,
    create_storage_adapter,
)


# Helper to run async tests
def run_async(coro):
    """Run async coroutine in sync context."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# Sample UUIDs for testing
SAMPLE_TENANT_ID = UUID("11111111-1111-1111-1111-111111111111")


# =============================================================================
# Factory Integration Tests
# =============================================================================


class TestFactoryIntegration:
    """Tests for factory dependency injection integration."""

    def test_create_processor_factory_returns_factory(self):
        """Test that create_processor_factory returns a working factory."""
        factory = create_processor_factory()

        assert factory is not None
        assert hasattr(factory, "get_processor")

    def test_factory_has_all_processor_types(self):
        """Test that factory includes all processor types."""
        factory = create_processor_factory()

        # Should support documents
        pdf_processor = factory.get_processor("application/pdf")
        assert pdf_processor is not None

        # Should support video (or raise if none available)
        try:
            video_processor = factory.get_processor("video/mp4")
            assert video_processor is not None
        except ProcessorNotFoundError:
            pass  # Expected if no video processor registered

    def test_create_cache_adapter_returns_adapter(self):
        """Test that create_cache_adapter returns working adapter."""
        adapter = create_cache_adapter()

        assert adapter is not None
        assert hasattr(adapter, "get_status")
        assert hasattr(adapter, "set_status")

    def test_create_storage_adapter_returns_adapter(self):
        """Test that create_storage_adapter returns working adapter."""
        import os

        base_dir = settings.BASE_DIR
        credentials_path = os.path.join(base_dir, "credentials", "gcs-credentials.json")

        # Skip if credentials file doesn't exist
        if not os.path.exists(credentials_path):
            pytest.skip("GCS credentials file not found - skipping real GCS tests")

        adapter = create_storage_adapter(
            {
                "STORAGE": {
                    "CREDENTIALS_PATH": credentials_path,
                    "PROJECT_ID": "brandsol",
                }
            }
        )

        assert adapter is not None
        assert hasattr(adapter, "upload_from_bytes")


# =============================================================================
# Full Pipeline Integration Tests
# =============================================================================


class TestFullPipelineIntegration:
    """Tests for end-to-end curation pipeline."""

    @pytest.fixture
    def mock_services(self):
        """Create mock services for integration testing."""
        from media_curation.tests.conftest import (
            MockContentProcessor,
            MockDLPAdapter,
            MockStorageAdapter,
            MockCacheAdapter,
            MockEventProducer,
        )

        processor = MockContentProcessor()
        factory = ProcessorFactory([processor])
        dlp = MockDLPAdapter()
        storage = MockStorageAdapter()
        cache = MockCacheAdapter()
        producer = MockEventProducer()

        service = CurationService(
            processor_factory=factory,
            dlp=dlp,
            storage=storage,
            cache=cache,
            producer=producer,
            output_topic="rag-sync-ready-topic",
            dlq_topic="curation-dlq",
            output_bucket="curated-content",
        )

        return {
            "service": service,
            "processor": processor,
            "dlp": dlp,
            "storage": storage,
            "cache": cache,
            "producer": producer,
        }

    def test_full_pipeline_document_processing(self, mock_services):
        """Test complete document processing through pipeline."""
        service = mock_services["service"]

        event = CurationEvent(
            event_id=uuid4(),
            trace_id=uuid4(),
            tenant_id=SAMPLE_TENANT_ID,
            file_id=uuid4(),
            raw_gcs_uri="gs://bucket/document.pdf",
            mime_type="application/pdf",
            content_type=ContentType.DOCUMENT,
            source_service="api",
            timestamp=datetime.now(timezone.utc),
        )

        result = service.process_event(event)

        # Verify full pipeline executed
        assert result is not None
        assert result.trace_id == event.trace_id
        assert result.tenant_id == event.tenant_id

        # Verify status was updated through pipeline
        cache = mock_services["cache"]
        assert len(cache.set_calls) >= 2  # At least PROCESSING and CURATED

        # Verify document was saved
        storage = mock_services["storage"]
        assert len(storage.save_calls) == 1

        # Verify success event was published
        producer = mock_services["producer"]
        success_events = [
            e for e in producer.published_events if e["topic"] == "rag-sync-ready-topic"
        ]
        assert len(success_events) == 1

    def test_pipeline_with_pii_redaction(self, mock_services):
        """Test pipeline with PII redaction enabled."""
        from media_curation.tests.conftest import MockContentProcessor

        # Create processor that returns text with PII
        processor_with_pii = MockContentProcessor(
            extracted_text="Contact john@example.com for more info."
        )
        factory = ProcessorFactory([processor_with_pii])

        cache = mock_services["cache"]
        dlp = mock_services["dlp"]

        # Configure tenant for PII redaction
        tenant_config = TenantConfig(
            tenant_id=SAMPLE_TENANT_ID,
            dlp_enabled=True,
            dlp_info_types=["EMAIL_ADDRESS"],
        )
        run_async(cache.set_tenant_config(str(SAMPLE_TENANT_ID), tenant_config))

        # Configure DLP to detect PII
        dlp._should_redact = True

        # Create service with the PII-returning processor
        service = CurationService(
            processor_factory=factory,
            dlp=dlp,
            storage=mock_services["storage"],
            cache=cache,
            producer=mock_services["producer"],
            output_topic="rag-sync-ready-topic",
            dlq_topic="curation-dlq",
            output_bucket="curated-content",
        )

        event = CurationEvent(
            event_id=uuid4(),
            trace_id=uuid4(),
            tenant_id=SAMPLE_TENANT_ID,
            file_id=uuid4(),
            raw_gcs_uri="gs://bucket/document.pdf",
            mime_type="application/pdf",
            content_type=ContentType.DOCUMENT,
            source_service="api",
            timestamp=datetime.now(timezone.utc),
        )

        result = service.process_event(event)

        # Verify PII was redacted
        assert result.pii_redacted is True
        assert len(dlp.redact_calls) > 0

    def test_pipeline_status_tracking(self, mock_services):
        """Test status tracking through entire pipeline."""
        service = mock_services["service"]
        _cache = mock_services["cache"]  # noqa: F841

        event = CurationEvent(
            event_id=uuid4(),
            trace_id=uuid4(),
            tenant_id=SAMPLE_TENANT_ID,
            file_id=uuid4(),
            raw_gcs_uri="gs://bucket/document.pdf",
            mime_type="application/pdf",
            content_type=ContentType.DOCUMENT,
            source_service="api",
            timestamp=datetime.now(timezone.utc),
        )

        service.process_event(event)

        # Get final status
        final_status = service.get_status(event.trace_id)

        assert final_status is not None
        assert final_status.status == CurationStatus.CURATED
        assert final_status.trace_id == event.trace_id

    def test_pipeline_handles_processor_failure(self, mock_services):
        """Test pipeline handles processor failure correctly."""
        from media_curation.tests.conftest import MockContentProcessor

        # Create failing processor
        failing_processor = MockContentProcessor(
            should_fail=True,
            failure_exception=AIModelError("Model unavailable"),
        )
        factory = ProcessorFactory([failing_processor])

        service = CurationService(
            processor_factory=factory,
            dlp=mock_services["dlp"],
            storage=mock_services["storage"],
            cache=mock_services["cache"],
            producer=mock_services["producer"],
            output_topic="rag-sync-ready-topic",
            dlq_topic="curation-dlq",
            output_bucket="curated-content",
        )

        event = CurationEvent(
            event_id=uuid4(),
            trace_id=uuid4(),
            tenant_id=SAMPLE_TENANT_ID,
            file_id=uuid4(),
            raw_gcs_uri="gs://bucket/document.pdf",
            mime_type="application/pdf",
            content_type=ContentType.DOCUMENT,
            source_service="api",
            timestamp=datetime.now(timezone.utc),
        )

        with pytest.raises(AIModelError):
            service.process_event(event)

        # Verify status was updated to FAILED
        cache = mock_services["cache"]
        failed_calls = [
            c
            for c in cache.set_calls
            if c.get("status") and c["status"].status == CurationStatus.FAILED
        ]
        assert len(failed_calls) >= 1


# =============================================================================
# Cross-Component Integration Tests
# =============================================================================


class TestCrossComponentIntegration:
    """Tests for interactions between different components."""

    def test_cache_and_service_integration(self):
        """Test cache adapter integrates with service correctly."""
        cache = RedisAdapter()  # Uses in-memory mock if Redis unavailable

        # Store a status
        status = CurationStatusRecord(
            trace_id=uuid4(),
            event_id=uuid4(),
            tenant_id=SAMPLE_TENANT_ID,
            file_id=uuid4(),
            status=CurationStatus.PROCESSING,
            message="Test",
            updated_at=datetime.now(timezone.utc),
        )

        run_async(cache.set_status(str(status.trace_id), status))

        # Retrieve status
        retrieved = run_async(cache.get_status(str(status.trace_id)))

        assert retrieved is not None
        assert retrieved.status == CurationStatus.PROCESSING

    def test_tenant_config_flow(self):
        """Test tenant configuration flow through cache."""
        cache = RedisAdapter()

        # Store tenant config
        config = TenantConfig(
            tenant_id=SAMPLE_TENANT_ID,
            dlp_enabled=True,
            dlp_info_types=["EMAIL_ADDRESS", "PHONE_NUMBER"],
            ai_model="gemini-2.0-flash",
        )

        run_async(cache.set_tenant_config(str(SAMPLE_TENANT_ID), config))

        # Retrieve config
        retrieved = run_async(cache.get_tenant_config(str(SAMPLE_TENANT_ID)))

        assert retrieved is not None
        assert retrieved.dlp_enabled is True
        assert "EMAIL_ADDRESS" in retrieved.dlp_info_types

    def test_deduplication_flow(self):
        """Test event deduplication through cache."""
        cache = RedisAdapter()

        event_id = str(uuid4())

        # Event should not be duplicate initially
        is_dup = run_async(cache.is_duplicate(event_id))
        assert is_dup is False

        # Mark as processed
        run_async(cache.mark_processed(event_id))

        # Now should be duplicate
        is_dup = run_async(cache.is_duplicate(event_id))
        assert is_dup is True


# =============================================================================
# Error Recovery Integration Tests
# =============================================================================


class TestErrorRecoveryIntegration:
    """Tests for error recovery scenarios."""

    @pytest.fixture
    def mock_services(self):
        """Create mock services for error recovery testing."""
        from media_curation.tests.conftest import (
            MockContentProcessor,
            MockDLPAdapter,
            MockStorageAdapter,
            MockCacheAdapter,
            MockEventProducer,
        )

        processor = MockContentProcessor()
        factory = ProcessorFactory([processor])
        dlp = MockDLPAdapter()
        storage = MockStorageAdapter()
        cache = MockCacheAdapter()
        producer = MockEventProducer()

        service = CurationService(
            processor_factory=factory,
            dlp=dlp,
            storage=storage,
            cache=cache,
            producer=producer,
            output_topic="rag-sync-ready-topic",
            dlq_topic="curation-dlq",
            output_bucket="curated-content",
        )

        return {
            "service": service,
            "producer": producer,
            "cache": cache,
        }

    def test_retry_recovery_success(self, mock_services):
        """Test successful recovery after retries."""
        service = mock_services["service"]

        # Track call count for simulated recovery
        call_count = [0]
        original_process = service.process_event

        def mock_process(event):
            call_count[0] += 1
            if call_count[0] < 2:
                raise StorageError("Temporary failure")
            return original_process(event)

        with patch.object(service, "process_event", side_effect=mock_process):
            event = CurationEvent(
                event_id=uuid4(),
                trace_id=uuid4(),
                tenant_id=SAMPLE_TENANT_ID,
                file_id=uuid4(),
                raw_gcs_uri="gs://bucket/document.pdf",
                mime_type="application/pdf",
                content_type=ContentType.DOCUMENT,
                source_service="api",
                timestamp=datetime.now(timezone.utc),
            )

            _ = service.process_with_retry(event, max_retries=3, backoff_seconds=0.01)

        # Verify eventually succeeded
        assert call_count[0] == 2

    def test_dlq_after_max_retries(self, mock_services):
        """Test event goes to DLQ after max retries exhausted."""
        service = mock_services["service"]
        producer = mock_services["producer"]

        event = CurationEvent(
            event_id=uuid4(),
            trace_id=uuid4(),
            tenant_id=SAMPLE_TENANT_ID,
            file_id=uuid4(),
            raw_gcs_uri="gs://bucket/document.pdf",
            mime_type="application/pdf",
            content_type=ContentType.DOCUMENT,
            source_service="api",
            timestamp=datetime.now(timezone.utc),
        )

        with patch.object(
            service, "process_event", side_effect=StorageError("Always fails")
        ):
            result = service.process_with_retry(
                event, max_retries=2, backoff_seconds=0.01
            )

        # Should return None (failed)
        assert result is None

        # Should have published to DLQ
        dlq_events = [
            e for e in producer.published_events if e["topic"] == "curation-dlq"
        ]
        assert len(dlq_events) >= 1

    def test_non_retryable_error_immediate_dlq(self, mock_services):
        """Test non-retryable errors go to DLQ immediately."""
        service = mock_services["service"]
        producer = mock_services["producer"]

        event = CurationEvent(
            event_id=uuid4(),
            trace_id=uuid4(),
            tenant_id=SAMPLE_TENANT_ID,
            file_id=uuid4(),
            raw_gcs_uri="gs://bucket/unknown.xyz",
            mime_type="application/x-unknown",
            content_type=ContentType.DOCUMENT,
            source_service="api",
            timestamp=datetime.now(timezone.utc),
        )

        with patch.object(
            service, "process_event", side_effect=ProcessorNotFoundError("No processor")
        ):
            result = service.process_with_retry(
                event, max_retries=5, backoff_seconds=0.01
            )

        # Should return None (failed)
        assert result is None

        # Should have published to DLQ immediately (no retries)
        dlq_events = [
            e for e in producer.published_events if e["topic"] == "curation-dlq"
        ]
        assert len(dlq_events) >= 1


# =============================================================================
# Real GCS Integration Tests
# =============================================================================


class TestRealGCSIntegration:
    """Tests with real GCS integration (requires credentials)."""

    @pytest.fixture
    def gcs_adapter(self):
        """Create real GCS adapter with credentials."""
        import os

        base_dir = settings.BASE_DIR
        credentials_path = os.path.join(base_dir, "credentials", "gcs-credentials.json")

        if not os.path.exists(credentials_path):
            pytest.skip("GCS credentials not available")

        return GCSAdapter(
            project_id="brandsol-project",
            credentials_path=credentials_path,
            default_bucket="onboarding-brandsol-customer-bucket-1",
        )

    def test_gcs_read_write_roundtrip(self, gcs_adapter):
        """Test writing and reading back from GCS."""
        import uuid

        test_id = str(uuid.uuid4())[:8]
        test_data = {"test": "data", "id": test_id}
        bucket = "onboarding-brandsol-customer-bucket-1"
        destination = f"gs://{bucket}/tests/integration-{test_id}.json"

        # Write
        result = run_async(
            gcs_adapter.save_json(
                data=test_data,
                destination_path=destination,
            )
        )

        assert result is not None

        # Read back
        content = run_async(gcs_adapter.download_as_bytes(destination))
        data = json.loads(content.decode("utf-8"))

        assert data["test"] == "data"
        assert data["id"] == test_id

    def test_gcs_file_exists_check(self, gcs_adapter):
        """Test file existence checking."""
        bucket = "onboarding-brandsol-customer-bucket-1"
        # Existing file
        test_file = f"gs://{bucket}/customer-1/customer-1-onboarding-file-example-1.txt"
        exists = run_async(gcs_adapter.exists(test_file))
        assert exists is True

        # Non-existing file
        not_exists = run_async(
            gcs_adapter.exists(f"gs://{bucket}/does-not-exist-12345.txt")
        )
        assert not_exists is False
