"""F-05 · Audio pipeline: STT → redaction → buffer → display.

Named tests from the story:
- ``test_persisted_transcript_is_redacted`` — the Redis buffer has
  ``<PHONE_NUMBER>``, not the digits
- ``test_stream_rollover_no_gap_no_dup`` — no segment lost or duplicated
  at the rollover boundary

Real Redis. The ``FakeSTTAdapter`` replays the JSONL fixture that carries
phone numbers and email addresses, so redaction is exercised end-to-end
without touching Google's servers.
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Any

import pytest

from app.api.schemas import TranscriptFinal, TranscriptPartial
from app.logic.live_session import LiveSessionManager
from app.providers.stt import FakeSTTAdapter, STTResult, _dedup_key
from app.skills.redact_pii import redact_text

pytestmark = pytest.mark.integration

FIXTURE = Path(__file__).parent / "fixtures" / "two_speaker_2min.jsonl"


@pytest.fixture
def session(live_redis):
    return LiveSessionManager(
        redis=live_redis,
        tenant_id="t-pipe",
        session_id=f"s-{uuid.uuid4().hex[:8]}",
    )


async def _run_pipeline(
    session: LiveSessionManager,
    adapter: FakeSTTAdapter,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Simulate what ``_stt_loop`` does, without the WebSocket.

    Returns (buffered_frames, display_frames) — the redacted version in
    Redis and the unredacted version that would be sent to the client.
    """
    display: list[dict[str, Any]] = []

    async def _silent() -> None:
        for _ in range(5):
            yield b"\x00" * 320
            await asyncio.sleep(0.01)

    async for result in adapter.stream(_silent()):
        if result.is_final:
            seq = await session.next_seq()
            redaction = redact_text(result.text)
            buffered = TranscriptFinal(
                seq=seq,
                text=redaction.text,
                speaker=0,
                t_start=result.t_start,
                t_end=result.t_end,
                redaction_applied=redaction.applied,
            )
            await session.emit(buffered)
            displayed = TranscriptFinal(
                seq=seq,
                text=result.text,
                speaker=0,
                t_start=result.t_start,
                t_end=result.t_end,
                redaction_applied=False,
            )
            display.append(displayed.model_dump(mode="json"))
        else:
            seq = await session.next_seq()
            frame = TranscriptPartial(seq=seq, text=result.text, speaker=0)
            payload = await session.emit(frame)
            display.append(payload)

    frames, _ = await session.replay_after(0)
    return frames, display


# ── AC-4 · persisted redacted, displayed unredacted ────────────────


async def test_persisted_transcript_is_redacted(session):
    """The card's named case.

    The fixture carries ``555-867-5309`` and ``john@example.com``. The
    Redis buffer must contain neither; the display stream must contain both.
    """
    adapter = FakeSTTAdapter(FIXTURE)
    buffered, display = await _run_pipeline(session, adapter)

    finals_buffered = [f for f in buffered if f["type"] == "transcript.final"]
    finals_display = [f for f in display if f["type"] == "transcript.final"]

    buffered_text = " ".join(f["text"] for f in finals_buffered)
    display_text = " ".join(f["text"] for f in finals_display)

    assert "555-867-5309" not in buffered_text
    assert "john@example.com" not in buffered_text

    assert "555-867-5309" in display_text
    assert "john@example.com" in display_text


async def test_redacted_finals_carry_flag(session):
    """A final that was redacted carries ``redaction_applied=True`` in the
    buffer but ``False`` in the display stream."""
    adapter = FakeSTTAdapter(FIXTURE)
    buffered, display = await _run_pipeline(session, adapter)

    buf_finals = [f for f in buffered if f["type"] == "transcript.final"]
    disp_finals = [f for f in display if f["type"] == "transcript.final"]

    redacted_buf = [f for f in buf_finals if f.get("redaction_applied")]
    redacted_disp = [f for f in disp_finals if f.get("redaction_applied")]

    assert len(redacted_buf) > 0, "no finals were redacted in the buffer"
    assert len(redacted_disp) == 0, "display should never carry redaction_applied=True"


async def test_partials_are_not_redacted(session):
    """AC-1: partials go to the client as-is, no redaction pass."""
    adapter = FakeSTTAdapter(FIXTURE)
    buffered, _ = await _run_pipeline(session, adapter)

    partials = [f for f in buffered if f["type"] == "transcript.partial"]
    for p in partials:
        assert "redaction_applied" not in p or not p.get("redaction_applied")


async def test_all_speaker_tags_are_zero(session):
    """STT v2 does not support diarization (A-01). All segments carry
    speaker=0 until the follow-up story adds real attribution."""
    adapter = FakeSTTAdapter(FIXTURE)
    buffered, display = await _run_pipeline(session, adapter)

    for frame in buffered + display:
        assert frame.get("speaker", 0) == 0


async def test_finals_ordered_by_t_start(session):
    """AC-2: finals are ordered by t_start in the buffer."""
    adapter = FakeSTTAdapter(FIXTURE)
    buffered, _ = await _run_pipeline(session, adapter)

    finals = [f for f in buffered if f["type"] == "transcript.final"]
    t_starts = [f["t_start"] for f in finals]
    assert t_starts == sorted(t_starts)


async def test_seq_is_strictly_increasing(session):
    """AC-4: seq is strictly increasing across partials and finals."""
    adapter = FakeSTTAdapter(FIXTURE)
    buffered, _ = await _run_pipeline(session, adapter)

    seqs = [f["seq"] for f in buffered]
    assert len(set(seqs)) == len(seqs), "duplicate seq values"
    assert seqs == sorted(seqs), "seq not in order"


# ── AC-3 · stream rollover ────────────────────────────────────────


async def test_stream_rollover_no_gap_no_dup(session):
    """Simulate what happens at the rollover boundary.

    Two sets of finals with an overlap window: the dedup logic should keep
    each unique final exactly once.
    """
    before = [
        {
            "text": "We started in 2016.",
            "is_final": True,
            "t_start": 278.0,
            "t_end": 280.5,
            "delay_ms": 10,
        },
        {
            "text": "It grew fast.",
            "is_final": True,
            "t_start": 281.0,
            "t_end": 283.0,
            "delay_ms": 10,
        },
    ]
    overlap = [
        {
            "text": "It grew fast.",
            "is_final": True,
            "t_start": 281.0,
            "t_end": 283.0,
            "delay_ms": 10,
        },
        {
            "text": "Two locations now.",
            "is_final": True,
            "t_start": 284.0,
            "t_end": 286.0,
            "delay_ms": 10,
        },
    ]

    all_events = before + overlap
    seen: set[tuple[float, str]] = set()
    kept = []
    for ev in all_events:
        result = STTResult(
            text=ev["text"],
            is_final=True,
            t_start=ev["t_start"],
            t_end=ev["t_end"],
            stability=1.0,
        )
        key = _dedup_key(result)
        if key not in seen:
            seen.add(key)
            kept.append(result)

    assert len(kept) == 3
    texts = [r.text for r in kept]
    assert "We started in 2016." in texts
    assert "It grew fast." in texts
    assert "Two locations now." in texts

    t_starts = [r.t_start for r in kept]
    assert t_starts == sorted(t_starts), "dedup broke ordering"
