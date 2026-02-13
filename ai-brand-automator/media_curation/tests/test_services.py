"""
Unit tests for CurationService orchestrator.

Tests the main service orchestration logic including:
- Event processing flow
- Retry logic
- Error handling
- Status updates
- Event publishing
"""

import pytest
from datetime import datetime, timezone
from uuid import uuid4
from unittest.mock import MagicMock, patch

from media_curation.domain.services import CurationService, ProcessorFactory
from media_curation.domain.models import (
    CurationEvent,
    TenantConfig,
    ProcessorResult,
    CuratedDocument,
    CurationStatus,
    ContentType,
)
from media_curation.domain.exceptions import (
    ProcessorNotFoundError,
    StorageError,
    AIModelError,
)
from media_curation.tests.conftest import (
    MockContentProcessor,
    MockDLPAdapter,
    MockCacheAdapter,
    SAMPLE_TENANT_ID,
)


class TestProcessorFactory:
    """Tests for ProcessorFactory."""

    def test_get_processor_for_supported_type(
        self,
        mock_content_processor,
        mock_video_processor,
    ):
        """Test getting a processor for a supported MIME type."""
        factory = ProcessorFactory([mock_content_processor, mock_video_processor])

        processor = factory.get_processor("application/pdf")
        assert processor is mock_content_processor

    def test_get_processor_for_video(
        self,
        mock_content_processor,
        mock_video_processor,
    ):
        """Test getting a processor for video MIME type."""
        factory = ProcessorFactory([mock_content_processor, mock_video_processor])

        processor = factory.get_processor("video/mp4")
        assert processor is mock_video_processor

    def test_get_processor_unsupported_type_raises_error(
        self,
        mock_content_processor,
    ):
        """Test that unsupported MIME type raises ProcessorNotFoundError."""
        factory = ProcessorFactory([mock_content_processor])

        with pytest.raises(ProcessorNotFoundError) as exc_info:
            factory.get_processor("application/unknown")

        assert "application/unknown" in str(exc_info.value)

    def test_list_supported_types(
        self,
        mock_content_processor,
        mock_video_processor,
    ):
        """Test listing all supported MIME types."""
        factory = ProcessorFactory([mock_content_processor, mock_video_processor])

        supported = factory.list_supported_types()
        assert "application/pdf" in supported
        assert "text/plain" in supported

    def test_empty_processor_list(self):
        """Test factory with no processors."""
        factory = ProcessorFactory([])

        with pytest.raises(ProcessorNotFoundError):
            factory.get_processor("application/pdf")


class TestCurationServiceProcessEvent:
    """Tests for CurationService.process_event()."""

    def test_successful_processing(
        self,
        curation_service,
        sample_curation_event,
        mock_cache_adapter,
        mock_storage_adapter,
        mock_event_producer,
    ):
        """Test successful event processing."""
        result = curation_service.process_event(sample_curation_event)

        assert isinstance(result, CuratedDocument)
        assert result.trace_id == sample_curation_event.trace_id
        assert result.tenant_id == sample_curation_event.tenant_id

    def test_status_updated_to_processing(
        self,
        curation_service,
        sample_curation_event,
        mock_cache_adapter,
    ):
        """Test that status is updated to PROCESSING."""
        curation_service.process_event(sample_curation_event)

        # Check that status was set multiple times
        assert len(mock_cache_adapter.set_calls) > 0

        # Find the PROCESSING status update
        processing_calls = [
            c
            for c in mock_cache_adapter.set_calls
            if c.get("status") and c["status"].status == CurationStatus.PROCESSING
        ]
        assert len(processing_calls) >= 1

    def test_status_updated_to_curated_on_success(
        self,
        curation_service,
        sample_curation_event,
        mock_cache_adapter,
    ):
        """Test that status is updated to CURATED on success."""
        curation_service.process_event(sample_curation_event)

        # Find the CURATED status update (should be the last one)
        final_call = mock_cache_adapter.set_calls[-1]
        assert final_call["status"].status == CurationStatus.CURATED

    def test_document_saved_to_storage(
        self,
        curation_service,
        sample_curation_event,
        mock_storage_adapter,
    ):
        """Test that curated document is saved to storage."""
        curation_service.process_event(sample_curation_event)

        assert len(mock_storage_adapter.save_calls) == 1
        save_call = mock_storage_adapter.save_calls[0]
        # Check destination_path contains tenant_id
        assert sample_curation_event.tenant_id in save_call["destination_path"]
        assert save_call["content_type"] == "application/json"

    def test_success_event_published(
        self,
        curation_service,
        sample_curation_event,
        mock_event_producer,
    ):
        """Test that success event is published to output topic."""
        curation_service.process_event(sample_curation_event)

        # Should publish to output topic
        success_events = [
            e
            for e in mock_event_producer.published_events
            if e["topic"] == "rag-sync-ready-topic"
        ]
        assert len(success_events) == 1
        assert success_events[0]["key"] == sample_curation_event.tenant_id

    def test_processor_not_found_raises_error(
        self,
        curation_service,
        mock_cache_adapter,
    ):
        """Test that unsupported MIME type raises error."""
        event = CurationEvent(
            event_id=uuid4(),
            trace_id=uuid4(),
            tenant_id=SAMPLE_TENANT_ID,
            file_id=uuid4(),
            raw_gcs_uri="gs://bucket/file.xyz",
            mime_type="application/x-unknown",
            content_type=ContentType.DOCUMENT,
            source_service="test",
            timestamp=datetime.now(timezone.utc),
        )

        with pytest.raises(ProcessorNotFoundError):
            curation_service.process_event(event)

    def test_status_updated_to_failed_on_error(
        self,
        processor_factory,
        mock_dlp_adapter,
        mock_storage_adapter,
        mock_cache_adapter,
        mock_event_producer,
    ):
        """Test that status is updated to FAILED on error."""
        # Create a processor that fails
        failing_processor = MockContentProcessor(
            should_fail=True,
            failure_exception=AIModelError("Model failed"),
        )
        factory = ProcessorFactory([failing_processor])

        service = CurationService(
            processor_factory=factory,
            dlp=mock_dlp_adapter,
            storage=mock_storage_adapter,
            cache=mock_cache_adapter,
            producer=mock_event_producer,
            output_topic="rag-sync-ready-topic",
            dlq_topic="curation-dlq",
            output_bucket="curated-content",
        )

        event = CurationEvent(
            event_id=uuid4(),
            trace_id=uuid4(),
            tenant_id=SAMPLE_TENANT_ID,
            file_id=uuid4(),
            raw_gcs_uri="gs://bucket/file.pdf",
            mime_type="application/pdf",
            content_type=ContentType.DOCUMENT,
            source_service="test",
            timestamp=datetime.now(timezone.utc),
        )

        with pytest.raises(AIModelError):
            service.process_event(event)

        # Check status was set to FAILED
        failed_calls = [
            c
            for c in mock_cache_adapter.set_calls
            if c.get("status") and c["status"].status == CurationStatus.FAILED
        ]
        assert len(failed_calls) >= 1


