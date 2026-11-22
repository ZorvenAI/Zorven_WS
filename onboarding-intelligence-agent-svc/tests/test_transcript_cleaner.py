"""Three-Tier Transcript · T-02 — TranscriptCleaner tests.

Unit tests (no network): static helpers, GCS path construction, version
tracking, prompt assembly.

Integration tests (real Redis): run_batch end-to-end, finalize cycle,
Redis key read/write.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from app.cache.redis_manager import RedisManager, TenantKeys, TTL_SESSION
from app.logic.transcript_cleaner import TranscriptCleaner, CLEAN_PROMPT

TENANT = "t-cleaner-test"
SESSION = "sess-clean-001"


# ── Helpers ──────────────────────────────────────────────────────────


def _segments(*texts: str) -> list[dict[str, object]]:
    """Build transcript segments with speaker labels."""
    return [
        {
            "speaker_name": f"Speaker {i % 2 + 1}",
            "speaker": i % 2,
            "speaker_role": "operator" if i % 2 == 0 else "customer",
            "text": t,
            "start_time": float(i * 5),
        }
        for i, t in enumerate(texts)
    ]


class FakeSettings:
    CLEAN_INTERVAL_S = 1
    CLEAN_MIN_SEGMENTS = 2
    CLEAN_MODEL = "claude-sonnet-4"
    DESCRIPTION_INTERVAL_S = 1
    DESCRIPTION_MIN_CHARS = 10
    DESCRIPTION_MODEL = "claude-sonnet-4"
    ANALYSIS_TIMEOUT_S = 30.0
    FINALIZE_TIMEOUT_S = 10


class FakeLLM:
    """Records calls and returns a fixed response."""

    def __init__(self, response: str = "Cleaned transcript."):
        self.response = response
        self.calls: list[dict[str, object]] = []

    async def generate(
        self, prompt: str, *, temperature: float = 0.2, model: str | None = None
    ) -> str:
        self.calls.append(
            {"prompt": prompt, "temperature": temperature, "model": model}
        )
        return self.response


class FakeStorage:
    """Stubs just enough for the breaker + bucket interface."""

    def __init__(self):
        self.uploads: list[dict[str, str]] = []

    class _FakeBreaker:
        def before_call(self):
            pass

        def record_success(self):
            pass

        def record_failure(self):
            pass

    _breaker = _FakeBreaker()

    def _ensure_bucket(self):
        return self

    def blob(self, path: str):
        return _Blob(path, self.uploads)


class _Blob:
    def __init__(self, path: str, store: list[dict[str, str]]):
        self._path = path
        self._store = store

    def upload_from_string(self, data: str, content_type: str = "") -> None:
        self._store.append({"path": self._path, "data": data})


# ── Unit tests (no network) ─────────────────────────────────────────


@pytest.mark.unit
def test_segments_to_text_joins_speaker_lines():
    segs = _segments("Hello there.", "I'm good, thanks.")
    result = TranscriptCleaner._segments_to_text(segs)
    assert "Speaker 1: Hello there." in result
    assert "Speaker 2: I'm good, thanks." in result
    assert result.count("\n") == 1


@pytest.mark.unit
def test_segments_to_text_skips_empty():
    segs = [{"speaker_name": "A", "text": ""}, {"speaker_name": "B", "text": "hi"}]
    result = TranscriptCleaner._segments_to_text(segs)
    assert result == "B: hi"


@pytest.mark.unit
def test_segments_to_text_falls_back_to_speaker_number():
    segs = [{"speaker": 0, "text": "hi"}]
    result = TranscriptCleaner._segments_to_text(segs)
    assert result.startswith("0: hi") or result.startswith("Unknown: hi")


@pytest.mark.unit
def test_extract_speaker_map_with_roles():
    segs = [
        {"speaker_name": "Alice", "speaker_role": "operator", "text": "hi"},
        {"speaker_name": "Bob", "speaker_role": "customer", "text": "hello"},
        {"speaker_name": "Alice", "speaker_role": "operator", "text": "so..."},
    ]
    result = TranscriptCleaner._extract_speaker_map(segs)
    assert "Alice (operator)" in result
    assert "Bob (customer)" in result


@pytest.mark.unit
def test_extract_speaker_map_no_roles():
    segs = [{"speaker_name": "X", "text": "hi"}]
    result = TranscriptCleaner._extract_speaker_map(segs)
    assert result == "X"


@pytest.mark.unit
def test_extract_speaker_map_empty():
    result = TranscriptCleaner._extract_speaker_map([])
    assert result == "Unknown speakers"


@pytest.mark.unit
def test_gcs_path_format():
    keys = TenantKeys(TENANT)
    cleaner = TranscriptCleaner(
        redis=None,  # type: ignore[arg-type]
        keys=keys,
        session_id=SESSION,
        llm=FakeLLM(),  # type: ignore[arg-type]
        storage=FakeStorage(),  # type: ignore[arg-type]
        settings=FakeSettings(),
    )
    assert cleaner.gcs_path == f"_landing/oia/{TENANT}/{SESSION}/transcript/clean.json"


@pytest.mark.unit
def test_initial_state():
    keys = TenantKeys(TENANT)
    cleaner = TranscriptCleaner(
        redis=None,  # type: ignore[arg-type]
        keys=keys,
        session_id=SESSION,
        llm=FakeLLM(),  # type: ignore[arg-type]
        storage=FakeStorage(),  # type: ignore[arg-type]
        settings=FakeSettings(),
    )
    assert cleaner.clean_text == ""
    assert cleaner.version == 0


@pytest.mark.unit
def test_clean_prompt_has_placeholders():
    assert "{speaker_map}" in CLEAN_PROMPT
    assert "{raw_text}" in CLEAN_PROMPT


# ── Integration tests (real Redis) ──────────────────────────────────


@pytest.mark.integration
async def test_run_batch_calls_llm_and_returns_text(live_redis: RedisManager):
    keys = live_redis.keys_for(TENANT)
    llm = FakeLLM("This is the cleaned version.")
    cleaner = TranscriptCleaner(
        redis=live_redis,
        keys=keys,
        session_id=SESSION,
        llm=llm,  # type: ignore[arg-type]
        storage=FakeStorage(),  # type: ignore[arg-type]
        settings=FakeSettings(),
    )

    segs = _segments("um hello", "yeah like sure", "so basically we do X")
    result = await cleaner.run_batch(segs)

    assert result == "This is the cleaned version."
    assert len(llm.calls) == 1
    assert llm.calls[0]["temperature"] == 0.1
    assert llm.calls[0]["model"] == "claude-sonnet-4"


@pytest.mark.integration
async def test_run_batch_empty_segments(live_redis: RedisManager):
    keys = live_redis.keys_for(TENANT)
    llm = FakeLLM()
    cleaner = TranscriptCleaner(
        redis=live_redis,
        keys=keys,
        session_id=SESSION,
        llm=llm,  # type: ignore[arg-type]
        storage=FakeStorage(),  # type: ignore[arg-type]
        settings=FakeSettings(),
    )

    result = await cleaner.run_batch([])
    assert result == ""
    assert len(llm.calls) == 0


@pytest.mark.integration
async def test_finalize_reads_redis_and_flushes_gcs(live_redis: RedisManager):
    keys = live_redis.keys_for(TENANT)
    session_id = "sess-finalize-t2"

    # Seed T1 segments in Redis.
    t1_key = keys.transcript(session_id)
    for seg in _segments("Hello there", "I'm doing well", "Let's talk brand"):
        await live_redis.client.rpush(t1_key, json.dumps(seg))

    storage = FakeStorage()
    llm = FakeLLM("Final cleaned transcript.")
    cleaner = TranscriptCleaner(
        redis=live_redis,
        keys=keys,
        session_id=session_id,
        llm=llm,  # type: ignore[arg-type]
        storage=storage,  # type: ignore[arg-type]
        settings=FakeSettings(),
    )

    await cleaner.finalize()

    assert cleaner.clean_text == "Final cleaned transcript."
    assert cleaner.version == 1

    # Verify Redis was written.
    stored = await live_redis.client.get(keys.transcript_clean(session_id))
    assert stored is not None
    assert b"Final cleaned" in (
        stored if isinstance(stored, bytes) else stored.encode()
    )

    ver = await live_redis.client.get(keys.clean_version(session_id))
    assert ver is not None

    # Verify GCS upload was attempted.
    assert len(storage.uploads) == 1
    assert "/transcript/clean.json" in storage.uploads[0]["path"]

    # Cleanup.
    await live_redis.client.delete(
        t1_key,
        keys.transcript_clean(session_id),
        keys.clean_version(session_id),
    )


@pytest.mark.integration
async def test_live_loop_runs_cycles(live_redis: RedisManager):
    """Test that run() loops and cleans when enough segments accumulate."""
    keys = live_redis.keys_for(TENANT)
    session_id = "sess-live-loop-t2"

    t1_key = keys.transcript(session_id)
    for seg in _segments("one", "two", "three", "four", "five"):
        await live_redis.client.rpush(t1_key, json.dumps(seg))

    ws_frames: list[dict] = []

    async def capture_ws(frame: dict) -> None:
        ws_frames.append(frame)

    llm = FakeLLM("Live cleaned.")
    cleaner = TranscriptCleaner(
        redis=live_redis,
        keys=keys,
        session_id=session_id,
        llm=llm,  # type: ignore[arg-type]
        storage=FakeStorage(),  # type: ignore[arg-type]
        settings=FakeSettings(),
        send_ws=capture_ws,
    )

    cancel = asyncio.Event()

    async def stop_after_one_cycle():
        await asyncio.sleep(1.5)
        cancel.set()

    await asyncio.gather(
        cleaner.run(cancel),
        stop_after_one_cycle(),
    )

    assert cleaner.version >= 1
    assert cleaner.clean_text == "Live cleaned."
    assert any(f.get("type") == "transcript.clean_progress" for f in ws_frames)

    # Cleanup.
    await live_redis.client.delete(
        t1_key,
        keys.transcript_clean(session_id),
        keys.clean_version(session_id),
    )
