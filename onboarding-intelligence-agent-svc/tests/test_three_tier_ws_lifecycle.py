"""Three-Tier Transcript · T-04/T-05 — WS lifecycle and PROCESS mode tests.

Unit tests: config defaults, T2→T3 sequential flow, T3 skip on short input.
Integration tests (real Redis): round-trip T2→T3, concurrent cancel.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from app.cache.redis_manager import RedisManager, TenantKeys, TTL_SESSION

TENANT = "t-ws-lifecycle"


class FakeSettings:
    CLEAN_INTERVAL_S = 1
    CLEAN_MIN_SEGMENTS = 2
    DESCRIPTION_INTERVAL_S = 1
    DESCRIPTION_MIN_CHARS = 10
    DESCRIPTION_MODEL = "claude-sonnet-4"
    CLEAN_MODEL = "claude-sonnet-4"
    ANALYSIS_TIMEOUT_S = 30.0
    FINALIZE_TIMEOUT_S = 10


class FakeLLM:
    def __init__(self, response: str = "cleaned"):
        self.response = response
        self.calls: list[dict] = []

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

    async def upload_transcript_tier(
        self, tenant_id: str, session_id: str, tier: str, content: str
    ) -> str:
        path = f"_landing/oia/{tenant_id}/{session_id}/transcript/{tier}.json"
        self.uploads.append({"path": path, "data": content})
        return path

    async def write_manifest(
        self, tenant_id: str, session_id: str, artefacts: list
    ) -> str:
        path = f"_landing/oia/{tenant_id}/{session_id}/manifest.json"
        self.uploads.append({"path": path, "data": json.dumps(artefacts)})
        return path


class _Blob:
    def __init__(self, path: str, store: list):
        self._path = path
        self._store = store

    def upload_from_string(self, data: str, content_type: str = "") -> None:
        self._store.append({"path": self._path, "data": data})


# ── Unit: T2→T3 sequential (PROCESS mode pattern) ───────────────────


@pytest.mark.unit
async def test_t2_then_t3_sequential():
    """PROCESS mode: T2 feeds into T3 sequentially."""
    from app.logic.transcript_cleaner import TranscriptCleaner
    from app.logic.description_generator import DescriptionGenerator

    keys = TenantKeys(TENANT)
    t2_llm = FakeLLM("Speaker 1: Hello. Speaker 2: Welcome to Acme Corp.")
    t3_llm = FakeLLM("## Business Identity\nAcme Corp is a retail business.")

    cleaner = TranscriptCleaner(
        redis=None,  # type: ignore[arg-type]
        keys=keys,
        session_id="sess-seq",
        llm=t2_llm,  # type: ignore[arg-type]
        storage=FakeStorage(),  # type: ignore[arg-type]
        settings=FakeSettings(),
    )
    generator = DescriptionGenerator(
        redis=None,  # type: ignore[arg-type]
        keys=keys,
        session_id="sess-seq",
        llm=t3_llm,  # type: ignore[arg-type]
        storage=FakeStorage(),  # type: ignore[arg-type]
        settings=FakeSettings(),
    )

    segments = [
        {"speaker_name": "Host", "text": "um hello there"},
        {"speaker_name": "Guest", "text": "yeah like welcome to Acme"},
    ]
    t2_text = await cleaner.run_batch(segments)
    assert t2_text != ""

    t3_text = await generator.run_batch(t2_text)
    assert "Acme Corp" in t3_text
    assert len(t2_llm.calls) == 1
    assert len(t3_llm.calls) == 1


@pytest.mark.unit
async def test_t3_skips_when_t2_empty():
    """T3 generator returns empty when T2 text is empty/whitespace."""
    from app.logic.description_generator import DescriptionGenerator

    keys = TenantKeys(TENANT)
    llm = FakeLLM()
    gen = DescriptionGenerator(
        redis=None,  # type: ignore[arg-type]
        keys=keys,
        session_id="sess-short",
        llm=llm,  # type: ignore[arg-type]
        storage=FakeStorage(),  # type: ignore[arg-type]
        settings=FakeSettings(),
    )

    result = await gen.run_batch("")
    assert result == ""
    assert len(llm.calls) == 0


@pytest.mark.unit
def test_config_models_are_claude():
    """T-01: All three models default to claude-sonnet-4."""
    from app.core.config import get_settings

    get_settings.cache_clear()
    cfg = get_settings()
    assert cfg.CLEAN_MODEL == "claude-sonnet-4"
    assert cfg.DESCRIPTION_MODEL == "claude-sonnet-4"
    assert cfg.PROCESS_MODEL == "claude-sonnet-4"
    get_settings.cache_clear()


@pytest.mark.unit
def test_config_intervals():
    """T-01: Interval defaults match design doc."""
    from app.core.config import get_settings

    get_settings.cache_clear()
    cfg = get_settings()
    assert cfg.CLEAN_INTERVAL_S == 30
    assert cfg.DESCRIPTION_INTERVAL_S == 60
    assert cfg.CLEAN_MIN_SEGMENTS == 5
    assert cfg.DESCRIPTION_MIN_CHARS == 200
    assert cfg.FINALIZE_TIMEOUT_S == 30
    get_settings.cache_clear()


# ── Integration: T2/T3 with real Redis ───────────────────────────────


@pytest.mark.integration
async def test_process_t2t3_round_trip(live_redis: RedisManager):
    """Full PROCESS-mode T2->T3 round-trip through real Redis."""
    from app.logic.transcript_cleaner import TranscriptCleaner
    from app.logic.description_generator import DescriptionGenerator

    keys = live_redis.keys_for(TENANT)
    session_id = "sess-process-rt"

    t1_key = keys.transcript(session_id)
    segments = [
        {"speaker_name": "Host", "text": "Welcome to our meeting."},
        {"speaker_name": "Guest", "text": "Thanks for having me."},
        {"speaker_name": "Host", "text": "Tell us about your business."},
        {
            "speaker_name": "Guest",
            "text": "We sell widgets online to small businesses.",
        },
        {"speaker_name": "Host", "text": "What are your brand goals?"},
    ]
    for seg in segments:
        await live_redis.client.rpush(t1_key, json.dumps(seg))

    t2_llm = FakeLLM(
        "Host: Welcome. Guest: Thanks. Host: Tell us about your business. "
        "Guest: We sell widgets. Host: Brand goals?"
    )
    cleaner = TranscriptCleaner(
        redis=live_redis,
        keys=keys,
        session_id=session_id,
        llm=t2_llm,  # type: ignore[arg-type]
        storage=FakeStorage(),  # type: ignore[arg-type]
        settings=FakeSettings(),
    )
    t2_text = await cleaner.run_batch(segments)
    assert t2_text != ""

    await live_redis.client.set(
        keys.transcript_clean(session_id), t2_text, ex=TTL_SESSION
    )

    t3_llm = FakeLLM(
        "## Business Identity\nWidget seller\n## Products & Services\nOnline widgets"
    )
    gen = DescriptionGenerator(
        redis=live_redis,
        keys=keys,
        session_id=session_id,
        llm=t3_llm,  # type: ignore[arg-type]
        storage=FakeStorage(),  # type: ignore[arg-type]
        settings=FakeSettings(),
    )
    t3_text = await gen.run_batch(t2_text)
    assert "Widget" in t3_text

    await live_redis.client.set(keys.description(session_id), t3_text, ex=TTL_SESSION)

    stored_t2 = await live_redis.client.get(keys.transcript_clean(session_id))
    assert stored_t2 is not None

    stored_t3 = await live_redis.client.get(keys.description(session_id))
    assert stored_t3 is not None
    assert b"Widget" in (
        stored_t3 if isinstance(stored_t3, bytes) else stored_t3.encode()
    )

    await live_redis.client.delete(
        t1_key,
        keys.transcript_clean(session_id),
        keys.clean_version(session_id),
        keys.description(session_id),
        keys.desc_version(session_id),
    )


@pytest.mark.integration
async def test_live_t2_t3_concurrent_cancel(live_redis: RedisManager):
    """T2 and T3 tasks cancel cleanly via shared Event."""
    from app.logic.transcript_cleaner import TranscriptCleaner
    from app.logic.description_generator import DescriptionGenerator

    keys = live_redis.keys_for(TENANT)
    session_id = "sess-cancel"

    cancel = asyncio.Event()

    cleaner = TranscriptCleaner(
        redis=live_redis,
        keys=keys,
        session_id=session_id,
        llm=FakeLLM(),  # type: ignore[arg-type]
        storage=FakeStorage(),  # type: ignore[arg-type]
        settings=FakeSettings(),
    )
    gen = DescriptionGenerator(
        redis=live_redis,
        keys=keys,
        session_id=session_id,
        llm=FakeLLM(),  # type: ignore[arg-type]
        storage=FakeStorage(),  # type: ignore[arg-type]
        settings=FakeSettings(),
    )

    cancel.set()

    await asyncio.gather(
        cleaner.run(cancel),
        gen.run(cancel),
    )

    assert cleaner.version == 0
    assert gen.version == 0