class TestCurationServicePIIRedaction:
    """Tests for PII redaction in CurationService."""

    def test_pii_redaction_when_enabled(
        self,
        curation_service,
        sample_curation_event,
        mock_cache_adapter,
        mock_dlp_adapter,
    ):
        """Test that PII redaction is performed when enabled."""
        # Set up tenant config with DLP enabled
        tenant_config = TenantConfig(
            tenant_id=sample_curation_event.tenant_id,
            dlp_enabled=True,
            dlp_info_types=["EMAIL_ADDRESS", "PHONE_NUMBER"],
        )
        mock_cache_adapter.set(
            f"config:tenant:{sample_curation_event.tenant_id}",
            tenant_config.model_dump(mode="json"),
        )

        # Process event
        curation_service.process_event(sample_curation_event)

        # Verify DLP was called
        assert len(mock_dlp_adapter.redact_calls) > 0

    def test_pii_redaction_skipped_when_disabled(
        self,
        processor_factory,
        sample_curation_event,
        mock_storage_adapter,
        mock_event_producer,
    ):
        """Test that PII redaction is skipped when disabled."""
        import asyncio

        # Create fresh mock adapters
        mock_dlp = MockDLPAdapter(should_redact=True)
        mock_cache = MockCacheAdapter()

        # Set up tenant config with DLP disabled
        tenant_config = TenantConfig(
            tenant_id=sample_curation_event.tenant_id,
            dlp_enabled=False,
        )
        loop = asyncio.new_event_loop()
        loop.run_until_complete(
            mock_cache.set_tenant_config(
                sample_curation_event.tenant_id,
                tenant_config,
            )
        )
        loop.close()

        service = CurationService(
            processor_factory=processor_factory,
            dlp=mock_dlp,
            storage=mock_storage_adapter,
            cache=mock_cache,
            producer=mock_event_producer,
            output_topic="rag-sync-ready-topic",
            dlq_topic="curation-dlq",
            output_bucket="curated-content",
        )

        # Process event
        result = service.process_event(sample_curation_event)

        # Verify DLP was not called
        assert len(mock_dlp.redact_calls) == 0
        assert result.pii_redacted is False

    def test_pii_redacted_flag_set_when_pii_found(
        self,
        processor_factory,
        mock_storage_adapter,
        mock_event_producer,
    ):
        """Test that pii_redacted flag is set when PII is detected."""
        import asyncio

        # Create processor that returns text with PII
        processor = MockContentProcessor(
            extracted_text="Contact john@example.com for more info."
        )
        factory = ProcessorFactory([processor])

        # Create DLP adapter that will redact
        dlp = MockDLPAdapter(should_redact=True)
        mock_cache = MockCacheAdapter()

        # Set up tenant config with DLP enabled
        tenant_config = TenantConfig(
            tenant_id=SAMPLE_TENANT_ID,
            dlp_enabled=True,
        )
        loop = asyncio.new_event_loop()
        loop.run_until_complete(
            mock_cache.set_tenant_config(
                str(SAMPLE_TENANT_ID),
                tenant_config,
            )
        )
        loop.close()

        service = CurationService(
            processor_factory=factory,
            dlp=dlp,
            storage=mock_storage_adapter,
            cache=mock_cache,
            producer=mock_event_producer,
            output_topic="rag-sync-ready-topic",
            dlq_topic="curation-dlq",
            output_bucket="curated-content",
        )

        event = CurationEvent(
            event_id=uuid4(),
            trace_id=uuid4(),
            tenant_id=SAMPLE_TENANT_ID,
            file_id=uuid4(),
            raw_gcs_uri="gs://bucket/file.pdf",
            mime_type="application/pdf",
            content_type=ContentType.DOCUMENT,
            source_service="test",
            timestamp=datetime.now(timezone.utc),
        )

        result = service.process_event(event)

        assert result.pii_redacted is True
        assert "[REDACTED]" in result.extracted_text

    def test_dlp_failure_continues_curation_without_redaction(
        self,
        processor_factory,
        mock_storage_adapter,
        mock_event_producer,
    ):
        """Test that DLP failure is non-fatal: curation succeeds with original text."""
        import asyncio

        # Create a DLP adapter that raises on redact_pii
        failing_dlp = MockDLPAdapter(should_fail=True)
        mock_cache = MockCacheAdapter()

        # Set up tenant config with DLP enabled
        tenant_config = TenantConfig(
            tenant_id=SAMPLE_TENANT_ID,
            dlp_enabled=True,
            dlp_info_types=["EMAIL_ADDRESS"],
        )
        loop = asyncio.new_event_loop()
        loop.run_until_complete(
            mock_cache.set_tenant_config(
                str(SAMPLE_TENANT_ID),
                tenant_config,
            )
        )
        loop.close()

        service = CurationService(
            processor_factory=processor_factory,
            dlp=failing_dlp,
            storage=mock_storage_adapter,
            cache=mock_cache,
            producer=mock_event_producer,
            output_topic="rag-sync-ready-topic",
            dlq_topic="curation-dlq",
            output_bucket="curated-content",
        )

        event = CurationEvent(
            event_id=uuid4(),
            trace_id=uuid4(),
            tenant_id=SAMPLE_TENANT_ID,
            file_id=uuid4(),
            raw_gcs_uri="gs://bucket/file.pdf",
            mime_type="application/pdf",
            content_type=ContentType.DOCUMENT,
            source_service="test",
            timestamp=datetime.now(timezone.utc),
        )

        # DLP fails, but curation should still succeed
        result = service.process_event(event)

        # Verify curation completed with original (unredacted) text
        assert result is not None
        assert result.pii_redacted is False
        assert result.extracted_text == "Mock extracted text"

        # Verify DLP was attempted (called but failed)
        assert len(failing_dlp.redact_calls) == 1


