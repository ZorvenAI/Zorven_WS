"""Tests for PersonaRegistry — Redis Hash CRUD + evolution detection."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.registry.persona_registry import PersonaRegistry


def _mock_redis():
    """Create a mock Redis client."""
    mock = AsyncMock()
    mock.hget = AsyncMock(return_value=None)
    mock.hgetall = AsyncMock(return_value={})
    mock.hset = AsyncMock()
    mock.hdel = AsyncMock(return_value=1)
    mock.hlen = AsyncMock(return_value=0)
    mock.set = AsyncMock()
    return mock


def _mock_emitter():
    """Create a mock EventEmitter."""
    emitter = AsyncMock()
    emitter.emit = AsyncMock()
    return emitter


class TestPersonaRegistry:
    async def test_get_persona_no_redis(self):
        registry = PersonaRegistry(redis_client=None)
        result = await registry.get_persona("t", "slug")
        assert result is None

    async def test_get_all_personas_no_redis(self):
        registry = PersonaRegistry(redis_client=None)
        result = await registry.get_all_personas("t")
        assert result == {}

    async def test_get_persona_found(self):
        redis = _mock_redis()
        persona = {"slug": "it-leader", "segment_label": "IT Leader"}
        redis.hget = AsyncMock(return_value=json.dumps(persona))
        registry = PersonaRegistry(redis_client=redis)

        result = await registry.get_persona("t", "it-leader")
        assert result is not None
        assert result["segment_label"] == "IT Leader"
        redis.hget.assert_called_once_with("apa:t:registry:personas", "it-leader")

    async def test_get_persona_not_found(self):
        redis = _mock_redis()
        registry = PersonaRegistry(redis_client=redis)
        result = await registry.get_persona("t", "nonexistent")
        assert result is None

    async def test_get_all_personas(self):
        redis = _mock_redis()
        redis.hgetall = AsyncMock(
            return_value={
                "it-leader": json.dumps({"slug": "it-leader"}),
                "cfo": json.dumps({"slug": "cfo"}),
            }
        )
        registry = PersonaRegistry(redis_client=redis)
        result = await registry.get_all_personas("t")
        assert len(result) == 2
        assert "it-leader" in result
        assert "cfo" in result

    async def test_upsert_new_persona(self):
        redis = _mock_redis()
        emitter = _mock_emitter()
        registry = PersonaRegistry(redis_client=redis, event_emitter=emitter)
        persona = {"slug": "it-leader", "segment_label": "IT Leader"}

        await registry.upsert_persona("t", "it-leader", persona)

        redis.hset.assert_called_once()
        assert persona["version"] == 1
        assert "last_updated" in persona

        # Should create snapshot
        redis.set.assert_called_once()

        # Should emit registry updated event
        assert emitter.emit.call_count >= 1

    async def test_upsert_detects_evolution(self):
        redis = _mock_redis()
        emitter = _mock_emitter()
        existing = {
            "slug": "it-leader",
            "segment_label": "IT Leader",
            "pain_points": ["Old pain"],
            "version": 1,
        }
        redis.hget = AsyncMock(return_value=json.dumps(existing))
        registry = PersonaRegistry(redis_client=redis, event_emitter=emitter)

        new_profile = {
            "slug": "it-leader",
            "segment_label": "IT Leader",
            "pain_points": ["New pain"],
        }
        await registry.upsert_persona("t", "it-leader", new_profile)

        assert new_profile["version"] == 2
        # Should emit both evolution and registry events
        assert emitter.emit.call_count == 2

    async def test_upsert_no_evolution(self):
        redis = _mock_redis()
        emitter = _mock_emitter()
        existing = {
            "slug": "it-leader",
            "segment_label": "IT Leader",
            "version": 3,
        }
        redis.hget = AsyncMock(return_value=json.dumps(existing))
        registry = PersonaRegistry(redis_client=redis, event_emitter=emitter)

        same_profile = {
            "slug": "it-leader",
            "segment_label": "IT Leader",
        }
        await registry.upsert_persona("t", "it-leader", same_profile)

        # Version stays the same
        assert same_profile["version"] == 3
        # Only registry updated event (no evolution)
        assert emitter.emit.call_count == 1

    async def test_delete_persona(self):
        redis = _mock_redis()
        registry = PersonaRegistry(redis_client=redis)
        result = await registry.delete_persona("t", "it-leader")
        assert result is True
        redis.hdel.assert_called_once_with("apa:t:registry:personas", "it-leader")

    async def test_delete_persona_no_redis(self):
        registry = PersonaRegistry(redis_client=None)
        result = await registry.delete_persona("t", "it-leader")
        assert result is False

    async def test_persona_count(self):
        redis = _mock_redis()
        redis.hlen = AsyncMock(return_value=5)
        registry = PersonaRegistry(redis_client=redis)
        count = await registry.persona_count("t")
        assert count == 5

    async def test_persona_count_no_redis(self):
        registry = PersonaRegistry(redis_client=None)
        count = await registry.persona_count("t")
        assert count == 0

    def test_detect_evolution_changes(self):
        old = {"segment_label": "IT Leader", "pain_points": ["Old"]}
        new = {"segment_label": "IT Leader", "pain_points": ["New"]}
        changes = PersonaRegistry.detect_evolution(old, new)
        assert "pain_points" in changes
        assert changes["pain_points"]["old"] == ["Old"]
        assert changes["pain_points"]["new"] == ["New"]

    def test_detect_evolution_no_changes(self):
        profile = {"segment_label": "IT Leader", "pain_points": ["Same"]}
        changes = PersonaRegistry.detect_evolution(profile, dict(profile))
        assert changes == {}

    async def test_redis_error_graceful(self):
        redis = _mock_redis()
        redis.hget = AsyncMock(side_effect=Exception("Redis error"))
        registry = PersonaRegistry(redis_client=redis)
        result = await registry.get_persona("t", "slug")
        assert result is None
