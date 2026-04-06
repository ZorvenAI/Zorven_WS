"""Nano Banana 2 image generation client (google-genai SDK).

Adapter pattern: ImageGenAdapter ABC with NanoBanana2Adapter and StubAdapter.
Includes retry with exponential backoff and circuit breaker.
"""

import asyncio
import base64
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

# Nano Banana 2 cost estimate per image
_COST_PER_IMAGE_USD = 0.065

# Supported aspect ratios for Meta Ads
ASPECT_RATIOS = {
    "1:1": "1:1",  # Feed (1080×1080)
    "9:16": "9:16",  # Stories/Reels (1080×1920)
    "16:9": "16:9",  # Audience Network (1200×628 approx)
}


@dataclass
class GeneratedImage:
    """Result of a single image generation."""

    image_data: bytes = b""
    prompt_used: str = ""
    aspect_ratio: str = "1:1"
    provider: str = "nano_banana_2"
    cost_usd: float = 0.0
    generation_time_ms: int = 0
    text_description: str = ""


@dataclass
class CircuitBreakerState:
    """Track failures for circuit breaker pattern."""

    failure_count: int = 0
    last_failure_time: float = 0.0
    is_open: bool = False
    window_seconds: float = 60.0
    threshold: int = 3

    def record_failure(self):
        now = time.time()
        if now - self.last_failure_time > self.window_seconds:
            self.failure_count = 0
        self.failure_count += 1
        self.last_failure_time = now
        if self.failure_count >= self.threshold:
            self.is_open = True
            logger.error(
                "Circuit breaker OPEN: %d failures in %.0fs",
                self.failure_count,
                self.window_seconds,
            )

    def record_success(self):
        self.failure_count = 0
        self.is_open = False

    def can_attempt(self) -> bool:
        if not self.is_open:
            return True
        if time.time() - self.last_failure_time > self.window_seconds:
            self.is_open = False
            self.failure_count = 0
            return True
        return False


