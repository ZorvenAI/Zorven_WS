"""Gemini multimodal semantic pass over captured media.

Design §8.4 · implemented by stories H-03 (image) and H-04 (video).

Mirrors :class:`app.providers.llm.LLMProvider` — same breaker discipline,
same ``_ensure_client`` pattern (genai.Client lifetime bug from C-02),
same treatment of a missing key as degradation rather than a crash.
"""

from __future__ import annotations

import json
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
DEFAULT_MODEL = "gemini-3.5-flash"

VALID_DOC_TYPES = frozenset(
    {
        "invoice",
        "receipt",
        "contract",
        "id_card",
        "passport",
        "business_card",
        "presentation",
        "report",
        "letter",
        "form",
        "photo",
        "screenshot",
        "other",
    }
)

VALID_SENSITIVITY = frozenset({"GENERAL", "IDENTITY", "FINANCIAL"})

MULTI_FRAME_PROMPT = """\
You are analyzing frames extracted from a short video snippet captured \
during a business onboarding meeting. The video shows a document, product, \
or premises that a single photo could not capture.

Given the frames and the merged OCR text extracted from them, provide a \
JSON response with:

1. "caption": A brief one-sentence description of what the video shows.
2. "doc_type": One of: invoice, receipt, contract, id_card, passport, \
business_card, presentation, report, letter, form, photo, screenshot, other.
3. "sensitivity_class": One of:
   - "GENERAL" — no sensitive personal or financial data
   - "IDENTITY" — contains personal identification (names+IDs, photos, \
signatures, addresses linked to persons)
   - "FINANCIAL" — contains financial data (account numbers, tax IDs, \
salary, bank details)

Merged OCR text from all frames:
{ocr_text}

Respond ONLY with valid JSON, no markdown fences, no explanation.
Example: {{"caption": "A multi-page contract", "doc_type": "contract", \
"sensitivity_class": "GENERAL"}}
"""

MAX_MULTI_FRAMES = 4

ANALYSIS_PROMPT = """\
You are analyzing a document image captured during a business onboarding meeting.

Given the image and the OCR text extracted from it, provide a JSON response with:

1. "caption": A brief one-sentence description of what the document is.
2. "doc_type": One of: invoice, receipt, contract, id_card, passport, \
business_card, presentation, report, letter, form, photo, screenshot, other.
3. "sensitivity_class": One of:
   - "GENERAL" — no sensitive personal or financial data
   - "IDENTITY" — contains personal identification (names+IDs, photos, \
signatures, addresses linked to persons)
   - "FINANCIAL" — contains financial data (account numbers, tax IDs, \
salary, bank details)

OCR text:
{ocr_text}

Respond ONLY with valid JSON, no markdown fences, no explanation.
Example: {{"caption": "A business invoice", "doc_type": "invoice", \
"sensitivity_class": "FINANCIAL"}}
"""


@dataclass(frozen=True)
class VisionResult:
    """Semantic classification of a captured image."""

    caption: str
    doc_type: str
    sensitivity_class: str


