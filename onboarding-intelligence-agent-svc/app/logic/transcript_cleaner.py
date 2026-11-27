"""T2 — concurrent background cleaner for raw transcript segments.

Uses full-transcript re-cleaning: each cycle reads ALL T1 segments
and produces a complete cleaned version that replaces the previous one.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Callable, Awaitable

from app.logic.live_session import frames_for_latest_recording
from app.cache.redis_manager import RedisManager, TenantKeys, TTL_SESSION
from app.core.logging import get_logger
from app.providers.llm import LLMProvider, LLMUnavailable
from app.providers.storage import StorageProvider

logger = get_logger(__name__)

LANDING_PREFIX = "_landing/oia"

CLEAN_PROMPT = """\
You are a professional meeting transcript editor. Clean the following raw
speech-to-text transcript. Rules:

1. Remove filler words (um, uh, like, you know, so, basically)
2. Remove false starts and self-corrections (keep only the corrected version)
3. Remove repetitions (keep only one instance)
4. Fix obvious STT errors where context makes the intended word clear
5. Preserve the speaker's exact meaning — do not add, remove, or rephrase ideas
6. Preserve speaker labels and chronological order
7. Maintain domain-specific terms, proper nouns, numbers, and dates exactly
8. Produce clean, grammatically correct sentences
9. Do NOT summarize — the output should be the same conversation, just cleaner

Speaker labels: {speaker_map}

Raw transcript:
{raw_text}

