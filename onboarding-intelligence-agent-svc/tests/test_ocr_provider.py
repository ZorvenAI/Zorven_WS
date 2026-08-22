"""H-03 · OCR provider and its breaker wiring.

The real ``ImageAnnotatorAsyncClient`` talks to a GCP endpoint and needs
ADC — spinning up a fake Vision API is not practical in a test. Instead
these inject a test double through the ``client`` constructor parameter,
which exercises the provider's own logic (breaker discipline, response
parsing, confidence calculation) against realistic response shapes.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from app.circuit_breaker.breaker import BreakerConfig, CircuitBreaker, State
from app.providers.ocr import OCRProvider, OCRResult, OCRUnavailable


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


def _make_block(confidence: float = 0.95):
    """A minimal block with a confidence attribute."""

    class Block:
        pass

    b = Block()
    b.confidence = confidence
    return b


def _make_page(blocks):
    class Page:
        pass

    p = Page()
    p.blocks = blocks
    return p


def _make_annotation(text: str, pages=None, error_message: str = ""):
    class Error:
        pass

    class FullTextAnnotation:
        pass

    class Annotation:
        pass

    err = Error()
    err.message = error_message

    ann = Annotation()
    ann.error = err

    if text or pages:
        fta = FullTextAnnotation()
        fta.text = text
        fta.pages = pages or []
        ann.full_text_annotation = fta
    else:
        ann.full_text_annotation = None

    return ann


def _make_response(annotations):
    class Response:
        pass

    r = Response()
    r.responses = annotations
    return r


def _fake_client(annotation):
    """An async client that returns a canned response."""
    client = AsyncMock()
    response = _make_response([annotation])
    client.batch_annotate_images.return_value = response
    return client


class TestOCRResult:
    def test_result_shape(self):
        r = OCRResult(text="hello", confidence=0.95, pages=1)
        assert r.text == "hello"
        assert r.confidence == 0.95
        assert r.pages == 1


class TestOCRProviderBreakerDiscipline:
    def test_open_breaker_raises_unavailable(self):
        b = breaker(failure_threshold=1)
        b.record_failure()
        provider = OCRProvider(breaker=b)
        with pytest.raises(OCRUnavailable) as exc_info:
            asyncio.run(provider.detect_text(b"fake"))
        assert exc_info.value.degraded_mode == "GEMINI_ONLY_OCR"

    def test_success_records_on_breaker(self):
        b = breaker()
        annotation = _make_annotation(
            "Invoice total: $100",
            pages=[_make_page([_make_block(0.92)])],
        )
        client = _fake_client(annotation)
        provider = OCRProvider(breaker=b, client=client)
        result = asyncio.run(provider.detect_text(b"image"))
        assert result.text == "Invoice total: $100"
        assert b.state == State.CLOSED

    def test_failure_records_on_breaker(self):
        b = breaker(failure_threshold=2)
        client = AsyncMock()
        client.batch_annotate_images.side_effect = RuntimeError("boom")
        provider = OCRProvider(breaker=b, client=client)
        with pytest.raises(OCRUnavailable):
            asyncio.run(provider.detect_text(b"image"))
        assert len(b._failures) == 1


class TestOCRProviderParsing:
    def test_empty_text_returns_zero_confidence(self):
        annotation = _make_annotation("", pages=[])
        annotation.full_text_annotation = None
        client = _fake_client(annotation)
        b = breaker()
        provider = OCRProvider(breaker=b, client=client)
        result = asyncio.run(provider.detect_text(b"image"))
        assert result.text == ""
        assert result.confidence == 0.0
        assert result.pages == 0

    def test_multi_page_confidence_is_average(self):
        pages = [
            _make_page([_make_block(0.9), _make_block(0.8)]),
            _make_page([_make_block(1.0)]),
        ]
        annotation = _make_annotation("text across pages", pages=pages)
        client = _fake_client(annotation)
        b = breaker()
        provider = OCRProvider(breaker=b, client=client)
        result = asyncio.run(provider.detect_text(b"image"))
        expected = round((0.9 + 0.8 + 1.0) / 3, 4)
        assert result.confidence == expected
        assert result.pages == 2

    def test_confidence_clamped_to_0_1(self):
        pages = [_make_page([_make_block(1.5)])]
        annotation = _make_annotation("over", pages=pages)
        client = _fake_client(annotation)
        b = breaker()
        provider = OCRProvider(breaker=b, client=client)
        result = asyncio.run(provider.detect_text(b"image"))
        assert result.confidence <= 1.0

    def test_error_in_annotation_raises_unavailable(self):
        annotation = _make_annotation("", error_message="Image too large")
        client = _fake_client(annotation)
        b = breaker()
        provider = OCRProvider(breaker=b, client=client)
        with pytest.raises(OCRUnavailable, match="OCR failed"):
            asyncio.run(provider.detect_text(b"image"))
