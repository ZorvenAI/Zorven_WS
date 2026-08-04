"""
Tests for Media Curation Celery Tasks.

Integration tests using real CurationService with mock adapters.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import patch
from uuid import uuid4

from media_curation.tasks import _detect_content_type
from media_curation.domain.models import (
    CurationStatus,
    CurationStatusRecord,
    ContentType,
    TenantConfig,
)
from media_curation.domain.exceptions import (
    RetryableError,
    NonRetryableError,
)

# Import mock adapters and fixtures from conftest
from media_curation.tests.conftest import (
    MockContentProcessor,
    MockCacheAdapter,
    MockStorageAdapter,
    MockEventProducer,
    MockDLPAdapter,
    SAMPLE_TENANT_ID,
    SAMPLE_TRACE_ID,
    SAMPLE_EVENT_ID,
)


class TestDetectContentType:
    """Tests for content type detection helper."""

    def test_video_mime_type(self):
        assert _detect_content_type("video/mp4") == ContentType.VIDEO
        assert _detect_content_type("video/webm") == ContentType.VIDEO

    def test_audio_mime_type(self):
        assert _detect_content_type("audio/mpeg") == ContentType.AUDIO
        assert _detect_content_type("audio/wav") == ContentType.AUDIO

    def test_image_mime_type(self):
        assert _detect_content_type("image/png") == ContentType.IMAGE
        assert _detect_content_type("image/jpeg") == ContentType.IMAGE

    def test_document_mime_type(self):
        assert _detect_content_type("application/pdf") == ContentType.DOCUMENT
        assert _detect_content_type("text/plain") == ContentType.DOCUMENT

    def test_unknown_defaults_to_document(self):
        assert _detect_content_type("application/octet-stream") == ContentType.DOCUMENT


@pytest.fixture
def test_adapters():
    """Create test adapters for integration testing."""
    cache = MockCacheAdapter()
    storage = MockStorageAdapter()
    producer = MockEventProducer()
    dlp = MockDLPAdapter()
    content_processor = MockContentProcessor(
        extracted_text="Test extracted content from document"
    )

    return {
        "cache": cache,
        "storage": storage,
        "producer": producer,
        "dlp": dlp,
        "content_processor": content_processor,
    }


@pytest.fixture
def real_curation_service(test_adapters):
    """Create a real CurationService with mock adapters injected."""
    from media_curation.domain.services import CurationService, ProcessorFactory
    from media_curation.tests.conftest import MockVideoProcessor

    processor_factory = ProcessorFactory(
        processors=[
            test_adapters["content_processor"],
            MockVideoProcessor(),
        ]
    )

    service = CurationService(
        processor_factory=processor_factory,
        cache=test_adapters["cache"],
        storage=test_adapters["storage"],
        producer=test_adapters["producer"],
        dlp=test_adapters["dlp"],
        output_topic="rag-sync-ready-topic",
        dlq_topic="curation-dlq",
        output_bucket="curated-content",
    )

    return service


class TestProcessCurationEventIntegration:
    """Integration tests for process_curation_event task with real service."""

    @pytest.mark.django_db
    def test_successful_processing(self, real_curation_service, test_adapters):
        """Test successful event processing through the real service pipeline."""
        # Patch factory to return our real service with mock adapters
        with patch(
            "media_curation.tasks.get_curation_service",
            return_value=real_curation_service,
        ):
            from media_curation.tasks import process_curation_event

            event_id = str(SAMPLE_EVENT_ID)
            trace_id = str(SAMPLE_TRACE_ID)
            tenant_id = str(SAMPLE_TENANT_ID)

            result = process_curation_event.apply(
                args=(
                    event_id,
                    trace_id,
                    tenant_id,
                    "gs://test-bucket/input.pdf",
                    "application/pdf",
                ),
            ).get()

            assert result["status"] == "success"
            assert result["event_id"] == event_id

            # Verify the processor was called
            assert len(test_adapters["content_processor"].process_calls) == 1

            # Verify storage was called (document saved)
            assert len(test_adapters["storage"].save_calls) == 1
            saved = test_adapters["storage"].save_calls[0]
            assert "curated" in saved["destination_path"]

            # Verify event was published to output topic
            assert len(test_adapters["producer"].published_events) >= 1

    @pytest.mark.django_db
    def test_status_updates_through_pipeline(
        self, real_curation_service, test_adapters
    ):
        """Test that status is updated at each stage of processing."""
        with patch(
            "media_curation.tasks.get_curation_service",
            return_value=real_curation_service,
        ):
            from media_curation.tasks import process_curation_event

            event_id = str(uuid4())
            trace_id = str(uuid4())
            tenant_id = str(SAMPLE_TENANT_ID)

            result = process_curation_event.apply(
                args=(
                    event_id,
                    trace_id,
                    tenant_id,
                    "gs://test-bucket/doc.pdf",
                    "application/pdf",
                ),
            ).get()

            assert result["status"] == "success"

            # Verify status was set (at least PROCESSING and CURATED)
            status_calls = [
                c for c in test_adapters["cache"].set_calls if "status" in c
            ]
            assert len(status_calls) >= 1

            # Final status should be CURATED
            final_status = status_calls[-1]["status"]
            assert final_status.status == CurationStatus.CURATED

    @pytest.mark.django_db
    def test_pii_redaction_when_enabled(self, real_curation_service, test_adapters):
        """Test that PII is redacted when tenant config enables it."""
        # Pre-configure tenant with DLP enabled
        tenant_config = TenantConfig(
            tenant_id=SAMPLE_TENANT_ID,
            dlp_enabled=True,
            dlp_info_types=["EMAIL_ADDRESS", "PHONE_NUMBER"],
        )

        # Use blocking call to set tenant config
        import asyncio

        loop = asyncio.new_event_loop()
        loop.run_until_complete(
            test_adapters["cache"].set_tenant_config(
                str(SAMPLE_TENANT_ID), tenant_config
            )
        )
        loop.close()

        # Create processor that returns text with PII
        test_adapters["content_processor"]._extracted_text = (
            "Contact john@example.com or call 555-123-4567"
        )

        with patch(
            "media_curation.tasks.get_curation_service",
            return_value=real_curation_service,
        ):
            from media_curation.tasks import process_curation_event

            result = process_curation_event.apply(
                args=(
                    str(uuid4()),
                    str(uuid4()),
                    str(SAMPLE_TENANT_ID),
                    "gs://test-bucket/pii-doc.pdf",
                    "application/pdf",
                ),
            ).get()

            assert result["status"] == "success"

            # Verify DLP was called for redaction
            assert len(test_adapters["dlp"].redact_calls) >= 1

    @pytest.mark.django_db
    def test_processor_failure_updates_status_to_failed(self, test_adapters):
        """Test that processor failure results in FAILED status."""
        from media_curation.domain.services import CurationService, ProcessorFactory
        from media_curation.tests.conftest import MockVideoProcessor

        # Create a processor that fails
        failing_processor = MockContentProcessor(
            should_fail=True,
            failure_exception=NonRetryableError("Invalid PDF format"),
        )

        processor_factory = ProcessorFactory(
            processors=[failing_processor, MockVideoProcessor()]
        )

        service = CurationService(
            processor_factory=processor_factory,
            cache=test_adapters["cache"],
            storage=test_adapters["storage"],
            producer=test_adapters["producer"],
            dlp=test_adapters["dlp"],
            output_topic="rag-sync-ready-topic",
            dlq_topic="curation-dlq",
            output_bucket="curated-content",
        )

        with (
            patch("media_curation.tasks.get_curation_service", return_value=service),
            patch(
                "media_curation.tasks.create_kafka_producer",
                return_value=test_adapters["producer"],
            ),
        ):
            from media_curation.tasks import process_curation_event

            result = process_curation_event.apply(
                args=(
                    str(uuid4()),
                    str(uuid4()),
                    str(SAMPLE_TENANT_ID),
                    "gs://test-bucket/bad.pdf",
                    "application/pdf",
                ),
            ).get()

            assert result["status"] == "failed"
            assert result["sent_to_dlq"] is True

            # Verify status was updated to FAILED
            status_calls = [
                c for c in test_adapters["cache"].set_calls if "status" in c
            ]
            failed_statuses = [
                c for c in status_calls if c["status"].status == CurationStatus.FAILED
            ]
            assert len(failed_statuses) >= 1

    @pytest.mark.django_db
    def test_retryable_error_triggers_celery_retry(self, test_adapters):
        """Test that retryable errors trigger Celery's retry mechanism."""
        from celery.exceptions import Retry
        from media_curation.domain.services import CurationService, ProcessorFactory
        from media_curation.tests.conftest import MockVideoProcessor

        # Create a processor that fails with retryable error
        failing_processor = MockContentProcessor(
            should_fail=True,
            failure_exception=RetryableError("Temporary GCS timeout"),
        )

        processor_factory = ProcessorFactory(
            processors=[failing_processor, MockVideoProcessor()]
        )

        service = CurationService(
            processor_factory=processor_factory,
            cache=test_adapters["cache"],
            storage=test_adapters["storage"],
            producer=test_adapters["producer"],
            dlp=test_adapters["dlp"],
            output_topic="rag-sync-ready-topic",
            dlq_topic="curation-dlq",
            output_bucket="curated-content",
        )

        with patch("media_curation.tasks.get_curation_service", return_value=service):
            from media_curation.tasks import process_curation_event

            # Celery autoretry converts RetryableError to Retry exception
            with pytest.raises(Retry):
                process_curation_event.apply(
                    args=(
                        str(uuid4()),
                        str(uuid4()),
                        str(SAMPLE_TENANT_ID),
                        "gs://test-bucket/timeout.pdf",
                        "application/pdf",
                    ),
                    throw=True,
                ).get()


