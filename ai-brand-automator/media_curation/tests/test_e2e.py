"""
End-to-End Tests for Media Curation Service.

Tests the complete curation pipeline from event to output.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock, AsyncMock
from uuid import uuid4, UUID

from media_curation.domain.models import (
    CurationEvent,
    CurationStatus,
    ContentType,
)
from media_curation.ports.dlp_port import RedactionResult
from media_curation.ports.storage_port import FileInfo


def run_async(coro):
    """Run async coroutine synchronously."""
    import asyncio

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TestFullPipelineE2E:
    """End-to-end tests for the complete curation pipeline."""

    @pytest.fixture
    def mock_service(self):
        """Create a mock CurationService for E2E testing."""
        from media_curation.domain.services import CurationService, ProcessorFactory
        from media_curation.domain.models import ProcessorResult

        # Create mock ProcessorResult
        mock_result = ProcessorResult(
            extracted_text="Test content extracted from document",
            confidence_score=0.95,
            processing_time_ms=100,
            language_code="en",
        )

        # Create mock dependencies
        mock_processor = MagicMock()
        mock_processor.content_type = ContentType.DOCUMENT
        mock_processor.process = AsyncMock(return_value=mock_result)

        mock_factory = MagicMock(spec=ProcessorFactory)
        mock_factory.get_processor = MagicMock(return_value=mock_processor)

        mock_dlp = MagicMock()
        mock_dlp.redact_pii = AsyncMock(
            return_value=RedactionResult(
                original_text="Test content extracted from document",
                redacted_text="Test content extracted from document",
                findings=[],
                findings_count=0,
                redaction_applied=False,
            )
        )

        mock_storage = MagicMock()
        mock_storage.download = AsyncMock(return_value=b"Test content")
        mock_storage.upload_from_bytes = AsyncMock(
            return_value=FileInfo(
                path="gs://curated-bucket/curated/output.json",
                bucket="curated-bucket",
                name="curated/output.json",
                size_bytes=100,
                content_type="application/json",
            )
        )

        mock_cache = MagicMock()
        mock_cache.set_status = AsyncMock()
        mock_cache.get_tenant_config = AsyncMock(return_value=None)

        mock_producer = MagicMock()
        mock_producer.send_async = AsyncMock()
        mock_producer.publish_raw = AsyncMock()

        service = CurationService(
            processor_factory=mock_factory,
            dlp=mock_dlp,
            storage=mock_storage,
            cache=mock_cache,
            producer=mock_producer,
            output_topic="rag-sync-ready-topic",
            dlq_topic="curation-dlq-topic",
            output_bucket="curated-bucket",
        )

        return {
            "service": service,
            "factory": mock_factory,
            "processor": mock_processor,
            "dlp": mock_dlp,
            "storage": mock_storage,
            "cache": mock_cache,
            "producer": mock_producer,
        }

    def test_pdf_document_full_pipeline(self, mock_service):
        """Test complete pipeline for PDF document curation."""
        event = CurationEvent(
            event_id=uuid4(),
            trace_id=uuid4(),
            tenant_id=str(uuid4()),
            file_id=uuid4(),
            raw_gcs_uri="gs://test-bucket/document.pdf",
            mime_type="application/pdf",
            content_type=ContentType.DOCUMENT,
        )

        service = mock_service["service"]
        document = service.process_event(event)

        assert document is not None
        assert document.trace_id == event.trace_id
        assert document.status == CurationStatus.CURATED
        assert len(document.extracted_text) > 0

    def test_image_file_full_pipeline(self, mock_service):
        """Test complete pipeline for image file curation."""
        # Update mock processor for image type
        mock_service["processor"].content_type = ContentType.IMAGE

        event = CurationEvent(
            event_id=uuid4(),
            trace_id=uuid4(),
            tenant_id=str(uuid4()),
            file_id=uuid4(),
            raw_gcs_uri="gs://test-bucket/image.jpg",
            mime_type="image/jpeg",
            content_type=ContentType.IMAGE,
        )

        service = mock_service["service"]
        document = service.process_event(event)

        assert document is not None
        assert document.status == CurationStatus.CURATED

    def test_video_file_full_pipeline(self, mock_service):
        """Test complete pipeline for video file curation."""
        mock_service["processor"].content_type = ContentType.VIDEO

        event = CurationEvent(
            event_id=uuid4(),
            trace_id=uuid4(),
            tenant_id=str(uuid4()),
            file_id=uuid4(),
            raw_gcs_uri="gs://test-bucket/video.mp4",
            mime_type="video/mp4",
            content_type=ContentType.VIDEO,
        )

        service = mock_service["service"]
        document = service.process_event(event)

        assert document is not None
        assert document.status == CurationStatus.CURATED

    def test_audio_file_full_pipeline(self, mock_service):
        """Test complete pipeline for audio file curation."""
        mock_service["processor"].content_type = ContentType.AUDIO

        event = CurationEvent(
            event_id=uuid4(),
            trace_id=uuid4(),
            tenant_id=str(uuid4()),
            file_id=uuid4(),
            raw_gcs_uri="gs://test-bucket/audio.mp3",
            mime_type="audio/mpeg",
            content_type=ContentType.AUDIO,
        )

        service = mock_service["service"]
        document = service.process_event(event)

        assert document is not None
        assert document.status == CurationStatus.CURATED

    def test_text_file_full_pipeline(self, mock_service):
        """Test complete pipeline for text file curation."""
        mock_service["processor"].content_type = ContentType.TEXT

        event = CurationEvent(
            event_id=uuid4(),
            trace_id=uuid4(),
            tenant_id=str(uuid4()),
            file_id=uuid4(),
            raw_gcs_uri="gs://test-bucket/text.txt",
            mime_type="text/plain",
            content_type=ContentType.TEXT,
        )

        service = mock_service["service"]
        document = service.process_event(event)

        assert document is not None
        assert document.status == CurationStatus.CURATED

    def test_pipeline_status_progression(self, mock_service):
        """Test that status progresses correctly through pipeline."""
        event = CurationEvent(
            event_id=uuid4(),
            trace_id=uuid4(),
            tenant_id=str(uuid4()),
            file_id=uuid4(),
            raw_gcs_uri="gs://test-bucket/document.pdf",
            mime_type="application/pdf",
            content_type=ContentType.DOCUMENT,
        )

        service = mock_service["service"]
        document = service.process_event(event)

        # Verify status was updated during processing
        cache = mock_service["cache"]
        assert cache.set_status.call_count >= 1

        # Final status should be CURATED
        assert document.status == CurationStatus.CURATED

    def test_pipeline_publishes_success_event(self, mock_service):
        """Test that success event is published after processing."""
        event = CurationEvent(
            event_id=uuid4(),
            trace_id=uuid4(),
            tenant_id=str(uuid4()),
            file_id=uuid4(),
            raw_gcs_uri="gs://test-bucket/document.pdf",
            mime_type="application/pdf",
            content_type=ContentType.DOCUMENT,
        )

        service = mock_service["service"]
        _document = service.process_event(event)  # noqa: F841

        # Verify Kafka event was sent
        producer = mock_service["producer"]
        assert producer.publish_raw.called

    def test_pipeline_saves_to_storage(self, mock_service):
        """Test that curated document is saved to storage."""
        event = CurationEvent(
            event_id=uuid4(),
            trace_id=uuid4(),
            tenant_id=str(uuid4()),
            file_id=uuid4(),
            raw_gcs_uri="gs://test-bucket/document.pdf",
            mime_type="application/pdf",
            content_type=ContentType.DOCUMENT,
        )

        service = mock_service["service"]
        _document = service.process_event(event)  # noqa: F841

        # Verify document was uploaded
        storage = mock_service["storage"]
        assert storage.upload_from_bytes.called

    def test_pipeline_handles_processing_error(self, mock_service):
        """Test that pipeline handles processing errors gracefully."""
        from media_curation.domain.exceptions import NonRetryableError

        # Make processor raise error
        mock_service["processor"].process = AsyncMock(
            side_effect=NonRetryableError("Processing failed")
        )

        event = CurationEvent(
            event_id=uuid4(),
            trace_id=uuid4(),
            tenant_id=str(uuid4()),
            file_id=uuid4(),
            raw_gcs_uri="gs://test-bucket/invalid.xyz",
            mime_type="application/octet-stream",
            content_type=ContentType.UNKNOWN,
        )

        service = mock_service["service"]

        with pytest.raises((NonRetryableError, Exception)):
            service.process_event(event)

    def test_pipeline_with_metadata(self, mock_service):
        """Test pipeline preserves event metadata."""
        metadata = {"source": "upload", "user_id": "user123", "campaign": "test"}

        event = CurationEvent(
            event_id=uuid4(),
            trace_id=uuid4(),
            tenant_id=str(uuid4()),
            file_id=uuid4(),
            raw_gcs_uri="gs://test-bucket/document.pdf",
            mime_type="application/pdf",
            content_type=ContentType.DOCUMENT,
            metadata=metadata,
        )

        service = mock_service["service"]
        document = service.process_event(event)

        assert document is not None
        # Document should be created successfully
        assert document.status == CurationStatus.CURATED


class TestAPIToProcessingE2E:
    """End-to-end tests from API to processing."""

    # authenticated_client fixture comes from the global conftest.py
    # (uses a real Django User instance required by TenantMembershipMiddleware).

    @pytest.mark.django_db
    def test_api_to_task_submission(self, authenticated_client):
        """Test that API correctly submits to Celery task."""
        with patch("media_curation.tasks.process_curation_event") as mock_task:
            mock_task.delay = MagicMock()

            response = authenticated_client.post(
                "/api/v1/curation/",
                data={
                    "tenant_id": str(uuid4()),
                    "source_path": "gs://test-bucket/file.pdf",
                    "file_type": "application/pdf",
                },
                format="json",
            )

            assert response.status_code == 202
            assert mock_task.delay.called

            # Verify task arguments
            call_kwargs = mock_task.delay.call_args.kwargs
            assert "event_id" in call_kwargs
            assert "trace_id" in call_kwargs
            assert call_kwargs["source_path"] == "gs://test-bucket/file.pdf"

    @pytest.mark.django_db
    def test_batch_api_to_multiple_tasks(self, authenticated_client):
        """Test that batch API submits multiple Celery tasks."""
        with patch("media_curation.tasks.process_curation_event") as mock_task:
            mock_task.delay = MagicMock()

            tenant_id = str(uuid4())
            response = authenticated_client.post(
                "/api/v1/curation/batch/",
                data={
                    "events": [
                        {
                            "tenant_id": tenant_id,
                            "source_path": f"gs://test-bucket/file{i}.pdf",
                            "file_type": "application/pdf",
                        }
                        for i in range(5)
                    ]
                },
                format="json",
            )

            assert response.status_code == 202
            assert mock_task.delay.call_count == 5

            data = response.json()
            assert data["accepted"] == 5
            assert len(data["results"]) == 5

    @pytest.mark.django_db
    def test_status_check_after_processing(self, authenticated_client):
        """Test status check returns correct status after processing."""
        from media_curation.domain.models import CurationStatusRecord, CurationStatus

        trace_id = str(uuid4())

        mock_status = CurationStatusRecord(
            trace_id=UUID(trace_id),
            event_id=uuid4(),
            tenant_id=str(uuid4()),
            file_id=uuid4(),
            status=CurationStatus.CURATED,
            message="Processing complete",
            output_gcs_uri="gs://curated/output.json",
            updated_at=datetime.now(timezone.utc),
        )

        with patch("media_curation.factory.create_cache_adapter") as mock_cache_factory:
            mock_cache = MagicMock()
            mock_cache.get_status = AsyncMock(return_value=mock_status)
            mock_cache_factory.return_value = mock_cache

            response = authenticated_client.get(f"/api/v1/curation/status/{trace_id}/")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "curated"
            assert data["destination_path"] == "gs://curated/output.json"
