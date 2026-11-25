"""Three-Tier Transcript · T-03 — DescriptionGenerator tests.

Unit tests: GCS path, initial state, prompt template, version tracking.
Integration tests (real Redis): run_batch, finalize, live loop with WS frames.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from app.cache.redis_manager import RedisManager, TenantKeys, TTL_SESSION
from app.logic.description_generator import (
    DescriptionGenerator,
    DESCRIPTION_PROMPT,
)

TENANT = "t-desc-test"
SESSION = "sess-desc-001"


class FakeSettings:
    CLEAN_INTERVAL_S = 1
    CLEAN_MIN_SEGMENTS = 2
    DESCRIPTION_INTERVAL_S = 1
    DESCRIPTION_MIN_CHARS = 10
    DESCRIPTION_MODEL = "claude-sonnet-4"
    ANALYSIS_TIMEOUT_S = 30.0
    FINALIZE_TIMEOUT_S = 10


class FakeLLM:
    def __init__(self, response: str = "## Business Identity\nAcme Corp"):
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


# ── Unit tests ───────────────────────────────────────────────────────


@pytest.mark.unit
def test_gcs_path_format():
    keys = TenantKeys(TENANT)
    gen = DescriptionGenerator(
        redis=None,  # type: ignore[arg-type]
        keys=keys,
        session_id=SESSION,
        llm=FakeLLM(),  # type: ignore[arg-type]
        storage=FakeStorage(),  # type: ignore[arg-type]
        settings=FakeSettings(),
    )
    expected = f"_landing/oia/{TENANT}/{SESSION}/transcript/description.json"
    assert gen.gcs_path == expected


@pytest.mark.unit
def test_initial_state():
    keys = TenantKeys(TENANT)
    gen = DescriptionGenerator(
        redis=None,  # type: ignore[arg-type]
        keys=keys,
        session_id=SESSION,
        llm=FakeLLM(),  # type: ignore[arg-type]
        storage=FakeStorage(),  # type: ignore[arg-type]
        settings=FakeSettings(),
    )
    assert gen.description_text == ""
    assert gen.version == 0


@pytest.mark.unit
def test_description_prompt_has_all_sections():
    for section in [
        "Agreements",
        "Business Identity",
        "Products & Services",
        "Target Audience",
        "Brand Aspirations",
        "Competitive Landscape",
        "Marketing Goals",
        "Customer Pain Points",
        "Success Metrics",
    ]:
        assert section in DESCRIPTION_PROMPT


@pytest.mark.unit
def test_description_prompt_has_transcript_placeholder():
    assert "{clean_transcript}" in DESCRIPTION_PROMPT


# ── Integration tests (real Redis) ──────────────────────────────────


@pytest.mark.integration
async def test_run_batch_calls_llm(live_redis: RedisManager):
    keys = live_redis.keys_for(TENANT)
    llm = FakeLLM("## Business Identity\nAcme Corp in retail.")
    gen = DescriptionGenerator(
        redis=live_redis,
        keys=keys,
        session_id=SESSION,
        llm=llm,  # type: ignore[arg-type]
        storage=FakeStorage(),  # type: ignore[arg-type]
        settings=FakeSettings(),
    )

    result = await gen.run_batch("Speaker 1: We sell widgets online.")
    assert "Acme Corp" in result
    assert len(llm.calls) == 1
    assert llm.calls[0]["temperature"] == 0.2
    assert llm.calls[0]["model"] == "claude-sonnet-4"


@pytest.mark.integration
async def test_run_batch_empty_transcript(live_redis: RedisManager):
    keys = live_redis.keys_for(TENANT)
    llm = FakeLLM()
    gen = DescriptionGenerator(
        redis=live_redis,
        keys=keys,
        session_id=SESSION,
        llm=llm,  # type: ignore[arg-type]
        storage=FakeStorage(),  # type: ignore[arg-type]
        settings=FakeSettings(),
    )

    result = await gen.run_batch("")
    assert result == ""
    assert len(llm.calls) == 0


@pytest.mark.integration
async def test_run_batch_whitespace_only(live_redis: RedisManager):
    keys = live_redis.keys_for(TENANT)
    llm = FakeLLM()
    gen = DescriptionGenerator(
        redis=live_redis,
        keys=keys,
        session_id=SESSION,
        llm=llm,  # type: ignore[arg-type]
        storage=FakeStorage(),  # type: ignore[arg-type]
        settings=FakeSettings(),
    )

    result = await gen.run_batch("   \n  ")
    assert result == ""
    assert len(llm.calls) == 0


@pytest.mark.integration
async def test_finalize_reads_t2_and_flushes_gcs(live_redis: RedisManager):
    keys = live_redis.keys_for(TENANT)
    session_id = "sess-finalize-t3"

    # Seed T2 clean transcript in Redis.
    t2_key = keys.transcript_clean(session_id)
    clean_text = "Speaker 1: We are a retail company selling widgets online."
    await live_redis.client.set(t2_key, clean_text, ex=TTL_SESSION)

    storage = FakeStorage()
    llm = FakeLLM("## Business Identity\nWidget Corp")
    gen = DescriptionGenerator(
        redis=live_redis,
        keys=keys,
        session_id=session_id,
        llm=llm,  # type: ignore[arg-type]
        storage=storage,  # type: ignore[arg-type]
        settings=FakeSettings(),
    )

    await gen.finalize()

    assert gen.description_text == "## Business Identity\nWidget Corp"
    assert gen.version == 1

    # Verify Redis was written.
    stored = await live_redis.client.get(keys.description(session_id))
    assert stored is not None

    ver = await live_redis.client.get(keys.desc_version(session_id))
    assert ver is not None

    # Verify GCS upload.
    assert len(storage.uploads) == 1
    assert "/transcript/description.json" in storage.uploads[0]["path"]
    blob_data = json.loads(storage.uploads[0]["data"])
    assert blob_data["version"] == 1
    assert "Widget Corp" in blob_data["text"]

    # Cleanup.
    await live_redis.client.delete(
        t2_key,
        keys.description(session_id),
        keys.desc_version(session_id),
    )


@pytest.mark.integration
async def test_finalize_skips_when_no_t2(live_redis: RedisManager):
    """If there is no T2 in Redis, finalize should not crash or upload."""
    keys = live_redis.keys_for(TENANT)
    session_id = "sess-finalize-t3-empty"

    storage = FakeStorage()
    llm = FakeLLM()
    gen = DescriptionGenerator(
        redis=live_redis,
        keys=keys,
        session_id=session_id,
        llm=llm,  # type: ignore[arg-type]
        storage=storage,  # type: ignore[arg-type]
        settings=FakeSettings(),
    )

    await gen.finalize()

    assert gen.description_text == ""
    assert gen.version == 0
    assert len(storage.uploads) == 0
    assert len(llm.calls) == 0


@pytest.mark.integration
async def test_live_loop_pushes_ws_frames(live_redis: RedisManager):
    """run() should read T2 from Redis and push description.updated frames."""
    keys = live_redis.keys_for(TENANT)
    session_id = "sess-live-loop-t3"

    # Seed T2 with enough characters to pass min_chars threshold.
    t2_key = keys.transcript_clean(session_id)
    t2_text = "Speaker 1: We are a retail company. " * 10
    await live_redis.client.set(t2_key, t2_text, ex=TTL_SESSION)

    ws_frames: list[dict] = []

    async def capture_ws(frame: dict) -> None:
        ws_frames.append(frame)

    llm = FakeLLM("## Business Identity\nLive description")
    gen = DescriptionGenerator(
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
        gen.run(cancel),
        stop_after_one_cycle(),
    )

    assert gen.version >= 1
    assert "Live description" in gen.description_text
    assert any(f.get("type") == "description.updated" for f in ws_frames)

    # Cleanup.
    await live_redis.client.delete(
        t2_key,
        keys.description(session_id),
        keys.desc_version(session_id),
    )


@pytest.mark.integration
async def test_live_loop_skips_short_t2(live_redis: RedisManager):
    """run() should skip generation when T2 is below DESCRIPTION_MIN_CHARS."""
    keys = live_redis.keys_for(TENANT)
    session_id = "sess-skip-short-t3"

    # Seed T2 with text shorter than min_chars (10).
    t2_key = keys.transcript_clean(session_id)
    await live_redis.client.set(t2_key, "short", ex=TTL_SESSION)

    llm = FakeLLM()
    gen = DescriptionGenerator(
        redis=live_redis,
        keys=keys,
        session_id=session_id,
        llm=llm,  # type: ignore[arg-type]
        storage=FakeStorage(),  # type: ignore[arg-type]
        settings=FakeSettings(),
    )

    cancel = asyncio.Event()

    async def stop_quickly():
        await asyncio.sleep(1.5)
        cancel.set()

    await asyncio.gather(gen.run(cancel), stop_quickly())

    assert gen.version == 0
    assert len(llm.calls) == 0

    # Cleanup.
    await live_redis.client.delete(t2_key)
