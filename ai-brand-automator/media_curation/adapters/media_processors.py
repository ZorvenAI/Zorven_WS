"""
Video Processor - AI-powered video content extraction.

Handles video MIME types using Vertex AI Video Intelligence API.
"""

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from django.conf import settings

from media_curation.ports.ai_port import ContentProcessorPort
from media_curation.domain.models import (
    CurationEvent,
    ProcessorResult,
    TenantConfig,
)
from media_curation.domain.exceptions import AIModelError


logger = logging.getLogger(__name__)

# Thread pool for async I/O operations
_executor = ThreadPoolExecutor(max_workers=2)


class VideoProcessor(ContentProcessorPort):
    """
    Video content processor using Vertex AI Video Intelligence.

    Handles video/* MIME types for transcription and analysis.
    """

    _SUPPORTED_MIME_TYPES = [
        "video/mp4",
        "video/webm",
        "video/mpeg",
        "video/quicktime",
        "video/x-msvideo",
        "video/*",  # Wildcard for any video type
    ]

    def __init__(
        self,
        project_id: Optional[str] = None,
        location: str = "us-central1",
        credentials_path: Optional[str] = None,
    ):
        """
        Initialize the video processor.

        Args:
            project_id: GCP project ID
            location: Vertex AI location
            credentials_path: Path to service account JSON
        """
        # Lazy import when google-cloud-videointelligence is not installed
        try:
            from google.cloud import videointelligence_v1

            self._video_ai_available = True
        except ImportError:
            self._video_ai_available = False
            logger.warning("google-cloud-videointelligence not installed")
            return

        self.project_id = project_id or getattr(settings, "GCP_PROJECT_ID", None)
        self.location = location

        if credentials_path:
            client_cls = videointelligence_v1.VideoIntelligenceServiceClient
            self.client = client_cls.from_service_account_json(credentials_path)
        else:
            # Use Application Default Credentials
            self.client = videointelligence_v1.VideoIntelligenceServiceClient()

        logger.info(
            "Video processor initialized",
            extra={"project_id": self.project_id, "location": location},
        )

    @property
    def supported_mime_types(self) -> list[str]:
        """Return list of MIME types this processor supports."""
        return self._SUPPORTED_MIME_TYPES

    async def process(
        self,
        event: CurationEvent,
        tenant_config: Optional[TenantConfig] = None,
    ) -> ProcessorResult:
        """Process video content and extract transcription/metadata."""
        start_time = time.time()

        if not self._video_ai_available:
            # Mock mode: return sample extraction
            mock_text = f"[Mock video transcription] Video from {event.raw_gcs_uri}"
            return ProcessorResult(
                extracted_text=mock_text,
                struct_data={
                    "duration_seconds": 120,
                    "has_audio": True,
                    "has_speech": True,
                    "mime_type": event.mime_type,
                    "mock": True,
                },
                confidence_score=0.0,
                processing_time_ms=int((time.time() - start_time) * 1000),
                language_code="en",
            )

        def _process():
            from google.cloud import videointelligence_v1 as vi

            try:
                # Configure features to extract
                features = [
                    vi.Feature.SPEECH_TRANSCRIPTION,
                    vi.Feature.LABEL_DETECTION,
                ]

                # Speech transcription config
                speech_config = vi.SpeechTranscriptionConfig(
                    language_code="en-US",
                    enable_automatic_punctuation=True,
                    enable_speaker_diarization=True,
                    diarization_speaker_count=2,
                )

                video_context = vi.VideoContext(
                    speech_transcription_config=speech_config,
                )

                # Start the async operation
                operation = self.client.annotate_video(
                    request={
                        "input_uri": event.raw_gcs_uri,
                        "features": features,
                        "video_context": video_context,
                    }
                )

                logger.info(
                    "Video processing started",
                    extra={"uri": event.raw_gcs_uri},
                )

                # Wait for operation to complete (with timeout)
                result = operation.result(timeout=600)  # 10 minute timeout

                # Extract transcription
                transcription_parts = []
                speech_annotations = []

                for annotation_result in result.annotation_results:
                    for speech in annotation_result.speech_transcriptions:
                        for alternative in speech.alternatives:
                            transcription_parts.append(alternative.transcript)
                            speech_annotations.append(
                                {
                                    "transcript": alternative.transcript,
                                    "confidence": alternative.confidence,
                                    "words": [
                                        {
                                            "word": word.word,
                                            "start_time": (
                                                word.start_time.total_seconds()
                                            ),
                                            "end_time": (word.end_time.total_seconds()),
                                            "speaker_tag": getattr(
                                                word, "speaker_tag", 0
                                            ),
                                        }
                                        for word in alternative.words
                                    ],
                                }
                            )

                # Extract labels
                labels = []
                for annotation_result in result.annotation_results:
                    for label in annotation_result.segment_label_annotations:
                        labels.append(
                            {
                                "description": label.entity.description,
                                "confidence": (
                                    max(seg.confidence for seg in label.segments)
                                    if label.segments
                                    else 0.0
                                ),
                            }
                        )

                # Build struct_data
                struct_data = {
                    "speech_transcriptions": speech_annotations,
                    "labels": labels,
                    "has_speech": len(transcription_parts) > 0,
                    "label_count": len(labels),
                }

                # Calculate average confidence
                confidences = [
                    alt.confidence
                    for ar in result.annotation_results
                    for speech in ar.speech_transcriptions
                    for alt in speech.alternatives
                    if alt.confidence > 0
                ]
                avg_confidence = (
                    sum(confidences) / len(confidences) if confidences else 0.5
                )

                return ProcessorResult(
                    extracted_text=" ".join(transcription_parts),
                    struct_data=struct_data,
                    confidence_score=avg_confidence,
                    processing_time_ms=int((time.time() - start_time) * 1000),
                    language_code="en",
                )

            except Exception as e:
                logger.error(f"Video processing error: {e}")
                raise AIModelError(f"Video processing failed: {e}")

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, _process)


