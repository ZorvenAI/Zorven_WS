"""OCR provider — Cloud Vision DOCUMENT_TEXT_DETECTION.

Design §8.4 · implemented by story H-03.

Mirrors :class:`app.providers.llm.LLMProvider` deliberately — same
breaker discipline, same "unavailable is not empty" distinction.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from app.circuit_breaker.breaker import (
    BreakerRegistry,
    CircuitBreaker,
    CircuitBreakerOpen,
)

logger = logging.getLogger(__name__)

DEPENDENCY = "vision"


@dataclass(frozen=True)
class OCRResult:
    """Cloud Vision DOCUMENT_TEXT_DETECTION output."""

    text: str
    confidence: float
    pages: int


class OCRUnavailable(Exception):
    """OCR could not be performed."""

    def __init__(self, reason: str, *, degraded_mode: str = "GEMINI_ONLY_OCR") -> None:
        super().__init__(reason)
        self.reason = reason
        self.degraded_mode = degraded_mode


class OCRProvider:
    """Cloud Vision DOCUMENT_TEXT_DETECTION, behind the vision breaker.

    Parameters
    ----------
    breaker : CircuitBreaker | None
        The ``vision`` circuit breaker.  Falls back to the registry if
        not supplied (mirrors LLMProvider).
    client : Any | None
        Injected ``ImageAnnotatorAsyncClient`` for testing.
    """

    def __init__(
        self,
        *,
        breaker: CircuitBreaker | None = None,
        client: Any | None = None,
    ) -> None:
        self._breaker = breaker or BreakerRegistry().get(DEPENDENCY)
        self._client = client

    def _ensure_client(self) -> Any:
        if self._client is None:
            from google.cloud.vision import ImageAnnotatorAsyncClient

            self._client = ImageAnnotatorAsyncClient()
        return self._client

    async def detect_text(self, image_bytes: bytes) -> OCRResult:
        """Run DOCUMENT_TEXT_DETECTION and return structured text."""
        try:
            self._breaker.before_call()
        except CircuitBreakerOpen as exc:
            raise OCRUnavailable(
                exc.user_message or f"{exc.dependency} is unavailable",
                degraded_mode=exc.degraded_mode,
            ) from exc

        try:
            from google.cloud.vision import Image, Feature, AnnotateImageRequest

            image = Image(content=image_bytes)
            feature = Feature(type_=Feature.Type.DOCUMENT_TEXT_DETECTION)
            request = AnnotateImageRequest(image=image, features=[feature])

            client = self._ensure_client()
            response = await client.batch_annotate_images(requests=[request])
            annotation = response.responses[0]

            if annotation.error.message:
                raise RuntimeError(annotation.error.message)

            full_text_annotation = annotation.full_text_annotation
            if not full_text_annotation or not full_text_annotation.text:
                self._breaker.record_success()
                return OCRResult(text="", confidence=0.0, pages=0)

            pages = full_text_annotation.pages or []
            page_count = len(pages)

            if pages:
                total_conf = sum(
                    block.confidence
                    for page in pages
                    for block in (page.blocks or [])
                    if hasattr(block, "confidence")
                )
                block_count = sum(
                    1
                    for page in pages
                    for block in (page.blocks or [])
                    if hasattr(block, "confidence")
                )
                confidence = total_conf / block_count if block_count else 0.0
            else:
                confidence = 0.0

        except OCRUnavailable:
            raise
        except Exception as exc:
            self._breaker.record_failure()
            logger.warning("cloud vision failed: %s: %s", type(exc).__name__, exc)
            raise OCRUnavailable(f"OCR failed: {type(exc).__name__}") from exc

        self._breaker.record_success()
        return OCRResult(
            text=full_text_annotation.text.strip(),
            confidence=round(min(max(confidence, 0.0), 1.0), 4),
            pages=page_count,
        )