class ImageGenAdapter(ABC):
    """Abstract base for image generation providers."""

    @abstractmethod
    async def generate(self, prompt: str, aspect_ratio: str = "1:1") -> GeneratedImage:
        """Generate a single image from a text prompt."""

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the provider is configured and available."""


class NanoBanana2Adapter(ImageGenAdapter):
    """Nano Banana 2 image generation via google-genai SDK.

    Uses gemini-3.1-flash-image-preview model with generateContent API.
    Images returned as inline base64 data.
    """

    def __init__(self):
        self._client: Any = None
        self._circuit = CircuitBreakerState()
        self._init_client()

    def _init_client(self):
        """Initialize google-genai client."""
        if not settings.GOOGLE_API_KEY:
            logger.info("Nano Banana 2 in stub mode (no GOOGLE_API_KEY)")
            return
        try:
            from google import genai

            self._client = genai.Client(api_key=settings.GOOGLE_API_KEY)
            logger.info(
                "Nano Banana 2 client initialized (model: %s)",
                settings.IMAGE_GEN_MODEL,
            )
        except Exception as exc:
            logger.warning("Nano Banana 2 client init failed: %s", exc)
            self._client = None

    def is_available(self) -> bool:
        return self._client is not None and self._circuit.can_attempt()

    async def generate(self, prompt: str, aspect_ratio: str = "1:1") -> GeneratedImage:
        """Generate image via Nano Banana 2.

        Uses the dedicated generate_images API (Imagen 3) if the model
        name contains 'imagen', otherwise falls back to generate_content
        with responseModalities=["IMAGE"] (Gemini Flash).
        """
        if not self._client:
            raise RuntimeError("Nano Banana 2 client not initialized")
        if not self._circuit.can_attempt():
            raise RuntimeError("Circuit breaker is open for Nano Banana 2")

        from google.genai import types

        start_ms = int(time.time() * 1000)
        last_exc: Exception | None = None
        model = settings.IMAGE_GEN_MODEL
        use_imagen_api = "imagen" in model.lower()

        for attempt in range(settings.MAX_IMAGE_GEN_RETRIES):
            try:
                if use_imagen_api:
                    image_data, text_desc = await self._generate_imagen(
                        prompt, aspect_ratio, types
                    )
                else:
                    image_data, text_desc = await self._generate_gemini(
                        prompt, aspect_ratio, types
                    )

                if not image_data:
                    raise ValueError("No image data in response")

                elapsed_ms = int(time.time() * 1000) - start_ms
                self._circuit.record_success()

                logger.info(
                    "Nano Banana 2 image generated: ratio=%s, size=%d bytes, %dms",
                    aspect_ratio,
                    len(image_data),
                    elapsed_ms,
                )

                return GeneratedImage(
                    image_data=image_data,
                    prompt_used=prompt,
                    aspect_ratio=aspect_ratio,
                    provider="nano_banana_2",
                    cost_usd=_COST_PER_IMAGE_USD,
                    generation_time_ms=elapsed_ms,
                    text_description=text_desc,
                )

            except Exception as exc:
                last_exc = exc
                wait = 2**attempt  # 1s, 2s, 4s
                logger.warning(
                    "Nano Banana 2 attempt %d/%d failed: %s. Retrying in %ds",
                    attempt + 1,
                    settings.MAX_IMAGE_GEN_RETRIES,
                    exc,
                    wait,
                )
                if attempt < settings.MAX_IMAGE_GEN_RETRIES - 1:
                    await asyncio.sleep(wait)

        self._circuit.record_failure()
        raise RuntimeError(
            f"Nano Banana 2 image generation failed after "
            f"{settings.MAX_IMAGE_GEN_RETRIES} retries: {last_exc}"
        )

    async def _generate_imagen(
        self, prompt: str, aspect_ratio: str, types: Any
    ) -> tuple[bytes, str]:
        """Generate via dedicated Imagen API (generate_images)."""
        response = await asyncio.to_thread(
            self._client.models.generate_images,
            model=settings.IMAGE_GEN_MODEL,
            prompt=prompt,
            config=types.GenerateImagesConfig(
                numberOfImages=1,
                aspectRatio=ASPECT_RATIOS.get(aspect_ratio, "1:1"),
            ),
        )
        if response.generated_images and len(response.generated_images) > 0:
            img = response.generated_images[0]
            image_data = img.image.image_bytes
            return image_data, ""
        return b"", ""

    async def _generate_gemini(
        self, prompt: str, aspect_ratio: str, types: Any
    ) -> tuple[bytes, str]:
        """Generate via Gemini generate_content with IMAGE modality."""
        ratio_str = ASPECT_RATIOS.get(aspect_ratio, "1:1")
        enhanced_prompt = (
            f"Generate a high-quality {ratio_str} aspect ratio "
            f"advertising image: {prompt}"
        )
        logger.info(
            "Gemini image gen: calling generate_content model=%s ratio=%s "
            "prompt_len=%d",
            settings.IMAGE_GEN_MODEL,
            ratio_str,
            len(enhanced_prompt),
        )
        try:
            response = await asyncio.to_thread(
                self._client.models.generate_content,
                model=settings.IMAGE_GEN_MODEL,
                contents=[enhanced_prompt],
                config=types.GenerateContentConfig(
                    response_modalities=["IMAGE", "TEXT"],
                ),
            )
        except Exception as exc:
            logger.error(
                "Gemini image gen: generate_content raised %s: %s",
                type(exc).__name__,
                exc,
                exc_info=True,
            )
            raise
        image_data = b""
        text_desc = ""
        # Surface prompt feedback / safety blocks if present
        prompt_feedback = getattr(response, "prompt_feedback", None)
        if prompt_feedback:
            logger.warning(
                "Gemini image gen: prompt_feedback=%s", prompt_feedback
            )
        if not response.candidates:
            logger.warning(
                "Gemini image gen: no candidates in response "
                "(prompt_feedback=%s)",
                prompt_feedback,
            )
            return b"", ""
        candidate = response.candidates[0]
        finish_reason = getattr(candidate, "finish_reason", None)
        safety_ratings = getattr(candidate, "safety_ratings", None)
        if finish_reason and str(finish_reason) not in ("FinishReason.STOP", "STOP", "1"):
            logger.warning(
                "Gemini image gen: non-STOP finish_reason=%s safety=%s",
                finish_reason,
                safety_ratings,
            )
        parts = candidate.content.parts if candidate.content else None
        if not parts:
            logger.warning(
                "Gemini image gen: no parts in response "
                "(finish_reason=%s safety=%s)",
                finish_reason,
                safety_ratings,
            )
            return b"", ""
        for part in parts:
            if hasattr(part, "inline_data") and part.inline_data:
                raw = part.inline_data.data
                if isinstance(raw, str):
                    image_data = base64.b64decode(raw)
                else:
                    image_data = raw
            elif hasattr(part, "text") and part.text:
                text_desc = part.text
        return image_data, text_desc


class StubAdapter(ImageGenAdapter):
    """Stub adapter that returns placeholder URLs (no real image gen)."""

    def is_available(self) -> bool:
        return True

    async def generate(self, prompt: str, aspect_ratio: str = "1:1") -> GeneratedImage:
        """Return a placeholder image."""
        logger.info(
            "Stub image generation: ratio=%s, prompt=%s...",
            aspect_ratio,
            prompt[:80],
        )
        placeholder = b"\x89PNG\r\n\x1a\n"  # PNG magic bytes (minimal stub)
        return GeneratedImage(
            image_data=placeholder,
            prompt_used=prompt,
            aspect_ratio=aspect_ratio,
            provider="stub",
            cost_usd=0.0,
            generation_time_ms=0,
            text_description="[Stub] Placeholder image for testing",
        )


def create_image_gen_client() -> ImageGenAdapter:
    """Factory: create the appropriate image gen adapter based on config."""
    if settings.GOOGLE_API_KEY:
        adapter = NanoBanana2Adapter()
        if adapter.is_available():
            return adapter
        logger.warning("Nano Banana 2 init failed, falling back to stub adapter")
    else:
        logger.info("No GOOGLE_API_KEY configured, using stub image adapter")
    return StubAdapter()