class AudioProcessor(ContentProcessorPort):
    """
    Audio content processor using Speech-to-Text API.

    Handles audio/* MIME types for transcription.
    """

    _SUPPORTED_MIME_TYPES = [
        "audio/mpeg",
        "audio/mp3",
        "audio/wav",
        "audio/ogg",
        "audio/flac",
        "audio/webm",
        "audio/*",  # Wildcard for any audio type
    ]

    def __init__(
        self,
        project_id: Optional[str] = None,
        credentials_path: Optional[str] = None,
    ):
        """
        Initialize the audio processor.

        Args:
            project_id: GCP project ID
            credentials_path: Path to service account JSON
        """
        # Lazy import to avoid issues when google-cloud-speech is not installed
        try:
            from google.cloud import speech_v1

            self._speech_available = True
        except ImportError:
            self._speech_available = False
            logger.warning("google-cloud-speech not installed, using mock mode")
            return

        self.project_id = project_id or getattr(settings, "GCP_PROJECT_ID", None)

        if credentials_path:
            self.client = speech_v1.SpeechClient.from_service_account_json(
                credentials_path
            )
        else:
            self.client = speech_v1.SpeechClient()

        logger.info("Audio processor initialized")

    @property
    def supported_mime_types(self) -> list[str]:
        """Return list of MIME types this processor supports."""
        return self._SUPPORTED_MIME_TYPES

    async def process(
        self,
        event: CurationEvent,
        tenant_config: Optional[TenantConfig] = None,
    ) -> ProcessorResult:
        """Process audio content and extract transcription."""
        start_time = time.time()

        if not self._speech_available:
            # Mock mode: return sample transcription
            mock_text = f"[Mock audio transcription] Audio from {event.raw_gcs_uri}"
            return ProcessorResult(
                extracted_text=mock_text,
                struct_data={
                    "duration_seconds": 60,
                    "mime_type": event.mime_type,
                    "mock": True,
                },
                confidence_score=0.0,
                processing_time_ms=int((time.time() - start_time) * 1000),
                language_code="en",
            )

        def _process():
            from google.cloud import speech_v1

            try:
                # Configure recognition
                config = speech_v1.RecognitionConfig(
                    language_code="en-US",
                    enable_automatic_punctuation=True,
                    enable_word_time_offsets=True,
                    enable_speaker_diarization=True,
                    diarization_speaker_count=2,
                )

                audio = speech_v1.RecognitionAudio(uri=event.raw_gcs_uri)

                # Use long-running recognize for files > 1 minute
                operation = self.client.long_running_recognize(
                    config=config,
                    audio=audio,
                )

                logger.info(
                    "Audio transcription started",
                    extra={"uri": event.raw_gcs_uri},
                )

                # Wait for operation (timeout 10 minutes)
                response = operation.result(timeout=600)

                # Extract transcription
                transcripts = []
                word_info = []
                confidences = []

                for result in response.results:
                    alternative = result.alternatives[0]
                    transcripts.append(alternative.transcript)
                    confidences.append(alternative.confidence)

                    for word in alternative.words:
                        word_info.append(
                            {
                                "word": word.word,
                                "start_time": word.start_time.total_seconds(),
                                "end_time": word.end_time.total_seconds(),
                                "speaker_tag": getattr(word, "speaker_tag", 0),
                            }
                        )

                struct_data = {
                    "word_timestamps": word_info,
                    "result_count": len(response.results),
                }

                avg_confidence = (
                    sum(confidences) / len(confidences) if confidences else 0.5
                )

                return ProcessorResult(
                    extracted_text=" ".join(transcripts),
                    struct_data=struct_data,
                    confidence_score=avg_confidence,
                    processing_time_ms=int((time.time() - start_time) * 1000),
                    language_code="en",
                )

            except Exception as e:
                logger.error(f"Audio processing error: {e}")
                raise AIModelError(f"Audio processing failed: {e}")

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, _process)


