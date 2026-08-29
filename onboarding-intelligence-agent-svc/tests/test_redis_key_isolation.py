"""AC-4 — every Redis key is namespaced, structurally.

OIA shares DB 2 with the prompt cache and the rest of the fleet, so the key
prefix *is* the isolation guarantee that a dedicated database would have given
for free. ERRATA-01 is explicit that this test "becomes more important, not
less"; A-03's scope note says the same.

Assertions sweep every key builder by reflection rather than a hand-written
list, so a builder added by a later story is covered the moment it exists.
"""

from __future__ import annotations

import inspect

import pytest

from app.cache import redis_manager
from app.cache.redis_manager import (
    KEY_PREFIX,
    PROMPT_CACHE_PREFIX,
    TenantKeys,
    circuit_key,
)

pytestmark = pytest.mark.unit

TENANT = "tenant-alpha"

#: Every public key-building method on TenantKeys, discovered by reflection.
BUILDERS = [
    (name, fn)
    for name, fn in inspect.getmembers(TenantKeys, inspect.isfunction)
    if not name.startswith("_")
]


def call(fn, tenant: str = TENANT) -> str:
    """Invoke a builder with plausible arguments for whatever it declares."""
    keys = TenantKeys(tenant)
    params = [p for p in inspect.signature(fn).parameters if p != "self"]
    return fn(keys, *[f"val-{p}" for p in params])


def test_builders_were_discovered():
    """Guards the reflection itself — an empty sweep would pass vacuously."""
    assert len(BUILDERS) >= 10, [n for n, _ in BUILDERS]


@pytest.mark.parametrize("name,fn", BUILDERS, ids=[n for n, _ in BUILDERS])
def test_every_key_carries_tenant_and_prefix(name, fn):
    """The whole isolation guarantee on a shared DB, in one assertion."""
    key = call(fn)
    assert key.startswith(f"{KEY_PREFIX}{TENANT}:"), f"{name} escapes the namespace"


@pytest.mark.parametrize("name,fn", BUILDERS, ids=[n for n, _ in BUILDERS])
def test_no_key_uses_another_services_namespace(name, fn):
    key = call(fn)
    for foreign in ("poi:", "prompt:", "bpa:", "coa:", "ila:", "tenant:", "celery"):
        assert not key.startswith(foreign), f"{name} writes into {foreign}"


def test_tenant_is_a_constructor_argument_not_a_per_call_one():
    """A-03: 'a helper that can be called without a tenant will eventually be
    called without one.' No builder accepts a tenant, so none can omit it."""
    for name, fn in BUILDERS:
        params = set(inspect.signature(fn).parameters)
        assert (
            "tenant_id" not in params
        ), f"{name} takes a per-call tenant; it belongs on the constructor"


@pytest.mark.parametrize("bad", ["", "   ", None])
def test_constructing_without_a_tenant_fails(bad):
    with pytest.raises((ValueError, TypeError)):
        TenantKeys(bad)  # type: ignore[arg-type]


def test_circuit_key_is_deliberately_not_tenant_scoped():
    """A dependency being down is a global fact, not a per-tenant one."""
    key = circuit_key("google-stt")
    assert key == f"{KEY_PREFIX}circuit:google-stt"
    assert key.startswith(KEY_PREFIX)
    assert not hasattr(TenantKeys, "circuit")


def test_circuit_key_rejects_an_empty_dependency():
    with pytest.raises(ValueError):
        circuit_key("")


def test_config_key_was_renamed_under_the_service_prefix():
    """ERRATA-01 §4: tenant:{id}:oia:config → oia:v1:{tenant}:config."""
    key = TenantKeys(TENANT).config()
    assert key == f"{KEY_PREFIX}{TENANT}:config"
    assert not key.startswith("tenant:")


def test_keys_match_design_section_14_patterns():
    """The §14 catalogue is the contract; drift here is a silent migration."""
    k = TenantKeys(TENANT)
    p = f"{KEY_PREFIX}{TENANT}"
    assert k.session("s1") == f"{p}:session:s1"
    assert k.session_summary("s1") == f"{p}:session:s1:summary"
    assert k.transcript("s1") == f"{p}:live:s1:transcript"
    assert k.questions("s1") == f"{p}:live:s1:questions"
    assert k.coverage("s1") == f"{p}:live:s1:coverage"
    assert k.idempotency("d1") == f"{p}:idempotency:d1"
    assert k.outbox("s1") == f"{p}:outbox:s1"
    assert k.ratelimit("u1") == f"{p}:ratelimit:u1"
    assert k.live_lock("c1") == f"{p}:lock:live:c1"
    assert k.config() == f"{p}:config"


def test_keys_are_distinct_across_builders():
    keys = [call(fn) for _, fn in BUILDERS]
    assert len(keys) == len(set(keys))


def test_two_tenants_never_share_a_key():
    for name, fn in BUILDERS:
        assert call(fn, "tenant-a") != call(fn, "tenant-b"), name


def test_prompt_cache_prefix_is_foreign_and_read_only():
    """The prompt: namespace belongs to prompt-optimization-svc."""
    assert not PROMPT_CACHE_PREFIX.startswith(KEY_PREFIX)
    writers = [
        name for name, fn in BUILDERS if call(fn).startswith(PROMPT_CACHE_PREFIX)
    ]
    assert writers == [], f"OIA must not build keys under poi:: {writers}"


def test_every_ttl_constant_is_positive_and_bounded():
    """ERRATA-01: an untrimmed key creates eviction pressure fleet-wide."""
    ttls = {
        name: value
        for name, value in vars(redis_manager).items()
        if name.startswith("TTL_")
    }
    assert ttls, "no TTL policy declared"
    for name, value in ttls.items():
        assert isinstance(value, int) and 0 < value <= 7 * 24 * 3600, name


def test_transcript_list_is_capped():
    """§14: the cap bounds reconnect replay cost to a known worst case."""
    assert redis_manager.TRANSCRIPT_MAX_ENTRIES == 4000
