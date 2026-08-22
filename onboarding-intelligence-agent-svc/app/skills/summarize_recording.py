"""SKL-OIA-08 — Summarise a recording into key moments with timestamps.

Design §8.1 · implemented by story I-02.
"""

from __future__ import annotations

import json
from typing import Any

from app.core.logging import get_logger

from app.cache.redis_manager import RedisManager, TTL_IDEMPOTENCY
from app.providers.llm import LLMProvider
from app.services.backend_client import BackendClient
from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillResult

logger = get_logger(__name__)

PROMPT_TEMPLATE = """\
You are summarising an onboarding meeting recording for a brand-building \
platform. The transcript below has been processed for privacy: segments \
containing personal information have had those values replaced with markers \
like [PHONE_NUMBER], [EMAIL_ADDRESS], [PERSON_NAME], etc.

Produce a JSON object with exactly two keys:

1. "text": A concise summary (2-4 paragraphs) of the conversation. Where a \
redaction marker appears and the redacted content was material to the \
conversation, note what kind of information was shared — for example, \
"The brand owner shared contact information (redacted for privacy)" — \
rather than silently omitting it.

2. "key_moments": An array of objects, each with:
   - "t": The timestamp in seconds (float) from the transcript where the \
moment begins.
   - "label": A short, descriptive label in the operator's language — \
"founding story", "budget discussion", "target audience", "brand vision". \
NOT a timestamp repeated as text. NOT a direct quote. The label is the \
retrieval affordance: it must tell the reader what they will hear if they \
click it.

Return ONLY valid JSON. No markdown fences, no commentary.

TRANSCRIPT:
{transcript}
"""


class SummarizeRecording(BaseSkill):
    """Summarise a recording into key moments with timestamps."""

    def __init__(
        self,
        meta: Any,
        *,
        llm: LLMProvider | None = None,
        backend: BackendClient | None = None,
        redis: RedisManager | None = None,
    ) -> None:
        super().__init__(meta)
        self._llm = llm
        self._backend = backend
        self._redis = redis

    async def run(self, context: SkillContext) -> SkillResult:
        recording_id = context.input_context["recording_id"]
        session_id = context.input_context["session_id"]
        tenant_id = context.tenant_context.tenant_id
        started_at = float(context.input_context["started_at"])
        stopped_at = float(context.input_context["stopped_at"])

        if self._redis is None or self._llm is None:
            raise RuntimeError("SummarizeRecording requires llm and redis providers")

        cached = await self._check_idempotency(tenant_id, recording_id)
        if cached is not None:
            logger.info("summary_idempotent_hit", recording_id=recording_id)
            return SkillResult(skill_id=self.meta.skill_id, output=cached)

        segments = await self._read_transcript(
            tenant_id, session_id, started_at, stopped_at
        )
        if not segments:
            logger.warning("summary_no_transcript", recording_id=recording_id)
            summary: dict[str, Any] = {
                "text": "No transcript available for this recording.",
                "key_moments": [],
            }
        else:
            transcript_text = self._format_transcript(segments)
            prompt = PROMPT_TEMPLATE.format(transcript=transcript_text)
            raw = await self._llm.generate(prompt, temperature=0.2)
            summary = self._parse_response(raw, segments)

        if self._backend is not None:
            await self._backend.update_recording_summary(
                tenant_id=tenant_id,
                recording_id=recording_id,
                summary=summary,
            )

        await self._store_idempotency(tenant_id, recording_id, summary)

        return SkillResult(skill_id=self.meta.skill_id, output=summary)

    # -- transcript assembly --------------------------------------------------

    async def _read_transcript(
        self,
        tenant_id: str,
        session_id: str,
        started_at: float,
        stopped_at: float,
    ) -> list[dict[str, Any]]:
        assert self._redis is not None
        keys = self._redis.keys_for(tenant_id)
        key = keys.live_frames(session_id)
        raw_frames = await self._redis.client.lrange(key, 0, -1)
        return extract_transcript_segments(raw_frames, started_at, stopped_at)

    @staticmethod
    def _format_transcript(segments: list[dict[str, Any]]) -> str:
        lines: list[str] = []
        for seg in segments:
            t = seg["t_start"]
            m, s = divmod(int(t), 60)
            tag = "[REDACTED] " if seg.get("redaction_applied") else ""
            lines.append(f"[{m:02d}:{s:02d}] {tag}{seg['text']}")
        return "\n".join(lines)

    # -- LLM response parsing -------------------------------------------------

    @staticmethod
    def _parse_response(raw: str, segments: list[dict[str, Any]]) -> dict[str, Any]:
        try:
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned
                if cleaned.endswith("```"):
                    cleaned = cleaned[: -len("```")]
                cleaned = cleaned.strip()

            parsed = json.loads(cleaned)
        except (json.JSONDecodeError, ValueError):
            logger.warning("summary_parse_failed", raw_len=len(raw))
            text = "\n".join(seg["text"] for seg in segments)
            return {"text": text, "key_moments": []}

        text = parsed.get("text", "")
        raw_moments = parsed.get("key_moments", [])

        moments: list[dict[str, Any]] = []
        seg_times = [s["t_start"] for s in segments]
        for km in raw_moments:
            if not isinstance(km, dict):
                continue
            t = km.get("t")
            label = km.get("label", "")
            if t is None or not label:
                continue
            snapped = _snap_to_boundary(float(t), seg_times)
            moments.append({"t": snapped, "label": str(label)})

        return {"text": str(text), "key_moments": moments}

    # -- idempotency -----------------------------------------------------------

    async def _check_idempotency(
        self, tenant_id: str, recording_id: str
    ) -> dict[str, Any] | None:
        assert self._redis is not None
        keys = self._redis.keys_for(tenant_id)
        key = keys.idempotency(f"skl08:{recording_id}")
        raw = await self._redis.client.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None

    async def _store_idempotency(
        self, tenant_id: str, recording_id: str, summary: dict[str, Any]
    ) -> None:
        assert self._redis is not None
        keys = self._redis.keys_for(tenant_id)
        key = keys.idempotency(f"skl08:{recording_id}")
        await self._redis.client.set(key, json.dumps(summary), ex=TTL_IDEMPOTENCY)


# -- pure helpers (module-level for testability) ------------------------------


def extract_transcript_segments(
    raw_frames: list[bytes | str],
    started_at: float,
    stopped_at: float,
) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    for raw in raw_frames:
        try:
            frame = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        if frame.get("type") != "transcript.final":
            continue
        t_start = frame.get("t_start")
        t_end = frame.get("t_end")
        if t_start is None or t_end is None:
            continue
        if t_start < started_at or t_end > stopped_at:
            continue
        segments.append(
            {
                "text": frame.get("text", ""),
                "speaker": frame.get("speaker", 0),
                "t_start": float(t_start),
                "t_end": float(t_end),
                "redaction_applied": frame.get("redaction_applied", False),
            }
        )
    segments.sort(key=lambda s: s["t_start"])
    return segments


def _snap_to_boundary(t: float, seg_times: list[float]) -> float:
    if not seg_times:
        return t
    closest = min(seg_times, key=lambda s: abs(s - t))
    return closest
