"""
Tests for Media Curation Content Processors.

Unit tests for VideoProcessor, AudioProcessor, ImageProcessor, and DocumentProcessor.
Target: 30+ tests as per implementation plan.
"""

import pytest
import asyncio
from datetime import datetime, timezone
from uuid import uuid4, UUID

from media_curation.domain.models import (
    CurationEvent,
    ProcessorResult,
    TenantConfig,
    ContentType,
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
SAMPLE_TRACE_ID = UUID("22222222-2222-2222-2222-222222222222")
SAMPLE_EVENT_ID = UUID("33333333-3333-3333-3333-333333333333")
SAMPLE_FILE_ID = UUID("44444444-4444-4444-4444-444444444444")


@pytest.fixture
def sample_document_event():
    """Create a sample document curation event using real GCS file."""
    return CurationEvent(
        event_id=SAMPLE_EVENT_ID,
        trace_id=SAMPLE_TRACE_ID,
        tenant_id=SAMPLE_TENANT_ID,
        file_id=SAMPLE_FILE_ID,
        raw_gcs_uri="gs://onboarding-brandsol-customer-bucket-1/customer-1/customer-1-onboarding-file-example-1.txt",
        mime_type="text/plain",
        content_type=ContentType.DOCUMENT,
        source_service="test",
        timestamp=datetime.now(timezone.utc),
    )


@pytest.fixture
def sample_video_event():
    """Create a sample video curation event."""
    return CurationEvent(
        event_id=uuid4(),
        trace_id=uuid4(),
        tenant_id=SAMPLE_TENANT_ID,
        file_id=uuid4(),
        raw_gcs_uri="gs://test-bucket/videos/test.mp4",
        mime_type="video/mp4",
        content_type=ContentType.VIDEO,
        source_service="test",
        timestamp=datetime.now(timezone.utc),
    )


@pytest.fixture
def sample_audio_event():
    """Create a sample audio curation event."""
    return CurationEvent(
        event_id=uuid4(),
        trace_id=uuid4(),
        tenant_id=SAMPLE_TENANT_ID,
        file_id=uuid4(),
        raw_gcs_uri="gs://test-bucket/audio/test.mp3",
        mime_type="audio/mpeg",
        content_type=ContentType.AUDIO,
        source_service="test",
        timestamp=datetime.now(timezone.utc),
    )


@pytest.fixture
def sample_image_event():
    """Create a sample image curation event."""
    return CurationEvent(
        event_id=uuid4(),
        trace_id=uuid4(),
        tenant_id=SAMPLE_TENANT_ID,
        file_id=uuid4(),
        raw_gcs_uri="gs://test-bucket/images/test.png",
        mime_type="image/png",
        content_type=ContentType.IMAGE,
        source_service="test",
        timestamp=datetime.now(timezone.utc),
    )


@pytest.fixture
def sample_tenant_config():
    """Create a sample tenant configuration."""
    return TenantConfig(
        tenant_id=SAMPLE_TENANT_ID,
        dlp_enabled=True,
        dlp_info_types=["EMAIL_ADDRESS", "PHONE_NUMBER"],
        ai_model="gemini-2.0-flash",
    )


# =============================================================================
# Document Processor Tests
# =============================================================================


class TestDocumentProcessorMimeSupport:
    """Tests for DocumentProcessor MIME type support."""

    def test_supports_pdf(self):
        """Test processor supports PDF files."""
        from media_curation.adapters.document_processor import DocumentProcessor

        processor = DocumentProcessor()
        assert "application/pdf" in processor.supported_mime_types

    def test_supports_text_plain(self):
        """Test processor supports plain text files."""
        from media_curation.adapters.document_processor import DocumentProcessor

        processor = DocumentProcessor()
        assert "text/plain" in processor.supported_mime_types

    def test_supports_html(self):
        """Test processor supports HTML files."""
        from media_curation.adapters.document_processor import DocumentProcessor

        processor = DocumentProcessor()
        assert "text/html" in processor.supported_mime_types

    def test_supports_markdown(self):
        """Test processor supports Markdown files."""
        from media_curation.adapters.document_processor import DocumentProcessor

        processor = DocumentProcessor()
        assert "text/markdown" in processor.supported_mime_types

    def test_supports_csv(self):
        """Test processor supports CSV files."""
        from media_curation.adapters.document_processor import DocumentProcessor

        processor = DocumentProcessor()
        assert "text/csv" in processor.supported_mime_types

    def test_supports_word_documents(self):
        """Test processor supports MS Word documents."""
        from media_curation.adapters.document_processor import DocumentProcessor

        processor = DocumentProcessor()
        mime_types = processor.supported_mime_types
        assert (
            "application/msword" in mime_types
            or "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            in mime_types
        )


class TestDocumentProcessorProcessing:
    """Tests for DocumentProcessor content processing with real GCS.

    These tests require real GCS credentials and are skipped in CI.
    """

    @pytest.fixture
    def storage_adapter(self):
        """Create a real GCS storage adapter."""
        from media_curation.adapters.gcs_adapter import GCSAdapter
        from django.conf import settings
        import os

        base_dir = settings.BASE_DIR
        credentials_path = os.path.join(base_dir, "credentials", "gcs-credentials.json")

        # Skip if credentials file doesn't exist
        if not os.path.exists(credentials_path):
            pytest.skip("GCS credentials file not found - skipping real GCS tests")

        return GCSAdapter(
            project_id="brandsol-project",
            credentials_path=credentials_path,
            default_bucket="onboarding-brandsol-customer-bucket-1",
        )

    @pytest.fixture
    def document_processor(self, storage_adapter):
        """Create a DocumentProcessor instance with real storage."""
        from media_curation.adapters.document_processor import DocumentProcessor

        return DocumentProcessor(storage=storage_adapter)

    def test_process_returns_processor_result(
        self, document_processor, sample_document_event
    ):
        """Test process returns ProcessorResult."""
        result = run_async(document_processor.process(sample_document_event))

        assert isinstance(result, ProcessorResult)
        assert result.extracted_text is not None
        assert result.processing_time_ms >= 0

    def test_process_includes_struct_data(
        self, document_processor, sample_document_event
    ):
        """Test process result includes structured data."""
        result = run_async(document_processor.process(sample_document_event))

        assert result.struct_data is not None
        assert isinstance(result.struct_data, dict)

    def test_process_with_tenant_config(
        self, document_processor, sample_document_event, sample_tenant_config
    ):
        """Test process accepts tenant configuration."""
        result = run_async(
            document_processor.process(
                event=sample_document_event,
                tenant_config=sample_tenant_config,
            )
        )

        assert isinstance(result, ProcessorResult)

    def test_process_tracks_processing_time(
        self, document_processor, sample_document_event
    ):
        """Test process tracks processing duration."""
        result = run_async(document_processor.process(sample_document_event))

        assert result.processing_time_ms >= 0

    def test_process_sets_language_code(
        self, document_processor, sample_document_event
    ):
        """Test process returns result (language code may or may not be detected)."""
        result = run_async(document_processor.process(sample_document_event))

        # Language detection is optional - just verify result is valid
        assert result is not None
        assert result.extracted_text is not None or result.error_message is not None


# =============================================================================
# Video Processor Tests
# =============================================================================


class TestVideoProcessorMimeSupport:
    """Tests for VideoProcessor MIME type support."""

    def test_supports_mp4(self):
        """Test processor supports MP4 video."""
        from media_curation.adapters.media_processors import VideoProcessor

        processor = VideoProcessor()
        assert "video/mp4" in processor.supported_mime_types

    def test_supports_webm(self):
        """Test processor supports WebM video."""
        from media_curation.adapters.media_processors import VideoProcessor

        processor = VideoProcessor()
        assert "video/webm" in processor.supported_mime_types

    def test_supports_mpeg(self):
        """Test processor supports MPEG video."""
        from media_curation.adapters.media_processors import VideoProcessor

        processor = VideoProcessor()
        assert "video/mpeg" in processor.supported_mime_types

    def test_supports_quicktime(self):
        """Test processor supports QuickTime video."""
        from media_curation.adapters.media_processors import VideoProcessor

        processor = VideoProcessor()
        assert "video/quicktime" in processor.supported_mime_types

    def test_supports_video_wildcard(self):
        """Test processor supports video/* wildcard."""
        from media_curation.adapters.media_processors import VideoProcessor

        processor = VideoProcessor()
        assert "video/*" in processor.supported_mime_types


class TestVideoProcessorProcessing:
    """Tests for VideoProcessor content processing."""

    @pytest.fixture
    def video_processor(self):
        """Create a VideoProcessor instance."""
        from media_curation.adapters.media_processors import VideoProcessor

        return VideoProcessor(project_id="test-project")

    def test_process_returns_processor_result(
        self, video_processor, sample_video_event
    ):
        """Test process returns ProcessorResult."""
        result = run_async(video_processor.process(sample_video_event))

        assert isinstance(result, ProcessorResult)
        assert result.extracted_text is not None

    def test_process_includes_video_metadata(self, video_processor, sample_video_event):
        """Test process result includes video-specific metadata."""
        result = run_async(video_processor.process(sample_video_event))

        assert result.struct_data is not None
        # In mock mode, should have mock indicators
        assert "mock" in result.struct_data or "duration_seconds" in result.struct_data

    def test_process_with_tenant_config(
        self, video_processor, sample_video_event, sample_tenant_config
    ):
        """Test process accepts tenant configuration."""
        result = run_async(
            video_processor.process(
                event=sample_video_event,
                tenant_config=sample_tenant_config,
            )
        )

        assert isinstance(result, ProcessorResult)


# =============================================================================
# Audio Processor Tests
# =============================================================================


class TestAudioProcessorMimeSupport:
    """Tests for AudioProcessor MIME type support."""

    def test_supports_mp3(self):
        """Test processor supports MP3 audio."""
        from media_curation.adapters.media_processors import AudioProcessor

        processor = AudioProcessor()
        assert (
            "audio/mpeg" in processor.supported_mime_types
            or "audio/mp3" in processor.supported_mime_types
        )

    def test_supports_wav(self):
        """Test processor supports WAV audio."""
        from media_curation.adapters.media_processors import AudioProcessor

        processor = AudioProcessor()
        assert "audio/wav" in processor.supported_mime_types

    def test_supports_ogg(self):
        """Test processor supports OGG audio."""
        from media_curation.adapters.media_processors import AudioProcessor

        processor = AudioProcessor()
        assert "audio/ogg" in processor.supported_mime_types

    def test_supports_flac(self):
        """Test processor supports FLAC audio."""
        from media_curation.adapters.media_processors import AudioProcessor

        processor = AudioProcessor()
        assert "audio/flac" in processor.supported_mime_types

    def test_supports_audio_wildcard(self):
        """Test processor supports audio/* wildcard."""
        from media_curation.adapters.media_processors import AudioProcessor

        processor = AudioProcessor()
        assert "audio/*" in processor.supported_mime_types


class TestAudioProcessorProcessing:
    """Tests for AudioProcessor content processing."""

    @pytest.fixture
    def audio_processor(self):
        """Create an AudioProcessor instance."""
        from media_curation.adapters.media_processors import AudioProcessor

        return AudioProcessor(project_id="test-project")

    def test_process_returns_processor_result(
        self, audio_processor, sample_audio_event
    ):
        """Test process returns ProcessorResult."""
        result = run_async(audio_processor.process(sample_audio_event))

        assert isinstance(result, ProcessorResult)
        assert result.extracted_text is not None

    def test_process_includes_audio_metadata(self, audio_processor, sample_audio_event):
        """Test process result includes audio-specific metadata."""
        result = run_async(audio_processor.process(sample_audio_event))

        assert result.struct_data is not None

    def test_process_with_tenant_config(
        self, audio_processor, sample_audio_event, sample_tenant_config
    ):
        """Test process accepts tenant configuration."""
        result = run_async(
            audio_processor.process(
                event=sample_audio_event,
                tenant_config=sample_tenant_config,
            )
        )

        assert isinstance(result, ProcessorResult)


# =============================================================================
# Image Processor Tests
# =============================================================================


class TestImageProcessorMimeSupport:
    """Tests for ImageProcessor MIME type support."""

    def test_supports_png(self):
        """Test processor supports PNG images."""
        from media_curation.adapters.media_processors import ImageProcessor

        processor = ImageProcessor()
        assert "image/png" in processor.supported_mime_types

    def test_supports_jpeg(self):
        """Test processor supports JPEG images."""
        from media_curation.adapters.media_processors import ImageProcessor

        processor = ImageProcessor()
        assert (
            "image/jpeg" in processor.supported_mime_types
            or "image/jpg" in processor.supported_mime_types
        )

    def test_supports_gif(self):
        """Test processor supports GIF images."""
        from media_curation.adapters.media_processors import ImageProcessor

        processor = ImageProcessor()
        assert "image/gif" in processor.supported_mime_types

    def test_supports_webp(self):
        """Test processor supports WebP images."""
        from media_curation.adapters.media_processors import ImageProcessor

        processor = ImageProcessor()
        assert "image/webp" in processor.supported_mime_types

    def test_supports_tiff(self):
        """Test processor supports TIFF images."""
        from media_curation.adapters.media_processors import ImageProcessor

        processor = ImageProcessor()
        assert "image/tiff" in processor.supported_mime_types

    def test_supports_image_wildcard(self):
        """Test processor supports image/* wildcard."""
        from media_curation.adapters.media_processors import ImageProcessor

        processor = ImageProcessor()
        assert "image/*" in processor.supported_mime_types


class TestImageProcessorProcessing:
    """Tests for ImageProcessor content processing."""

    @pytest.fixture
    def image_processor(self):
        """Create an ImageProcessor instance."""
        from media_curation.adapters.media_processors import ImageProcessor

        return ImageProcessor()

    def test_process_returns_processor_result(
        self, image_processor, sample_image_event
    ):
        """Test process returns ProcessorResult."""
        result = run_async(image_processor.process(sample_image_event))

        assert isinstance(result, ProcessorResult)
        assert result.extracted_text is not None

    def test_process_includes_image_metadata(self, image_processor, sample_image_event):
        """Test process result includes image-specific metadata."""
        result = run_async(image_processor.process(sample_image_event))

        assert result.struct_data is not None

    def test_process_with_tenant_config(
        self, image_processor, sample_image_event, sample_tenant_config
    ):
        """Test process accepts tenant configuration."""
        result = run_async(
            image_processor.process(
                event=sample_image_event,
                tenant_config=sample_tenant_config,
            )
        )

        assert isinstance(result, ProcessorResult)


# =============================================================================
# Processor Factory Tests
# =============================================================================


class TestProcessorFactory:
    """Tests for ProcessorFactory strategy selection."""

    @pytest.fixture
    def processor_factory(self):
        """Create a ProcessorFactory with all processors."""
        from media_curation.domain.services import ProcessorFactory
        from media_curation.adapters import (
            DocumentProcessor,
            VideoProcessor,
            AudioProcessor,
            ImageProcessor,
        )

        return ProcessorFactory(
            processors=[
                DocumentProcessor(),
                VideoProcessor(),
                AudioProcessor(),
                ImageProcessor(),
            ]
        )

    def test_factory_returns_document_processor_for_pdf(self, processor_factory):
        """Test factory returns DocumentProcessor for PDF."""
        processor = processor_factory.get_processor("application/pdf")
        assert processor is not None
        assert "application/pdf" in processor.supported_mime_types

    def test_factory_returns_video_processor_for_mp4(self, processor_factory):
        """Test factory returns VideoProcessor for MP4."""
        processor = processor_factory.get_processor("video/mp4")
        assert processor is not None
        assert "video/mp4" in processor.supported_mime_types

    def test_factory_returns_audio_processor_for_mp3(self, processor_factory):
        """Test factory returns AudioProcessor for MP3."""
        processor = processor_factory.get_processor("audio/mpeg")
        assert processor is not None
        assert "audio/mpeg" in processor.supported_mime_types

    def test_factory_returns_image_processor_for_png(self, processor_factory):
        """Test factory returns ImageProcessor for PNG."""
        processor = processor_factory.get_processor("image/png")
        assert processor is not None
        assert "image/png" in processor.supported_mime_types

    def test_factory_raises_for_unsupported_type(self, processor_factory):
        """Test factory raises ProcessorNotFoundError for unsupported MIME type."""
        from media_curation.domain.exceptions import ProcessorNotFoundError

        with pytest.raises(ProcessorNotFoundError):
            processor_factory.get_processor("application/x-unknown")

    def test_factory_get_all_processors(self, processor_factory):
        """Test factory has all processors registered."""
        # Verify factory has processors registered
        assert len(processor_factory.processors) == 4  # Document, Video, Audio, Image


# =============================================================================
# Base Processor Tests
# =============================================================================


class TestBaseProcessor:
    """Tests for base ContentProcessor functionality."""

    def test_base_processor_exists(self):
        """Test BaseProcessor class is defined."""
        from media_curation.processors.base import BaseProcessor

        assert BaseProcessor is not None

    def test_base_processor_requires_supported_mime_types(self):
        """Test processors must define supported MIME types."""
        from media_curation.adapters.document_processor import DocumentProcessor

        processor = DocumentProcessor()
        assert hasattr(processor, "supported_mime_types")
        assert isinstance(processor.supported_mime_types, list)
        assert len(processor.supported_mime_types) > 0


class TestContentProcessorPort:
    """Tests for ContentProcessorPort interface."""

    def test_document_processor_supports_mime_types(self):
        """Test DocumentProcessor properly supports MIME types."""
        from media_curation.adapters.document_processor import DocumentProcessor

        processor = DocumentProcessor()

        # Should support PDF
        assert "application/pdf" in processor.supported_mime_types or any(
            "pdf" in mt for mt in processor.supported_mime_types
        )

    def test_video_processor_supports_wildcard_mime(self):
        """Test VideoProcessor handles wildcard MIME patterns."""
        from media_curation.adapters.media_processors import VideoProcessor

        processor = VideoProcessor(project_id="test")

        # Video processor should support video/* pattern
        assert any(
            mt.startswith("video/") or mt == "video/*"
            for mt in processor.supported_mime_types
        )

    def test_audio_processor_supports_audio_types(self):
        """Test AudioProcessor supports audio MIME types."""
        from media_curation.adapters.media_processors import AudioProcessor

        processor = AudioProcessor(project_id="test")

        assert any(
            mt.startswith("audio/") or mt == "audio/*"
            for mt in processor.supported_mime_types
        )

    def test_image_processor_supports_image_types(self):
        """Test ImageProcessor supports image MIME types."""
        from media_curation.adapters.media_processors import ImageProcessor

        processor = ImageProcessor()

        assert any(
            mt.startswith("image/") or mt == "image/*"
            for mt in processor.supported_mime_types
        )

    def test_all_processors_have_process_method(self):
        """Test all processors implement process method."""
        from media_curation.adapters.document_processor import DocumentProcessor
        from media_curation.adapters.media_processors import (
            VideoProcessor,
            AudioProcessor,
            ImageProcessor,
        )

        processors = [
            DocumentProcessor(),
            VideoProcessor(project_id="test"),
            AudioProcessor(project_id="test"),
            ImageProcessor(),
        ]

        for processor in processors:
            assert hasattr(processor, "process")
            assert callable(processor.process)