class ImageProcessor(ContentProcessorPort):
    """
    Image content processor using Vision AI.

    Handles image/* MIME types for OCR and analysis.
    """

    _SUPPORTED_MIME_TYPES = [
        "image/png",
        "image/jpeg",
        "image/jpg",
        "image/gif",
        "image/webp",
        "image/tiff",
        "image/*",
    ]

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
    ):
        """
        Initialize the image processor.

        Args:
            api_key: Gemini API key
            model_name: Model to use
        """
        # Lazy import
        try:
            import google.generativeai as genai

            self._genai_available = True
        except ImportError:
            self._genai_available = False
            logger.warning("google-generativeai not installed, using mock mode")
            return

        ai_config = getattr(settings, "MEDIA_CURATION", {}).get("AI_MODEL", {})
        self.api_key = api_key or ai_config.get(
            "API_KEY", getattr(settings, "GOOGLE_API_KEY", None)
        )
        self.model_name = model_name or ai_config.get(
            "MODEL", ai_config.get("MODEL_NAME", "gemini-3.5-flash")
        )

        if self.api_key:
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel(self.model_name)
            logger.info(f"Image processor initialized with model: {self.model_name}")
        else:
            self._genai_available = False
            logger.warning("No GOOGLE_API_KEY found, using mock mode")

    @property
    def supported_mime_types(self) -> list[str]:
        """Return list of MIME types this processor supports."""
        return self._SUPPORTED_MIME_TYPES

    async def process(
        self,
        event: CurationEvent,
        tenant_config: Optional[TenantConfig] = None,
    ) -> ProcessorResult:
        """Process image content and extract text/metadata."""
        start_time = time.time()

        if not self._genai_available:
            return ProcessorResult(
                extracted_text=f"[Mock image analysis] Image from {event.raw_gcs_uri}",
                struct_data={
                    "mime_type": event.mime_type,
                    "mock": True,
                },
                confidence_score=0.0,
                processing_time_ms=int((time.time() - start_time) * 1000),
                language_code="en",
            )

        # Note: For production, download image and send to Gemini Vision
        # This is a simplified implementation
        return ProcessorResult(
            extracted_text=f"[Image analysis] Image from {event.raw_gcs_uri}",
            struct_data={
                "mime_type": event.mime_type,
                "requires_implementation": True,
            },
            confidence_score=0.5,
            processing_time_ms=int((time.time() - start_time) * 1000),
            language_code="en",
        )
