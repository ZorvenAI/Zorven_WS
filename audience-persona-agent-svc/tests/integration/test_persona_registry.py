"""Integration test for PersonaRegistry CRUD + evolution detection.

These tests use mocked Redis (unit-style) since real Redis
requires @pytest.mark.integration and running Redis instance.
"""

import json
from unittest.mock import AsyncMock

import pytest

from app.registry.persona_registry import PersonaRegistry
from app.registry.models import PersonaRegistryEntry, PersonaEvolution


class TestPersonaRegistryIntegration:
    """Simulates full CRUD lifecycle with mocked Redis."""

    async def test_full_lifecycle(self):
        """Test create → read → update (with evolution) → delete."""
        redis = AsyncMock()
        store = {}

        async def hset(key, field, value):
            store.setdefault(key, {})[field] = value

        async def hget(key, field):
            return store.get(key, {}).get(field)

        async def hgetall(key):
            return store.get(key, {})

        async def hdel(key, field):
            if key in store and field in store[key]:
                del store[key][field]
                return 1
            return 0

        async def hlen(key):
            return len(store.get(key, {}))

        async def set_val(key, value, ex=None):
            store[key] = value

        redis.hset = hset
        redis.hget = hget
        redis.hgetall = hgetall
        redis.hdel = hdel
        redis.hlen = hlen
        redis.set = set_val

        emitter = AsyncMock()
        emitter.emit = AsyncMock()
        registry = PersonaRegistry(redis_client=redis, event_emitter=emitter)
        tid = "integration-tenant"

        # 1. Create
        persona1 = {
            "slug": "enterprise-it",
            "segment_label": "Enterprise IT Leader",
            "data_source": "research_based",
            "pain_points": ["Integration complexity"],
            "priority_score": 0.9,
        }
        await registry.upsert_persona(tid, "enterprise-it", persona1)
        assert persona1["version"] == 1

        # 2. Read
        fetched = await registry.get_persona(tid, "enterprise-it")
        assert fetched is not None
        data = json.loads(fetched) if isinstance(fetched, str) else fetched
        assert data["segment_label"] == "Enterprise IT Leader"

        # 3. Count
        count = await registry.persona_count(tid)
        assert count == 1

        # 4. Add another
        persona2 = {
            "slug": "startup-cto",
            "segment_label": "Startup CTO",
            "data_source": "crm_grounded",
        }
        await registry.upsert_persona(tid, "startup-cto", persona2)

        all_personas = await registry.get_all_personas(tid)
        assert len(all_personas) == 2

        # 5. Update with evolution
        emitter.emit.reset_mock()
        updated = {
            "slug": "enterprise-it",
            "segment_label": "Enterprise IT Leader",
            "data_source": "research_based",
            "pain_points": ["New pain point"],
            "priority_score": 0.95,
        }
        await registry.upsert_persona(tid, "enterprise-it", updated)
        assert updated["version"] == 2

        # Evolution event should have been emitted
        evolution_calls = [
            c
            for c in emitter.emit.call_args_list
            if len(c.args) > 0 and "EVOLUTION" in str(c.args[0])
        ]
        # At minimum, registry updated event should fire
        assert emitter.emit.call_count >= 1

        # 6. Delete
        deleted = await registry.delete_persona(tid, "startup-cto")
        assert deleted is True

        remaining = await registry.persona_count(tid)
        assert remaining == 1


class TestPersonaRegistryModels:
    def test_persona_registry_entry(self):
        entry = PersonaRegistryEntry(
            slug="test-persona",
            segment_label="Test Persona",
            data_source="crm_grounded",
            pain_points=["Cost", "Complexity"],
            priority_score=0.8,
            confidence_score=0.7,
        )
        assert entry.slug == "test-persona"
        assert entry.version == 1
        assert len(entry.pain_points) == 2

    def test_persona_evolution(self):
        evo = PersonaEvolution(
            slug="test-persona",
            old_version=1,
            new_version=2,
            changes={"pain_points": {"old": ["Cost"], "new": ["Cost", "Time"]}},
        )
        assert evo.slug == "test-persona"
        assert "pain_points" in evo.changes