class TestCurationServiceRetryLogic:
    """Tests for CurationService.process_with_retry()."""

    def test_retry_on_retryable_error(
        self,
        processor_factory,
        mock_dlp_adapter,
        mock_storage_adapter,
        mock_cache_adapter,
        mock_event_producer,
    ):
        """Test that retryable errors trigger retry logic."""
        # Track call count
        call_count = [0]

        def mock_process(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] < 3:
                raise StorageError("Temporary failure")
            return ProcessorResult(
                extracted_text="Success after retry",
                struct_data={},
                confidence_score=0.9,
                processing_time_ms=100,
            )

        # Create processor with custom behavior
        processor = MockContentProcessor()
        processor.process = mock_process
        factory = ProcessorFactory([processor])

        service = CurationService(
            processor_factory=factory,
            dlp=mock_dlp_adapter,
            storage=mock_storage_adapter,
            cache=mock_cache_adapter,
            producer=mock_event_producer,
            output_topic="rag-sync-ready-topic",
            dlq_topic="curation-dlq",
            output_bucket="curated-content",
        )

        event = CurationEvent(
            event_id=uuid4(),
            trace_id=uuid4(),
            tenant_id=SAMPLE_TENANT_ID,
            file_id=uuid4(),
            raw_gcs_uri="gs://bucket/file.pdf",
            mime_type="application/pdf",
            content_type=ContentType.DOCUMENT,
            source_service="test",
            timestamp=datetime.now(timezone.utc),
        )

        with patch.object(service, "process_event") as mock_process_event:
            mock_process_event.side_effect = [
                StorageError("Retry 1"),
                StorageError("Retry 2"),
                MagicMock(spec=CuratedDocument),
            ]

            result = service.process_with_retry(
                event, max_retries=3, backoff_seconds=0.01
            )

            assert result is not None
            assert mock_process_event.call_count == 3

    def test_no_retry_on_non_retryable_error(
        self,
        curation_service,
    ):
        """Test that non-retryable errors don't trigger retry."""
        event = CurationEvent(
            event_id=uuid4(),
            trace_id=uuid4(),
            tenant_id=SAMPLE_TENANT_ID,
            file_id=uuid4(),
            raw_gcs_uri="gs://bucket/file.xyz",
            mime_type="application/x-unknown",
            content_type=ContentType.DOCUMENT,
            source_service="test",
            timestamp=datetime.now(timezone.utc),
        )

        with patch.object(curation_service, "process_event") as mock_process_event:
            mock_process_event.side_effect = ProcessorNotFoundError("No processor")

            result = curation_service.process_with_retry(event, max_retries=3)

            assert result is None
            # Should only be called once (no retries)
            assert mock_process_event.call_count == 1

    def test_sends_to_dlq_after_max_retries(
        self,
        curation_service,
        mock_event_producer,
    ):
        """Test that event is sent to DLQ after max retries."""
        event = CurationEvent(
            event_id=uuid4(),
            trace_id=uuid4(),
            tenant_id=SAMPLE_TENANT_ID,
            file_id=uuid4(),
            raw_gcs_uri="gs://bucket/file.pdf",
            mime_type="application/pdf",
            content_type=ContentType.DOCUMENT,
            source_service="test",
            timestamp=datetime.now(timezone.utc),
        )

        with patch.object(curation_service, "process_event") as mock_process_event:
            mock_process_event.side_effect = StorageError("Always fails")

            result = curation_service.process_with_retry(
                event, max_retries=2, backoff_seconds=0.01
            )

            assert result is None

            # Check DLQ event was published
            dlq_events = [
                e
                for e in mock_event_producer.published_events
                if e["topic"] == "curation-dlq"
            ]
            assert len(dlq_events) >= 1


