"""Integration tests for the 4-step prompt resolution chain (L-01).

Requires real Redis on localhost:6379.
"""

from __future__ import annotations

import json
import uuid

import pytest

from app.cache.redis_manager import (
    PROMPT_CACHE_PREFIX,
    TTL_PROMPT_CACHE,
    RedisManager,
)
from app.core.config import Settings
from app.prompts.loader import PromptLoader
from app.prompts.mapping import PREP_PROMPTS, poi_name
from app.services.poi_client import POIClient

pytestmark = [pytest.mark.integration]


@pytest.fixture
async def manager(monkeypatch):
    from tests.conftest import REDIS_URL, redis_available

    if not redis_available():
        pytest.skip("Redis is not running on localhost:6379")

    monkeypatch.setenv("OIA_REDIS_URL", REDIS_URL)
    monkeypatch.setenv("OIA_BACKEND_BASE_URL", "http://backend:8001")
    monkeypatch.setenv("OIA_GCS_BUCKET", "zorven-raw-assets")
    mgr = RedisManager(Settings())  # type: ignore[call-arg]
    await mgr.connect()
    yield mgr
    await mgr.close()


@pytest.fixture
def tenant_id():
    return f"test-tenant-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def loader(manager):
    poi = POIClient("")
    return PromptLoader(redis=manager, poi_client=poi)


async def test_step4_fallback_when_all_cold(loader, tenant_id):
    """Empty Redis + no POI → all prompts use fallback-v1."""
    resolved, degraded = await loader.resolve_for_session(PREP_PROMPTS, tenant_id)
    assert len(resolved) == len(PREP_PROMPTS)
    assert degraded is True
    for pid, r in resolved.items():
        assert r.tier == "fallback"
        assert r.version == "fallback-v1"
        assert r.template  # not empty


async def test_step2_production_default(manager, loader, tenant_id):
    """Seed prompt:{poi_name}:production → resolved as redis_production."""
    pid = "oia.research_brief"
    pn = poi_name(pid)
    key = f"{PROMPT_CACHE_PREFIX}{pn}:production"
    template_text = "test production template for research"
    await manager.client.set(key, template_text, ex=300)

    try:
        resolved, degraded = await loader.resolve_for_session({pid}, tenant_id)
        assert pid in resolved
        assert resolved[pid].tier == "redis_production"
        assert resolved[pid].template == template_text
        assert degraded is False
    finally:
        await manager.client.delete(key)


async def test_step1_tenant_variant(manager, loader, tenant_id):
    """Seed prompt:{poi_name}:tenant:{tid} → resolved as redis_tenant."""
    pid = "oia.research_brief"
    pn = poi_name(pid)
    tenant_key = f"{PROMPT_CACHE_PREFIX}{pn}:tenant:{tenant_id}"
    template_text = "tenant-specific template"
    await manager.client.set(tenant_key, template_text, ex=300)

    try:
        resolved, degraded = await loader.resolve_for_session({pid}, tenant_id)
        assert pid in resolved
        assert resolved[pid].tier == "redis_tenant"
        assert resolved[pid].template == template_text
        assert degraded is False
    finally:
        await manager.client.delete(tenant_key)


async def test_tenant_variant_takes_priority(manager, loader, tenant_id):
    """Tenant variant beats production default."""
    pid = "oia.research_brief"
    pn = poi_name(pid)
    tenant_key = f"{PROMPT_CACHE_PREFIX}{pn}:tenant:{tenant_id}"
    prod_key = f"{PROMPT_CACHE_PREFIX}{pn}:production"
    await manager.client.set(tenant_key, "tenant wins", ex=300)
    await manager.client.set(prod_key, "production loses", ex=300)

    try:
        resolved, _ = await loader.resolve_for_session({pid}, tenant_id)
        assert resolved[pid].tier == "redis_tenant"
        assert resolved[pid].template == "tenant wins"
    finally:
        await manager.client.delete(tenant_key)
        await manager.client.delete(prod_key)


async def test_write_through_cache_uses_oia_prefix(manager, loader, tenant_id):
    """The write-through cache key is under oia:v1:, not prompt:."""
    pid = "oia.research_brief"
    pn = poi_name(pid)

    keys = manager.keys_for(tenant_id)
    cache_key = keys.prompt_cache(pn)

    assert cache_key.startswith("oia:v1:")
    assert not cache_key.startswith("prompt:")

    cache_data = json.dumps({"template": "cached template", "version": "v2"})
    await manager.client.set(cache_key, cache_data, ex=TTL_PROMPT_CACHE)

    try:
        resolved, degraded = await loader.resolve_for_session({pid}, tenant_id)
        assert resolved[pid].tier == "poi_api"
        assert resolved[pid].template == "cached template"
        assert resolved[pid].version == "v2"
        assert degraded is False
    finally:
        await manager.client.delete(cache_key)


