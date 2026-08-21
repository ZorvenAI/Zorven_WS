"""H-03 · SKL-OIA-07 analyze_captured_media skill tests.

Tests the skill pipeline: OCR → Vision → Redaction → PG-08.
Providers are injected directly (no mocks on the skill itself — only
the providers are test doubles, which the skill accepts by design).
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

from app.providers.ocr import OCRResult
from app.providers.vision import VisionResult
from app.skills.analyze_captured_media import (
    AnalyzeCapturedMedia,
    RETAKE_THRESHOLD,
)
from app.skills.models import (
    Origin,
    SkillContext,
    SkillMeta,
    TenantContext,
)


def _meta() -> SkillMeta:
    return SkillMeta(
        skill_id="SKL-OIA-07",
        name="analyze_captured_media",
        timeout_ms=90000,
    )


def _context(**overrides) -> SkillContext:
    base = dict(
        input_prompt="",
        tenant_context=TenantContext(
            tenant_id="t-1",
            session_id="s-1",
            role="OWNER",
        ),
        input_context={
            "media_id": "m-001",
            "gcs_uri": "gs://bucket/test.jpg",
            "usage_tag": "business_photo",
            "asset_id": "42",
            "redis": None,
            "events": None,
        },
        origin=Origin.INTERNAL,
    )
    base.update(overrides)
    return SkillContext(**base)


def _ocr_provider(text="Invoice total: $100", confidence=0.92):
    provider = AsyncMock()
    provider.detect_text.return_value = OCRResult(
        text=text,
        confidence=confidence,
        pages=1,
    )
    return provider


def _vision_provider(
    caption="An invoice",
    doc_type="invoice",
    sensitivity_class="FINANCIAL",
):
    provider = AsyncMock()
    provider.analyze.return_value = VisionResult(
        caption=caption,
        doc_type=doc_type,
        sensitivity_class=sensitivity_class,
    )
    return provider


def _backend():
    backend = AsyncMock()
    backend.update_asset_ocr.return_value = True
    return backend


class TestPipelineStageOrder:
    def test_ocr_then_vision_then_result(self):
        """AC-1: the pipeline produces the expected output shape."""
        ocr = _ocr_provider()
        vision = _vision_provider()
        backend = _backend()

        skill = AnalyzeCapturedMedia(
            _meta(),
            ocr=ocr,
            vision=vision,
            backend=backend,
        )
        skill._download_image = AsyncMock(return_value=b"fake-image")

        result = asyncio.get_event_loop().run_until_complete(skill.run(_context()))

        assert ocr.detect_text.called
        assert vision.analyze.called
        assert result.output["media_id"] == "m-001"
        assert result.output["doc_type"] == "invoice"
        assert result.output["sensitivity_class"] == "FINANCIAL"
        assert "ocr_text" in result.output

    def test_redacted_text_stored(self):
        """AC-4: ocr_text in the result is redacted."""
        ocr = _ocr_provider(text="Email us at test@example.com for info")
        vision = _vision_provider(sensitivity_class="GENERAL")
        backend = _backend()

        skill = AnalyzeCapturedMedia(
            _meta(),
            ocr=ocr,
            vision=vision,
            backend=backend,
        )
        skill._download_image = AsyncMock(return_value=b"fake-image")

        result = asyncio.get_event_loop().run_until_complete(skill.run(_context()))

        assert "test@example.com" not in result.output["ocr_text"]
        assert result.output["redaction_applied"] is True


class TestRetakeSuggested:
    def test_low_confidence_suggests_retake(self):
        """AC-2: retake_suggested when confidence < threshold."""
        ocr = _ocr_provider(confidence=0.3)
        vision = _vision_provider(sensitivity_class="GENERAL")

        skill = AnalyzeCapturedMedia(
            _meta(),
            ocr=ocr,
            vision=vision,
            backend=_backend(),
        )
        skill._download_image = AsyncMock(return_value=b"fake")

        result = asyncio.get_event_loop().run_until_complete(skill.run(_context()))

        assert result.output["retake_suggested"] is True
        assert result.output["ocr_confidence"] < RETAKE_THRESHOLD

    def test_high_confidence_no_retake(self):
        ocr = _ocr_provider(confidence=0.95)
        vision = _vision_provider(sensitivity_class="GENERAL")

        skill = AnalyzeCapturedMedia(
            _meta(),
            ocr=ocr,
            vision=vision,
            backend=_backend(),
        )
        skill._download_image = AsyncMock(return_value=b"fake")

        result = asyncio.get_event_loop().run_until_complete(skill.run(_context()))

        assert result.output["retake_suggested"] is False


class TestPG08:
    def test_identity_unredacted_excludes_from_rag(self):
        """AC-3: IDENTITY without redaction → rag_excluded."""
        ocr = _ocr_provider(text="", confidence=0.0)
        vision = _vision_provider(sensitivity_class="IDENTITY")

        skill = AnalyzeCapturedMedia(
            _meta(),
            ocr=ocr,
            vision=vision,
            backend=_backend(),
        )
        skill._download_image = AsyncMock(return_value=b"fake")

        result = asyncio.get_event_loop().run_until_complete(skill.run(_context()))

        assert result.output["rag_excluded"] is True

    def test_financial_unredacted_excludes_from_rag(self):
        ocr = _ocr_provider(text="", confidence=0.0)
        vision = _vision_provider(sensitivity_class="FINANCIAL")

        skill = AnalyzeCapturedMedia(
            _meta(),
            ocr=ocr,
            vision=vision,
            backend=_backend(),
        )
        skill._download_image = AsyncMock(return_value=b"fake")

        result = asyncio.get_event_loop().run_until_complete(skill.run(_context()))

        assert result.output["rag_excluded"] is True

    def test_general_not_excluded(self):
        ocr = _ocr_provider()
        vision = _vision_provider(sensitivity_class="GENERAL")

        skill = AnalyzeCapturedMedia(
            _meta(),
            ocr=ocr,
            vision=vision,
            backend=_backend(),
        )
        skill._download_image = AsyncMock(return_value=b"fake")

        result = asyncio.get_event_loop().run_until_complete(skill.run(_context()))

        assert result.output["rag_excluded"] is False

    def test_identity_with_redaction_not_excluded(self):
        """IDENTITY + redacted text → safe, NOT excluded."""
        ocr = _ocr_provider(text="Contact user@example.com")
        vision = _vision_provider(sensitivity_class="IDENTITY")

        skill = AnalyzeCapturedMedia(
            _meta(),
            ocr=ocr,
            vision=vision,
            backend=_backend(),
        )
        skill._download_image = AsyncMock(return_value=b"fake")

        result = asyncio.get_event_loop().run_until_complete(skill.run(_context()))

        assert result.output["rag_excluded"] is False
        assert result.output["redaction_applied"] is True


class TestDegradation:
    def test_both_down_enqueues_retry(self):
        """Both OCR and Vision down → queued_for_retry."""
        from app.providers.ocr import OCRUnavailable
        from app.providers.vision import VisionUnavailable

        ocr = AsyncMock()
        ocr.detect_text.side_effect = OCRUnavailable("down")
        vision = AsyncMock()
        vision.analyze.side_effect = VisionUnavailable("down")

        skill = AnalyzeCapturedMedia(
            _meta(),
            ocr=ocr,
            vision=vision,
            backend=_backend(),
        )
        skill._download_image = AsyncMock(return_value=b"fake")

        result = asyncio.get_event_loop().run_until_complete(skill.run(_context()))

        assert result.output["status"] == "queued_for_retry"
        assert result.output["degraded"] is True


class TestBackendWrite:
    def test_backend_called_with_correct_args(self):
        ocr = _ocr_provider()
        vision = _vision_provider(sensitivity_class="GENERAL")
        backend = _backend()

        skill = AnalyzeCapturedMedia(
            _meta(),
            ocr=ocr,
            vision=vision,
            backend=backend,
        )
        skill._download_image = AsyncMock(return_value=b"fake")

        asyncio.get_event_loop().run_until_complete(skill.run(_context()))

        backend.update_asset_ocr.assert_called_once()
        call_kwargs = backend.update_asset_ocr.call_args.kwargs
        assert call_kwargs["tenant_id"] == "t-1"
        assert call_kwargs["asset_id"] == 42
        assert call_kwargs["sensitivity_class"] == "GENERAL"