Cleaned transcript:"""


class TranscriptCleaner:
    """T2 — concurrent background cleaner for raw transcript segments."""

    def __init__(
        self,
        redis: RedisManager,
        keys: TenantKeys,
        session_id: str,
        llm: LLMProvider,
        storage: StorageProvider,
        settings: Any,
        send_ws: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    ) -> None:
        self._redis = redis
        self._keys = keys
        self._session_id = session_id
        self._llm = llm
        self._storage = storage
        self._settings = settings
        self._send_ws = send_ws
        self._last_segment_count = 0
        self._clean_text: str = ""
        self._version = 0

    async def run(self, cancel: asyncio.Event) -> None:
        """LIVE mode loop: read all T1 -> re-clean full transcript -> write T2."""
        interval = getattr(self._settings, "CLEAN_INTERVAL_S", 30)
        min_segments = getattr(self._settings, "CLEAN_MIN_SEGMENTS", 5)
        model = getattr(self._settings, "CLEAN_MODEL", None) or None

        while not cancel.is_set():
            try:
                await asyncio.wait_for(cancel.wait(), timeout=interval)
                break
            except asyncio.TimeoutError:
                pass

            try:
                all_segments = await self._read_all_raw_segments()
                if len(all_segments) < min_segments:
                    continue
                if len(all_segments) == self._last_segment_count:
                    continue
                self._last_segment_count = len(all_segments)

                cleaned = await self._clean_full(all_segments, model=model)
                if cleaned:
                    self._clean_text = cleaned
                    self._version += 1
                    await self._write_clean(cleaned)
                    await self._push_progress(len(all_segments))
            except LLMUnavailable:
                logger.warning(
                    "t2_llm_unavailable",
                    session_id=self._session_id,
                )
            except Exception:
                logger.exception(
                    "t2_clean_cycle_error",
                    session_id=self._session_id,
                )

    async def finalize(self) -> None:
        """Final re-clean of complete transcript and flush to GCS."""
        model = getattr(self._settings, "CLEAN_MODEL", None) or None
        try:
            all_segments = await self._read_all_raw_segments()
            if all_segments:
                cleaned = await self._clean_full(all_segments, model=model)
                if cleaned:
                    self._clean_text = cleaned
                    self._version += 1
                    await self._write_clean(cleaned)
        except (LLMUnavailable, Exception):
            logger.exception(
                "t2_finalize_llm_error",
                session_id=self._session_id,
            )

        await self._flush_to_gcs()

    async def run_batch(self, raw_segments: list[dict[str, Any]]) -> str:
        """PROCESS mode: single-pass clean of a complete transcript."""
        model = getattr(self._settings, "CLEAN_MODEL", None) or None
        cleaned = await self._clean_full(raw_segments, model=model)
        return cleaned or ""

    async def _read_all_raw_segments(self) -> list[dict[str, Any]]:
        key = self._keys.transcript(self._session_id)
        raw = await self._redis.client.lrange(key, 0, -1)
        segments: list[dict[str, Any]] = []
        for item in raw or []:
            try:
                parsed = json.loads(item)
                if isinstance(parsed, dict):
                    segments.append(parsed)
            except (json.JSONDecodeError, TypeError):
                continue
        return frames_for_latest_recording(segments)

    async def _clean_full(
        self,
        segments: list[dict[str, Any]],
        *,
        model: str | None = None,
    ) -> str:
        raw_text = self._segments_to_text(segments)
        if not raw_text.strip():
            return ""

        speaker_map = self._extract_speaker_map(segments)
        prompt = CLEAN_PROMPT.format(
            speaker_map=speaker_map,
            raw_text=raw_text,
        )

        timeout = getattr(self._settings, "ANALYSIS_TIMEOUT_S", 15.0)
        return await asyncio.wait_for(
            self._llm.generate(prompt, temperature=0.1, model=model),
            timeout=timeout * 4,
        )

    async def _write_clean(self, cleaned: str) -> None:
        key = self._keys.transcript_clean(self._session_id)
        version_key = self._keys.clean_version(self._session_id)
        pipe = self._redis.client.pipeline(transaction=False)
        pipe.set(key, cleaned, ex=TTL_SESSION)
        pipe.set(version_key, str(self._version), ex=TTL_SESSION)
        await pipe.execute()

    async def _push_progress(self, total_segments: int) -> None:
        if not self._send_ws:
            return
        try:
            await self._send_ws(
                {
                    "type": "transcript.clean_progress",
                    "segments_total": total_segments,
                    "version": self._version,
                    "preview": self._clean_text[:500] if self._clean_text else "",
                }
            )
        except Exception:
            pass

    async def _flush_to_gcs(self) -> None:
        if not self._clean_text:
            return
        path = self.gcs_path
        try:
            self._storage._breaker.before_call()
        except Exception:
            logger.warning(
                "t2_gcs_breaker_open",
                session_id=self._session_id,
            )
            return

        try:
            content = json.dumps(
                {
                    "version": self._version,
                    "text": self._clean_text,
                }
            )
            bucket = self._storage._ensure_bucket()
            blob = bucket.blob(path)
            await asyncio.to_thread(
                blob.upload_from_string,
                content,
                content_type="application/json",
            )
            self._storage._breaker.record_success()
            logger.info(
                "t2_gcs_uploaded",
                session_id=self._session_id,
                path=path,
            )
        except Exception:
            self._storage._breaker.record_failure()
            logger.warning(
                "t2_gcs_upload_failed",
                session_id=self._session_id,
            )

    @staticmethod
    def _segments_to_text(segments: list[dict[str, Any]]) -> str:
        lines: list[str] = []
        for seg in segments:
            speaker = seg.get("speaker_name") or seg.get("speaker") or "Unknown"
            text = seg.get("text", "")
            if text:
                lines.append(f"{speaker}: {text}")
        return "\n".join(lines)

    @staticmethod
    def _extract_speaker_map(segments: list[dict[str, Any]]) -> str:
        speakers: dict[str, str] = {}
        for seg in segments:
            name = seg.get("speaker_name") or seg.get("speaker") or "Unknown"
            role = seg.get("speaker_role", "")
            if name not in speakers:
                speakers[name] = role
        parts = [
            f"{name} ({role})" if role else name for name, role in speakers.items()
        ]
        return ", ".join(parts) if parts else "Unknown speakers"

    @property
    def clean_text(self) -> str:
        return self._clean_text

    @property
    def version(self) -> int:
        return self._version

    @property
    def gcs_path(self) -> str:
        tenant_id = self._keys.tenant_id
        return (
            f"{LANDING_PREFIX}/{tenant_id}/{self._session_id}" f"/transcript/clean.json"
        )