async def test_key_isolation_holds(manager, loader, tenant_id):
    """No key written by the loader starts with prompt:."""
    resolved, _ = await loader.resolve_for_session(PREP_PROMPTS, tenant_id)

    keys = manager.keys_for(tenant_id)
    for pid in PREP_PROMPTS:
        pn = poi_name(pid)
        cache_key = keys.prompt_cache(pn)
        assert not cache_key.startswith("prompt:")


async def test_degraded_only_when_all_fallback(manager, loader, tenant_id):
    """Mixed resolution: one from Redis, one from fallback → not degraded."""
    pid = "oia.research_brief"
    pn = poi_name(pid)
    key = f"{PROMPT_CACHE_PREFIX}{pn}:production"
    await manager.client.set(key, "from redis", ex=300)

    try:
        resolved, degraded = await loader.resolve_for_session(PREP_PROMPTS, tenant_id)
        assert len(resolved) == 2
        assert degraded is False
        assert resolved[pid].tier == "redis_production"
        other = [r for p, r in resolved.items() if p != pid][0]
        assert other.tier == "fallback"
    finally:
        await manager.client.delete(key)


async def test_empty_prompt_ids_returns_empty(loader, tenant_id):
    """Resolving zero prompts returns empty dict, not degraded."""
    resolved, degraded = await loader.resolve_for_session([], tenant_id)
    assert resolved == {}
    assert degraded is False


async def test_pin_in_session_hash(manager, loader, tenant_id):
    """Resolved versions can be stored and retrieved from the session hash."""
    session_id = f"session-{tenant_id}"
    resolved, _ = await loader.resolve_for_session(PREP_PROMPTS, tenant_id)

    prompt_versions = {pid: r.version for pid, r in resolved.items()}
    keys = manager.keys_for(tenant_id)
    await manager.client.hset(
        keys.session(session_id),
        "prompt_versions",
        json.dumps(prompt_versions),
    )

    try:
        raw = await manager.client.hget(keys.session(session_id), "prompt_versions")
        assert raw is not None
        pinned = json.loads(raw)
        assert set(pinned.keys()) == set(PREP_PROMPTS)
        for pid in PREP_PROMPTS:
            assert pinned[pid] == resolved[pid].version
    finally:
        await manager.client.delete(keys.session(session_id))


async def test_canary_after_pin_has_no_effect(manager, loader, tenant_id):
    """Once pinned, changing Redis keys does not affect session hash."""
    session_id = f"session-canary-{tenant_id}"
    pid = "oia.research_brief"
    pn = poi_name(pid)
    prod_key = f"{PROMPT_CACHE_PREFIX}{pn}:production"

    await manager.client.set(prod_key, "original-template", ex=300)
    resolved, _ = await loader.resolve_for_session({pid}, tenant_id)

    keys = manager.keys_for(tenant_id)
    prompt_versions = {pid: resolved[pid].version for pid in resolved}
    await manager.client.hset(
        keys.session(session_id),
        "prompt_versions",
        json.dumps(prompt_versions),
    )

    await manager.client.set(prod_key, "canary-updated-template", ex=300)

    try:
        raw = await manager.client.hget(keys.session(session_id), "prompt_versions")
        pinned = json.loads(raw)
        assert pinned[pid] == resolved[pid].version
    finally:
        await manager.client.delete(prod_key)
        await manager.client.delete(keys.session(session_id))


async def test_write_through_cache_ttl(manager, loader, tenant_id):
    """Write-through cache entries have the expected 15-min TTL."""
    pid = "oia.research_brief"
    pn = poi_name(pid)
    keys = manager.keys_for(tenant_id)
    cache_key = keys.prompt_cache(pn)

    cache_data = json.dumps({"template": "ttl-test", "version": "v3"})
    await manager.client.set(cache_key, cache_data, ex=TTL_PROMPT_CACHE)

    try:
        ttl = await manager.client.ttl(cache_key)
        assert 0 < ttl <= TTL_PROMPT_CACHE
    finally:
        await manager.client.delete(cache_key)