class TestCurationServiceGetStatus:
    """Tests for CurationService.get_status()."""

    def test_get_existing_status(
        self,
        curation_service,
        sample_curation_event,
        mock_cache_adapter,
    ):
        """Test getting status for a processed event."""
        # Process the event first
        curation_service.process_event(sample_curation_event)

        # Get status
        status = curation_service.get_status(sample_curation_event.trace_id)

        assert status is not None
        assert status.status == CurationStatus.CURATED
        assert status.trace_id == sample_curation_event.trace_id

    def test_get_nonexistent_status_returns_none(
        self,
        curation_service,
    ):
        """Test getting status for unknown trace_id returns None."""
        unknown_trace_id = uuid4()
        status = curation_service.get_status(unknown_trace_id)

        assert status is None


class TestCurationServiceTenantConfig:
    """Tests for tenant configuration handling."""

    def test_uses_default_config_when_not_found(
        self,
        curation_service,
        sample_curation_event,
        mock_cache_adapter,
    ):
        """Test that default config is used when tenant config not found."""
        # Don't set any tenant config
        result = curation_service.process_event(sample_curation_event)

        # Should still process successfully with defaults
        assert result is not None

    def test_uses_tenant_specific_config(
        self,
        processor_factory,
        sample_curation_event,
        mock_storage_adapter,
        mock_event_producer,
    ):
        """Test that tenant-specific config is used when available."""
        import asyncio

        # Create fresh mock adapters
        mock_dlp = MockDLPAdapter(should_redact=True)
        mock_cache = MockCacheAdapter()

        # Set up custom tenant config
        custom_config = TenantConfig(
            tenant_id=sample_curation_event.tenant_id,
            dlp_enabled=True,
            dlp_info_types=["CREDIT_CARD_NUMBER"],
            ai_model="gemini-1.5-pro",
        )
        loop = asyncio.new_event_loop()
        loop.run_until_complete(
            mock_cache.set_tenant_config(
                sample_curation_event.tenant_id,
                custom_config,
            )
        )
        loop.close()

        service = CurationService(
            processor_factory=processor_factory,
            dlp=mock_dlp,
            storage=mock_storage_adapter,
            cache=mock_cache,
            producer=mock_event_producer,
            output_topic="rag-sync-ready-topic",
            dlq_topic="curation-dlq",
            output_bucket="curated-content",
        )

        service.process_event(sample_curation_event)

        # Verify the custom DLP config was passed as tenant_config
        if mock_dlp.redact_calls:
            tenant_config = mock_dlp.redact_calls[0]["tenant_config"]
            assert tenant_config.dlp_info_types == ["CREDIT_CARD_NUMBER"]
