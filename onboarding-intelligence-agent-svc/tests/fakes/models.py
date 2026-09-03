"""Shared provider fakes for the OIA test suite (N-01, AC-2).

Every fake honours realistic timing via ``delay_ms`` so that tests which pass
only because a fake returned in zero milliseconds cannot mask latency
regressions (Design §22, F-05).

These are seams, not mocks: nothing is patched.  The providers' breakers,
error handling, and text extraction all still run.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

from app.circuit_breaker.breaker import BreakerConfig, CircuitBreaker
from app.providers.llm import LLMProvider
from app.providers.stt import FakeSTTAdapter
from app.providers.vision import VisionResult

__all__ = [
    "StubModels",
    "FakeVisionProvider",
    "FakeSTTAdapter",
    "llm_for_stub",
]


class StubModels:
    """Stand-in for ``genai.Client(...).aio.models``.

    Supports two constructor styles found across the test suite:

    * ``StubModels(text="...", raises=...)`` — research/sufficiency/followup
    * ``StubModels(payload)`` where payload is a dict — questionnaire gen

    The unified constructor auto-serialises dicts and lists to JSON.
    ``delay_ms`` adds realistic pacing per AC-2.
    """

    def __init__(
        self,
        text_or_payload: str | dict | list = "",
        *,
        text: str | None = None,
        raises: Exception | None = None,
        delay_ms: int = 5,
    ) -> None:
        raw = text if text is not None else text_or_payload
        if isinstance(raw, (dict, list)):
            self._text = json.dumps(raw)
        else:
            self._text = raw
        self._raises = raises
        self._delay_ms = delay_ms
        self.prompts: list[str] = []

    async def generate_content(
        self, *, model: Any, contents: Any, config: Any = None
    ) -> Any:
        self.prompts.append(contents)
        if self._delay_ms:
            await asyncio.sleep(self._delay_ms / 1000.0)
        if self._raises:
            raise self._raises

        class Response:
            text = self._text

        return Response()


@dataclass
class _FakeVisionResponse:
    result: VisionResult
    delay_ms: int


class FakeVisionProvider:
    """Canned ``VisionResult`` responses with realistic delay.

    Replaces ``AsyncMock`` usage in vision tests so that the provider's
    breaker and parsing logic are exercised for real.
    """

    configured: bool = True

    def __init__(
        self,
        responses: list[VisionResult],
        *,
        delay_ms: int = 50,
    ) -> None:
        self._responses = list(responses)
        self._delay_ms = delay_ms
        self.calls: list[str] = []

    async def analyze(self, image_bytes: bytes, ocr_text: str) -> VisionResult:
        self.calls.append("analyze")
        await asyncio.sleep(self._delay_ms / 1000.0)
        if not self._responses:
            raise ValueError("FakeVisionProvider: no more canned responses")
        return self._responses.pop(0)

    async def analyze_multi(self, frames: list[bytes], ocr_text: str) -> VisionResult:
        self.calls.append("analyze_multi")
        await asyncio.sleep(self._delay_ms / 1000.0)
        if not self._responses:
            raise ValueError("FakeVisionProvider: no more canned responses")
        return self._responses.pop(0)


def _default_breaker() -> CircuitBreaker:
    return CircuitBreaker(
        BreakerConfig(
            name="llm",
            failure_threshold=5,
            window_seconds=30,
            success_threshold=2,
            half_open_max_calls=1,
            reset_timeout_seconds=60,
            degraded_mode="MANUAL_CHECKBOXES",
            user_message="x",
        )
    )


def llm_for_stub(
    stub: StubModels, *, breaker: CircuitBreaker | None = None
) -> LLMProvider:
    """Build a real ``LLMProvider`` backed by a ``StubModels`` stand-in."""
    return LLMProvider("k", breaker=breaker or _default_breaker(), client=stub)
