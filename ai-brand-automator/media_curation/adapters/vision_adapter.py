"""
Vision API Adapter - Google Cloud Vision implementation.

Provides OCR and image analysis capabilities using Google Cloud Vision API.
Supports both synchronous image processing and asynchronous PDF batch processing.
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from django.conf import settings

from media_curation.domain.exceptions import (
    AIModelError,
    AIModelRateLimitError,
    StorageError,
)


logger = logging.getLogger(__name__)

# Thread pool for async I/O operations
_executor = ThreadPoolExecutor(max_workers=4)


class VisionAdapter:
    """
    Google Vision API adapter for OCR and image analysis.

    Supports:
    - Synchronous text detection for images
    - Asynchronous batch annotation for PDFs
    - Document text detection for dense text
    """

    # Supported image types for sync processing
    SUPPORTED_IMAGE_TYPES = [
        "image/png",
        "image/jpeg",
        "image/jpg",
        "image/gif",
        "image/bmp",
        "image/webp",
        "image/tiff",
    ]

    # Supported document types for async processing
    SUPPORTED_DOCUMENT_TYPES = [
        "application/pdf",
        "image/tiff",  # Multi-page TIFF
    ]

    def __init__(
        self,
        project_id: Optional[str] = None,
        credentials_path: Optional[str] = None,
    ):
        """
        Initialize the Vision API adapter.

        Args:
            project_id: GCP project ID
            credentials_path: Path to service account JSON file
        """
        # Lazy import to avoid issues when google-cloud-vision is not installed
        try:
            from google.cloud import vision

            self._vision_available = True
        except ImportError:
            self._vision_available = False
            logger.warning("google-cloud-vision not installed, using mock mode")
            self.client = None
            return

        self.project_id = project_id or getattr(settings, "GCP_PROJECT_ID", None)

        try:
            if credentials_path:
                self.client = vision.ImageAnnotatorClient.from_service_account_json(
                    credentials_path
                )
            else:
                # Use Application Default Credentials
                self.client = vision.ImageAnnotatorClient()

            logger.info(
                "Vision API adapter initialized",
                extra={"project_id": self.project_id},
            )
        except Exception as e:
            logger.error(f"Failed to initialize Vision API: {e}")
            self._vision_available = False
            self.client = None

    def detect_text(self, gcs_uri: str) -> str:
        """
        Detect text in an image using synchronous API.

        Args:
            gcs_uri: GCS path to the image (gs://bucket/path)

        Returns:
            Extracted text from the image

        Raises:
            AIModelError: For Vision API errors
        """
        if not self._vision_available:
            return f"[Mock Vision API text detection] from {gcs_uri}"

        from google.cloud import vision

        try:
            image = vision.Image(source=vision.ImageSource(gcs_image_uri=gcs_uri))

            response = self.client.text_detection(image=image)

            if response.error.message:
                raise AIModelError(f"Vision API error: {response.error.message}")

            # Get full text annotation
            texts = response.text_annotations
            if texts:
                return texts[0].description
            return ""

        except Exception as e:
            if "RESOURCE_EXHAUSTED" in str(e):
                raise AIModelRateLimitError(f"Vision API rate limit: {e}")
            raise AIModelError(f"Vision API text detection failed: {e}")

    def detect_document_text(self, gcs_uri: str) -> str:
        """
        Detect dense text in a document image.

        Uses document_text_detection for better OCR on dense text.

        Args:
            gcs_uri: GCS path to the image

        Returns:
            Extracted text with preserved structure
        """
        if not self._vision_available:
            return f"[Mock Vision API document text detection] from {gcs_uri}"

        from google.cloud import vision

        try:
            image = vision.Image(source=vision.ImageSource(gcs_image_uri=gcs_uri))

            response = self.client.document_text_detection(image=image)

            if response.error.message:
                raise AIModelError(f"Vision API error: {response.error.message}")

            # Get full text annotation with structure
            if response.full_text_annotation:
                return response.full_text_annotation.text
            return ""

        except Exception as e:
            if "RESOURCE_EXHAUSTED" in str(e):
                raise AIModelRateLimitError(f"Vision API rate limit: {e}")
            raise AIModelError(f"Vision API document detection failed: {e}")

    async def detect_text_async(self, gcs_uri: str) -> str:
        """Async wrapper for detect_text."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, self.detect_text, gcs_uri)

    async def detect_document_text_async(self, gcs_uri: str) -> str:
        """Async wrapper for detect_document_text."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, self.detect_document_text, gcs_uri)

    def batch_annotate_pdf(
        self,
        gcs_input_uri: str,
        gcs_output_uri: str,
        batch_size: int = 100,
        timeout_seconds: int = 600,
    ) -> str:
        """
        Process a PDF using async batch annotation.

        This method starts the operation and polls until completion.

        Args:
            gcs_input_uri: GCS path to the input PDF
            gcs_output_uri: GCS path prefix for output JSON files
            batch_size: Pages per output file
            timeout_seconds: Maximum time to wait for completion

        Returns:
            Concatenated extracted text from all pages

        Raises:
            AIModelError: For Vision API errors
            StorageError: For output retrieval errors
        """
        if not self._vision_available:
            return f"[Mock Vision API batch PDF annotation] from {gcs_input_uri}"

        from google.cloud import vision

        try:
            # Configure input
            gcs_source = vision.GcsSource(uri=gcs_input_uri)
            input_config = vision.InputConfig(
                gcs_source=gcs_source,
                mime_type="application/pdf",
            )

            # Configure output
            gcs_destination = vision.GcsDestination(uri=gcs_output_uri)
            output_config = vision.OutputConfig(
                gcs_destination=gcs_destination,
                batch_size=batch_size,
            )

            # Configure features
            feature = vision.Feature(type_=vision.Feature.Type.DOCUMENT_TEXT_DETECTION)

            # Build request
            async_request = vision.AsyncAnnotateFileRequest(
                features=[feature],
                input_config=input_config,
                output_config=output_config,
            )

            # Start async operation
            operation = self.client.async_batch_annotate_files(requests=[async_request])

            logger.info(
                "PDF batch annotation started",
                extra={"input": gcs_input_uri, "output": gcs_output_uri},
            )

            # Poll for completion
            result = operation.result(timeout=timeout_seconds)

            # Collect output
            output_texts = []
            for response in result.responses:
                if response.error.message:
                    logger.error(f"Batch annotation error: {response.error.message}")
                    continue

                # Read output JSON from GCS
                output_texts.append(
                    self._read_batch_output(response.output_config.gcs_destination.uri)
                )

            return "\n\n".join(output_texts)

        except Exception as e:
            if "RESOURCE_EXHAUSTED" in str(e):
                raise AIModelRateLimitError(f"Vision API rate limit: {e}")
            raise AIModelError(f"Vision API batch annotation failed: {e}")

    def _read_batch_output(self, gcs_output_prefix: str) -> str:
        """
        Read batch annotation output from GCS.

        Args:
            gcs_output_prefix: GCS prefix where output files are stored

        Returns:
            Concatenated text from all output files
        """
        try:
            from google.cloud import storage
            import json

            # Parse bucket and prefix
            if not gcs_output_prefix.startswith("gs://"):
                raise StorageError(f"Invalid GCS URI: {gcs_output_prefix}")

            path = gcs_output_prefix[5:]
            parts = path.split("/", 1)
            bucket_name = parts[0]
            prefix = parts[1] if len(parts) > 1 else ""

            # List output files
            storage_client = storage.Client(project=self.project_id)
            bucket = storage_client.bucket(bucket_name)
            blobs = list(bucket.list_blobs(prefix=prefix))

            texts = []
            for blob in blobs:
                if blob.name.endswith(".json"):
                    content = json.loads(blob.download_as_text())

                    # Extract text from each response
                    for response in content.get("responses", []):
                        full_text = response.get("fullTextAnnotation", {}).get(
                            "text", ""
                        )
                        if full_text:
                            texts.append(full_text)

            return "\n\n".join(texts)

        except Exception as e:
            logger.error(f"Failed to read batch output: {e}")
            raise StorageError(f"Failed to read batch output: {e}")

    async def batch_annotate_pdf_async(
        self,
        gcs_input_uri: str,
        gcs_output_uri: str,
        batch_size: int = 100,
        timeout_seconds: int = 600,
    ) -> str:
        """
        Async wrapper for batch_annotate_pdf.

        Runs the blocking operation in a thread pool.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            _executor,
            lambda: self.batch_annotate_pdf(
                gcs_input_uri, gcs_output_uri, batch_size, timeout_seconds
            ),
        )

    def analyze_image(self, gcs_uri: str) -> dict:
        """
        Perform comprehensive image analysis.

        Includes:
        - Text detection
        - Label detection
        - Object detection
        - Face detection (count only for privacy)

        Args:
            gcs_uri: GCS path to the image

        Returns:
            Dictionary with analysis results
        """
        if not self._vision_available:
            return {
                "text": f"[Mock analysis] from {gcs_uri}",
                "labels": [],
                "objects": [],
                "face_count": 0,
                "mock": True,
            }

        from google.cloud import vision

        try:
            image = vision.Image(source=vision.ImageSource(gcs_image_uri=gcs_uri))

            # Request multiple features
            features = [
                vision.Feature(type_=vision.Feature.Type.TEXT_DETECTION),
                vision.Feature(type_=vision.Feature.Type.LABEL_DETECTION),
                vision.Feature(type_=vision.Feature.Type.OBJECT_LOCALIZATION),
                vision.Feature(type_=vision.Feature.Type.FACE_DETECTION),
            ]

            response = self.client.annotate_image(
                {"image": image, "features": features}
            )

            if response.error.message:
                raise AIModelError(f"Vision API error: {response.error.message}")

            # Extract text
            text = ""
            if response.text_annotations:
                text = response.text_annotations[0].description

            # Extract labels
            labels = [
                {"description": label.description, "score": label.score}
                for label in response.label_annotations
            ]

            # Extract objects
            objects = [
                {"name": obj.name, "score": obj.score}
                for obj in response.localized_object_annotations
            ]

            # Count faces (don't store face data for privacy)
            face_count = len(response.face_annotations)

            return {
                "text": text,
                "labels": labels,
                "objects": objects,
                "face_count": face_count,
            }

        except Exception as e:
            if "RESOURCE_EXHAUSTED" in str(e):
                raise AIModelRateLimitError(f"Vision API rate limit: {e}")
            raise AIModelError(f"Vision API image analysis failed: {e}")

    async def analyze_image_async(self, gcs_uri: str) -> dict:
        """Async wrapper for analyze_image."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, self.analyze_image, gcs_uri)

    async def is_healthy(self) -> bool:
        """Check if Vision API is available."""
        if not self._vision_available:
            return False

        def _check():
            try:
                return self.client is not None
            except Exception as e:
                logger.warning(f"Vision API health check failed: {e}")
                return False

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, _check)
