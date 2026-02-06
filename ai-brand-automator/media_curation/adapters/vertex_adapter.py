"""
Vertex AI Adapter - Google Vertex AI Gemini implementation.

Provides multimodal content processing for video and audio files
using Vertex AI's Gemini models with retry logic for rate limiting.
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from django.conf import settings

from tenacity import (
    retry,
    retry_if_exception_type,
    wait_exponential,
    stop_after_attempt,
    before_sleep_log,
)

from media_curation.domain.exceptions import (
    AIModelError,
    AIModelRateLimitError,
    AIModelQuotaExceededError,
)


logger = logging.getLogger(__name__)

# Thread pool for async I/O operations
_executor = ThreadPoolExecutor(max_workers=2)


class VertexAIAdapter:
    """
    Google Vertex AI Gemini adapter for multimodal processing.

    Handles video and audio content processing using Gemini 1.5 Pro/Flash models.
    Includes retry logic with exponential backoff for rate limiting.
    """

    # Default prompts for different content types
    VIDEO_TRANSCRIPTION_PROMPT = (
        "Transcribe the audio in this video. Include timestamps for each segment. "
        "Format: [MM:SS] - text"
    )
    AUDIO_TRANSCRIPTION_PROMPT = (
        "Transcribe this audio file. Include timestamps for each segment. "
        "Format: [MM:SS] - text"
    )
    VIDEO_ANALYSIS_PROMPT = (
        "Analyze this video and provide:\n"
        "1. A detailed transcription of any speech\n"
        "2. Description of key visual elements\n"
        "3. Any text visible in the video (OCR)\n"
        "4. Timestamps for significant events"
    )

    def __init__(
        self,
        project_id: Optional[str] = None,
        location: str = "us-central1",
        model_name: str = "gemini-1.5-pro",
        credentials_path: Optional[str] = None,
    ):
        """
        Initialize the Vertex AI adapter.

        Args:
            project_id: GCP project ID
            location: Vertex AI region (default: us-central1)
            model_name: Gemini model to use (default: gemini-1.5-pro)
            credentials_path: Path to service account JSON file
        """
        # Set these before early return so they're always available
        self.project_id = project_id or getattr(settings, "GCP_PROJECT_ID", None)
        self.location = location
        self.model_name = model_name

        # Lazy import to avoid issues when vertexai is not installed
        try:
            import vertexai
            from vertexai.generative_models import GenerativeModel

            self._vertex_available = True
        except ImportError:
            self._vertex_available = False
            logger.warning("vertexai not installed, using mock mode")
            self.model = None
            return

        # Initialize Vertex AI
        try:
            if credentials_path:
                from google.oauth2 import service_account

                credentials = service_account.Credentials.from_service_account_file(
                    credentials_path
                )
                vertexai.init(
                    project=self.project_id,
                    location=location,
                    credentials=credentials,
                )
            else:
                vertexai.init(project=self.project_id, location=location)

            self.model = GenerativeModel(model_name)

            logger.info(
                "Vertex AI adapter initialized",
                extra={
                    "project_id": self.project_id,
                    "location": location,
                    "model": model_name,
                },
            )
        except Exception as e:
            logger.error(f"Failed to initialize Vertex AI: {e}")
            self._vertex_available = False
            self.model = None

    def _is_rate_limit_error(self, exception: Exception) -> bool:
        """Check if exception is a rate limit error."""
        try:
            from google.api_core.exceptions import ResourceExhausted

            return isinstance(exception, ResourceExhausted)
        except ImportError:
            return False

    def _is_quota_error(self, exception: Exception) -> bool:
        """Check if exception is a quota exceeded error."""
        try:
            from google.api_core.exceptions import ResourceExhausted

            if isinstance(exception, ResourceExhausted):
                error_msg = str(exception).lower()
                return "quota" in error_msg
            return False
        except ImportError:
            return False

    @retry(
        retry=retry_if_exception_type(AIModelRateLimitError),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        stop=stop_after_attempt(5),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def generate_from_uri(
        self,
        gcs_uri: str,
        mime_type: str,
        prompt: Optional[str] = None,
    ) -> str:
        """
        Generate content from a GCS URI using Gemini.

        Args:
            gcs_uri: GCS path to the media file (gs://bucket/path)
            mime_type: MIME type of the file
            prompt: Custom prompt (uses default if not provided)

        Returns:
            Generated text content

        Raises:
            AIModelError: For general AI errors
            AIModelRateLimitError: For rate limiting (retryable)
            AIModelQuotaExceededError: For quota exhaustion
        """
        if not self._vertex_available:
            return f"[Mock Vertex AI response] Content from {gcs_uri}"

        from vertexai.generative_models import Part

        try:
            # Create Part from GCS URI
            media_part = Part.from_uri(gcs_uri, mime_type=mime_type)

            # Select appropriate prompt
            if prompt is None:
                if mime_type.startswith("video/"):
                    prompt = self.VIDEO_ANALYSIS_PROMPT
                elif mime_type.startswith("audio/"):
                    prompt = self.AUDIO_TRANSCRIPTION_PROMPT
                else:
                    prompt = "Analyze this content and extract all text and metadata."

            # Generate content
            response = self.model.generate_content([media_part, prompt])

            return response.text

        except Exception as e:
            # Check for credential errors — fall back to mock mode
            if "credentials" in str(e).lower():
                logger.warning(
                    f"Vertex AI credentials not available, "
                    f"switching to mock mode: {e}"
                )
                self._vertex_available = False
                return f"[Mock Vertex AI response] Content from {gcs_uri}"
            elif self._is_quota_error(e):
                raise AIModelQuotaExceededError(
                    f"Quota exceeded for Vertex AI: {e}",
                )
            elif self._is_rate_limit_error(e):
                raise AIModelRateLimitError(
                    f"Rate limit hit for Vertex AI: {e}",
                    retry_after_seconds=30.0,
                )
            else:
                raise AIModelError(f"Vertex AI processing failed: {e}")

    async def generate_from_uri_async(
        self,
        gcs_uri: str,
        mime_type: str,
        prompt: Optional[str] = None,
    ) -> str:
        """
        Async wrapper for generate_from_uri.

        Args:
            gcs_uri: GCS path to the media file
            mime_type: MIME type of the file
            prompt: Custom prompt

        Returns:
            Generated text content
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            _executor,
            lambda: self.generate_from_uri(gcs_uri, mime_type, prompt),
        )

    def transcribe_video(self, gcs_uri: str, mime_type: str = "video/mp4") -> str:
        """
        Transcribe audio from a video file.

        Args:
            gcs_uri: GCS path to the video file
            mime_type: Video MIME type

        Returns:
            Transcribed text with timestamps
        """
        return self.generate_from_uri(
            gcs_uri,
            mime_type,
            self.VIDEO_TRANSCRIPTION_PROMPT,
        )

    def transcribe_audio(self, gcs_uri: str, mime_type: str = "audio/mpeg") -> str:
        """
        Transcribe an audio file.

        Args:
            gcs_uri: GCS path to the audio file
            mime_type: Audio MIME type

        Returns:
            Transcribed text with timestamps
        """
        return self.generate_from_uri(
            gcs_uri,
            mime_type,
            self.AUDIO_TRANSCRIPTION_PROMPT,
        )

    def analyze_video(self, gcs_uri: str, mime_type: str = "video/mp4") -> str:
        """
        Perform comprehensive video analysis.

        Args:
            gcs_uri: GCS path to the video file
            mime_type: Video MIME type

        Returns:
            Analysis including transcription, visual descriptions, and OCR
        """
        return self.generate_from_uri(
            gcs_uri,
            mime_type,
            self.VIDEO_ANALYSIS_PROMPT,
        )

    async def is_healthy(self) -> bool:
        """Check if Vertex AI service is available."""
        if not self._vertex_available:
            return False

        def _check():
            try:
                # Simple model info check
                return self.model is not None
            except Exception as e:
                logger.warning(f"Vertex AI health check failed: {e}")
                return False

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, _check)