class VisionUnavailable(Exception):
    """Semantic analysis could not be performed."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class VisionProvider:
    """Gemini multimodal semantic analysis, behind the vision breaker.

    Parameters
    ----------
    api_key : str
        The Gemini API key (``OIA_GEMINI_KEY``).
    breaker : CircuitBreaker | None
        The ``vision`` circuit breaker.
    model : str
        Gemini model name.
    client : Any | None
        Injected ``genai.Client.aio.models`` handle for testing.
    """

    def __init__(
        self,
        api_key: str,
        *,
        model: str = DEFAULT_MODEL,
        breaker: CircuitBreaker | None = None,
        client: Any | None = None,
    ) -> None:
        self._api_key = api_key
        self._model_name = model
        self._breaker = breaker or BreakerRegistry().get(DEPENDENCY)
        self._client = client
        self._owner: Any = None

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    def _ensure_client(self) -> Any:
        if self._client is None:
            from google import genai

            self._owner = genai.Client(api_key=self._api_key)
            self._client = self._owner.aio.models
        return self._client

    async def analyze(self, image_bytes: bytes, ocr_text: str) -> VisionResult:
        """Send image + OCR text to Gemini for semantic classification."""
        if not self.configured:
            raise VisionUnavailable("no Gemini API key is configured")

        try:
            self._breaker.before_call()
        except CircuitBreakerOpen as exc:
            raise VisionUnavailable(
                exc.user_message or f"{exc.dependency} is unavailable"
            ) from exc

        try:
            from google.genai import types

            prompt = ANALYSIS_PROMPT.format(
                ocr_text=ocr_text[:2000] if ocr_text else "(no text detected)"
            )
            image_part = types.Part.from_bytes(data=image_bytes, mime_type="image/png")

            response = await self._ensure_client().generate_content(
                model=self._model_name,
                contents=[image_part, prompt],
                config={"temperature": 0.1},
            )

            text = getattr(response, "text", None)
            if not text or not str(text).strip():
                raise ValueError("the model returned no text")

            result = self._parse_response(str(text))

        except VisionUnavailable:
            raise
        except Exception as exc:
            self._breaker.record_failure()
            logger.warning("vision analysis failed: %s: %s", type(exc).__name__, exc)
            raise VisionUnavailable(f"analysis failed: {type(exc).__name__}") from exc

        self._breaker.record_success()
        return result

    async def analyze_multi(self, frames: list[bytes], ocr_text: str) -> VisionResult:
        """Send multiple video frames + merged OCR text to Gemini.

        Used by the video snippet path (H-04 AC-4): one doc_type and one
        caption for the entire video, not per-frame.
        """
        if not self.configured:
            raise VisionUnavailable("no Gemini API key is configured")

        try:
            self._breaker.before_call()
        except CircuitBreakerOpen as exc:
            raise VisionUnavailable(
                exc.user_message or f"{exc.dependency} is unavailable"
            ) from exc

        try:
            from google.genai import types

            prompt = MULTI_FRAME_PROMPT.format(
                ocr_text=ocr_text[:4000] if ocr_text else "(no text detected)"
            )

            contents: list[Any] = []
            for frame_bytes in frames[:MAX_MULTI_FRAMES]:
                contents.append(
                    types.Part.from_bytes(data=frame_bytes, mime_type="image/png")
                )
            contents.append(prompt)

            response = await self._ensure_client().generate_content(
                model=self._model_name,
                contents=contents,
                config={"temperature": 0.1},
            )

            text = getattr(response, "text", None)
            if not text or not str(text).strip():
                raise ValueError("the model returned no text")

            result = self._parse_response(str(text))

        except VisionUnavailable:
            raise
        except Exception as exc:
            self._breaker.record_failure()
            logger.warning(
                "vision multi-frame analysis failed: %s: %s",
                type(exc).__name__,
                exc,
            )
            raise VisionUnavailable(
                f"multi-frame analysis failed: {type(exc).__name__}"
            ) from exc

        self._breaker.record_success()
        return result

    @staticmethod
    def _parse_response(text: str) -> VisionResult:
        """Parse the JSON response, defaulting invalid values to safe ones."""
        clean = text.strip()
        if clean.startswith("```"):
            lines = clean.split("\n")
            clean = "\n".join(lines[1:-1]) if len(lines) > 2 else clean

        data = json.loads(clean)

        caption = str(data.get("caption", "Captured document"))
        doc_type = str(data.get("doc_type", "other"))
        sensitivity = str(data.get("sensitivity_class", "GENERAL"))

        if doc_type not in VALID_DOC_TYPES:
            doc_type = "other"
        if sensitivity not in VALID_SENSITIVITY:
            sensitivity = "GENERAL"

        return VisionResult(
            caption=caption,
            doc_type=doc_type,
            sensitivity_class=sensitivity,
        )
