"""T3 — concurrent background description generator from clean transcript.

Regenerates the full description each cycle because a description is a
holistic document, not a stream of segments.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Callable, Awaitable

from app.cache.redis_manager import RedisManager, TenantKeys, TTL_SESSION
from app.core.logging import get_logger
from app.providers.llm import LLMProvider, LLMUnavailable
from app.providers.storage import StorageProvider

logger = get_logger(__name__)

LANDING_PREFIX = "_landing/oia"

DESCRIPTION_PROMPT = """\
You are an expert brand strategist reviewing an onboarding conversation.
From the transcript below, produce a structured brand-building brief that
a growth manager can act on. This is NOT a summary — it is the actionable
outcome of the onboarding.

Structure your output with these sections (omit any section with no evidence):

## Business Identity
Company name, industry, location, founding story, years in operation.

## Products & Services
What they offer, pricing model, delivery method, differentiators.

## Target Audience
Who they serve: demographics, psychographics, buying behaviour.

## Brand Aspirations
Desired positioning, tone, values, personality traits they want to project.

## Competitive Landscape
Named competitors, how the customer differentiates, market gaps they see.

## Marketing Goals
Channels they want to use, campaign ideas, budget constraints, timeline.

## Customer Pain Points
Problems their customers face, unmet needs, friction in current experience.

## Success Metrics
How they measure success, KPIs, growth targets, revenue goals.

For each section, cite the speaker and approximate timestamp. If the customer
was unclear or contradictory on a point, flag it as "needs clarification"
rather than guessing.

Transcript:
{clean_transcript}"""


class DescriptionGenerator:
    """T3 — concurrent background description generator from clean transcript."""

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
        self._description: str = ""
        self._version = 0

    async def run(self, cancel: asyncio.Event) -> None:
        """LIVE mode loop: accumulate T2 -> regenerate description."""
        interval = getattr(self._settings, "DESCRIPTION_INTERVAL_S", 60)
        min_chars = getattr(self._settings, "DESCRIPTION_MIN_CHARS", 200)
        model = getattr(self._settings, "DESCRIPTION_MODEL", None) or None

        while not cancel.is_set():
            try:
                await asyncio.wait_for(cancel.wait(), timeout=interval)
                break
            except asyncio.TimeoutError:
                pass

            try:
                clean_text = await self._read_clean_transcript()
                if len(clean_text) < min_chars:
                    continue

                description = await self._generate(clean_text, model=model)
                if description:
                    self._description = description
                    self._version += 1
                    await self._write_description(description)
                    await self._push_update()
            except LLMUnavailable:
                logger.warning(
                    "t3_llm_unavailable",
                    session_id=self._session_id,
                )
            except Exception:
                logger.exception(
                    "t3_desc_cycle_error",
                    session_id=self._session_id,
                )

    async def finalize(self) -> None:
        """Final generation with complete clean transcript, flush to GCS."""
        model = getattr(self._settings, "DESCRIPTION_MODEL", None) or None
        try:
            clean_text = await self._read_clean_transcript()
            if clean_text:
                description = await self._generate(clean_text, model=model)
                if description:
                    self._description = description
                    self._version += 1
                    await self._write_description(description)
        except (LLMUnavailable, Exception):
            logger.exception(
                "t3_finalize_llm_error",
                session_id=self._session_id,
            )

        await self._flush_to_gcs()

    async def run_batch(self, clean_transcript: str) -> str:
        """PROCESS mode: single-pass description from a complete clean transcript."""
        model = getattr(self._settings, "DESCRIPTION_MODEL", None) or None
        description = await self._generate(clean_transcript, model=model)
        return description or ""

    async def _read_clean_transcript(self) -> str:
        key = self._keys.transcript_clean(self._session_id)
        value = await self._redis.client.get(key)
        if value is None:
            return ""
        if isinstance(value, bytes):
            return value.decode("utf-8")
        return str(value)

    async def _generate(
        self,
        clean_transcript: str,
        *,
        model: str | None = None,
    ) -> str:
        if not clean_transcript.strip():
            return ""

        prompt = DESCRIPTION_PROMPT.format(clean_transcript=clean_transcript)

        timeout = getattr(self._settings, "ANALYSIS_TIMEOUT_S", 15.0)
        return await asyncio.wait_for(
            self._llm.generate(prompt, temperature=0.2, model=model),
            timeout=timeout * 4,
        )

    async def _write_description(self, description: str) -> None:
        key = self._keys.description(self._session_id)
        version_key = self._keys.desc_version(self._session_id)
        pipe = self._redis.client.pipeline(transaction=False)
        pipe.set(key, description, ex=TTL_SESSION)
        pipe.set(version_key, str(self._version), ex=TTL_SESSION)
        await pipe.execute()

    async def _push_update(self) -> None:
        if not self._send_ws:
            return
        try:
            await self._send_ws(
                {
                    "type": "description.updated",
                    "version": self._version,
                    "description": self._description,
                }
            )
        except Exception:
            pass

    async def _flush_to_gcs(self) -> None:
        if not self._description:
            return
        path = self.gcs_path
        try:
            self._storage._breaker.before_call()
        except Exception:
            logger.warning(
                "t3_gcs_breaker_open",
                session_id=self._session_id,
            )
            return

        try:
            content = json.dumps(
                {
                    "version": self._version,
                    "text": self._description,
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
                "t3_gcs_uploaded",
                session_id=self._session_id,
                path=path,
            )
        except Exception:
            self._storage._breaker.record_failure()
            logger.warning(
                "t3_gcs_upload_failed",
                session_id=self._session_id,
            )

    @property
    def description_text(self) -> str:
        return self._description

    @property
    def version(self) -> int:
        return self._version

    @property
    def gcs_path(self) -> str:
        tenant_id = self._keys.tenant_id
        return (
            f"{LANDING_PREFIX}/{tenant_id}/{self._session_id}"
            f"/transcript/description.json"
        )
