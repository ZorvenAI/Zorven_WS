"""SKL-OIA-07 — Describe and classify media captured during the meeting.

Design §8.1, §8.4 · implemented by stories H-03 (image) and H-04 (video).

Image path: download → preprocess → Cloud Vision OCR → Gemini semantic
→ PII redaction → PG-08 check → write back to Django → emit EVT-106.

Video path: download → ffmpeg keyframe extraction → perceptual hash dedup
→ per-frame Cloud Vision OCR → merge text with timestamps → Gemini
multi-frame semantic → PII redaction → PG-08 check → write back → EVT-106.
"""

from __future__ import annotations

import hashlib
import time
from typing import Any

from app.cache.redis_manager import TenantKeys
from app.core.config import get_settings
from app.core.logging import get_logger
from app.cache.retry_queue import OCRRetryItem, enqueue_retry
from app.events.catalog import EventType
from app.logic.preprocessing import preprocess_image
from app.logic.video_pipeline import (
    FrameOCRResult,
    dedup_frames,
    extract_keyframes,
    merge_ocr_texts,
)
from app.providers.ocr import OCRProvider, OCRResult, OCRUnavailable
from app.providers.vision import VisionProvider, VisionResult, VisionUnavailable
from app.services.backend_client import BackendClient
from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillResult
from app.skills.redact_pii import redact_text

logger = get_logger(__name__)

RETAKE_THRESHOLD = 0.5
DEGRADED_CONFIDENCE_CAP = 0.7
IDEMPOTENCY_TTL = 86400


