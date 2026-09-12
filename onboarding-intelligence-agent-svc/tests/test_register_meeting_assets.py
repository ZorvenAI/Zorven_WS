"""J-03 · SKL-OIA-11, meeting asset registration.

Tests cover: happy path registration, idempotency, partial failures,
empty input, missing backend, and edge cases.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.skills.models import SkillContext, SkillMeta, TenantContext
from app.skills.register_meeting_assets import RegisterMeetingAssets

pytestmark = pytest.mark.unit


def meta() -> SkillMeta:
    return SkillMeta(skill_id="SKL-OIA-11", name="register_meeting_assets")


def context(**overrides) -> SkillContext:
    input_context: dict[str, Any] = {
        "session_id": "sess-001",
        "assets": [
            {
                "file_name": "recording.webm",
                "file_type": "video/webm",
                "file_size": 5242880,
                "gcs_uri": "gs://zorven-raw-assets/t-1/sess-001/recording.webm",
            },
            {
                "file_name": "transcript.json",
                "file_type": "application/json",
                "file_size": 10240,
                "gcs_uri": "gs://zorven-raw-assets/t-1/sess-001/transcript.json",
            },
        ],
    }
    input_context.update(overrides)
    return SkillContext(
        input_prompt="register meeting assets",
        tenant_context=TenantContext(tenant_id="t-1", user_id="u-1", role="ADMIN"),
        input_context=input_context,
    )


class FakeBackendClient:
    """Stand-in that records calls and returns canned responses."""

    def __init__(self, responses: list[dict | None] | None = None) -> None:
        self._responses = list(responses) if responses else []
        self.calls: list[dict] = []

    async def register_brand_asset(
        self,
        *,
        tenant_id: str,
        file_name: str,
        file_type: str,
        file_size: int,
        gcs_uri: str,
    ) -> dict[str, Any] | None:
        self.calls.append(
            {
                "tenant_id": tenant_id,
                "file_name": file_name,
                "file_type": file_type,
                "file_size": file_size,
                "gcs_uri": gcs_uri,
            }
        )
        if self._responses:
            return self._responses.pop(0)
        return {"asset_id": len(self.calls), "pipeline_status": "pending"}


class FakeRedisManager:
    """Stand-in for idempotency checks."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    def keys_for(self, tenant_id: str):
        return FakeKeys(tenant_id)

    @property
    def client(self):
        return self

    async def get(self, key: str) -> str | None:
        return self._store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self._store[key] = value


class FakeKeys:
    def __init__(self, tenant_id: str) -> None:
        self._tenant_id = tenant_id

    def idempotency(self, suffix: str) -> str:
        return f"oia:v1:{self._tenant_id}:idempotency:{suffix}"


# ── Happy path ──────────────────────────────────────────────────────


async def test_registers_all_assets():
    backend = FakeBackendClient()
    skill = RegisterMeetingAssets(meta(), backend=backend, redis=FakeRedisManager())

    result = await skill.run(context())
    output = result.output

    assert output["registered_count"] == 2
    assert output["failed_count"] == 0
    assert len(backend.calls) == 2
    assert backend.calls[0]["file_name"] == "recording.webm"
    assert backend.calls[1]["file_name"] == "transcript.json"


async def test_output_contains_asset_ids():
    backend = FakeBackendClient(
        [
            {"asset_id": 42, "pipeline_status": "pending"},
            {"asset_id": 43, "pipeline_status": "pending"},
        ]
    )
    skill = RegisterMeetingAssets(meta(), backend=backend, redis=FakeRedisManager())

    result = await skill.run(context())
    assert result.output["registered"][0]["asset_id"] == 42
    assert result.output["registered"][1]["asset_id"] == 43


# ── Idempotency ─────────────────────────────────────────────────────


async def test_idempotent_hit_returns_cached():
    redis = FakeRedisManager()
    cached = {
        "session_id": "sess-001",
        "registered": [{"file_name": "old.webm", "asset_id": 99}],
    }
    key = FakeKeys("t-1").idempotency("skl11:sess-001")
    redis._store[key] = json.dumps(cached)

    backend = FakeBackendClient()
    skill = RegisterMeetingAssets(meta(), backend=backend, redis=redis)

    result = await skill.run(context())
    assert result.output["registered"][0]["asset_id"] == 99
    assert len(backend.calls) == 0


async def test_idempotency_stored_after_success():
    redis = FakeRedisManager()
    backend = FakeBackendClient()
    skill = RegisterMeetingAssets(meta(), backend=backend, redis=redis)

    await skill.run(context())

    key = FakeKeys("t-1").idempotency("skl11:sess-001")
    assert key in redis._store
    stored = json.loads(redis._store[key])
    assert stored["registered_count"] == 2


async def test_idempotency_not_stored_on_total_failure():
    backend = FakeBackendClient([None, None])
    redis = FakeRedisManager()
    skill = RegisterMeetingAssets(meta(), backend=backend, redis=redis)

    result = await skill.run(context())
    assert result.output["registered_count"] == 0
    assert result.output["failed_count"] == 2

    key = FakeKeys("t-1").idempotency("skl11:sess-001")
    assert key not in redis._store


# ── Partial failures ────────────────────────────────────────────────


async def test_partial_failure_reports_both():
    backend = FakeBackendClient(
        [
            {"asset_id": 42, "pipeline_status": "pending"},
            None,
        ]
    )
    skill = RegisterMeetingAssets(meta(), backend=backend, redis=FakeRedisManager())

    result = await skill.run(context())
    assert result.output["registered_count"] == 1
    assert result.output["failed_count"] == 1
    assert result.output["failed"][0]["file_name"] == "transcript.json"


# ── Edge cases ──────────────────────────────────────────────────────


async def test_no_session_id_returns_error():
    skill = RegisterMeetingAssets(meta(), backend=FakeBackendClient())
    result = await skill.run(context(session_id=None))
    assert "error" in result.output
    assert result.output["registered"] == []


async def test_empty_assets_returns_skipped():
    skill = RegisterMeetingAssets(meta(), backend=FakeBackendClient())
    result = await skill.run(context(assets=[]))
    assert result.output["registered"] == []
    assert "skipped" in result.output


async def test_no_backend_returns_error():
    skill = RegisterMeetingAssets(meta())
    result = await skill.run(context())
    assert "error" in result.output


async def test_malformed_asset_entries_skipped():
    assets = [
        "not a dict",
        {"file_name": "", "file_type": "text/plain"},
        {
            "file_name": "valid.txt",
            "file_type": "text/plain",
            "file_size": 100,
            "gcs_uri": "gs://b/p",
        },
    ]
    backend = FakeBackendClient()
    skill = RegisterMeetingAssets(meta(), backend=backend, redis=FakeRedisManager())
    await skill.run(context(assets=assets))
    assert len(backend.calls) == 1
    assert backend.calls[0]["file_name"] == "valid.txt"


async def test_no_redis_still_works():
    """Without Redis, idempotency is skipped but registration proceeds."""
    backend = FakeBackendClient()
    skill = RegisterMeetingAssets(meta(), backend=backend)

    result = await skill.run(context())
    assert result.output["registered_count"] == 2
