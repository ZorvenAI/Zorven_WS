"""SKL-OIA-08 — Summarise a recording into key moments with timestamps.

Design §8.1 · implemented by story I-02.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable
from typing import Any, cast

from app.core.logging import get_logger

from app.cache.idempotency import IdempotencyGuard
from app.cache.redis_manager import RedisManager
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
        self._guard = IdempotencyGuard(redis) if redis is not None else None

    async def run(self, context: SkillContext) -> SkillResult:
        recording_id = context.input_context["recording_id"]
        session_id = context.input_context["session_id"]
        tenant_id = context.tenant_context.tenant_id
        started_at = float(context.input_context["started_at"])
        stopped_at = float(context.input_context["stopped_at"])

        if self._redis is None or self._llm is None:
            raise RuntimeError("SummarizeRecording requires llm and redis providers")

        assert self._guard is not None  # guaranteed by _redis check above
        cached = await self._guard.check(tenant_id, f"skl08:{recording_id}")
        if cached is not None and "transcript_segments" in cached:
            logger.info("summary_idempotent_hit", recording_id=recording_id)
            return SkillResult(skill_id=self.meta.skill_id, output=cached)

        segments = await self._read_transcript(
            tenant_id, session_id, started_at, stopped_at
        )
        coverage = compute_transcript_coverage(
            await self._read_markers(tenant_id, session_id),
            started_at,
            stopped_at,
        )
        if not coverage["complete"]:
            logger.warning(
                "summary_transcript_incomplete",
                recording_id=recording_id,
                missing_s=coverage["missing_s"],
                gaps=len(coverage["gaps"]),
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

        # Carried on the summary rather than as a new write-back field: the
        # summary dict is already persisted whole, so Django learns the
        # transcript is partial through the call it already makes.
        summary["transcript_coverage"] = coverage

        output: dict[str, Any] = {
            **summary,
            "transcript_segments": segments,
        }

        if self._backend is not None:
            await self._backend.update_recording_summary(
                tenant_id=tenant_id,
                recording_id=recording_id,
                summary=summary,
                transcript_segments=segments,
            )

            await self._guard.store(tenant_id, f"skl08:{recording_id}", output)

        return SkillResult(skill_id=self.meta.skill_id, output=output)

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
        raw_frames = await cast(
            "Awaitable[list[Any]]", self._redis.client.lrange(key, 0, -1)
        )
        return extract_transcript_segments(raw_frames, started_at, stopped_at)

    async def _read_markers(
        self, tenant_id: str, session_id: str
    ) -> list[dict[str, Any]]:
        """Interruption markers for this session (#662).

        Read straight from the key rather than through ``LiveSessionManager``:
        finalisation runs long after the socket is gone, usually on another
        Cloud Run instance, and there is no session object left to ask.
        """
        assert self._redis is not None
        keys = self._redis.keys_for(tenant_id)
        key = keys.live_markers(session_id)
        raw = await cast("Awaitable[list[Any]]", self._redis.client.lrange(key, 0, -1))
        markers: list[dict[str, Any]] = []
        for item in raw or []:
            try:
                parsed = json.loads(item)
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(parsed, dict) and isinstance(parsed.get("at"), (int, float)):
                markers.append(parsed)
        return markers

    @staticmethod
    def _format_transcript(segments: list[dict[str, Any]]) -> str:
        """Render the transcript for the summary prompt, attributed by role.

        Unattributed, the summary could not tell the operator's leading question
        from the business's answer — and the summary becomes an evidence block
        of its own, so "so you focus on wholesale?" could reach extraction as
        "the business focuses on wholesale", competing with the correctly
        attributed transcript block.

        Roles rather than names, for the reason ``build_speaker_labels``
        documents: the body has already had PERSON redacted out of it.
        """
        from app.logic.evidence_assembler import (
            attribute_segment,
            build_speaker_labels,
            label_for,
        )

        labels = build_speaker_labels(segments)
        lines: list[str] = []
        for seg in segments:
            t = seg["t_start"]
            m, s = divmod(int(t), 60)
            tag = "[REDACTED] " if seg.get("redaction_applied") else ""
            said = attribute_segment(seg["text"], label_for(labels, seg.get("speaker")))
            lines.append(f"[{m:02d}:{s:02d}] {tag}{said}")
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


# -- pure helpers (module-level for testability) ------------------------------


def compute_transcript_coverage(
    markers: list[dict[str, Any]],
    started_at: float,
    stopped_at: float,
) -> dict[str, Any]:
    """How much of the recording the transcript actually covers (#662).

    Derived from interruption markers, **never** from where the transcript
    happens to stop. The tempting rule -- "the last segment is far from
    ``stopped_at``, so the transcript is truncated" -- is wrong, and wrong in
    the direction that matters: an operator who says "thanks, I'll send that
    over" and stops the recording forty seconds later leaves a forty-second
    tail gap with nothing at all wrong. Labelling that recording's legal header
    partial is its own correctness bug, and a header that cries wolf is ignored
    exactly when it is right. Silence and a dead socket look identical from the
    transcript alone, so only a positive signal counts.

    An ``interrupted`` marker with no matching ``resumed`` ran to the end of
    the recording: the socket never came back.
    """
    span = max(0.0, stopped_at - started_at)
    gaps: list[dict[str, Any]] = []
    open_at: float | None = None
    open_reason = ""

    for marker in sorted(markers, key=lambda m: float(m.get("at", 0.0))):
        kind = marker.get("type")
        at = float(marker.get("at", 0.0))
        if kind == "transcript.interrupted":
            # Two interruptions with no resume between them are one gap: the
            # first is when transcription actually stopped.
            if open_at is None:
                open_at = at
                open_reason = str(marker.get("reason", "") or "")
        elif kind == "transcript.resumed" and open_at is not None:
            gaps.append({"from": open_at, "to": at, "reason": open_reason})
            open_at = None
            open_reason = ""

    if open_at is not None:
        gaps.append({"from": open_at, "to": stopped_at, "reason": open_reason})

    # Clamp into the recording window before measuring. A marker can land
    # outside it -- the socket teardown races the stop -- and an unclamped gap
    # could claim more missing time than the recording has.
    clamped: list[dict[str, Any]] = []
    missing = 0.0
    for gap in gaps:
        lo = max(started_at, min(float(gap["from"]), stopped_at))
        hi = max(started_at, min(float(gap["to"]), stopped_at))
        if hi - lo <= 0:
            continue
        clamped.append({"from": lo, "to": hi, "reason": gap["reason"]})
        missing += hi - lo

    missing = min(missing, span)
    return {
        "complete": not clamped,
        "gaps": clamped,
        "missing_s": round(missing, 3),
        "recording_s": round(span, 3),
    }


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
                # O-08 AC-1. The buffered frame has carried this since O-03;
                # dropping it here was why the persisted transcript held only
                # integer indices, so nothing downstream could name a speaker
                # even though the mics had already established who was talking.
                #
                # `.get` with no default, so a single-mic recording persists
                # null rather than a fabricated name (AC-2).
                "speaker_name": frame.get("speaker_name"),
                # The role, not the name, is what prompts are attributed by —
                # it distinguishes who asked from who answered without sending
                # a person's name to a model provider.
                "speaker_role": frame.get("speaker_role"),
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