class AnalyzeCapturedMedia(BaseSkill):
    """Describe and classify media captured during the meeting, including OCR."""

    def __init__(
        self,
        meta: Any,
        *,
        ocr: OCRProvider | None = None,
        vision: VisionProvider | None = None,
        backend: BackendClient | None = None,
    ) -> None:
        super().__init__(meta)
        self._ocr = ocr
        self._vision = vision
        self._backend = backend

    async def run(self, context: SkillContext) -> SkillResult:
        mime_type = context.input_context.get("mime_type", "image/jpeg")

        if mime_type.startswith("video/"):
            return await self._run_video_pipeline(context)
        return await self._run_image_pipeline(context)

    async def _run_image_pipeline(self, context: SkillContext) -> SkillResult:
        """Original image OCR path from H-03."""
        start_ms = int(time.time() * 1000)

        media_id = context.input_context.get("media_id", "")
        gcs_uri = context.input_context.get("gcs_uri", "")
        usage_tag = context.input_context.get("usage_tag", "other")
        tenant_id = context.tenant_context.tenant_id
        asset_id = context.input_context.get("asset_id")
        redis = context.input_context.get("redis")
        events = context.input_context.get("events")
        session_id = context.tenant_context.session_id

        keys = TenantKeys(tenant_id)

        idem_key = keys.idempotency(
            hashlib.sha256(f"ocr:{media_id}".encode()).hexdigest()[:16]
        )
        if redis:
            existing = await redis.get(idem_key)
            if existing:
                logger.info("ocr_idempotent_skip", media_id=media_id)
                return SkillResult(
                    skill_id=self.meta.skill_id,
                    output={"status": "already_processed", "media_id": media_id},
                )

        image_bytes = await self._download_media(gcs_uri)

        preprocessed = preprocess_image(image_bytes)

        ocr_result: OCRResult | None = None
        vision_result: VisionResult | None = None
        degraded = False

        assert self._ocr is not None
        assert self._vision is not None

        try:
            ocr_result = await self._ocr.detect_text(preprocessed)
        except (OCRUnavailable, Exception) as exc:
            logger.warning("ocr_unavailable", error=str(exc))
            try:
                vision_result = await self._vision.analyze(preprocessed, "")
                ocr_result = OCRResult(text="", confidence=0.0, pages=0)
                degraded = True
            except (VisionUnavailable, Exception):
                return await self._enqueue_and_degrade(
                    redis,
                    keys,
                    media_id,
                    gcs_uri,
                    usage_tag,
                    tenant_id,
                    start_ms,
                )

        if ocr_result and not vision_result:
            try:
                vision_result = await self._vision.analyze(
                    preprocessed, ocr_result.text
                )
            except (VisionUnavailable, Exception) as exc:
                logger.warning("vision_unavailable", error=str(exc))
                vision_result = VisionResult(
                    caption="Document capture",
                    doc_type="other",
                    sensitivity_class="GENERAL",
                )

        raw_text = ocr_result.text if ocr_result else ""
        confidence = ocr_result.confidence if ocr_result else 0.0
        if degraded:
            confidence = min(confidence, DEGRADED_CONFIDENCE_CAP)

        redaction = redact_text(raw_text) if raw_text else None
        redacted_text = redaction.text if redaction else ""
        redaction_applied = bool(redaction and redaction.applied)

        sensitivity_class = (
            vision_result.sensitivity_class if vision_result else "GENERAL"
        )
        doc_type = vision_result.doc_type if vision_result else "other"
        caption = vision_result.caption if vision_result else "Document capture"

        rag_excluded = False
        if sensitivity_class in ("IDENTITY", "FINANCIAL"):
            if not redaction_applied:
                rag_excluded = True

        if self._backend and asset_id:
            await self._backend.update_asset_ocr(
                tenant_id=tenant_id,
                asset_id=int(asset_id),
                ocr_text=redacted_text,
                ocr_confidence=confidence,
                sensitivity_class=sensitivity_class,
                rag_excluded=rag_excluded,
            )

        if redis:
            await redis.set(idem_key, "1", ex=IDEMPOTENCY_TTL)

        if events and session_id:
            try:
                await events.emit(
                    EventType.MEDIA_CAPTURED_ANALYZED,
                    tenant_id=tenant_id,
                    correlation_id=media_id,
                    session_id=session_id,
                    payload={
                        "media_id": media_id,
                        "usage_tag": usage_tag,
                        "ocr_confidence": confidence,
                        "sensitivity_class": sensitivity_class,
                        "doc_type": doc_type,
                        "rag_excluded": rag_excluded,
                    },
                    outcome="SUCCESS",
                )
            except Exception:
                logger.warning("evt106_emission_failed", media_id=media_id)

        duration_ms = int(time.time() * 1000) - start_ms

        return SkillResult(
            skill_id=self.meta.skill_id,
            output={
                "media_id": media_id,
                "ocr_text": redacted_text,
                "ocr_confidence": confidence,
                "caption": caption,
                "doc_type": doc_type,
                "usage_tag": usage_tag,
                "sensitivity_class": sensitivity_class,
                "rag_excluded": rag_excluded,
                "retake_suggested": confidence < RETAKE_THRESHOLD,
                "redaction_applied": redaction_applied,
                "degraded": degraded,
            },
            confidence=confidence,
            duration_ms=duration_ms,
        )

    async def _run_video_pipeline(self, context: SkillContext) -> SkillResult:
        """Video snippet OCR path from H-04."""
        start_ms = int(time.time() * 1000)
        settings = get_settings()

        media_id = context.input_context.get("media_id", "")
        gcs_uri = context.input_context.get("gcs_uri", "")
        usage_tag = context.input_context.get("usage_tag", "other")
        tenant_id = context.tenant_context.tenant_id
        asset_id = context.input_context.get("asset_id")
        redis = context.input_context.get("redis")
        events = context.input_context.get("events")
        session_id = context.tenant_context.session_id

        keys = TenantKeys(tenant_id)

        idem_key = keys.idempotency(
            hashlib.sha256(f"video_ocr:{media_id}".encode()).hexdigest()[:16]
        )
        if redis:
            existing = await redis.get(idem_key)
            if existing:
                logger.info("video_ocr_idempotent_skip", media_id=media_id)
                return SkillResult(
                    skill_id=self.meta.skill_id,
                    output={"status": "already_processed", "media_id": media_id},
                )

        video_bytes = await self._download_media(gcs_uri)

        frames = await extract_keyframes(
            video_bytes,
            fps=settings.VIDEO_FPS,
            max_frames=settings.VIDEO_MAX_FRAMES,
            max_duration_s=settings.VIDEO_MAX_DURATION_S,
        )

        if not frames:
            logger.warning("video_no_frames", media_id=media_id)
            duration_ms = int(time.time() * 1000) - start_ms
            return SkillResult(
                skill_id=self.meta.skill_id,
                output={
                    "media_id": media_id,
                    "ocr_text": "",
                    "ocr_confidence": 0.0,
                    "caption": "Video snippet (no readable frames)",
                    "doc_type": "other",
                    "usage_tag": usage_tag,
                    "sensitivity_class": "GENERAL",
                    "rag_excluded": False,
                    "retake_suggested": True,
                    "redaction_applied": False,
                    "degraded": False,
                },
                confidence=0.0,
                duration_ms=duration_ms,
            )

        unique_frames, reduction_ratio = dedup_frames(
            frames, threshold=settings.VIDEO_DEDUP_THRESHOLD
        )
        logger.info(
            "video_dedup_complete",
            media_id=media_id,
            total_frames=len(frames),
            unique_frames=len(unique_frames),
            reduction_ratio=reduction_ratio,
        )

        assert self._ocr is not None
        assert self._vision is not None

        frame_results: list[FrameOCRResult] = []
        degraded = False

        for frame in unique_frames:
            preprocessed = preprocess_image(frame.frame_bytes)
            try:
                ocr_result = await self._ocr.detect_text(preprocessed)
                frame_results.append(
                    FrameOCRResult(
                        timestamp_s=frame.timestamp_s,
                        text=ocr_result.text,
                        confidence=ocr_result.confidence,
                        frame_bytes=preprocessed,
                    )
                )
            except (OCRUnavailable, Exception) as exc:
                logger.warning(
                    "frame_ocr_failed",
                    media_id=media_id,
                    timestamp_s=frame.timestamp_s,
                    error=str(exc),
                )
                frame_results.append(
                    FrameOCRResult(
                        timestamp_s=frame.timestamp_s,
                        text="",
                        confidence=0.0,
                        frame_bytes=preprocessed,
                    )
                )
                degraded = True

        if not frame_results:
            return await self._enqueue_and_degrade(
                redis, keys, media_id, gcs_uri, usage_tag, tenant_id, start_ms
            )

        merged_text, avg_confidence = merge_ocr_texts(frame_results)

        best_frames = sorted(
            [fr for fr in frame_results if fr.text.strip()],
            key=lambda fr: fr.confidence,
            reverse=True,
        )[:4]
        if not best_frames:
            best_frames = frame_results[:4]

        try:
            vision_result = await self._vision.analyze_multi(
                [fr.frame_bytes for fr in best_frames],
                merged_text,
            )
        except (VisionUnavailable, Exception) as exc:
            logger.warning("video_vision_unavailable", error=str(exc))
            vision_result = VisionResult(
                caption="Video snippet",
                doc_type="other",
                sensitivity_class="GENERAL",
            )

        redaction = redact_text(merged_text) if merged_text else None
        redacted_text = redaction.text if redaction else ""
        redaction_applied = bool(redaction and redaction.applied)

        sensitivity_class = vision_result.sensitivity_class
        doc_type = vision_result.doc_type
        caption = vision_result.caption

        confidence = avg_confidence
        if degraded:
            confidence = min(confidence, DEGRADED_CONFIDENCE_CAP)

        rag_excluded = False
        if sensitivity_class in ("IDENTITY", "FINANCIAL"):
            if not redaction_applied:
                rag_excluded = True

        if self._backend and asset_id:
            await self._backend.update_asset_ocr(
                tenant_id=tenant_id,
                asset_id=int(asset_id),
                ocr_text=redacted_text,
                ocr_confidence=confidence,
                sensitivity_class=sensitivity_class,
                rag_excluded=rag_excluded,
            )

        if redis:
            await redis.set(idem_key, "1", ex=IDEMPOTENCY_TTL)

        if events and session_id:
            try:
                await events.emit(
                    EventType.MEDIA_CAPTURED_ANALYZED,
                    tenant_id=tenant_id,
                    correlation_id=media_id,
                    session_id=session_id,
                    payload={
                        "media_id": media_id,
                        "usage_tag": usage_tag,
                        "ocr_confidence": confidence,
                        "sensitivity_class": sensitivity_class,
                        "doc_type": doc_type,
                        "rag_excluded": rag_excluded,
                    },
                    outcome="SUCCESS",
                )
            except Exception:
                logger.warning("evt106_emission_failed", media_id=media_id)

        duration_ms = int(time.time() * 1000) - start_ms

        return SkillResult(
            skill_id=self.meta.skill_id,
            output={
                "media_id": media_id,
                "ocr_text": redacted_text,
                "ocr_confidence": confidence,
                "caption": caption,
                "doc_type": doc_type,
                "usage_tag": usage_tag,
                "sensitivity_class": sensitivity_class,
                "rag_excluded": rag_excluded,
                "retake_suggested": confidence < RETAKE_THRESHOLD,
                "redaction_applied": redaction_applied,
                "degraded": degraded,
            },
            confidence=confidence,
            duration_ms=duration_ms,
        )

    async def _download_media(self, gcs_uri: str) -> bytes:
        """Download from GCS using the client library directly."""
        from google.cloud.storage import Client

        if not gcs_uri.startswith("gs://"):
            raise ValueError(f"Invalid GCS URI: {gcs_uri}")

        parts = gcs_uri[5:].split("/", 1)
        bucket_name = parts[0]
        blob_path = parts[1] if len(parts) > 1 else ""

        client = Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_path)
        return bytes(blob.download_as_bytes())

    async def _enqueue_and_degrade(
        self,
        redis: Any,
        keys: TenantKeys,
        media_id: str,
        gcs_uri: str,
        usage_tag: str,
        tenant_id: str,
        start_ms: int,
    ) -> SkillResult:
        """Both OCR and Vision are down — queue for retry."""
        if redis:
            item = OCRRetryItem(
                media_id=media_id,
                gcs_uri=gcs_uri,
                usage_tag=usage_tag,
                tenant_id=tenant_id,
            )
            await enqueue_retry(redis, keys, item)

        duration_ms = int(time.time() * 1000) - start_ms
        return SkillResult(
            skill_id=self.meta.skill_id,
            output={
                "media_id": media_id,
                "status": "queued_for_retry",
                "degraded": True,
            },
            confidence=0.0,
            duration_ms=duration_ms,
        )