class TestProcessBatchIntegration:
    """Integration tests for process_batch task."""

    @pytest.mark.django_db
    def test_batch_processing_success(self, real_curation_service, test_adapters):
        """Test successful batch processing with real service."""
        with patch(
            "media_curation.tasks.get_curation_service",
            return_value=real_curation_service,
        ):
            from media_curation.tasks import process_batch

            events = [
                {
                    "event_id": str(uuid4()),
                    "trace_id": str(uuid4()),
                    "tenant_id": str(SAMPLE_TENANT_ID),
                    "source_path": f"gs://test-bucket/file{i}.pdf",
                    "file_type": "application/pdf",
                }
                for i in range(3)
            ]

            result = process_batch.apply(args=(events,)).get()

            assert result["total"] == 3
            assert result["success"] + result["failed"] + result["skipped"] == 3

            # With working processors, all should succeed
            assert result["success"] == 3


class TestCheckStatusIntegration:
    """Integration tests for check_status task."""

    @pytest.mark.django_db
    def test_check_status_found(self, test_adapters):
        """Test checking status for existing trace_id using real cache adapter."""
        import asyncio

        # Pre-populate cache with status
        mock_status = CurationStatusRecord(
            trace_id=SAMPLE_TRACE_ID,
            event_id=SAMPLE_EVENT_ID,
            tenant_id=SAMPLE_TENANT_ID,
            file_id=uuid4(),
            status=CurationStatus.CURATED,
            message="Success",
            output_gcs_uri="gs://curated-bucket/output.json",
            updated_at=datetime.now(timezone.utc),
        )

        loop = asyncio.new_event_loop()
        loop.run_until_complete(
            test_adapters["cache"].set_status(str(SAMPLE_TRACE_ID), mock_status)
        )
        loop.close()

        with patch(
            "media_curation.tasks.create_cache_adapter",
            return_value=test_adapters["cache"],
        ):
            from media_curation.tasks import check_status

            result = check_status.apply(args=(str(SAMPLE_TRACE_ID),)).get()

            assert result is not None
            assert result["trace_id"] == str(SAMPLE_TRACE_ID)
            assert result["status"] == CurationStatus.CURATED.value

    @pytest.mark.django_db
    def test_check_status_not_found(self, test_adapters):
        """Test checking status for non-existent trace_id."""
        with patch(
            "media_curation.tasks.create_cache_adapter",
            return_value=test_adapters["cache"],
        ):
            from media_curation.tasks import check_status

            result = check_status.apply(args=(str(uuid4()),)).get()

            assert result is None


class TestReprocessFromDlqIntegration:
    """Integration tests for reprocess_from_dlq task."""

    @pytest.mark.django_db
    def test_reprocess_dlq_message(self, real_curation_service, test_adapters):
        """Test reprocessing a DLQ message with real service."""
        with patch(
            "media_curation.tasks.get_curation_service",
            return_value=real_curation_service,
        ):
            from media_curation.tasks import reprocess_from_dlq

            dlq_message = {
                "original_event": {
                    "event_id": str(SAMPLE_EVENT_ID),
                    "trace_id": str(SAMPLE_TRACE_ID),
                    "tenant_id": str(SAMPLE_TENANT_ID),
                    "source_path": "gs://test-bucket/input.pdf",
                    "file_type": "application/pdf",
                },
                "error": {
                    "message": "Temporary failure",
                    "type": "RetryableError",
                },
                "retry_count": 3,
            }

            result = reprocess_from_dlq.apply(args=(dlq_message,)).get()

            assert result["status"] == "success"

            # Verify the document was actually processed through the pipeline
            assert len(test_adapters["content_processor"].process_calls) == 1
            assert len(test_adapters["storage"].save_calls) == 1
