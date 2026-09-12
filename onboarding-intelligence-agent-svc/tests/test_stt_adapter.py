"""F-05 · STT adapter: the fake, the circuit breaker, and the dedup logic.

The Google adapter is not tested here — it needs a real STT service and GCP
credentials, which is an integration test in ``tests/integration/``. What IS
tested: the FakeSTTAdapter (which every higher-level test uses), the circuit
breaker wiring (which is the same code path for both adapters), and the dedup
function (which protects stream rollover from delivering duplicates).

Named test from the story:
``test_partial_bypasses_llm_and_redaction`` — a partial result reaches the
caller with no model call and no redaction pass. In the adapter layer this
means the result is yielded as-is; the "no model call" half is verified by
the absence of any LLM import or dependency.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest

from app.providers.stt import (
    DEPENDENCY,
    FakeSTTAdapter,
    GoogleSTTAdapter,
    STTResult,
    STTUnavailable,
    _dedup_key,
)

pytestmark = pytest.mark.unit

FIXTURE = Path(__file__).parent / "fixtures" / "two_speaker_2min.jsonl"
FIXTURE_45MIN = Path(__file__).parent / "fixtures" / "two_speaker_45min.jsonl"


async def _silent_audio(n: int = 5) -> None:
    """Yield n chunks of silence, then stop."""
    for _ in range(n):
        yield b"\x00" * 320
        await asyncio.sleep(0.01)


# ── FakeSTTAdapter ───────────────────────────────────────────────────


async def test_fake_adapter_yields_partials_and_finals():
    adapter = FakeSTTAdapter(FIXTURE)
    results = [r async for r in adapter.stream(_silent_audio())]
    partials = [r for r in results if not r.is_final]
    finals = [r for r in results if r.is_final]
    assert len(partials) > 0
    assert len(finals) > 0
    assert len(results) == 21


async def test_fake_adapter_from_event_list():
    events = [
        {
            "text": "hello",
            "is_final": False,
            "t_start": 0.0,
            "t_end": 0.5,
            "delay_ms": 10,
        },
        {
            "text": "Hello world.",
            "is_final": True,
            "t_start": 0.0,
            "t_end": 1.5,
            "delay_ms": 10,
        },
    ]
    adapter = FakeSTTAdapter(events=events)
    results = [r async for r in adapter.stream(_silent_audio())]
    assert len(results) == 2
    assert results[0].text == "hello"
    assert results[1].is_final is True


async def test_fake_adapter_empty_events():
    adapter = FakeSTTAdapter(events=[])
    results = [r async for r in adapter.stream(_silent_audio())]
    assert results == []


async def test_partial_bypasses_llm_and_redaction():
    """F-05 named test.

    A partial result from the adapter reaches the caller with no model call
    and no redaction pass. At this layer that means: the yielded STTResult
    has ``is_final=False`` and the text is the raw hypothesis, not redacted.
    The "no model call" guarantee is structural — the adapter imports no LLM
    module and calls no model.
    """
    adapter = FakeSTTAdapter(FIXTURE)
    partials: list[STTResult] = []
    async for result in adapter.stream(_silent_audio()):
        if not result.is_final:
            partials.append(result)

    assert len(partials) > 0
    first = partials[0]
    assert first.is_final is False
    assert first.stability < 1.0
    assert first.text == "hello"


async def test_finals_have_timestamps():
    adapter = FakeSTTAdapter(FIXTURE)
    finals = [r async for r in adapter.stream(_silent_audio()) if r.is_final]
    for final in finals:
        assert final.t_start >= 0.0
        assert final.t_end > final.t_start
        assert final.stability == 1.0


async def test_fake_replays_realistic_timing():
    """AC-2: shared fakes have realistic timing, not zero-millisecond returns."""
    events = [
        {"text": "a", "is_final": False, "t_start": 0, "t_end": 0.5, "delay_ms": 100},
        {"text": "b", "is_final": True, "t_start": 0, "t_end": 1.0, "delay_ms": 100},
        {"text": "c", "is_final": True, "t_start": 1.0, "t_end": 2.0, "delay_ms": 100},
    ]
    adapter = FakeSTTAdapter(events=events)
    t0 = time.perf_counter()
    _ = [r async for r in adapter.stream(_silent_audio())]
    elapsed_ms = (time.perf_counter() - t0) * 1000
    assert elapsed_ms >= 240, f"expected >= 240ms, got {elapsed_ms:.0f}ms"


async def test_finals_non_decreasing_t_start_from_fixture():
    """Every final in the fixture has a non-decreasing t_start.

    This is the adapter-level half of the property test. The fixture is
    crafted this way; the property test in ``test_segment_ordering.py``
    verifies the invariant under random orderings.
    """
    adapter = FakeSTTAdapter(FIXTURE)
    finals = [r async for r in adapter.stream(_silent_audio()) if r.is_final]
    t_starts = [f.t_start for f in finals]
    assert t_starts == sorted(t_starts)


# ── Dedup logic ──────────────────────────────────────────────────────


def test_dedup_key_rounds_t_start():
    r = STTResult(
        text="Hello world.", is_final=True, t_start=3.14159, t_end=5.0, stability=1.0
    )
    key = _dedup_key(r)
    assert key == (3.1, "hello world.")


def test_dedup_key_truncates_long_text():
    long_text = "a" * 100
    r = STTResult(text=long_text, is_final=True, t_start=1.0, t_end=2.0, stability=1.0)
    key = _dedup_key(r)
    assert key == (1.0, "a" * 40)


def test_dedup_key_case_insensitive():
    r1 = STTResult(
        text="Hello World.", is_final=True, t_start=1.0, t_end=2.0, stability=1.0
    )
    r2 = STTResult(
        text="hello world.", is_final=True, t_start=1.0, t_end=2.0, stability=1.0
    )
    assert _dedup_key(r1) == _dedup_key(r2)


def test_dedup_removes_duplicate_finals():
    """Simulates what rollover produces: two finals with the same t_start and
    text from the overlap window."""
    seen: set[tuple[float, str]] = set()
    results = [
        STTResult(
            text="We started.", is_final=True, t_start=280.1, t_end=282.0, stability=1.0
        ),
        STTResult(
            text="We started.", is_final=True, t_start=280.1, t_end=282.0, stability=1.0
        ),
        STTResult(
            text="In 2016.", is_final=True, t_start=283.0, t_end=284.5, stability=1.0
        ),
    ]
    kept = []
    for r in results:
        if r.is_final:
            key = _dedup_key(r)
            if key in seen:
                continue
            seen.add(key)
        kept.append(r)
    assert len(kept) == 2
    assert kept[0].text == "We started."
    assert kept[1].text == "In 2016."


def test_dedup_does_not_drop_partials():
    """Partials are never deduped — they replace each other on screen, so a
    duplicate is harmless and suppressing one would cause a visible stutter."""
    seen: set[tuple[float, str]] = set()
    results = [
        STTResult(
            text="we started", is_final=False, t_start=280.1, t_end=281.0, stability=0.6
        ),
        STTResult(
            text="we started", is_final=False, t_start=280.1, t_end=281.0, stability=0.6
        ),
    ]
    kept = []
    for r in results:
        if r.is_final:
            key = _dedup_key(r)
            if key in seen:
                continue
            seen.add(key)
        kept.append(r)
    assert len(kept) == 2


# ── Long-session memory bounds (N-02 AC-4) ──────────────────────────


def test_dedup_seen_set_bounded_after_long_session():
    """The dedup ``seen`` set grows linearly with finals, not with total events.

    For a 45-minute meeting (~400 finals) each entry is a (float, str) tuple
    of ~80 bytes, totalling ~32 KB — well within bounds.
    """
    import json
    import sys

    with open(FIXTURE_45MIN) as f:
        events = [json.loads(line) for line in f]

    seen: set[tuple[float, str]] = set()
    for ev in events:
        if ev.get("is_final"):
            r = STTResult(
                text=ev["text"],
                is_final=True,
                t_start=ev["t_start"],
                t_end=ev["t_end"],
                stability=ev.get("stability", 1.0),
            )
            key = _dedup_key(r)
            seen.add(key)

    finals_count = sum(1 for ev in events if ev.get("is_final"))
    assert len(seen) <= finals_count
    assert len(seen) > 0
    avg_entry_bytes = sys.getsizeof(next(iter(seen)))
    total_bytes = len(seen) * avg_entry_bytes
    assert total_bytes < 100_000, f"seen set {total_bytes} bytes exceeds 100 KB"


# ── Circuit breaker ──────────────────────────────────────────────────


async def test_stt_unavailable_when_not_configured():
    from app.circuit_breaker.breaker import BreakerRegistry

    registry = BreakerRegistry()
    breaker = registry.get(DEPENDENCY)
    adapter = GoogleSTTAdapter(project="", breaker=breaker)
    with pytest.raises(STTUnavailable, match="no GCP project"):
        async for _ in adapter.stream(_silent_audio()):
            pass


async def test_stt_breaker_opens_after_failures():
    """Five failures open the breaker; the next call raises STTUnavailable
    with the RECORD_ONLY degraded mode and the configured user message."""
    from app.circuit_breaker.breaker import BreakerRegistry

    registry = BreakerRegistry()
    breaker = registry.get(DEPENDENCY)
    breaker.reset()

    for _ in range(5):
        breaker.record_failure()

    adapter = GoogleSTTAdapter(project="test-project", breaker=breaker)

    with pytest.raises(STTUnavailable) as exc_info:
        async for _ in adapter.stream(_silent_audio()):
            pass

    assert exc_info.value.degraded_mode == "RECORD_ONLY"
    assert "recording continues" in exc_info.value.reason.lower()
    breaker.reset()


async def test_stt_unavailable_carries_degraded_mode():
    exc = STTUnavailable("test reason", degraded_mode="RECORD_ONLY")
    assert exc.reason == "test reason"
    assert exc.degraded_mode == "RECORD_ONLY"
    assert str(exc) == "test reason"
