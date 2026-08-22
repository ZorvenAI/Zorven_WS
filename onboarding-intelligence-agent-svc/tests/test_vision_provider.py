"""H-03 · Gemini multimodal vision provider.

Tests the provider's response parsing, breaker discipline, and input
validation. The real Gemini call needs an API key, so we inject a test
double through the ``client`` parameter.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from app.circuit_breaker.breaker import BreakerConfig, CircuitBreaker, State
from app.providers.vision import (
    VisionProvider,
    VisionResult,
    VisionUnavailable,
    VALID_DOC_TYPES,
    VALID_SENSITIVITY,
)


def breaker(**overrides) -> CircuitBreaker:
    base = dict(
        name="vision",
        failure_threshold=3,
        window_seconds=60,
        success_threshold=1,
        half_open_max_calls=1,
        reset_timeout_seconds=60,
        degraded_mode="GEMINI_ONLY_OCR",
        user_message="Reduced document-reading accuracy — captures still saved.",
    )
    base.update(overrides)
    return CircuitBreaker(BreakerConfig(**base))


def _fake_client(response_text: str):
    """A genai.Client.aio.models stand-in."""

    class FakeResponse:
        text = response_text

    client = AsyncMock()
    client.generate_content.return_value = FakeResponse()
    return client


class TestVisionResultParsing:
    def test_parse_valid_json(self):
        result = VisionProvider._parse_response(
            '{"caption": "An invoice", "doc_type": "invoice", '
            '"sensitivity_class": "FINANCIAL"}'
        )
        assert result.caption == "An invoice"
        assert result.doc_type == "invoice"
        assert result.sensitivity_class == "FINANCIAL"

    def test_invalid_doc_type_defaults_to_other(self):
        result = VisionProvider._parse_response(
            '{"caption": "test", "doc_type": "banana", '
            '"sensitivity_class": "GENERAL"}'
        )
        assert result.doc_type == "other"

    def test_invalid_sensitivity_defaults_to_general(self):
        result = VisionProvider._parse_response(
            '{"caption": "test", "doc_type": "invoice", '
            '"sensitivity_class": "TOP_SECRET"}'
        )
        assert result.sensitivity_class == "GENERAL"

    def test_markdown_fences_stripped(self):
        text = (
            '```json\n{"caption": "doc", "doc_type": "report",'
            ' "sensitivity_class": "GENERAL"}\n```'
        )
        result = VisionProvider._parse_response(text)
        assert result.doc_type == "report"

    def test_missing_fields_get_defaults(self):
        result = VisionProvider._parse_response("{}")
        assert result.caption == "Captured document"
        assert result.doc_type == "other"
        assert result.sensitivity_class == "GENERAL"


class TestVisionProviderBreakerDiscipline:
    def test_open_breaker_raises_unavailable(self):
        b = breaker(failure_threshold=1)
        b.record_failure()
        provider = VisionProvider("key", breaker=b)
        with pytest.raises(VisionUnavailable):
            asyncio.run(provider.analyze(b"img", "text"))

    def test_success_records_on_breaker(self):
        b = breaker()
        client = _fake_client(
            '{"caption": "A letter", "doc_type": "letter", '
            '"sensitivity_class": "GENERAL"}'
        )
        provider = VisionProvider("key", breaker=b, client=client)
        result = asyncio.run(provider.analyze(b"img", "hello"))
        assert result.doc_type == "letter"
        assert b.state == State.CLOSED

    def test_failure_records_on_breaker(self):
        b = breaker(failure_threshold=2)
        client = AsyncMock()
        client.generate_content.side_effect = RuntimeError("boom")
        provider = VisionProvider("key", breaker=b, client=client)
        with pytest.raises(VisionUnavailable):
            asyncio.run(provider.analyze(b"img", "text"))
        assert len(b._failures) == 1


class TestVisionProviderConfig:
    def test_no_api_key_raises_unavailable(self):
        b = breaker()
        provider = VisionProvider("", breaker=b)
        with pytest.raises(VisionUnavailable, match="no Gemini API key"):
            asyncio.run(provider.analyze(b"img", "text"))

    def test_configured_property(self):
        assert VisionProvider("key", breaker=breaker()).configured is True
        assert VisionProvider("", breaker=breaker()).configured is False

    def test_empty_model_response_raises(self):
        b = breaker()
        client = _fake_client("")
        provider = VisionProvider("key", breaker=b, client=client)
        with pytest.raises(VisionUnavailable, match="analysis failed"):
            asyncio.run(provider.analyze(b"img", "text"))


class TestVisionResultShape:
    def test_frozen_dataclass(self):
        r = VisionResult(
            caption="test", doc_type="invoice", sensitivity_class="FINANCIAL"
        )
        with pytest.raises(AttributeError):
            r.caption = "changed"

    def test_all_valid_doc_types_accepted(self):
        for dt in VALID_DOC_TYPES:
            result = VisionProvider._parse_response(
                f'{{"caption": "x", "doc_type": "{dt}", '
                f'"sensitivity_class": "GENERAL"}}'
            )
            assert result.doc_type == dt

    def test_all_valid_sensitivity_classes_accepted(self):
        for sc in VALID_SENSITIVITY:
            result = VisionProvider._parse_response(
                f'{{"caption": "x", "doc_type": "other", '
                f'"sensitivity_class": "{sc}"}}'
            )
            assert result.sensitivity_class == sc
